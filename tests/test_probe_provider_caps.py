"""Offline tests for ``scripts/agent/probe_provider_caps.py``.

The live probe script promises "exit status is the verdict" (module docstring
and AGENTS.md). These tests pin the verdict machinery — factored so BOTH the
text and ``--json`` modes return it — and the error classification that keeps
a rate limit or timeout from reading as cap enforcement, using fake method
results and a fake client. No network access, no API keys.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from aiochainscan.domain.method import Method
from aiochainscan.exceptions import ChainscanClientApiError, ChainscanRateLimitError

_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'agent' / 'probe_provider_caps.py'


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location('probe_provider_caps_under_test', _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault('probe_provider_caps_under_test', module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def probe_module() -> Any:
    module = _load_module()
    module.CALL_DELAY_S = 0
    return module


def _method_result(probe_module: Any, **over: Any) -> Any:
    """A healthy-looking ACCOUNT_TRANSACTIONS result: declared window 10_000,
    served page size 1_000, window enforced just past the declaration."""
    fields: dict[str, Any] = {
        'provider': 'etherscan/v2',
        'method': 'ACCOUNT_TRANSACTIONS',
        'declared_result_window': 10_000,
        'declared_max_page_size': 1_000,
        'observed_max_page_size': 1_000,
        'window_enforced_at': 11_000,
    }
    fields.update(over)
    return probe_module.MethodResult(**fields)


class TestVerdict:
    def test_everything_ok_exits_zero(self, probe_module: Any) -> None:
        code, parts = probe_module._verdict([_method_result(probe_module)])
        assert code == 0
        assert 'matches' in parts[0]

    def test_drift_exits_one(self, probe_module: Any) -> None:
        drifted = _method_result(probe_module, observed_max_page_size=10_000)
        code, parts = probe_module._verdict([drifted])
        assert code == 1
        assert any('DRIFT' in part for part in parts)

    def test_window_drift_exits_one(self, probe_module: Any) -> None:
        # Window enforced AT the declared value, not past it: the provider
        # refuses its own declaration.
        drifted = _method_result(probe_module, window_enforced_at=10_000)
        assert drifted.window_verdict == 'DRIFT'
        code, _ = probe_module._verdict([drifted])
        assert code == 1

    def test_blocked_provider_exits_one(self, probe_module: Any) -> None:
        code, parts = probe_module._verdict(
            [{'provider': 'etherscan/ethereum', 'blocked': 'ChainscanClientError: no key'}]
        )
        assert code == 1
        assert any('unconfirmed' in part for part in parts)

    def test_rate_limited_is_its_own_inconclusive_verdict(self, probe_module: Any) -> None:
        """A throttled probe measured nothing — it must be reported as
        rate-limited/unconfirmed, never folded into DRIFT (and never into a
        pass)."""
        throttled = _method_result(probe_module, window_enforced_at=None, rate_limited=True)
        assert throttled.page_size_verdict == 'OK'
        assert throttled.window_verdict == 'RATE_LIMITED'
        code, parts = probe_module._verdict([throttled])
        assert code == 1
        assert any('rate-limited' in part for part in parts)
        assert not any('DRIFT' in part for part in parts)

    def test_rate_limited_page_probe_is_inconclusive_not_drift(self, probe_module: Any) -> None:
        throttled = _method_result(
            probe_module, observed_max_page_size=None, window_enforced_at=None, rate_limited=True
        )
        assert throttled.page_size_verdict == 'RATE_LIMITED'
        code, parts = probe_module._verdict([throttled])
        assert code == 1
        assert not any('DRIFT' in part for part in parts)

    def test_undeclared_window_not_counted_inconclusive(self, probe_module: Any) -> None:
        """Cursor-paginated providers declare nothing — nothing to verify, no
        failure either."""
        cursor_paged = _method_result(
            probe_module,
            declared_result_window=None,
            observed_max_page_size=None,
            window_enforced_at=None,
        )
        assert cursor_paged.window_verdict == 'UNDECLARED'
        code, _ = probe_module._verdict([cursor_paged])
        assert code == 0

    def test_text_and_json_modes_return_same_verdict(
        self,
        probe_module: Any,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--json must not be a verdict-free escape hatch: the exit code comes
        from the same factored verdict in both modes."""
        results: list[Any] = [_method_result(probe_module, observed_max_page_size=10_000)]

        async def fake_probe_provider(
            scanner: str, network: str, methods: tuple[Method, ...], target: Any
        ) -> list[Any]:
            return results

        monkeypatch.setattr(probe_module, 'probe_provider', fake_probe_provider)
        text_code = asyncio.run(probe_module.main(['--provider', 'etherscan']))
        text_output = capsys.readouterr().out
        json_code = asyncio.run(probe_module.main(['--json', '--provider', 'etherscan']))
        assert json_code == text_code == 1
        assert 'VERDICT:' in text_output


