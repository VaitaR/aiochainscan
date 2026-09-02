"""Contract-domain API mixin for ``ChainscanClient``."""

from __future__ import annotations

import json
from typing import Any, Protocol, cast

from ...domain.contract import SmartContract
from ...domain.method import Method
from ...domain.models import Address
from ...exceptions import ChainscanClientApiError, ChainscanRateLimitError
from ..types import JSONDict, JSONList
from ._waiting import api_error_text, poll_until_final


class _ContractClientProtocol(Protocol):
    async def call(self, method: Method, **params: Any) -> Any: ...


class ContractMixin:
    """Contract-focused typed convenience methods."""

    async def get_contract_abi(self: _ContractClientProtocol, address: str) -> str:
        """Get contract ABI as JSON string."""
        result: Any = await self.call(Method.CONTRACT_ABI, address=str(Address(address)))
        return result if isinstance(result, str) else json.dumps(result)

    async def get_contract_source(self: _ContractClientProtocol, address: str) -> JSONDict:
        """Get verified contract source code."""
        result: Any = await self.call(Method.CONTRACT_SOURCE, address=str(Address(address)))
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return next((item for item in result if isinstance(item, dict)), {})
        return {}

    async def get_contract_creation(
        self: _ContractClientProtocol, addresses: list[str]
    ) -> JSONList:
        """Get contract creator and creation tx hash."""
        result: Any = await self.call(
            Method.CONTRACT_CREATION,
            contract_addresses=','.join(str(Address(address)) for address in addresses),
        )
        return result if isinstance(result, list) else []

    async def get_contract(self: _ContractClientProtocol, address: str) -> SmartContract:
        """Get a SmartContract instance with automatic ABI fetching."""
        return await SmartContract.from_address(address, cast(Any, self))

    async def wait_for_verification(
        self: _ContractClientProtocol,
        guid: str,
        timeout: float = 300.0,
        poll_interval: float = 10.0,
    ) -> str:
        """Wait for a contract-verification submission to reach a verdict.

        Polls the verification-status endpoint (``Method.CONTRACT_VERIFY_STATUS``,
        fed with the GUID returned by ``Method.CONTRACT_VERIFY``) until
        Etherscan-like explorers report a terminal verdict: any result
        starting with ``Pass`` (e.g. ``'Pass - Verified'``) or ``Fail``
        (e.g. ``'Fail - Unable to verify'``). A queued submission
        (``'Pending in queue'``, delivered as an API-error envelope) keeps
        the poll going; a ``Fail`` verdict is RETURNED, not raised — the
        caller decides how to react. Hard API errors (e.g. ``Unknown UID``
        for a malformed GUID) propagate immediately.

        Args:
            guid: Verification GUID returned by the verify submission call.
            timeout: Total wait budget in seconds (default: 300).
            poll_interval: Delay between polls in seconds (default: 10).

        Returns:
            Final verdict string, e.g. ``'Pass - Verified'`` or
            ``'Fail - Unable to verify'``.

        Raises:
            ValueError: If ``guid`` is empty or the timing arguments are
                negative.
            ChainscanClientApiError: On hard verification-status errors
                (malformed/unknown GUID).
            ChainscanWaitTimeoutError: If the submission is still queued or
                processing after ``timeout`` seconds.
        """
        if not guid:
            raise ValueError('guid must be a non-empty string')

        async def probe() -> tuple[bool, Any]:
            try:
                result: Any = await self.call(Method.CONTRACT_VERIFY_STATUS, guid=guid)
            except ChainscanClientApiError as exc:
                verdict = api_error_text(exc)
                if 'pending' in verdict or 'queue' in verdict:
                    return False, exc
                raise
            except ChainscanRateLimitError as exc:
                return False, exc
            if isinstance(result, str):
                normalized = result.strip().lower()
                if normalized.startswith('pass') or normalized.startswith('fail'):
                    return True, result
            return False, result

        outcome = await poll_until_final(
            probe,
            what=f'verification {guid} to reach a verdict',
            timeout=timeout,
            poll_interval=poll_interval,
        )
        return cast(str, outcome)
