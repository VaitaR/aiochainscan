from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aiochainscan.exceptions import SourceNotVerifiedError
from aiochainscan.modules.base import BaseModule


class Contract(BaseModule):
    """Contracts

    https://docs.etherscan.io/api-endpoints/contracts
    """

    # TODO: Deprecated in next major. Prefer facades in `aiochainscan.__init__`.

    @property
    def _module(self) -> str:
        return 'contract'

    async def contract_abi(self, address: str) -> str | None:
        """Get Contract ABI for Verified Contract Source Codes

        Args:
            address: Contract address to get ABI for

        Returns:
            JSON encoded ABI string

        Raises:
            SourceNotVerifiedError: If contract source code is not verified

        Examples:
            >>> abi = await client.contract.contract_abi("0xdAC17F958D2ee523a2206206994597C13D831ec7")
            >>> print(abi)  # JSON ABI string
        """
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.contract import (
            get_contract_abi as _svc_get_contract_abi,
        )

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_get_contract_abi(
            address=address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        # Check for unverified contract responses
        if isinstance(result, str) and result.startswith('Contract source code not verified'):
            raise SourceNotVerifiedError(address)
        return result if isinstance(result, str) or result is None else str(result)

    async def contract_source_code(self, address: str) -> list[dict[str, Any]]:
        """Get Contract Source Code for Verified Contract Source Codes

        Args:
            address: Contract address to get source code for

        Returns:
            List of source code information dictionaries

        Raises:
            SourceNotVerifiedError: If contract source code is not verified

        Examples:
            >>> source = await client.contract.contract_source_code("0xdAC17F958D2ee523a2206206994597C13D831ec7")
            >>> print(source[0]['SourceCode'])
        """
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.contract import (
            get_contract_source_code as _svc_get_source,
        )

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_get_source(
            address=address,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        # Check for unverified contract in the result list
        if (
            isinstance(result, list)
            and len(result) > 0
            and isinstance(result[0], dict)
            and result[0].get('ABI') == 'Contract source code not verified'
        ):
            raise SourceNotVerifiedError(address)
        return list(result)

    async def contract_source(self, address: str) -> list[dict[str, Any]]:
        """Get Contract Source Code for Verified Contract Source Codes

        Alias for contract_source_code method
        """
        return await self.contract_source_code(address)

    async def contract_creation(self, addresses: Iterable[str]) -> list[dict[str, Any]]:
        """Get Contract Creator and Creation Tx Hash"""
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.contract import (
            get_contract_creation as _svc_get_creation,
        )

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        return await _svc_get_creation(
            contract_addresses=list(addresses),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )

    async def verify_contract_source_code(
        self,
        contract_address: str,
        source_code: str,
        contract_name: str,
        compiler_version: str,
        optimization_used: bool = False,
        runs: int = 200,
        constructor_arguements: str | None = None,
        libraries: dict[str, str] | None = None,
    ) -> str:
        """Submits a contract source code to Chainscan for verification."""
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.contract import (
            verify_contract_source_code as _svc_verify_source,
        )

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_verify_source(
            contract_address=contract_address,
            source_code=source_code,
            contract_name=contract_name,
            compiler_version=compiler_version,
            optimization_used=optimization_used,
            runs=runs,
            constructor_arguements=constructor_arguements or '',
            libraries=libraries,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return str(result)

    async def check_verification_status(self, guid: str) -> str:
        """Check Source code verification submission status"""
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.contract import (
            check_verification_status as _svc_check_status,
        )

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_check_status(
            guid=guid,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return str(result)

    async def verify_proxy_contract(
        self, address: str, expected_implementation: str | None = None
    ) -> str:
        """Submits a proxy contract source code to Chainscan for verification."""
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.contract import (
            verify_proxy_contract as _svc_verify_proxy,
        )

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_verify_proxy(
            address=address,
            expected_implementation=expected_implementation,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return str(result)

    async def check_proxy_contract_verification(self, guid: str) -> str:
        """Checking Proxy Contract Verification Submission Status"""
        from aiochainscan.modules.base import _facade_injection
        from aiochainscan.services.contract import (
            check_proxy_contract_verification as _svc_check_proxy,
        )

        http, endpoint = _facade_injection(self._client)
        from aiochainscan.modules.base import _resolve_api_context

        api_kind, network, api_key = _resolve_api_context(self._client)
        result = await _svc_check_proxy(
            guid=guid,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
        return str(result)

    @staticmethod
    def _parse_libraries(libraries: dict[str, str]) -> dict[str, str]:
        return dict(
            part
            for i, (name, address) in enumerate(libraries.items(), start=1)
            for part in ((f'libraryname{i}', name), (f'libraryaddress{i}', address))
        )
