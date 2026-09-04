"""Event logs API mixin for ``ChainscanClient``."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ...domain.method import Method
from ...domain.models import Address
from ...domain.normalize import normalize_log
from ...domain.normalized import Log
from ..host import ClientHost
from ..streaming import collect_stream
from ..types import JSONList

if TYPE_CHECKING:
    from ...ports.progress import ProgressCallback

logger = logging.getLogger(__name__)


class LogsMixin:
    """Event logs convenience methods."""

    async def get_logs(
        self: ClientHost,
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
            'from_block': from_block,
            'to_block': to_block if to_block is not None else 'latest',
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

    async def get_logs_normalized(
        self: ClientHost,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        topic0: str | None = None,
        topic1: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
    ) -> list[Log]:
        """Same page as ``get_logs``, mapped onto ``domain.normalized.Log``."""
        raw = await LogsMixin.get_logs(
            self, address, from_block, to_block, topic0, topic1, topic2, topic3
        )
        return [normalize_log(item) for item in raw]

    async def get_all_logs(
        self: ClientHost,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        topic0: str | None = None,
        topic1: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> JSONList:
        return await collect_stream(
            self.iter_logs_streaming(
                address=address,
                from_block=from_block,
                to_block=to_block,
                topic0=topic0,
                topic1=topic1,
                topic2=topic2,
                topic3=topic3,
                batch_size=1000,
                on_progress=on_progress,
                guarantee_complete=guarantee_complete,
            ),
            stream_name='iter_logs_streaming',
            noun='logs',
            logger=logger,
        )

    async def get_all_logs_normalized(
        self: ClientHost,
        address: str,
        from_block: int = 0,
        to_block: int | str | None = None,
        topic0: str | None = None,
        topic1: str | None = None,
        topic2: str | None = None,
        topic3: str | None = None,
        on_progress: ProgressCallback | None = None,
        guarantee_complete: bool = True,
    ) -> list[Log]:
        """Materialize ``iter_logs_normalized`` into one list.

        Same completeness guarantee as :meth:`get_all_logs`; the only
        difference is the item type (``Log`` instead of ``dict``). The
        generator itself lives on ``ChainscanClient`` next to
        ``iter_logs_streaming`` (see core/client.py) and normalizes each
        batch as it arrives, never after collecting the raw list.
        """
        return await collect_stream(
            self.iter_logs_normalized(
                address,
                from_block=from_block,
                to_block=to_block,
                topic0=topic0,
                topic1=topic1,
                topic2=topic2,
                topic3=topic3,
                batch_size=1000,
                on_progress=on_progress,
                guarantee_complete=guarantee_complete,
            ),
            stream_name='iter_logs_normalized',
            noun='normalized logs',
            logger=logger,
        )
