from __future__ import annotations

import logging
from datetime import date
from typing import Any, cast

from aiochainscan.common import check_client_type, check_sync_mode, get_daily_stats_params
from aiochainscan.modules.base import BaseModule, _should_force_facades
from aiochainscan.modules.extra.utils import _default_date_range

logger = logging.getLogger(__name__)


class Stats(BaseModule):
    """Stats

    https://docs.etherscan.io/api-endpoints/stats-1
    """

    # TODO: Deprecated in next major. Prefer facades in `aiochainscan.__init__`.

    @property
    def _module(self) -> str:
        return 'stats'

    async def eth_supply(self) -> str:
        """Get Total Supply of Ether"""
        result = await self._get(action='ethsupply')
        return str(result)

    async def eth2_supply(self) -> str:
        """Get Total Supply of Ether"""
        result = await self._get(action='ethsupply2')
        return str(result)

    async def eth_price(self) -> dict[str, Any]:
        """Get ETHER LastPrice Price"""
        # Prefer new service path via facade for hexagonal migration
        try:
            from aiochainscan.modules.base import _facade_injection
            from aiochainscan.services.stats import get_eth_price as _svc_get_eth_price

            http, endpoint = _facade_injection(self._client)
            from aiochainscan.modules.base import _resolve_api_context

            api_kind, network, api_key = _resolve_api_context(self._client)
            return await _svc_get_eth_price(
                api_kind=api_kind,
                network=network,
                api_key=api_key,
                http=http,
                _endpoint_builder=endpoint,
            )
        except Exception:
            if _should_force_facades():
                raise
            result = await self._get(action='ethprice')
            return cast(dict[str, Any], result)

    async def chain_size(
        self,
        start_date: date,
        end_date: date,
        client_type: str,
        sync_mode: str,
        sort: str | None = None,
    ) -> dict[str, Any] | None:
        """Get Chain Size"""
        try:
            result = await self._get(
                **get_daily_stats_params('chainsize', start_date, end_date, sort),
                clienttype=check_client_type(client_type),
                syncmode=check_sync_mode(sync_mode),
            )
            # Return None if result is empty array
            if isinstance(result, list) and len(result) == 0:
                return None
            return cast(dict[str, Any], result)
        except ValueError:
            # Re-raise validation errors from check functions
            raise
        except Exception as e:
            logger.debug(
                f'Chain size action not supported for {self._client._url_builder._api_kind}: {e}'
            )
            return None

    async def eth_nodes_size(
        self,
        start_date: date,
        end_date: date,
        client_type: str,
        sync_mode: str,
        sort: str | None = None,
    ) -> dict[str, Any] | None:
        """Get Ethereum Nodes Size

        Deprecated: Use chain_size instead.
        """
        return await self.chain_size(start_date, end_date, client_type, sync_mode, sort)

    async def nodes_size(
        self,
        start: date | None = None,
        end: date | None = None,
        client: str = 'geth',
        sync: str = 'default',
    ) -> dict[str, Any] | None:
        """Get Node Size

        Args:
            start: Start date (default: today - 30 days)
            end: End date (default: today)
            client: Client type (default: 'geth')
            sync: Sync mode (default: 'default')

        Returns:
            Node size data or None if no data available
        """
        if start is None or end is None:
            start, end = _default_date_range(days=30)

        try:
            result = await self._get(
                action='chainsize',
                startdate=start.isoformat(),
                enddate=end.isoformat(),
                clienttype=check_client_type(client),
                syncmode=check_sync_mode(sync),
            )
            # Return None if result is empty array
            if isinstance(result, list) and len(result) == 0:
                return None
            return cast(dict[str, Any], result)
        except ValueError:
            # Re-raise validation errors from check functions
            raise
        except Exception as e:
            logger.debug(
                f'Nodes size action not supported for {self._client._url_builder._api_kind}: {e}'
            )
            return None

    async def daily_block_count(
        self, start: date, end: date, sort: str = 'asc'
    ) -> list[dict[str, Any]] | None:
        """Get Daily Block Count and Rewards

        Args:
            start: Start date
            end: End date
            sort: Sort direction ('asc' or 'desc', default: 'asc')

        Returns:
            Daily block count data or None if no data available
        """
        try:
            result = await self._get(
                action='dailyblkcount',
                startdate=start.isoformat(),
                enddate=end.isoformat(),
                sort=sort,
            )
            # Return None if result is empty array
            if isinstance(result, list) and len(result) == 0:
                return None
            return cast(list[dict[str, Any]], result)
        except Exception as e:
            logger.debug(
                f'Daily block count action not supported for {self._client._url_builder._api_kind}: {e}'
            )
            return None

    async def total_nodes_count(self) -> dict[str, Any]:
        """Get Total Nodes Count"""
        result = await self._get(action='nodecount')
        return cast(dict[str, Any], result)

    async def daily_network_tx_fee(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Network Transaction Fee"""
        try:
            from aiochainscan import get_daily_network_tx_fee  # lazy to avoid cycles

            data = await get_daily_network_tx_fee(
                start_date=start_date,
                end_date=end_date,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
                sort=sort,
            )
            return cast(dict[str, Any], data)
        except Exception:
            result = await self._get(
                **get_daily_stats_params('dailytxnfee', start_date, end_date, sort)
            )
            return cast(dict[str, Any], result)

    async def daily_new_address_count(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily New Address Count"""
        try:
            from aiochainscan import get_daily_new_address_count  # lazy

            data = await get_daily_new_address_count(
                start_date=start_date,
                end_date=end_date,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
                sort=sort,
            )
            return cast(dict[str, Any], data)
        except Exception:
            result = await self._get(
                **get_daily_stats_params('dailynewaddress', start_date, end_date, sort)
            )
            return cast(dict[str, Any], result)

    async def daily_network_utilization(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Network Utilization"""
        try:
            from aiochainscan import get_daily_network_utilization  # lazy

            data = await get_daily_network_utilization(
                start_date=start_date,
                end_date=end_date,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
                sort=sort,
            )
            return cast(dict[str, Any], data)
        except Exception:
            result = await self._get(
                **get_daily_stats_params('dailynetutilization', start_date, end_date, sort)
            )
            return cast(dict[str, Any], result)

    async def daily_average_network_hash_rate(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Average Network Hash Rate"""
        result = await self._get(
            **get_daily_stats_params('dailyavghashrate', start_date, end_date, sort)
        )
        return cast(dict[str, Any], result)

    async def daily_transaction_count(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Transaction Count"""
        try:
            from aiochainscan import get_daily_transaction_count  # lazy

            data = await get_daily_transaction_count(
                start_date=start_date,
                end_date=end_date,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
                sort=sort,
            )
            return cast(dict[str, Any], data)
        except Exception:
            result = await self._get(
                **get_daily_stats_params('dailytx', start_date, end_date, sort)
            )
            return cast(dict[str, Any], result)

    async def daily_average_network_difficulty(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Average Network Difficulty"""
        result = await self._get(
            **get_daily_stats_params('dailyavgnetdifficulty', start_date, end_date, sort)
        )
        return cast(dict[str, Any], result)

    async def ether_historical_daily_market_cap(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Ether Historical Daily Market Cap"""
        result = await self._get(
            **get_daily_stats_params('ethdailymarketcap', start_date, end_date, sort)
        )
        return cast(dict[str, Any], result)

    async def ether_historical_price(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Ether Historical Price"""
        result = await self._get(
            **get_daily_stats_params('ethdailyprice', start_date, end_date, sort)
        )
        return cast(dict[str, Any], result)
