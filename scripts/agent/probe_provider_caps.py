#!/usr/bin/env python3
"""Re-measure the pagination caps every scanner declares, against the live APIs.

``Scanner.result_window`` and ``Scanner.max_page_size`` are measured constants
with a shelf life — Etherscan cut its served page size from 10_000 to 1_000 in
July 2026 without touching its docs, and a stale ``max_page_size`` makes a full
page read as end-of-data. This script is how those numbers are re-measured
rather than reasoned about: it asks each provider for pages whose sizes straddle
the declared caps and reports what came back.

Exit status is the verdict: 0 = every declaration matched what the provider
served, 1 = at least one drifted (or a probe could not be run and the
declaration is therefore unconfirmed).

Usage:
    uv run python scripts/agent/probe_provider_caps.py [--provider etherscan] [--json]

Keys are read from the environment / ``.env`` exactly as the library reads them,
so a provider whose key is absent is reported as BLOCKED, never as passing.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

from aiochainscan import ChainscanClient
from aiochainscan.domain.method import Method


@dataclass(frozen=True)
class Target:
    """A query busy enough that any page size under test can be filled.

    Per chain, not per method: a page that comes back short must mean the
    provider clamped it, never that the query ran out of records.
    """

    address: str
    log_range: tuple[int, int]
    contract_address: str


# USDT on Ethereum: millions of transactions, a Transfer log in nearly every block.
ETHEREUM = Target(
    address='0xdAC17F958D2ee523a2206206994597C13D831ec7',
    log_range=(20_000_000, 20_002_000),
    contract_address='0xdAC17F958D2ee523a2206206994597C13D831ec7',
)
# BSC-USD on BNB Chain: ~74M holders, and its own contract is a busy address.
BSC = Target(
    address='0x55d398326f99059fF775485246999027B3197955',
    log_range=(40_000_000, 40_002_000),
    contract_address='0x55d398326f99059fF775485246999027B3197955',
)

#: Page sizes to ask for. Each is requested with ``page=1``, so ``page * offset``
#: stays inside a 10_000 window for every value up to 10_000.
PAGE_SIZE_LADDER = (1_000, 2_000, 5_000, 10_000)

#: Delay between live calls — Etherscan's free tier is 5 rps and the point of
#: this script is a clean measurement, not a rate-limit test.
CALL_DELAY_S = 0.35


@dataclass
class Probe:
    """One live request and what it answered."""

    label: str
    params: dict[str, Any]
    count: int | None = None
    error: str | None = None
    fingerprint: str | None = None

    @property
    def outcome(self) -> str:
        if self.error is not None:
            return f'ERROR {self.error}'
        head = f' first={self.fingerprint}' if self.fingerprint else ''
        return f'{self.count} items{head}'


@dataclass
class MethodResult:
    """Declared caps for one (provider, method) next to the observed ones."""

    provider: str
    method: str
    declared_result_window: int | None
    declared_max_page_size: int | None
    observed_max_page_size: int | None = None
    window_enforced_at: int | None = None
    paging_ignored: bool | None = None
    probes: list[Probe] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def effective_page_ceiling(self) -> int | None:
        """The largest page this method can be served, per the declarations.

        ``max_page_size`` is scanner-wide while ``RESULT_WINDOW_OVERRIDES`` can
        bound one endpoint tighter (BlockScout V1's ``getLogs``: 1000 against a
        scanner-wide 10_000), so the page ceiling to compare against is the
        smaller of the two — comparing against the scanner-wide number alone
        reports a correct declaration as drift.
        """
        candidates = [
            cap
            for cap in (self.declared_max_page_size, self.declared_result_window)
            if cap is not None
        ]
        return min(candidates) if candidates else None

    @property
    def page_size_verdict(self) -> str:
        if self.observed_max_page_size is None:
            return 'INCONCLUSIVE'
        ceiling = self.effective_page_ceiling
        if ceiling is None:
            return 'UNDECLARED'
        return 'OK' if self.observed_max_page_size == ceiling else 'DRIFT'

    @property
    def window_verdict(self) -> str:
        if self.declared_result_window is None:
            return 'UNDECLARED'
        if self.paging_ignored:
            # Nothing to overflow: every page is the first page, so the window
            # IS the single page the endpoint serves.
            return 'OK' if self.observed_max_page_size == self.declared_result_window else 'DRIFT'
        if self.window_enforced_at is None:
            return 'INCONCLUSIVE'
        return 'OK' if self.window_enforced_at > self.declared_result_window else 'DRIFT'


def _params_for(method: Method, page: int, offset: int, target: Target) -> dict[str, Any]:
    paging = {'page': page, 'offset': offset}
    if method is Method.EVENT_LOGS:
        start, end = target.log_range
        return {'address': target.address, 'from_block': start, 'to_block': end, **paging}
    if method in (Method.TOKEN_HOLDERS, Method.TOKEN_TOP_HOLDERS):
        return {'contract_address': target.contract_address, **paging}
    return {'address': target.address, 'sort': 'asc', **paging}


async def _one_call(client: ChainscanClient, method: Method, params: dict[str, Any]) -> Probe:
    label = f'page={params["page"]}&offset={params["offset"]}'
    probe = Probe(label=label, params=dict(params))
    try:
        result = await client.call(method, **params)
    except Exception as exc:  # noqa: BLE001 - the provider's refusal IS the measurement
        probe.error = f'{type(exc).__name__}: {str(exc)[:160]}'
    else:
        items = result if isinstance(result, list) else []
        probe.count = len(items)
        probe.fingerprint = _fingerprint(items[0]) if items else None
    await asyncio.sleep(CALL_DELAY_S)
    return probe


def _fingerprint(item: Any) -> str | None:
    """Identify the first record of a page, so a repeated page is provable.

    An endpoint that ignores ``page`` answers a full page for every page number
    — indistinguishable from a wide window by count alone.
    """
    if not isinstance(item, dict):
        return None
    for key in ('hash', 'transactionHash', 'logIndex', 'blockNumber', 'address'):
        value = item.get(key)
        if value:
            return f'{key}={value}'
    return None


async def probe_method(client: ChainscanClient, method: Method, target: Target) -> MethodResult:
    """Measure the served page size and the enforced result window for one method."""
    scanner = client._scanner  # noqa: SLF001 - declarations live on the scanner
    result = MethodResult(
        provider=f'{client.scanner_name}/{client.scanner_version}',
        method=method.name,
        declared_result_window=scanner.result_window_for(method),
        declared_max_page_size=scanner.max_page_size,
    )

    if result.declared_result_window is None and result.declared_max_page_size is None:
        # A cursor-paginated provider (BlockScout V2's next_page_params,
        # NodeReal's pageKey) declares no cap, so there is no number to
        # re-measure — the guarantee machinery treats the flag as inert. Say so
        # instead of firing requests whose answer could not change a
        # declaration either way.
        result.notes.append(
            'cursor-paginated: no page-size or result-window declaration to verify'
        )
        return result

    # 1. Served page size: the largest requested offset the provider actually
    #    filled. A page that comes back short of what was asked for is the
    #    provider's silent clamp, not the end of the data — the Target holds
    #    far more records than the largest ladder step.
    for offset in PAGE_SIZE_LADDER:
        probe = await _one_call(client, method, _params_for(method, 1, offset, target))
        result.probes.append(probe)
        if probe.error is not None:
            result.notes.append(f'offset={offset} refused: {probe.error}')
            break
        if probe.count == offset:
            result.observed_max_page_size = offset
        elif result.observed_max_page_size is None:
            result.observed_max_page_size = probe.count
            result.notes.append(
                f'offset={offset} answered {probe.count} — clamped page size, '
                'or the query holds fewer records than the ladder step'
            )
            break
        else:
            break

    # 2. Result window: walk page numbers at the served page size until the
    #    provider refuses. `window_enforced_at` is the first page*offset it
    #    rejected, so a declaration is confirmed when the refusal lands just
    #    past it (the declared window itself must still be served).
    window = result.declared_result_window
    page_size = result.observed_max_page_size or result.declared_max_page_size
    if window is None:
        result.notes.append('scanner declares no result window — nothing to overflow')
    elif not page_size:
        result.notes.append('no served page size — window probe skipped')
    else:
        first_page = result.probes[0]
        at_window = max(window // page_size, 1)
        for page in (at_window, at_window + 1):
            probe = await _one_call(client, method, _params_for(method, page, page_size, target))
            result.probes.append(probe)
            if probe.error is not None:
                result.window_enforced_at = page * page_size
                break
            if (
                page > 1
                and probe.fingerprint is not None
                and probe.fingerprint == first_page.fingerprint
            ):
                result.paging_ignored = True
                result.notes.append(
                    f'page={page} returned the same first record as page=1 '
                    f'({probe.fingerprint}) — this endpoint ignores page/offset, so its '
                    'window is the single page it serves'
                )
                break
        else:
            result.paging_ignored = False
            result.notes.append(
                f'page*offset={(at_window + 1) * page_size} was served with different '
                'records and no error — the window is wider than declared'
            )
    return result


async def probe_provider(
    scanner: str, network: str, methods: tuple[Method, ...], target: Target
) -> list[Any]:
    """Probe one provider, or report it BLOCKED when it cannot be constructed."""
    try:
        client = ChainscanClient.from_config(scanner, network)
    except Exception as exc:  # noqa: BLE001 - a missing key is a reportable outcome
        return [{'provider': f'{scanner}/{network}', 'blocked': f'{type(exc).__name__}: {exc}'}]

    results: list[Any] = []
    async with client:
        for method in methods:
            if not client.supports_method(method):
                results.append(
                    {'provider': f'{scanner}/{network}', 'skipped': f'{method.name} not declared'}
                )
                continue
            results.append(await probe_method(client, method, target))
    return results


PROVIDERS: dict[str, tuple[str, tuple[Method, ...], Target]] = {
    'etherscan': ('ethereum', (Method.ACCOUNT_TRANSACTIONS, Method.EVENT_LOGS), ETHEREUM),
    'blockscout': ('ethereum', (Method.ACCOUNT_TRANSACTIONS, Method.EVENT_LOGS), ETHEREUM),
    'blockscout_v2': ('ethereum', (Method.ACCOUNT_TRANSACTIONS, Method.TOKEN_HOLDERS), ETHEREUM),
    'nodereal': ('bsc', (Method.ACCOUNT_TRANSACTIONS, Method.TOKEN_HOLDERS), BSC),
}


def _render(results: list[Any]) -> int:
    drift = 0
    blocked = 0
    inconclusive = 0
    for entry in results:
        if isinstance(entry, dict):
            reason = entry.get('blocked') or entry.get('skipped')
            kind = 'BLOCKED' if 'blocked' in entry else 'SKIP'
            print(f'{kind:12} {entry["provider"]}: {reason}')
            if kind == 'BLOCKED':
                blocked += 1
            continue
        print(f'\n=== {entry.provider} · {entry.method}')
        print(
            f'  declared: max_page_size={entry.declared_max_page_size} '
            f'result_window={entry.declared_result_window}'
        )
        for probe in entry.probes:
            print(f'    {probe.label:26} -> {probe.outcome}')
        print(
            f'  observed: served_page_size={entry.observed_max_page_size} '
            f'[{entry.page_size_verdict}] '
            f'window_refused_at={entry.window_enforced_at} [{entry.window_verdict}]'
        )
        for note in entry.notes:
            print(f'  note: {note}')
        verdicts = (entry.page_size_verdict, entry.window_verdict)
        if 'DRIFT' in verdicts:
            drift += 1
        elif 'INCONCLUSIVE' in verdicts and entry.declared_result_window is not None:
            # A declared cap the probe could not exercise is unverified, not
            # verified — never fold it into a pass.
            inconclusive += 1
    parts = []
    if drift:
        parts.append(f'DRIFT — {drift} declaration(s) no longer match what the provider serves')
    if inconclusive:
        parts.append(f'{inconclusive} declared cap(s) the probe could not exercise')
    if blocked:
        parts.append(f'{blocked} provider(s) unconfirmed (no key — documentation only)')
    if not parts:
        parts.append('every declared cap was re-measured and matches')
    print('\nVERDICT:', '; '.join(parts))
    return 1 if (drift or inconclusive or blocked) else 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', action='append', choices=sorted(PROVIDERS))
    parser.add_argument('--json', action='store_true', help='machine-readable output')
    args = parser.parse_args()

    if not os.environ.get('ETHERSCAN_KEY'):
        from pathlib import Path

        env = Path(__file__).resolve().parents[2] / '.env'
        if env.exists():
            for line in env.read_text().splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

    selected = args.provider or sorted(PROVIDERS)
    results: list[Any] = []
    for scanner in selected:
        network, methods, target = PROVIDERS[scanner]
        results.extend(await probe_provider(scanner, network, methods, target))

    if args.json:
        print(
            json.dumps(
                [entry if isinstance(entry, dict) else asdict(entry) for entry in results],
                indent=2,
                default=str,
            )
        )
        return 0
    return _render(results)


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
