"""Progress callback protocol for long-running operations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressCallback(Protocol):
    """
    Protocol for progress callbacks during long-running operations.

    Progress callbacks provide real-time feedback during data fetching,
    allowing users to track progress, display progress bars, or log status.

    The callback is invoked periodically (typically once per page fetch) with
    updated progress information.

    Example:
        ```python
        async def simple_progress(
            fetched: int,
            total_expected: int | None,
            current_block: int | None = None,
            **kwargs
        ) -> None:
            if total_expected:
                pct = (fetched / total_expected) * 100
                print(f"Progress: {fetched}/{total_expected} ({pct:.1f}%)")
            else:
                print(f"Fetched: {fetched} items")

        txs = await client.get_all_transactions(
            address=address,
            on_progress=simple_progress
        )
        ```
    """

    async def __call__(
        self,
        fetched: int,
        total_expected: int | None,
        current_block: int | None = None,
        current_page: int | None = None,
        operation: str = 'fetch',
    ) -> None:
        """
        Progress callback invoked during long-running operations.

        Args:
            fetched: Number of items fetched so far
            total_expected: Expected total items (None if unknown)
            current_block: Current block number being processed (if applicable)
            current_page: Current page number (if applicable)
            operation: Description of the operation (e.g., "fetch", "decode", "chunk")

        Note:
            Implementations should be lightweight and fast. Heavy operations
            or blocking calls will slow down the data fetching process.

            Exceptions raised by the callback should be caught and logged
            by the caller to avoid disrupting the fetch operation.
        """
        ...
