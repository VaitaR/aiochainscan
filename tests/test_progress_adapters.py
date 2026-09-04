"""Tests for the progress-port adapters (`aiochainscan/adapters/progress.py`).

Covers path identity between the adapter module and the documented
`aiochainscan.utils.progress_helpers` re-export, callback behaviour, and
optional-dependency safety for `tqdm_progress` / `rich_progress`.
"""

from __future__ import annotations

import importlib
import io
import logging

import pytest

from aiochainscan.adapters import progress as adapters_progress
from aiochainscan.utils import progress_helpers

#: The six ProgressCallback factories that must live in one place
#: (`adapters/progress.py`) and be re-exported, unchanged, from
#: `utils/progress_helpers.py`.
PROGRESS_ADAPTER_NAMES = [
    'console_progress',
    'tqdm_progress',
    'rich_progress',
    'silent_progress',
    'logging_progress',
    'callback_with_interval',
]


def test_progress_adapter_names_has_six_entries() -> None:
    """Guard against the identity loop below silently shrinking to zero."""
    assert len(PROGRESS_ADAPTER_NAMES) == 6


@pytest.mark.parametrize('name', PROGRESS_ADAPTER_NAMES)
def test_documented_path_is_same_object_as_new_path(name: str) -> None:
    """`utils.progress_helpers.<name>` must be the SAME object as
    `adapters.progress.<name>`, not a re-definition."""
    new_path_obj = getattr(adapters_progress, name)
    documented_path_obj = getattr(progress_helpers, name)
    assert documented_path_obj is new_path_obj, (
        f'{name}: aiochainscan.utils.progress_helpers.{name} is not the same object as '
        f'aiochainscan.adapters.progress.{name}'
    )


async def test_console_progress_writes_to_supplied_file() -> None:
    buf = io.StringIO()
    callback = adapters_progress.console_progress(file=buf)
    await callback(fetched=5, total_expected=10, current_block=123)
    output = buf.getvalue()
    assert output != ''
    assert '5/10' in output
    assert '123' in output


async def test_silent_progress_writes_nothing() -> None:
    callback = adapters_progress.silent_progress()
    # Should accept arbitrary args/kwargs and produce no observable output.
    result = await callback(fetched=1, total_expected=2, current_block=3, operation='fetch')
    assert result is None


async def test_logging_progress_emits_on_named_logger(caplog: pytest.LogCaptureFixture) -> None:
    logger_name = 'aiochainscan.progress.test'
    callback = adapters_progress.logging_progress(logger_name=logger_name)
    with caplog.at_level(logging.INFO, logger=logger_name):
        await callback(fetched=7, total_expected=14, current_page=2, operation='fetch')
    records = [r for r in caplog.records if r.name == logger_name]
    assert len(records) == 1
    assert '7 items' in records[0].message
    assert 'page=2' in records[0].message


async def test_callback_with_interval_calls_wrapped_callback_first_time() -> None:
    calls: list[int] = []

    async def inner(fetched: int, total_expected: int | None, **kwargs: object) -> None:
        calls.append(fetched)

    wrapped = adapters_progress.callback_with_interval(inner, min_interval_seconds=100.0)
    await wrapped(fetched=1, total_expected=None)
    assert calls == [1]


def test_importing_adapters_package_succeeds_without_tqdm_or_rich() -> None:
    """Importing `aiochainscan.adapters` must not require tqdm/rich to be
    installed — those imports are lazy, inside the factory bodies."""
    module = importlib.import_module('aiochainscan.adapters')
    importlib.reload(module)
    # The factories themselves must be present as attributes.
    for name in PROGRESS_ADAPTER_NAMES:
        assert hasattr(module, name)


def test_tqdm_progress_and_rich_progress_are_importable_names() -> None:
    """Calling them may raise (if tqdm/rich absent) but the names must exist
    and be callable — the module import itself must never fail."""
    assert callable(adapters_progress.tqdm_progress)
    assert callable(adapters_progress.rich_progress)
