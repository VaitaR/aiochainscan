#!/usr/bin/env python3
"""Probe BlockScout's own mainnet instances against the three surfaces this library uses.

The host table in ``chain_registry.py`` is measured, not assumed, and the
directory at ``chains.blockscout.com`` is not evidence: it lists hosts that 404,
that only 301 to a chain-branded domain, and that serve part of the surface.
This script is how a row earns its place, and how an existing row is re-verified.

A host qualifies only when all three answer on its own hostname:

* ``GET /api`` — the Etherscan-compat REST the v1 leg is built on.
* ``GET /api/v2/stats`` — the native v2 surface.
* ``POST /api/eth-rpc`` with ``eth_chainId``, returning the expected id — this
  is what ``get_chain_info()``/``validate_chain()`` probe and what the v1 leg
  routes ``TX_BY_HASH`` and both ``PROXY_*`` methods through, so an unverified
  eth-rpc is three unverified methods.

**HTTP 429 is throttling, never a host verdict.** BlockScout rate-limits
``/api/eth-rpc`` per client IP across every instance at once — a sweep can leave
the endpoint refusing even hosts already declared here, while their REST
surfaces answer 200 — so a throttled probe is reported as INCONCLUSIVE and the
run exits non-zero. Re-run it later rather than reading a 429 as a dead host.

Usage:
    uv run python scripts/agent/probe_blockscout_hosts.py [--host H ...] [--new-only] [--json]

Exit status is the verdict: 0 = every probed host fully answered, 1 = at least
one failed or was left inconclusive.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass

import httpx

from aiochainscan.chain_registry import BLOCKSCOUT_INSTANCE_HOSTS, STANDARD_CHAINS

DIRECTORY_URL = 'https://chains.blockscout.com/api/chains'
TIMEOUT = httpx.Timeout(30.0)
#: Sequential, with gaps: the eth-rpc limit is per IP and shared across hosts,
#: so concurrency buys nothing but 429s.
GAP_SECONDS = 6.0
RETRY_DELAYS = (15.0, 30.0, 60.0)


@dataclass
class HostResult:
    chain_id: int
    host: str
    v1: str = 'unprobed'
    v2: str = 'unprobed'
    rpc: str = 'unprobed'
    reported_chain_id: int | None = None
    redirect: str | None = None

    @property
    def verdict(self) -> str:
        states = (self.v1, self.v2, self.rpc)
        if all(s == 'ok' for s in states):
            return 'OK'
        if any(s == 'throttled' for s in states):
            return 'INCONCLUSIVE'
        if self.redirect:
            return 'REDIRECT'
        return 'FAIL'


async def _get(
    client: httpx.AsyncClient, method: str, url: str, **kwargs: object
) -> httpx.Response:
    """One request, retrying a 429 with backoff so throttling is not mistaken for a verdict."""
    response = await client.request(method, url, **kwargs)  # type: ignore[arg-type]
    for delay in RETRY_DELAYS:
        if response.status_code != 429:
            return response
        await asyncio.sleep(delay)
        response = await client.request(method, url, **kwargs)  # type: ignore[arg-type]
    return response


async def probe_host(client: httpx.AsyncClient, chain_id: int, host: str) -> HostResult:
    result = HostResult(chain_id=chain_id, host=host)
    base = f'https://{host}'

    try:
        response = await _get(
            client,
            'GET',
            f'{base}/api',
            params={'module': 'block', 'action': 'eth_block_number'},
        )
        if response.is_redirect:
            result.redirect = response.headers.get('location')
            result.v1 = 'redirect'
        elif response.status_code == 429:
            result.v1 = 'throttled'
        elif response.status_code == 200 and 'json' in response.headers.get('content-type', ''):
            result.v1 = 'ok'
        else:
            result.v1 = f'http:{response.status_code}'
    except Exception as exc:
        result.v1 = f'error:{type(exc).__name__}'

    try:
        response = await _get(client, 'GET', f'{base}/api/v2/stats')
        if response.status_code == 429:
            result.v2 = 'throttled'
        elif response.status_code == 200 and 'json' in response.headers.get('content-type', ''):
            result.v2 = 'ok'
        else:
            result.v2 = f'http:{response.status_code}'
    except Exception as exc:
        result.v2 = f'error:{type(exc).__name__}'

    try:
        response = await _get(
            client,
            'POST',
            f'{base}/api/eth-rpc',
            json={'jsonrpc': '2.0', 'id': 1, 'method': 'eth_chainId', 'params': []},
        )
        if response.status_code == 429:
            result.rpc = 'throttled'
        elif response.status_code != 200:
            result.rpc = f'http:{response.status_code}'
        else:
            result.reported_chain_id = int(response.json()['result'], 16)
            result.rpc = 'ok' if result.reported_chain_id == chain_id else 'chain-id-mismatch'
    except Exception as exc:
        result.rpc = f'error:{type(exc).__name__}'

    return result


async def directory_targets(new_only: bool) -> list[tuple[int, str]]:
    """Mainnet instances BlockScout hosts itself.

    Third-party RaaS and self-hosted rows are deliberately excluded: they are
    listed by the directory but operated by someone else, with none of the
    availability this table's rows are asserting.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        listing = (await client.get(DIRECTORY_URL)).json()

    declared = {host.rstrip('/') for host in BLOCKSCOUT_INSTANCE_HOSTS.values()}
    targets: list[tuple[int, str]] = []
    for chain_id, meta in listing.items():
        if meta.get('isTestnet'):
            continue
        for explorer in meta.get('explorers') or []:
            if explorer.get('hostedBy') != 'blockscout' or not explorer.get('url'):
                continue
            host = explorer['url'].rstrip('/').removeprefix('https://')
            if new_only and host in declared:
                break
            targets.append((int(chain_id), host))
            break
    return targets


