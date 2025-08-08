from aiochainscan.adapters.aiohttp_client import AiohttpClient
from aiochainscan.client import Client  # noqa: F401
from aiochainscan.config import ChainScanConfig, ScannerConfig, config  # noqa: F401
from aiochainscan.domain.models import Address, BlockNumber, TxHash  # re-export domain VOs
from aiochainscan.services.account import get_address_balance  # facade use-case

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
]


async def get_balance(*, address: str, api_kind: str, network: str, api_key: str) -> int:
    """Fetch address balance using the default aiohttp adapter.

    Convenience facade for simple use without manual client wiring.
    """

    http = AiohttpClient()
    try:
        return await get_address_balance(
            address=Address(address),
            api_kind=api_kind,
            network=network,
            api_key=api_key,
            http=http,
        )
    finally:
        await http.aclose()
