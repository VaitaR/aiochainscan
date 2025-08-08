from __future__ import annotations

import logging
from datetime import date
from typing import Any, cast

from aiochainscan.capabilities import is_feature_supported
from aiochainscan.common import check_sort_direction
from aiochainscan.exceptions import FeatureNotSupportedError
from aiochainscan.modules.base import BaseModule

logger = logging.getLogger(__name__)


class GasTracker(BaseModule):
    """Gas Tracker

    https://docs.etherscan.io/api-endpoints/gas-tracker
    """

    @property
    def _module(self) -> str:
        return 'gastracker'

    async def gas_estimate(self, gasprice_wei: int) -> dict[str, Any]:
        """Get Gas Estimate

        Args:
            gasprice_wei: Gas price in wei

        Returns:
            Gas estimate data

        Raises:
            FeatureNotSupportedError: If gas estimate is not supported by this scanner/network
        """
        # Check capabilities
        scanner_id = self._client._url_builder._api_kind
        network = self._client._url_builder._network

        if not is_feature_supported('gas_estimate', scanner_id, network):
            raise FeatureNotSupportedError('gas_estimate', f'{scanner_id}:{network}')

        # Make API call and check status
        response = await self._get(action='gasestimate', gasprice=gasprice_wei)

        # Check if API returned error status
        if isinstance(response, dict) and response.get('status') != '1':
            raise FeatureNotSupportedError('gas_estimate', f'{scanner_id}:{network}')

        return cast(dict[str, Any], response)

    async def estimation_of_confirmation_time(self, gas_price: int) -> str:
        """Get Estimation of Confirmation Time"""
        result = await self._get(action='gasestimate', gasprice=gas_price)
        return cast(str, result)

    async def gas_oracle(self) -> dict[str, Any]:
        """Get Gas Oracle

        Returns:
            Gas oracle data

        Raises:
            FeatureNotSupportedError: If gas oracle is not supported by this scanner/network
        """
        # Prefer new service path via facade for hexagonal migration
        scanner_id = self._client._url_builder._api_kind
        network = self._client._url_builder._network

        if not is_feature_supported('gas_oracle', scanner_id, network):
            raise FeatureNotSupportedError('gas_oracle', f'{scanner_id}:{network}')

        try:
            from aiochainscan import get_gas_oracle  # lazy import to avoid cycles

            return await get_gas_oracle(
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            # Fallback to legacy behavior
            response = await self._get(action='gasoracle')
            if isinstance(response, dict) and response.get('status') != '1':
                raise FeatureNotSupportedError('gas_oracle', f'{scanner_id}:{network}') from None
            return cast(dict[str, Any], response)

    async def daily_average_gas_limit(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> list[dict[str, Any]]:
        """Get Daily Average Gas Limit"""
        try:
            from aiochainscan import get_daily_average_gas_limit  # lazy

            data = await get_daily_average_gas_limit(
                start_date=start_date,
                end_date=end_date,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
                sort=sort,
            )
            return data
        except Exception:
            result = await self._get(
                module='stats',
                action='dailyavggaslimit',
                startdate=start_date.isoformat(),
                enddate=end_date.isoformat(),
                sort=check_sort_direction(sort) if sort is not None else None,
            )
            return list(result)

    async def daily_total_gas_used(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Ethereum Daily Total Gas Used"""
        try:
            from aiochainscan import get_daily_total_gas_used  # lazy

            data = await get_daily_total_gas_used(
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
                module='stats',
                action='dailygasused',
                startdate=start_date.isoformat(),
                enddate=end_date.isoformat(),
                sort=check_sort_direction(sort) if sort is not None else None,
            )
            return cast(dict[str, Any], result)

    async def daily_average_gas_price(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict[str, Any]:
        """Get Daily Average Gas Price"""
        try:
            from aiochainscan import get_daily_average_gas_price  # lazy

            data = await get_daily_average_gas_price(
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
                module='stats',
                action='dailyavggasprice',
                startdate=start_date.isoformat(),
                enddate=end_date.isoformat(),
                sort=check_sort_direction(sort) if sort is not None else None,
            )
            return cast(dict[str, Any], result)
