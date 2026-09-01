"""
High-level SmartContract abstraction for automatic ABI fetching,
Proxy resolution, and decoded event/transaction iteration.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

from ..decode import canonical_abi_type, decode_log_data, decode_transaction_input
from ..exceptions import ChainscanClientError
from .method import Method


class ContractClient(Protocol):
    """Client capabilities required by :class:`SmartContract`."""

    async def call(self, method: Method, **params: Any) -> Any: ...

    def iter_transactions(
        self,
        address: str,
        abi: list[dict[str, Any]] | None = None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]: ...


class SmartContract:
    """
    High-level abstraction for smart contract interactions.

    Automatically handles:
    - ABI fetching from blockchain explorers
    - Proxy contract detection and resolution
    - Event log decoding and iteration
    - Transaction input decoding and iteration

    Example:
        ```python
        client = ChainscanClient.from_config('etherscan', 'ethereum')

        # Create contract instance (auto-fetches ABI, resolves proxies)
        contract = await client.get_contract("0xdac17f958d2ee523a2206206994597c13d831ec7")

        # Iterate through decoded Transfer events
        async for event in contract.iter_events(event_name="Transfer", limit=100):
            print(f"From: {event.args['from']}")
            print(f"To: {event.args['to']}")
            print(f"Value: {event.args['value']}")
        ```
    """

    def __init__(
        self,
        address: str,
        abi: list[dict[str, Any]],
        client: ContractClient,
        is_proxy: bool = False,
        implementation_address: str | None = None,
    ):
        """
        Initialize a SmartContract instance.

        Note: Prefer using `SmartContract.from_address()` for automatic setup.

        Args:
            address: Contract address
            abi: Contract ABI as list of dictionaries
            client: ChainscanClient instance for API calls
            is_proxy: Whether this contract is a proxy
            implementation_address: Implementation contract address (for proxies)
        """
        self.address = address.lower()
        self.abi = abi
        self.client = client
        self.is_proxy = is_proxy
        self.implementation_address = (
            implementation_address.lower() if implementation_address else None
        )

        # Build lookup maps for quick access
        self._function_map: dict[str, dict[str, Any]] = {}
        self._event_map: dict[str, dict[str, Any]] = {}
        self._event_signature_map: dict[str, dict[str, Any]] = {}  # topic hash -> event
        self._build_lookup_maps()

    def _build_lookup_maps(self) -> None:
        """Build internal lookup maps for functions and events."""
        from aiochainscan.crypto import keccak_hex

        for item in self.abi:
            item_type = item.get('type')

            if item_type == 'function':
                name = item.get('name', '')
                if name:
                    self._function_map[name] = item

            elif item_type == 'event':
                name = item.get('name', '')
                if name:
                    self._event_map[name] = item

                    # Also create topic hash mapping for non-anonymous logs.
                    if item.get('anonymous') is not True:
                        inputs = item.get('inputs', [])
                        input_types = ','.join(canonical_abi_type(param) for param in inputs)
                        signature_text = f'{name}({input_types})'
                        topic_hash = '0x' + keccak_hex(signature_text)
                        self._event_signature_map[topic_hash] = item

    @classmethod
    async def from_address(
        cls,
        address: str,
        client: ContractClient,
    ) -> SmartContract:
        """
        Create a SmartContract instance by fetching ABI and resolving proxies.

        This method:
        1. Fetches contract source code metadata
        2. Detects if it's a proxy contract
        3. If proxy, fetches the implementation contract's ABI
        4. Returns fully initialized SmartContract instance

        Args:
            address: Contract address
            client: ChainscanClient instance

        Returns:
            SmartContract instance with ABI loaded and proxies resolved

        Raises:
            ValueError: If contract source/ABI cannot be fetched

        Example:
            ```python
            # USDT is a proxy contract - this automatically resolves it
            usdt = await SmartContract.from_address(
                "0xdac17f958d2ee523a2206206994597c13d831ec7",
                client
            )
            print(f"Is proxy: {usdt.is_proxy}")
            print(f"Implementation: {usdt.implementation_address}")
            ```
        """
        address = address.lower()

        # Fetch contract source to check for proxy
        is_proxy = False
        implementation_address = None

        try:
            source_data = await client.call(Method.CONTRACT_SOURCE, address=address)

            # Check if it's a proxy (Etherscan/BlockScout format)
            if isinstance(source_data, list) and len(source_data) > 0:
                contract_info = source_data[0]
            elif isinstance(source_data, dict):
                contract_info = source_data
            else:
                contract_info = {}

            # Check proxy flag
            proxy_flag = contract_info.get('Proxy', '0')
            is_proxy = proxy_flag == '1' or str(proxy_flag).lower() == 'true'

            if is_proxy:
                # Extract implementation address
                implementation_address = contract_info.get('Implementation', '')
                if implementation_address:
                    implementation_address = implementation_address.lower()

        except ChainscanClientError:
            # If CONTRACT_SOURCE fails, continue with regular ABI fetch
            pass

        # Fetch ABI (from implementation if proxy, otherwise from contract itself)
        abi_address = implementation_address if implementation_address else address

        try:
            abi_json = await client.call(Method.CONTRACT_ABI, address=abi_address)
            abi = json.loads(abi_json) if isinstance(abi_json, str) else abi_json

            if not isinstance(abi, list):
                raise ValueError(f'Invalid ABI format for contract {abi_address}')

        except Exception as e:  # noqa: BLE001 - Wrap API errors with context
            raise ValueError(f'Failed to fetch ABI for contract {abi_address}: {e}') from e

        return cls(
            address=address,
            abi=abi,
            client=client,
            is_proxy=is_proxy,
            implementation_address=implementation_address,
        )

    def get_event_abi(self, event_name: str) -> dict[str, Any] | None:
        """
        Get ABI definition for a specific event.

        Args:
            event_name: Name of the event (e.g., "Transfer", "Approval")

        Returns:
            Event ABI dictionary or None if not found

        Example:
            ```python
            transfer_abi = contract.get_event_abi("Transfer")
            print(transfer_abi['inputs'])
            ```
        """
        return self._event_map.get(event_name)

    def get_function_abi(self, function_name: str) -> dict[str, Any] | None:
        """
        Get ABI definition for a specific function.

        Args:
            function_name: Name of the function (e.g., "transfer", "balanceOf")

        Returns:
            Function ABI dictionary or None if not found

        Example:
            ```python
            transfer_abi = contract.get_function_abi("transfer")
            print(transfer_abi['inputs'])
            ```
        """
        return self._function_map.get(function_name)

    async def iter_events(
        self,
        event_name: str | None = None,
        from_block: int = 0,
        to_block: int | str = 'latest',
        limit: int | None = None,
    ) -> AsyncIterator[DecodedEvent]:
        """
        Iterate through decoded event logs from this contract.

        Fetches event logs and yields them one by one with decoded arguments.
        Memory-efficient for processing large numbers of events.

        Args:
            event_name: Filter by event name (e.g., "Transfer"). If None, returns all events.
            from_block: Starting block number (default: 0)
            to_block: Ending block number or 'latest' (default: 'latest')
            limit: Maximum number of events to yield (None for unlimited)

        Yields:
            DecodedEvent instances with event name, args, and metadata

        Example:
            ```python
            # Get Transfer events
            async for event in contract.iter_events("Transfer", limit=1000):
                print(f"{event.args['from']} -> {event.args['to']}: {event.args['value']}")
                print(f"Block: {event.block_number}, Tx: {event.tx_hash}")

            # Get all events
            async for event in contract.iter_events():
                print(f"Event: {event.name}")
            ```
        """
        # Build params for EVENT_LOGS method
        params: dict[str, Any] = {
            'address': self.address,
            'fromBlock': from_block,
            'toBlock': to_block,
        }

        # Add event topic filter if specified
        if event_name:
            event_abi = self.get_event_abi(event_name)
            if not event_abi:
                raise ValueError(f"Event '{event_name}' not found in contract ABI")

            # Generate topic0 (event signature hash)
            from aiochainscan.crypto import keccak_hex

            inputs = event_abi.get('inputs', [])
            input_types = ','.join(canonical_abi_type(param) for param in inputs)
            signature_text = f'{event_name}({input_types})'
            topic0 = '0x' + keccak_hex(signature_text)
            params['topic0'] = topic0

        # Fetch logs
        try:
            logs = await self.client.call(Method.EVENT_LOGS, **params)
        except Exception as e:
            raise ValueError(f'Failed to fetch event logs: {e}') from e

        if not isinstance(logs, list):
            logs = []

        decoded_logs = await asyncio.to_thread(
            lambda: [decode_log_data(log, self.abi) for log in logs]
        )

        # Decode and yield events
        count = 0
        for log, decoded_log in zip(logs, decoded_logs, strict=False):
            if limit is not None and count >= limit:
                break

            # Only yield if successfully decoded
            if 'decoded_data' in decoded_log:
                decoded_data = decoded_log['decoded_data']
                event = DecodedEvent(
                    name=decoded_data.get('event', ''),
                    args={k: v for k, v in decoded_data.items() if k != 'event'},
                    address=log.get('address', ''),
                    block_number=int(log.get('blockNumber', 0), 16)
                    if isinstance(log.get('blockNumber'), str)
                    and log.get('blockNumber', '').startswith('0x')
                    else int(log.get('blockNumber', 0)),
                    tx_hash=log.get('transactionHash', ''),
                    log_index=int(log.get('logIndex', 0), 16)
                    if isinstance(log.get('logIndex'), str)
                    and log.get('logIndex', '').startswith('0x')
                    else int(log.get('logIndex', 0)),
                    raw_log=log,
                )
                yield event
                count += 1

    async def iter_transactions(
        self,
        from_block: int = 0,
        to_block: int | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[DecodedTransaction]:
        """
        Iterate through decoded transactions to this contract.

        Fetches transactions where this contract is the recipient (to_address),
        decodes the function call input, and yields them one by one.

        Args:
            from_block: Starting block number (default: 0)
            to_block: Ending block number (None for latest)
            limit: Maximum number of transactions to yield (None for unlimited)

        Yields:
            DecodedTransaction instances with function name, args, and metadata

        Example:
            ```python
            # Get all transactions to the contract
            async for tx in contract.iter_transactions(limit=100):
                print(f"Function: {tx.function_name}")
                print(f"Args: {tx.args}")
                print(f"From: {tx.from_address}, Value: {tx.value_wei}")
            ```
        """
        # Fetch transactions using the client's iter_transactions
        # Note: This gets all transactions for the address, we'll filter to contract interactions
        count = 0

        # Try to use client's streaming API if it's a real method (not just a Mock attribute)
        has_iter = hasattr(self.client, 'iter_transactions')
        is_callable = callable(getattr(self.client, 'iter_transactions', None))

        if has_iter and is_callable:
            async for tx in self.client.iter_transactions(self.address):
                if limit is not None and count >= limit:
                    break

                # Filter: only include transactions TO this contract
                to_address = tx.get('to', '').lower()
                if to_address != self.address:
                    continue

                # Check block range
                block_num = tx.get('blockNumber')
                if block_num:
                    if isinstance(block_num, str):
                        block_num = int(block_num)
                    if block_num < from_block:
                        continue
                    if to_block is not None and block_num > to_block:
                        break

                # Decode transaction input
                decoded_tx = decode_transaction_input(tx, self.abi)

                # Only yield if successfully decoded
                if decoded_tx.get('decoded_func'):
                    yield DecodedTransaction(
                        function_name=decoded_tx['decoded_func'],
                        args=decoded_tx.get('decoded_data', {}),
                        tx_hash=tx.get('hash', ''),
                        from_address=tx.get('from', ''),
                        to_address=tx.get('to', ''),
                        value_wei=int(tx.get('value', 0)) if tx.get('value') else 0,
                        block_number=block_num
                        if isinstance(block_num, int)
                        else int(block_num)
                        if block_num
                        else 0,
                        gas=int(tx.get('gas', 0)) if tx.get('gas') else 0,
                        gas_price_wei=int(tx.get('gasPrice', 0)) if tx.get('gasPrice') else 0,
                        raw_transaction=tx,
                    )
                    count += 1
        else:
            # Fallback: use get_transactions method
            params: dict[str, Any] = {'address': self.address}
            if from_block > 0:
                params['start_block'] = from_block
            if to_block is not None:
                params['end_block'] = to_block

            txs = await self.client.call(Method.ACCOUNT_TRANSACTIONS, **params)

            if not isinstance(txs, list):
                txs = []

            for tx in txs:
                if limit is not None and count >= limit:
                    break

                # Filter: only include transactions TO this contract
                to_address = tx.get('to', '').lower()
                if to_address != self.address:
                    continue

                # Decode transaction input
                decoded_tx = decode_transaction_input(tx, self.abi)

                # Only yield if successfully decoded
                if decoded_tx.get('decoded_func'):
                    block_num = tx.get('blockNumber', 0)
                    if isinstance(block_num, str):
                        block_num = int(block_num)

                    yield DecodedTransaction(
                        function_name=decoded_tx['decoded_func'],
                        args=decoded_tx.get('decoded_data', {}),
                        tx_hash=tx.get('hash', ''),
                        from_address=tx.get('from', ''),
                        to_address=tx.get('to', ''),
                        value_wei=int(tx.get('value', 0)) if tx.get('value') else 0,
                        block_number=block_num,
                        gas=int(tx.get('gas', 0)) if tx.get('gas') else 0,
                        gas_price_wei=int(tx.get('gasPrice', 0)) if tx.get('gasPrice') else 0,
                        raw_transaction=tx,
                    )
                    count += 1

    def __repr__(self) -> str:
        """String representation of the contract."""
        if self.is_proxy and self.implementation_address:
            return f'SmartContract(address={self.address}, proxy={self.is_proxy}, implementation={self.implementation_address})'
        return f'SmartContract(address={self.address})'


class DecodedEvent:
    """
    Represents a decoded event log with all relevant information.

    Attributes:
        name: Event name (e.g., "Transfer")
        args: Dictionary of decoded event arguments
        address: Contract address that emitted the event
        block_number: Block number where event was emitted
        tx_hash: Transaction hash
        log_index: Index of this log in the transaction
        raw_log: Original raw log data
    """

    def __init__(
        self,
        name: str,
        args: dict[str, Any],
        address: str,
        block_number: int,
        tx_hash: str,
        log_index: int,
        raw_log: dict[str, Any],
    ):
        self.name = name
        self.args = args
        self.address = address
        self.block_number = block_number
        self.tx_hash = tx_hash
        self.log_index = log_index
        self.raw_log = raw_log

    def __repr__(self) -> str:
        return f'DecodedEvent(name={self.name}, args={self.args}, block={self.block_number})'


class DecodedTransaction:
    """
    Represents a decoded transaction with all relevant information.

    Attributes:
        function_name: Called function name (e.g., "transfer")
        args: Dictionary of decoded function arguments
        tx_hash: Transaction hash
        from_address: Sender address
        to_address: Recipient address (contract)
        value_wei: ETH value sent (in Wei)
        block_number: Block number
        gas: Gas limit
        gas_price_wei: Gas price (in Wei)
        raw_transaction: Original raw transaction data
    """

    def __init__(
        self,
        function_name: str,
        args: dict[str, Any],
        tx_hash: str,
        from_address: str,
        to_address: str,
        value_wei: int,
        block_number: int,
        gas: int,
        gas_price_wei: int,
        raw_transaction: dict[str, Any],
    ):
        self.function_name = function_name
        self.args = args
        self.tx_hash = tx_hash
        self.from_address = from_address
        self.to_address = to_address
        self.value_wei = value_wei
        self.block_number = block_number
        self.gas = gas
        self.gas_price_wei = gas_price_wei
        self.raw_transaction = raw_transaction

    def __repr__(self) -> str:
        return f'DecodedTransaction(function={self.function_name}, args={self.args}, block={self.block_number})'