def declared_targets() -> list[tuple[int, str]]:
    by_host = {
        info['blockscout_instance']: chain_id
        for chain_id, info in STANDARD_CHAINS.items()
        if info.get('blockscout_instance')
    }
    return sorted({(by_host.get(host, 0), host) for host in BLOCKSCOUT_INSTANCE_HOSTS.values()})


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', action='append', help='Probe only these hosts (repeatable)')
    parser.add_argument(
        '--new-only', action='store_true', help='Only directory hosts not already declared'
    )
    parser.add_argument(
        '--declared', action='store_true', help='Re-verify the hosts this repo declares'
    )
    parser.add_argument('--json', action='store_true', help='Machine-readable output')
    args = parser.parse_args()

    if args.declared:
        targets = declared_targets()
    else:
        targets = await directory_targets(args.new_only)
    if args.host:
        wanted = set(args.host)
        targets = [t for t in targets if t[1] in wanted]

    results: list[HostResult] = []
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        for index, (chain_id, host) in enumerate(targets):
            results.append(await probe_host(client, chain_id, host))
            if index + 1 < len(targets):
                await asyncio.sleep(GAP_SECONDS)

    if args.json:
        print(json.dumps([asdict(r) | {'verdict': r.verdict} for r in results], indent=1))
    else:
        for result in results:
            line = f'{result.verdict:<12} {result.chain_id:>10}  {result.host:<40}'
            if result.verdict != 'OK':
                line += f' v1={result.v1} v2={result.v2} rpc={result.rpc}'
            if result.redirect:
                line += f' -> {result.redirect}'
            print(line)
        counts: dict[str, int] = {}
        for result in results:
            counts[result.verdict] = counts.get(result.verdict, 0) + 1
        print(
            f'\n{len(results)} probed: ' + ', '.join(f'{v} {k}' for k, v in sorted(counts.items()))
        )
        if any(r.verdict == 'INCONCLUSIVE' for r in results):
            print('INCONCLUSIVE = rate-limited, not a dead host. Re-run later.', file=sys.stderr)

    return 0 if all(r.verdict == 'OK' for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
