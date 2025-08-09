from __future__ import annotations

from datetime import date
from typing import Any, cast

from aiochainscan.common import (
    check_closest_value,
    check_sort_direction,
)
from aiochainscan.modules.base import BaseModule
from aiochainscan.utils.date import default_range


class Block(BaseModule):
    """Blocks

    https://docs.etherscan.io/api-endpoints/blocks
    """

    # TODO: Deprecated in next major. Prefer facades in `aiochainscan.__init__`.

    @property
    def _module(self) -> str:
        return 'block'

    async def block_reward(self, block_no: int | None = None) -> dict[str, Any] | None:
        """Get Block And Uncle Rewards by BlockNo"""
        if block_no is None:
            current_block_hex = await self._client.proxy.block_number()
            current_block = int(current_block_hex, 16)
            block_no = max(current_block - 1, 0)

        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.block import get_block_reward as _svc_block_reward

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_block_reward(
            block_no=block_no,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return cast(dict[str, Any] | None, data)

    async def get_by_number(self, number: int, *, full: bool = False) -> dict[str, Any]:
        """Fetch block by number via facade when available."""
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.block import get_block_by_number as _svc_get_block

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_block(
            tag=number,
            full=full,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def block_countdown(
        self, block_no: int | None = None, *, offset: int = 1_000
    ) -> dict[str, Any] | None:
        """Get Estimated Block Countdown Time by BlockNo"""
        # Compute default target block using current + offset
        current_block_hex = await self._client.proxy.block_number()
        current_block = int(current_block_hex, 16)
        if block_no is None:
            block_no = current_block + offset

        block_diff = block_no - current_block
        if block_diff <= 0:
            raise ValueError('Past block for countdown')
        if block_diff > 2_000_000:
            raise ValueError('Block number too large (max difference: 2,000,000 blocks)')

        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.block import get_block_countdown as _svc_block_countdown

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        response = await _svc_block_countdown(
            block_no=block_no,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        # Service returns None for "No transactions found"
        return cast(dict[str, Any] | None, response)

    async def est_block_countdown_time(self, blockno: int) -> dict[str, Any] | None:
        """Get Estimated Block Countdown Time by BlockNo

        Deprecated: Use block_countdown instead
        """
        return await self.block_countdown(blockno)

    async def block_number_by_ts(self, ts: int, closest: str) -> dict[str, Any]:
        """Get Block Number by Timestamp"""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.block import (
            get_block_number_by_timestamp as _svc_bn_by_ts,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_bn_by_ts(
            ts=ts,
            closest=check_closest_value(closest),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return cast(dict[str, Any], result)

    async def daily_average_block_size(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Average Block Size"""
        if sort is not None:
            sort = check_sort_direction(sort)
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.stats import (
            get_daily_average_block_size as _svc_get_daily_avg_block_size,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_get_daily_avg_block_size(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            sort=sort,
            http=http,
            _endpoint_builder=endpoint,
        )
        return cast(dict[str, Any], data)

    async def daily_block_count(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        sort: str | None = None,
    ) -> dict[str, Any] | None:
        """Get Daily Block Count and Rewards"""
        if start_date is None or end_date is None:
            start_date, end_date = default_range(days=30)

        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.stats import (
            get_daily_block_count as _svc_get_daily_block_count,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_get_daily_block_count(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            sort=sort,
            http=http,
            _endpoint_builder=endpoint,
        )
        # Service returns list; preserve previous dict|None signature by wrapping when needed
        if isinstance(data, list):
            if len(data) == 0:
                return None
            return {'result': data}
        return cast(dict[str, Any] | None, data)

    async def daily_block_rewards(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Block Rewards"""
        if sort is not None:
            sort = check_sort_direction(sort)
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.stats import (
            get_daily_block_rewards as _svc_get_daily_block_rewards,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_get_daily_block_rewards(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            sort=sort,
            http=http,
            _endpoint_builder=endpoint,
        )
        return cast(dict[str, Any], data)

    async def daily_average_time_for_a_block(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Average Time for A Block to be Included in the Ethereum Blockchain"""
        if sort is not None:
            sort = check_sort_direction(sort)
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.stats import (
            get_daily_average_block_time as _svc_get_daily_avg_block_time,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_get_daily_avg_block_time(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            sort=sort,
            http=http,
            _endpoint_builder=endpoint,
        )
        return cast(dict[str, Any], data)

    async def daily_uncle_block_count(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Uncle Block Count and Rewards"""
        if sort is not None:
            sort = check_sort_direction(sort)
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.stats import (
            get_daily_uncle_block_count as _svc_get_daily_uncle_block_count,
        )

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        data = await _svc_get_daily_uncle_block_count(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            sort=sort,
            http=http,
            _endpoint_builder=endpoint,
        )
        return cast(dict[str, Any], data)
