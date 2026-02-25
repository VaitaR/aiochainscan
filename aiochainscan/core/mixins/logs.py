"""Event logs API mixin for ``ChainscanClient``."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

from ...domain.models import Address
from ..method import Method
from ..types import JSONList

if TYPE_CHECKING:
    from ...ports.progress import ProgressCallback


logger = logging.getLogger(__name__)
AGGREGATION_WARNING_THRESHOLD = 100_000


class _LogsClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...

    def iter_logs_streaming(
        self,
        address: str | None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        topic0: str | None = None,
        topic1: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
        batch_size: int = 1000,
        on_progress: ProgressCallback | None = None,
    ) -> Any: ...


class LogsMixin:
    """Event logs convenience methods."""

    async def get_logs(
        self: _LogsClientProtocol,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        topic0: str | None = None,
        topic1: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
    ) -> JSONList:
        addr = Address(address)
        params: dict[str, Any] = {
            'address': str(addr),
            'fromBlock': from_block,
            'toBlock': to_block or 'latest',
        }
        if topic0:
            params['topic0'] = topic0
        if topic1:
            params['topic1'] = topic1
        if topic2:
            params['topic2'] = topic2
        if topic3:
            params['topic3'] = topic3
        result: JSONList = await self.call(Method.EVENT_LOGS, **params)
        return result if isinstance(result, list) else []

    async def get_all_logs(
        self: _LogsClientProtocol,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        topic0: str | None = None,
        topic1: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> JSONList:
        all_logs: JSONList = []
        async for batch in self.iter_logs_streaming(
            address=address,
            from_block=from_block,
            to_block=to_block,
            topic0=topic0,
            topic1=topic1,
            topic2=topic2,
            topic3=topic3,
            batch_size=1000,
            on_progress=on_progress,
        ):
            all_logs.extend(batch)
            if len(all_logs) == AGGREGATION_WARNING_THRESHOLD:
                logger.warning(
                    'Aggregating >100k logs in memory. '
                    'Consider using iter_logs_streaming() to avoid OOM.'
                )
        return all_logs
