from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from aiochainscan.exceptions import SourceNotVerifiedError
from aiochainscan.modules.base import BaseModule


class Contract(BaseModule):
    """Contracts

    https://docs.etherscan.io/api-endpoints/contracts
    """

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
        try:
            from aiochainscan import get_contract_abi  # lazy import to avoid cycles

            return await get_contract_abi(
                address=address,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            result = await self._get(action='getabi', address=address)

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
        try:
            from aiochainscan import get_contract_source_code  # lazy

            return await get_contract_source_code(
                address=address,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            result = await self._get(action='getsourcecode', address=address)

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
        try:
            from aiochainscan import get_contract_creation  # lazy

            return await get_contract_creation(
                contract_addresses=list(addresses),
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
        except Exception:
            result = await self._get(
                action='getcontractcreation', contractaddresses=','.join(addresses)
            )
            return list(result)

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
        try:
            from aiochainscan import verify_contract_source_code as verify  # lazy

            result = await verify(
                contract_address=contract_address,
                source_code=source_code,
                contract_name=contract_name,
                compiler_version=compiler_version,
                optimization_used=optimization_used,
                runs=runs,
                constructor_arguements=constructor_arguements or '',
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
            return str(result)
        except Exception:
            result = await self._post(
                headers=None,
                module='contract',
                action='verifysourcecode',
                contractaddress=contract_address,
                sourceCode=source_code,
                contractname=contract_name,
                compilerversion=compiler_version,
                optimizationUsed=1 if optimization_used else 0,
                runs=runs,
                constructorArguements=constructor_arguements,
                **(self._parse_libraries(libraries or {})),
            )
            return str(result)

    async def check_verification_status(self, guid: str) -> str:
        """Check Source code verification submission status"""
        try:
            from aiochainscan import check_verification_status  # lazy

            result = await check_verification_status(
                guid=guid,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
            return str(result)
        except Exception:
            result = await self._get(action='checkverifystatus', guid=guid)
            return str(result)

    async def verify_proxy_contract(
        self, address: str, expected_implementation: str | None = None
    ) -> str:
        """Submits a proxy contract source code to Chainscan for verification."""
        try:
            from aiochainscan import verify_proxy_contract  # lazy

            result = await verify_proxy_contract(
                address=address,
                expected_implementation=expected_implementation,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
            return str(result)
        except Exception:
            result = await self._post(
                headers=None,
                module='contract',
                action='verifyproxycontract',
                address=address,
                expectedimplementation=expected_implementation,
            )
            return str(result)

    async def check_proxy_contract_verification(self, guid: str) -> str:
        """Checking Proxy Contract Verification Submission Status"""
        try:
            from aiochainscan import check_proxy_contract_verification  # lazy

            result = await check_proxy_contract_verification(
                guid=guid,
                api_kind=self._client.api_kind,
                network=self._client.network,
                api_key=self._client.api_key,
            )
            return str(result)
        except Exception:
            result = await self._get(action='checkproxyverification', guid=guid)
            return str(result)

    @staticmethod
    def _parse_libraries(libraries: dict[str, str]) -> dict[str, str]:
        return dict(
            part
            for i, (name, address) in enumerate(libraries.items(), start=1)
            for part in ((f'libraryname{i}', name), (f'libraryaddress{i}', address))
        )
