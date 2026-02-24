"""Helper functions for creating common progress callbacks."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..ports.progress import ProgressCallback


def console_progress(file: Any = sys.stdout) -> ProgressCallback:
    """
    Create a simple console progress printer.

    Prints progress to stdout (or specified file) with carriage return
    to overwrite the same line.

    Args:
        file: Output file (default: sys.stdout)

    Returns:
        ProgressCallback that prints to console

    Example:
        ```python
        txs = await client.get_all_transactions(
            address="0x...",
            on_progress=console_progress()
        )
        # Output: Progress: 5000/10000 (50.0%) - Block 18500000
        ```
    """

    async def callback(
        fetched: int,
        total_expected: int | None,
        current_block: int | None = None,
        current_page: int | None = None,
        operation: str = 'fetch',
        **kwargs: Any,
    ) -> None:
        parts = []

        if total_expected:
            pct = (fetched / total_expected) * 100
            parts.append(f'Progress: {fetched}/{total_expected} ({pct:.1f}%)')
        else:
            parts.append(f'Fetched: {fetched}')

        if current_block is not None:
            parts.append(f'Block {current_block}')
        elif current_page is not None:
            parts.append(f'Page {current_page}')

        if operation and operation != 'fetch':
            parts.append(f'[{operation}]')

        message = ' - '.join(parts)
        print(f'\r{message}', end='', file=file, flush=True)

    return callback


def tqdm_progress(desc: str = 'Fetching', **tqdm_kwargs: Any) -> ProgressCallback:
    """
    Create a tqdm progress bar callback.

    Requires tqdm to be installed:
        pip install tqdm

    Args:
        desc: Progress bar description
        **tqdm_kwargs: Additional arguments passed to tqdm

    Returns:
        ProgressCallback that updates a tqdm progress bar

    Example:
        ```python
        from aiochainscan.utils.progress_helpers import tqdm_progress

        txs = await client.get_all_transactions(
            address="0x...",
            on_progress=tqdm_progress(desc="Fetching transactions")
        )
        ```
    """
    try:
        from tqdm.auto import tqdm  # type: ignore[import-untyped]
    except ImportError as e:
        raise ImportError(
            'tqdm is required for tqdm_progress. Install it with: pip install tqdm'
        ) from e

    pbar = tqdm(desc=desc, **tqdm_kwargs)

    async def callback(
        fetched: int,
        total_expected: int | None,
        current_block: int | None = None,
        current_page: int | None = None,
        operation: str = 'fetch',
        **kwargs: Any,
    ) -> None:
        # Update total if known and changed
        if total_expected is not None and pbar.total != total_expected:
            pbar.total = total_expected
            pbar.refresh()

        # Update progress
        if fetched > pbar.n:
            pbar.update(fetched - pbar.n)

        # Update postfix with additional info
        postfix: dict[str, int | str] = {}
        if current_block is not None:
            postfix['block'] = current_block
        if current_page is not None:
            postfix['page'] = current_page
        if operation and operation != 'fetch':
            postfix['op'] = operation

        if postfix:
            pbar.set_postfix(postfix)

    return callback


def rich_progress(description: str = 'Fetching') -> ProgressCallback:
    """
    Create a rich progress bar callback.

    Requires rich to be installed:
        pip install rich

    Args:
        description: Task description

    Returns:
        ProgressCallback that updates a rich progress bar

    Example:
        ```python
        from aiochainscan.utils.progress_helpers import rich_progress

        txs = await client.get_all_transactions(
            address="0x...",
            on_progress=rich_progress("Fetching transactions")
        )
        ```
    """
    try:
        from rich.progress import Progress, TaskID
    except ImportError as e:
        raise ImportError(
            'rich is required for rich_progress. Install it with: pip install rich'
        ) from e

    progress = Progress()
    progress.start()
    task_id: TaskID = progress.add_task(description, total=None)

    async def callback(
        fetched: int,
        total_expected: int | None,
        current_block: int | None = None,
        current_page: int | None = None,
        operation: str = 'fetch',
        **kwargs: Any,
    ) -> None:
        # Update total if known
        if total_expected is not None and progress.tasks[task_id].total != total_expected:
            progress.update(task_id, total=total_expected)

        # Update completed
        progress.update(task_id, completed=fetched)

        # Update description with extra info
        desc_parts = [description]
        if current_block is not None:
            desc_parts.append(f'Block {current_block}')
        if operation and operation != 'fetch':
            desc_parts.append(f'[{operation}]')

        progress.update(task_id, description=' - '.join(desc_parts))

    return callback


def silent_progress() -> ProgressCallback:
    """
    Create a no-op progress callback.

    Useful as a default or for disabling progress callbacks without
    changing code structure.

    Returns:
        ProgressCallback that does nothing

    Example:
        ```python
        on_progress = silent_progress() if quiet else console_progress()

        txs = await client.get_all_transactions(
            address="0x...",
            on_progress=on_progress
        )
        ```
    """

    async def callback(*args: Any, **kwargs: Any) -> None:
        pass

    return callback


def logging_progress(logger_name: str = 'aiochainscan.progress') -> ProgressCallback:
    """
    Create a logging-based progress callback.

    Logs progress updates at INFO level using Python's logging module.

    Args:
        logger_name: Logger name to use

    Returns:
        ProgressCallback that logs progress

    Example:
        ```python
        import logging
        logging.basicConfig(level=logging.INFO)

        from aiochainscan.utils.progress_helpers import logging_progress

        txs = await client.get_all_transactions(
            address="0x...",
            on_progress=logging_progress()
        )
        ```
    """
    import logging

    logger = logging.getLogger(logger_name)

    async def callback(
        fetched: int,
        total_expected: int | None,
        current_block: int | None = None,
        current_page: int | None = None,
        operation: str = 'fetch',
        **kwargs: Any,
    ) -> None:
        parts = [f'{operation}: {fetched} items']

        if total_expected:
            pct = (fetched / total_expected) * 100
            parts.append(f'({pct:.1f}%)')

        if current_block is not None:
            parts.append(f'block={current_block}')
        if current_page is not None:
            parts.append(f'page={current_page}')

        logger.info(' '.join(parts))

    return callback


def callback_with_interval(
    callback: ProgressCallback,
    min_interval_seconds: float = 1.0,
) -> ProgressCallback:
    """
    Wrap a progress callback to limit invocation frequency.

    Useful for expensive callbacks (e.g., updating a database or sending
    network requests) to avoid overwhelming the system.

    Args:
        callback: The callback to wrap
        min_interval_seconds: Minimum seconds between invocations

    Returns:
        Rate-limited ProgressCallback

    Example:
        ```python
        import asyncio

        async def expensive_callback(fetched, total, **kwargs):
            # Send progress to remote API
            await update_remote_progress(fetched, total)

        # Only call once per 5 seconds
        limited = callback_with_interval(expensive_callback, 5.0)

        txs = await client.get_all_transactions(
            address="0x...",
            on_progress=limited
        )
        ```
    """
    from time import monotonic

    last_call_time = 0.0

    async def wrapper(
        fetched: int,
        total_expected: int | None,
        current_block: int | None = None,
        current_page: int | None = None,
        operation: str = 'fetch',
        **kwargs: Any,
    ) -> None:
        nonlocal last_call_time

        now = monotonic()

        # Always call on first invocation or completion
        is_complete = total_expected is not None and fetched >= total_expected
        time_elapsed = now - last_call_time

        if is_complete or time_elapsed >= min_interval_seconds:
            await callback(
                fetched,
                total_expected,
                current_block=current_block,
                current_page=current_page,
                operation=operation,
                **kwargs,
            )
            last_call_time = now

    return wrapper
