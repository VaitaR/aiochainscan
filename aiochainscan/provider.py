"""
Provider factory for creating blockchain scanner clients.

This module provides a clean, user-friendly API for creating scanner clients
using the provider-first approach: select provider, then chain.
"""

from __future__ import annotations

from asyncio import AbstractEventLoop
from contextlib import AbstractAsyncContextManager
from typing import Any

from aiohttp import ClientTimeout
from aiohttp_retry import RetryOptionsBase

from .chains import Chain, ChainInfo, get_env_api_key, list_chains, resolve_chain
from .core.client import ChainscanClient


class ChainProvider:
    """
    Factory for creating blockchain scanner clients by provider.

    This is the main entry point for users. It provides static methods
    for each supported provider (etherscan, blockscout, moralis) that
    create configured client instances.

    Examples:
        >>> # By chain ID (most explicit)
        >>> client = ChainProvider.etherscan(chain_id=1)

        >>> # By chain name
        >>> client = ChainProvider.etherscan(chain='ethereum')

        >>> # By Chain enum
        >>> client = ChainProvider.etherscan(chain=Chain.ETHEREUM)

        >>> # Different providers
        >>> client = ChainProvider.blockscout(chain_id=1)
        >>> client = ChainProvider.moralis(chain='bsc')

        >>> # With explicit API key
        >>> client = ChainProvider.etherscan(chain_id=1, api_key='YOUR_KEY')
    """

    @staticmethod
    def etherscan(
        chain: int | str | Chain | None = None,
        chain_id: int | None = None,
        api_key: str | None = None,
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager[Any] | None = None,
        retry_options: RetryOptionsBase | None = None,
    ) -> ChainscanClient:
        """
        Create Etherscan API client for any supported EVM chain.

        Supports Etherscan V2 API which provides unified access to 50+ chains
        with a single API key.

        Args:
            chain: Chain identifier (name, alias, or Chain enum)
            chain_id: Chain ID (alternative to chain parameter)
            api_key: Etherscan API key (or reads ETHERSCAN_KEY from env)
            loop: Event loop instance
            timeout: Request timeout configuration
            proxy: Proxy URL
            throttler: Rate limiting throttler
            retry_options: Retry configuration

        Returns:
            Configured ChainscanClient for Etherscan

        Raises:
            ValueError: If chain is not supported or API key is missing

        Examples:
            >>> client = ChainProvider.etherscan(chain_id=1)
            >>> client = ChainProvider.etherscan(chain='ethereum')
            >>> client = ChainProvider.etherscan(chain=Chain.BSC, api_key='KEY')
        """
        chain_info = _resolve_chain_param(chain, chain_id, default=Chain.ETHEREUM)

        # Validate Etherscan support
        if not chain_info.etherscan_api_kind:
            raise ValueError(
                f"Chain '{chain_info.display_name}' (ID: {chain_info.chain_id}) "
                f'is not supported by Etherscan. '
                f'Try blockscout() or moralis() instead.'
            )

        # Get API key
        resolved_api_key = api_key or get_env_api_key('etherscan')
        if not resolved_api_key:
            raise ValueError(
                'Etherscan API key required. Set ETHERSCAN_KEY environment variable '
                'or pass api_key parameter. Get your key at: https://etherscan.io/apis'
            )

        return ChainscanClient(
            scanner_name='etherscan',
            scanner_version='v2',
            chain_info=chain_info,
            api_key=resolved_api_key,
            loop=loop,
            timeout=timeout,
            proxy=proxy,
            throttler=throttler,
            retry_options=retry_options,
        )

    @staticmethod
    def blockscout(
        chain: int | str | Chain | None = None,
        chain_id: int | None = None,
        api_key: str | None = None,
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager[Any] | None = None,
        retry_options: RetryOptionsBase | None = None,
    ) -> ChainscanClient:
        """
        Create BlockScout API client.

        BlockScout provides free public APIs for various chains.
        No API key required for most instances.

        Args:
            chain: Chain identifier (name, alias, or Chain enum)
            chain_id: Chain ID (alternative to chain parameter)
            api_key: Optional API key (most BlockScout instances don't require it)
            loop: Event loop instance
            timeout: Request timeout configuration
            proxy: Proxy URL
            throttler: Rate limiting throttler
            retry_options: Retry configuration

        Returns:
            Configured ChainscanClient for BlockScout

        Raises:
            ValueError: If chain is not supported by BlockScout

        Examples:
            >>> client = ChainProvider.blockscout(chain_id=1)  # Ethereum
            >>> client = ChainProvider.blockscout(chain='sepolia')
            >>> client = ChainProvider.blockscout(chain=Chain.GNOSIS)
        """
        chain_info = _resolve_chain_param(chain, chain_id, default=Chain.ETHEREUM)

        # Validate BlockScout support
        if not chain_info.blockscout_instance:
            available = [c.name for c in list_chains(provider='blockscout')]
            raise ValueError(
                f"Chain '{chain_info.display_name}' (ID: {chain_info.chain_id}) "
                f'does not have a BlockScout instance. '
                f'Available chains: {", ".join(available)}'
            )

        return ChainscanClient(
            scanner_name='blockscout',
            scanner_version='v1',
            chain_info=chain_info,
            api_key=api_key or '',
            loop=loop,
            timeout=timeout,
            proxy=proxy,
            throttler=throttler,
            retry_options=retry_options,
        )

    @staticmethod
    def moralis(
        chain: int | str | Chain | None = None,
        chain_id: int | None = None,
        api_key: str | None = None,
        loop: AbstractEventLoop | None = None,
        timeout: ClientTimeout | None = None,
        proxy: str | None = None,
        throttler: AbstractAsyncContextManager[Any] | None = None,
        retry_options: RetryOptionsBase | None = None,
    ) -> ChainscanClient:
        """
        Create Moralis Web3 Data API client.

        Moralis provides rich blockchain data with modern RESTful endpoints.
        Requires API key.

        Args:
            chain: Chain identifier (name, alias, or Chain enum)
            chain_id: Chain ID (alternative to chain parameter)
            api_key: Moralis API key (or reads MORALIS_API_KEY from env)
            loop: Event loop instance
            timeout: Request timeout configuration
            proxy: Proxy URL
            throttler: Rate limiting throttler
            retry_options: Retry configuration

        Returns:
            Configured ChainscanClient for Moralis

        Raises:
            ValueError: If chain is not supported or API key is missing

        Examples:
            >>> client = ChainProvider.moralis(chain_id=1, api_key='KEY')
            >>> client = ChainProvider.moralis(chain='polygon')
            >>> client = ChainProvider.moralis(chain=Chain.AVALANCHE)
        """
        chain_info = _resolve_chain_param(chain, chain_id, default=Chain.ETHEREUM)

        # Validate Moralis support
        if not chain_info.moralis_chain_id:
            available = [c.name for c in list_chains(provider='moralis')]
            raise ValueError(
                f"Chain '{chain_info.display_name}' (ID: {chain_info.chain_id}) "
                f'is not supported by Moralis. '
                f'Available chains: {", ".join(available)}'
            )

        # Get API key
        resolved_api_key = api_key or get_env_api_key('moralis')
        if not resolved_api_key:
            raise ValueError(
                'Moralis API key required. Set MORALIS_API_KEY environment variable '
                'or pass api_key parameter. Get your key at: https://moralis.io'
            )

        return ChainscanClient(
            scanner_name='moralis',
            scanner_version='v1',
            chain_info=chain_info,
            api_key=resolved_api_key,
            loop=loop,
            timeout=timeout,
            proxy=proxy,
            throttler=throttler,
            retry_options=retry_options,
        )

    @staticmethod
    def list_providers() -> list[str]:
        """
        Get list of available provider names.

        Returns:
            List of provider names that can be used

        Example:
            >>> ChainProvider.list_providers()
            ['etherscan', 'blockscout', 'moralis']
        """
        return ['etherscan', 'blockscout', 'moralis']

    @staticmethod
    def list_chains(provider: str | None = None, testnet: bool | None = None) -> list[ChainInfo]:
        """
        List all supported chains, optionally filtered.

        Args:
            provider: Filter by provider ('etherscan', 'blockscout', 'moralis')
            testnet: Filter by testnet status (True=testnets, False=mainnets, None=all)

        Returns:
            List of ChainInfo objects

        Examples:
            >>> ChainProvider.list_chains()  # All chains
            >>> ChainProvider.list_chains(provider='blockscout')  # BlockScout only
            >>> ChainProvider.list_chains(testnet=False)  # Mainnets only
        """
        return list_chains(provider=provider, testnet=testnet)

    @staticmethod
    def get_chain_info(chain: int | str | Chain) -> ChainInfo:
        """
        Get detailed information about a specific chain.

        Args:
            chain: Chain identifier (ID, name, alias, or enum)

        Returns:
            ChainInfo object with all chain metadata

        Examples:
            >>> info = ChainProvider.get_chain_info(1)
            >>> info = ChainProvider.get_chain_info('ethereum')
            >>> info = ChainProvider.get_chain_info(Chain.BSC)
        """
        return resolve_chain(chain)


def _resolve_chain_param(
    chain: int | str | Chain | None,
    chain_id: int | None,
    default: Chain,
) -> ChainInfo:
    """
    Internal helper to resolve chain parameter with fallback to default.

    Args:
        chain: Chain parameter from user
        chain_id: Chain ID parameter from user
        default: Default chain if neither is provided

    Returns:
        Resolved ChainInfo

    Raises:
        ValueError: If both chain and chain_id are provided
    """
    if chain is not None and chain_id is not None:
        raise ValueError('Cannot specify both chain and chain_id parameters')

    identifier: int | str | Chain
    if chain_id is not None:
        identifier = chain_id
    elif chain is not None:
        identifier = chain
    else:
        identifier = default

    return resolve_chain(identifier)


__all__ = ['ChainProvider']
