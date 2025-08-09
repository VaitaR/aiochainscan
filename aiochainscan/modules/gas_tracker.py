from __future__ import annotations

import logging
from datetime import date
from typing import Any

from aiochainscan.capabilities import is_feature_supported
from aiochainscan.common import check_sort_direction
from aiochainscan.exceptions import FeatureNotSupportedError
from aiochainscan.modules.base import BaseModule, _facade_injection, _resolve_api_context

logger = logging.getLogger(__name__)


class GasTracker(BaseModule):
    """Gas Tracker

    https://docs.etherscan.io/api-endpoints/gas-tracker
    """

    # TODO: Deprecated in next major. Prefer facades in `aiochainscan.__init__`.

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

        # Route via service
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.gas import get_gas_estimate as _svc_gas_estimate

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        response = await _svc_gas_estimate(
            gasprice_wei=gasprice_wei,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        if isinstance(response, dict) and response.get('status') not in (None, '1'):
            raise FeatureNotSupportedError('gas_estimate', f'{scanner_id}:{network}')
        return response

    async def estimation_of_confirmation_time(self, gas_price: int) -> str:
        """Get Estimation of Confirmation Time"""
        from aiochainscan.modules.base import _facade_injection, _resolve_api_context
        from aiochainscan.services.gas import get_gas_estimate as _svc_gas_estimate

        http, endpoint = _facade_injection(self._client)
        api_kind, network, api_key = _resolve_api_context(self._client)
        resp = await _svc_gas_estimate(
            gasprice_wei=gas_price,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return str(resp.get('result')) if isinstance(resp, dict) else str(resp)

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

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.services.gas import get_gas_oracle as _svc_get_gas_oracle

        api_kind, network, api_key = _resolve_api_context(self._client)
        raw = await _svc_get_gas_oracle(
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        # Service returns provider-shaped inner result or the whole dict if no 'result' wrapper.
        if isinstance(raw, dict) and 'status' in raw and raw.get('status') != '1':
            raise FeatureNotSupportedError('gas_oracle', f'{scanner_id}:{network}')
        if isinstance(raw, dict) and 'status' not in raw:
            return {'status': '1', 'result': raw}
        return raw

    async def daily_average_gas_limit(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> list[dict[str, Any]]:
        """Get Daily Average Gas Limit"""
        http, endpoint = _facade_injection(self._client)
        from aiochainscan.services.stats import (
            get_daily_average_gas_limit as _svc_daily_avg_gas_limit,
        )

        api_kind, network, api_key = _resolve_api_context(self._client)
        if sort is not None:
            sort = check_sort_direction(sort)
        data = await _svc_daily_avg_gas_limit(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            sort=sort,
            http=http,
            _endpoint_builder=endpoint,
        )
        return list(data)

    async def daily_total_gas_used(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> Any:
        """Get Ethereum Daily Total Gas Used"""
        http, endpoint = _facade_injection(self._client)
        from aiochainscan.services.stats import (
            get_daily_total_gas_used as _svc_daily_total_gas_used,
        )

        api_kind, network, api_key = _resolve_api_context(self._client)
        if sort is not None:
            sort = check_sort_direction(sort)
        data = await _svc_daily_total_gas_used(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            sort=sort,
            http=http,
            _endpoint_builder=endpoint,
        )
        return data

    async def daily_average_gas_price(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> Any:
        """Get Daily Average Gas Price"""
        http, endpoint = _facade_injection(self._client)
        from aiochainscan.services.stats import (
            get_daily_average_gas_price as _svc_daily_avg_gas_price,
        )

        api_kind, network, api_key = _resolve_api_context(self._client)
        if sort is not None:
            sort = check_sort_direction(sort)
        data = await _svc_daily_avg_gas_price(
            start_date=start_date,
            end_date=end_date,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            sort=sort,
            http=http,
            _endpoint_builder=endpoint,
        )
        return data
