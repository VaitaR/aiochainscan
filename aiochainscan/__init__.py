from typing import Any

from aiochainscan.adapters.aiohttp_client import AiohttpClient
from aiochainscan.adapters.endpoint_builder_urlbuilder import UrlBuilderEndpoint
from aiochainscan.client import Client  # noqa: F401
from aiochainscan.config import ChainScanConfig, ScannerConfig, config  # noqa: F401
from aiochainscan.domain.models import Address, BlockNumber, TxHash  # re-export domain VOs
from aiochainscan.services.account import get_address_balance  # facade use-case
from aiochainscan.services.block import get_block_by_number  # facade use-case
from aiochainscan.services.token import get_token_balance  # facade use-case
from aiochainscan.services.transaction import get_transaction_by_hash  # facade use-case

__all__ = [
    'Client',
    'ChainScanConfig',
    'ScannerConfig',
    'config',
    # Domain VOs
    'Address',
    'BlockNumber',
    'TxHash',
    # Services (facade)
    'get_address_balance',
    'get_block_by_number',
    'get_transaction_by_hash',
    'get_token_balance',
]


async def get_balance(*, address: str, api_kind: str, network: str, api_key: str) -> int:
    """Fetch address balance using the default aiohttp adapter.

    Convenience facade for simple use without manual client wiring.
    """

    http = AiohttpClient()
    endpoint = UrlBuilderEndpoint()
    try:
        return await get_address_balance(
            address=Address(address),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
    finally:
        await http.aclose()


async def get_block(
    *, tag: int | str, full: bool, api_kind: str, network: str, api_key: str
) -> dict[str, Any]:
    """Fetch block by number via default adapter."""

    http = AiohttpClient()
    endpoint = UrlBuilderEndpoint()
    try:
        return await get_block_by_number(
            tag=tag,
            full=full,
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
    finally:
        await http.aclose()


async def get_transaction(
    *, txhash: str, api_kind: str, network: str, api_key: str
) -> dict[str, Any]:
    """Fetch transaction by hash via default adapter."""

    http = AiohttpClient()
    endpoint = UrlBuilderEndpoint()
    try:
        return await get_transaction_by_hash(
            txhash=TxHash(txhash),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
    finally:
        await http.aclose()


async def get_token_balance_facade(
    *, holder: str, token_contract: str, api_kind: str, network: str, api_key: str
) -> int:
    """Fetch ERC-20 token balance via default adapter."""

    http = AiohttpClient()
    endpoint = UrlBuilderEndpoint()
    try:
        return await get_token_balance(
            holder=Address(holder),
            token_contract=Address(token_contract),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
            _endpoint_builder=endpoint,
        )
    finally:
        await http.aclose()