class _FakeScanner:
    max_page_size = 1_000

    def result_window_for(self, method: Method) -> int | None:
        return 10_000


def _fake_client(failure: Exception, fail_from_page: int) -> Any:
    """Serves page=1 like a 1_000-per-page provider (silent clamp) and serves
    window pages until ``fail_from_page``, where ``failure`` is raised."""

    class FakeClient:
        scanner_name = 'etherscan'
        scanner_version = 'v2'
        _scanner = _FakeScanner()

        async def call(self, method: Method, **params: Any) -> list[dict[str, str]]:
            page = int(params.get('page', 1))
            offset = int(params.get('offset', 1))
            if page < fail_from_page:
                return [{'hash': f'0x{page:064x}{i:060x}'} for i in range(min(offset, 1_000))]
            raise failure

    return FakeClient()


class TestErrorClassification:
    """The window walk used to read ANY error as cap enforcement — a 429 or a
    timeout against a healthy declaration produced a false DRIFT exit 1."""

    def test_rate_limit_on_first_window_page_is_not_enforcement(self, probe_module: Any) -> None:
        client = _fake_client(
            ChainscanRateLimitError('Max calls rate limit reached', 'NOTOK'),
            fail_from_page=10,  # page*offset == the declared window itself
        )
        result = asyncio.run(
            probe_module.probe_method(client, Method.ACCOUNT_TRANSACTIONS, probe_module.ETHEREUM)
        )
        assert result.observed_max_page_size == 1_000
        assert result.window_enforced_at is None
        assert result.rate_limited is True
        assert result.window_verdict == 'RATE_LIMITED'
        assert result.page_size_verdict == 'OK'
        code, parts = probe_module._verdict([result])
        assert code == 1
        assert not any('DRIFT' in part for part in parts)

    def test_deterministic_refusal_is_still_enforcement(self, probe_module: Any) -> None:
        client = _fake_client(
            ChainscanClientApiError(
                'Result window is too large', 'PageNo x Offset must be <= 10000'
            ),
            fail_from_page=11,  # the first page past the declared window
        )
        result = asyncio.run(
            probe_module.probe_method(client, Method.ACCOUNT_TRANSACTIONS, probe_module.ETHEREUM)
        )
        # The window itself was served; the refusal lands on the first
        # over-window page, so the declared 10_000 window is confirmed.
        assert result.window_enforced_at == 11_000
        assert result.window_verdict == 'OK'
        assert result.rate_limited is False
        code, _ = probe_module._verdict([result])
        assert code == 0

    def test_inconclusive_error_classifier(self, probe_module: Any) -> None:
        assert probe_module._is_inconclusive_error(ChainscanRateLimitError('throttled', 'NOTOK'))
        assert probe_module._is_inconclusive_error(
            ChainscanRateLimitError('throttled', 'NOTOK', failure_kind=None)
        )
        # A deterministic provider answer is a measurement, not a blip.
        assert not probe_module._is_inconclusive_error(
            ChainscanClientApiError('Result window is too large', 0)
        )
