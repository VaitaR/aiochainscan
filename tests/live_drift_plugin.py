"""Pytest plugin for the scheduled live-drift run (``-p tests.live_drift_plugin``).

Throttling and transport trouble that survived the client's own retries say
nothing about provider behaviour, so they are reported as skipped
(INCONCLUSIVE) instead of failed. Everything else - assertion errors, data
contract violations, auth failures - stays a failure: that is the drift signal.

A run in which nothing passed proves nothing, so it fails the session.
"""

from __future__ import annotations

import httpx
import pytest

from aiochainscan.exceptions import TRANSIENT_EXCEPTIONS, FailureKind

_INCONCLUSIVE_KINDS = frozenset({FailureKind.RATE_LIMIT, FailureKind.TRANSIENT})
_stats = {'passed': 0, 'inconclusive': 0}


def _is_inconclusive(exc: BaseException | None) -> bool:
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, TRANSIENT_EXCEPTIONS) and not isinstance(exc, httpx.HTTPStatusError):
            return True
        if getattr(exc, 'failure_kind', None) in _INCONCLUSIVE_KINDS:
            return True
        exc = exc.__cause__ or exc.__context__
    return False


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if (
        call.when == 'call'
        and report.failed
        and call.excinfo is not None
        and _is_inconclusive(call.excinfo.value)
    ):
        report.outcome = 'skipped'
        report.longrepr = (str(item.path), item.location[1] or 0, 'INCONCLUSIVE (throttled)')
        _stats['inconclusive'] += 1
    if call.when == 'call' and report.passed:
        _stats['passed'] += 1


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_line(
        f'live-drift: passed={_stats["passed"]} inconclusive={_stats["inconclusive"]}'
    )


def pytest_sessionfinish(session, exitstatus):
    if session.testscollected and not _stats['passed'] and session.exitstatus == 0:
        print('\nlive-drift: no test passed - run is vacuous')
        session.exitstatus = 1
