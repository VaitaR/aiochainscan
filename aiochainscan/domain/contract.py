"""
High-level SmartContract abstraction for automatic ABI fetching,
Proxy resolution, and decoded event/transaction iteration.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Literal, NamedTuple, Protocol

from ..decode import canonical_abi_type, decode_log_data, decode_transaction_input
from ..domain.method import Method
from ..exceptions import ChainscanClientError
from .normalize import (
    BLOCK_NUMBER_KEYS,
    GAS_KEYS,
    GAS_PRICE_KEYS,
    LOG_INDEX_KEYS,
    LOG_TRANSACTION_HASH_KEYS,
    TRANSACTION_HASH_KEYS,
    first_field,
    flat_address,
    int_or_default,
)


def _dict_field(value: Any) -> dict[str, Any]:
    """Return decoded arguments when the client supplied a mapping."""
    return value if isinstance(value, dict) else {}


class ContractClient(Protocol):
    """Client capabilities required by :class:`SmartContract`."""

    async def call(self, method: Method, **params: Any) -> Any: ...

    def iter_logs(
        self,
        address: str,
        abi: list[dict[str, Any]] | None = None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
        topics: list[str] | None = None,
        topic_operators: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]: ...

    def iter_transactions(
        self,
        address: str,
        abi: list[dict[str, Any]] | None = None,
        from_block: int = 0,
        to_block: int | str | None = 'latest',
        batch_size: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]: ...


# Two explorer dialects describe the same fact under different names, and a
# reader that knows only one reports every proxy on the other as a plain
# contract. Etherscan v2: Proxy='1'/'0' + Implementation. BlockScout:
# IsProxy='true' + ImplementationAddress, plus ImplementationAddresses, which
# lists EVERY implementation (a diamond's facets, EIP-2535).
_PROXY_FLAG_KEYS = ('Proxy', 'IsProxy')
_IMPLEMENTATION_KEYS = ('ImplementationAddresses', 'Implementation', 'ImplementationAddress')
_ZERO_ADDRESS = '0x' + '0' * 40

# Four standards put the implementation address in four different slots, and
# no single one of them is enough: USDC holds ZERO at the EIP-1967 slot and
# keeps its implementation in the legacy zeppelinos slot (measured
# 2026-09-15), while stkAAVE and etherfi answer at EIP-1967. Read in this
# order, first non-zero wins.
_EIP1967_IMPLEMENTATION_SLOT = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
_EIP1822_PROXIABLE_SLOT = '0xc5f16f0fcc639fa48a6947836d9850f504798523bf8c9a3a87d5876cf622bcf7'
_ZEPPELINOS_IMPLEMENTATION_SLOT = (
    '0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3'
)
_EIP1967_BEACON_SLOT = '0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50'

#: ``(slot, holds_a_beacon)`` — a beacon slot names a contract that must then
#: be asked for the implementation, one extra call.
_IMPLEMENTATION_SLOTS: tuple[tuple[str, bool], ...] = (
    (_EIP1967_IMPLEMENTATION_SLOT, False),
    (_EIP1822_PROXIABLE_SLOT, False),
    (_ZEPPELINOS_IMPLEMENTATION_SLOT, False),
    (_EIP1967_BEACON_SLOT, True),
)

_BEACON_IMPLEMENTATION_SELECTOR = '0x5c60da1b'  # implementation()
_FACETS_SELECTOR = '0x7a0ed627'  # facets() — the EIP-2535 diamond loupe
_FACETS_OUTPUTS: list[dict[str, Any]] = [
    {
        'name': 'facets_',
        'type': 'tuple[]',
        'components': [
            {'name': 'facetAddress', 'type': 'address'},
            {'name': 'functionSelectors', 'type': 'bytes4[]'},
        ],
    }
]

#: How hard to look. ``'metadata'`` asks the explorer only (no extra request,
#: blind to an unflagged proxy). ``'chain'`` reads the storage slots and the
#: diamond loupe only (works where the explorer flags nothing). ``'auto'``
#: asks the explorer first and falls through to the chain when the answer is
#: "not a proxy" or names at most one implementation — the two cases that can
#: be wrong — at a cost of up to five extra requests.
ProxyStrategy = Literal['metadata', 'chain', 'auto']


class ProxyMetadata(NamedTuple):
    """What is known about a proxy at one address, and who said so."""

    is_proxy: bool
    implementations: tuple[str, ...]
    source: str = 'none'

    @property
    def implementation(self) -> str | None:
        """The single implementation, or the first facet of a diamond."""
        return self.implementations[0] if self.implementations else None

    @property
    def is_diamond(self) -> bool:
        """Several implementations behind one address (EIP-2535)."""
        return len(self.implementations) > 1


_NOT_A_PROXY = ProxyMetadata(False, (), 'none')


def _implementation_addresses(contract_info: dict[str, Any]) -> tuple[str, ...]:
    """Lowercased, de-duplicated implementations across both explorer dialects."""
    found: list[str] = []
    for key in _IMPLEMENTATION_KEYS:
        value = contract_info.get(key)
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if not isinstance(candidate, str) or not candidate:
                continue
            normalized = candidate.lower()
            if normalized == _ZERO_ADDRESS or normalized in found:
                continue
            found.append(normalized)
    return tuple(found)


def _address_from_word(word: Any) -> str | None:
    """Read an address out of a 32-byte word, or ``None`` if it holds no address.

    A slot that is zero, unreadable, or whose upper 12 bytes are set holds
    something other than an implementation pointer — guessing at it would
    invent an address.
    """
    if not isinstance(word, str):
        return None
    digits = word[2:] if word.lower().startswith('0x') else word
    if not digits or len(digits) > 64:
        return None
    try:
        value = int(digits, 16)
    except ValueError:
        return None
    if value == 0 or value >= 1 << 160:
        return None
    return f'0x{value:040x}'


async def _quiet_call(client: ContractClient, method: Method, **params: Any) -> Any:
    """Call ``method``, answering ``None`` for anything that is not an answer.

    Chain probing is best effort by construction: a revert, a throttled
    explorer or a scanner that never declared the method all mean "this
    source cannot tell us", never "this address is not a proxy".
    """
    try:
        return await client.call(method, **params)
    except (ChainscanClientError, ValueError):
        return None


async def _resolve_from_slots(address: str, client: ContractClient) -> str | None:
    """Walk the slot ladder; ``None`` when no standard slot holds an address."""
    for slot, holds_a_beacon in _IMPLEMENTATION_SLOTS:
        word = await _quiet_call(
            client, Method.PROXY_GET_STORAGE_AT, address=address, position=slot, tag='latest'
        )
        found = _address_from_word(word)
        if found is None:
            continue
        if not holds_a_beacon:
            return found
        beacon_answer = await _quiet_call(
            client,
            Method.PROXY_ETH_CALL,
            to=found,
            data=_BEACON_IMPLEMENTATION_SELECTOR,
            tag='latest',
        )
        return _address_from_word(beacon_answer)
    return None


async def _diamond_facets(address: str, client: ContractClient) -> tuple[str, ...]:
    """Ask the EIP-2535 loupe for every facet; ``()`` when this is no diamond.

    A contract without the loupe reverts, which is the detection: there is no
    cheaper signal, and the call only runs where the other sources already
    came up short.
    """
    from ..abi_pure import decode_arguments

    answer = await _quiet_call(
        client, Method.PROXY_ETH_CALL, to=address, data=_FACETS_SELECTOR, tag='latest'
    )
    if not isinstance(answer, str) or len(answer) <= 2:
        return ()
    try:
        decoded = decode_arguments(_FACETS_OUTPUTS, answer)
    except (ValueError, KeyError):
        return ()
    facets = decoded.get('facets_')
    if not isinstance(facets, list):
        return ()
    found: list[str] = []
    for facet in facets:
        candidate = facet.get('facetAddress') if isinstance(facet, dict) else None
        if not isinstance(candidate, str):
            continue
        normalized = candidate.lower()
        if normalized == _ZERO_ADDRESS or normalized in found:
            continue
        found.append(normalized)
    return tuple(found)


async def _resolve_from_metadata(address: str, client: ContractClient) -> ProxyMetadata:
    """The explorer's own answer, or a non-proxy when it cannot give one."""
    source_data = await _quiet_call(client, Method.CONTRACT_SOURCE, address=address)

    if isinstance(source_data, list) and len(source_data) > 0:
        contract_info = source_data[0]
    elif isinstance(source_data, dict):
        contract_info = source_data
    else:
        contract_info = {}

    flags = [contract_info.get(key) for key in _PROXY_FLAG_KEYS]
    is_proxy = any(flag in (1, True, '1') or str(flag).lower() == 'true' for flag in flags)
    if not is_proxy:
        return _NOT_A_PROXY

    return ProxyMetadata(True, _implementation_addresses(contract_info), 'metadata')


async def _resolve_from_chain(address: str, client: ContractClient) -> tuple[str, ...]:
    """Slots first (one hit ends it), then the loupe for a diamond."""
    from_slot = await _resolve_from_slots(address, client)
    if from_slot is not None:
        return (from_slot,)
    return await _diamond_facets(address, client)


async def resolve_proxy_metadata(
    address: str,
    client: ContractClient,
    *,
    strategy: ProxyStrategy = 'metadata',
) -> ProxyMetadata:
    """Find out whether ``address`` is a proxy and what it points at.

    ``strategy`` picks the sources — see :data:`ProxyStrategy`. The default
    stays explorer metadata so the request count of an ordinary resolution
    does not change; ``'auto'`` is the one-word opt-in that also sees proxies
    the explorer never flagged, and diamonds on an explorer that reports a
    single implementation.

    When both sources answer and disagree, the chain wins and ``source`` says
    ``'both'``: explorers cache the implementation and go stale after an
    upgrade, while the slot is the truth at ``latest``.

    Failure of any source is an absent answer, never an exception — an
    explorer that cannot answer must not stop the caller from fetching the
    address's own ABI.
    """
    metadata = _NOT_A_PROXY
    if strategy in ('metadata', 'auto'):
        metadata = await _resolve_from_metadata(address, client)
    if strategy == 'metadata' or metadata.is_diamond:
        return metadata

    from_chain = await _resolve_from_chain(address, client)
    if not from_chain:
        return metadata
    source = 'both' if metadata.is_proxy else 'chain'
    return ProxyMetadata(True, from_chain, source)


#: A merged diamond ABI keeps only what a caller decodes or calls through the
#: proxy address. Constructors, fallbacks and receives belong to the
#: individual facets and describe nothing about the diamond.
_MERGEABLE_ABI_TYPES = frozenset({'function', 'event', 'error'})


class ResolvedAbi(NamedTuple):
    """An ABI plus the addresses it was actually assembled from."""

    abi: list[dict[str, Any]]
    sources: tuple[str, ...]
    missing: tuple[str, ...]


def _abi_entry_key(entry: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    inputs = entry.get('inputs') or []
    types = tuple(canonical_abi_type(param) for param in inputs)
    return str(entry.get('type', 'function')), str(entry.get('name', '')), types


def merge_facet_abis(facet_abis: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Concatenate facet ABIs into the one a diamond behaves like.

    Sound because EIP-2535 gives each selector exactly one facet, so functions
    cannot collide; events and errors are shared boilerplate and are
    de-duplicated by signature.
    """
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()
    for facet_abi in facet_abis:
        for entry in facet_abi:
            if not isinstance(entry, dict) or entry.get('type') not in _MERGEABLE_ABI_TYPES:
                continue
            key = _abi_entry_key(entry)
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
    return merged


async def _fetch_abi(address: str, client: ContractClient) -> list[dict[str, Any]] | None:
    """One address's ABI, or ``None`` when the explorer has none for it."""
    try:
        abi_json = await client.call(Method.CONTRACT_ABI, address=address)
        abi = json.loads(abi_json) if isinstance(abi_json, str) else abi_json
    except Exception:  # noqa: BLE001 - every failure means "no ABI here"
        return None
    return abi if isinstance(abi, list) else None


async def fetch_resolved_abi(
    address: str,
    client: ContractClient,
    metadata: ProxyMetadata,
) -> ResolvedAbi:
    """The ABI that decodes traffic sent to ``address``.

    A diamond's is merged from every facet, and a facet whose ABI cannot be
    fetched is reported in ``missing`` rather than dropped — a partial ABI
    that does not say it is partial reads exactly like a complete one.

    Raises:
        ValueError: if no ABI could be fetched at all.
    """
    if not metadata.is_diamond:
        source = metadata.implementation or address
        abi = await _fetch_abi(source, client)
        if abi is None:
            raise ValueError(f'Failed to fetch ABI for contract {source}')
        return ResolvedAbi(abi, (source,), ())

    facet_abis: list[list[dict[str, Any]]] = []
    used: list[str] = []
    missing: list[str] = []
    for facet in metadata.implementations:
        facet_abi = await _fetch_abi(facet, client)
        if facet_abi is None:
            missing.append(facet)
            continue
        facet_abis.append(facet_abi)
        used.append(facet)
    if not facet_abis:
        raise ValueError(
            f'Failed to fetch an ABI for any facet of diamond {address}: '
            f'{", ".join(metadata.implementations)}'
        )
    return ResolvedAbi(merge_facet_abis(facet_abis), tuple(used), tuple(missing))


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
        facets: tuple[str, ...] = (),
        missing_facets: tuple[str, ...] = (),
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
            facets: Addresses this ABI was assembled from, for a diamond
                (EIP-2535); empty for an ordinary contract or proxy
            missing_facets: Facets whose ABI could not be fetched, so the ABI
                covers less than the diamond's whole selector table
        """
        self.address = address.lower()
        self.abi = abi
        self.client = client
        self.is_proxy = is_proxy
        self.implementation_address = (
            implementation_address.lower() if implementation_address else None
        )
        self.facets = facets
        self.missing_facets = missing_facets

        # Build lookup maps for quick access
        self._function_map: dict[str, dict[str, Any]] = {}
        self._event_map: dict[str, dict[str, Any]] = {}
        self._event_topic_map: dict[str, str] = {}  # event name -> topic hash
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

                    # Derive the topic0 hash exactly once, here; every other
                    # consumer (iter_events) reads the map below instead of
                    # recomputing the signature hash. Named anonymous events
                    # get a topic too — iter_events has always filtered on
                    # one for them — preserve that, do not "fix" it.
                    inputs = item.get('inputs', [])
                    input_types = ','.join(canonical_abi_type(param) for param in inputs)
                    signature_text = f'{name}({input_types})'
                    topic_hash = '0x' + keccak_hex(signature_text)
                    self._event_topic_map[name] = topic_hash

    @classmethod
    async def from_address(
        cls,
        address: str,
        client: ContractClient,
        *,
        proxy_strategy: ProxyStrategy = 'metadata',
    ) -> SmartContract:
        """
        Create a SmartContract instance by fetching ABI and resolving proxies.

        For a proxy the ABI loaded is the IMPLEMENTATION's — the proxy's own ABI
        declares none of the functions its traffic calls. For a diamond
        (EIP-2535) it is every facet's ABI merged, and ``facets`` says which
        addresses it came from.

        Resolution reads explorer metadata by default, so a proxy the explorer
        has not flagged still yields the proxy's ABI and ``is_proxy`` says so;
        ``proxy_strategy='auto'`` also reads the storage slots and the diamond
        loupe (see :func:`resolve_proxy_metadata`).

        Args:
            address: Contract address
            client: ChainscanClient instance
            proxy_strategy: Where to look for an implementation

        Returns:
            SmartContract instance with ABI loaded and proxies resolved

        Raises:
            ValueError: If contract source/ABI cannot be fetched

        Example:
            ```python
            # USDC is a proxy (FiatTokenProxy) - this resolves it
            usdc = await SmartContract.from_address(
                "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                client
            )
            print(f"Is proxy: {usdc.is_proxy}")                 # True
            print(f"Implementation: {usdc.implementation_address}")
            ```
        """
        address = address.lower()

        metadata = await resolve_proxy_metadata(address, client, strategy=proxy_strategy)
        resolved = await fetch_resolved_abi(address, client, metadata)

        return cls(
            address=address,
            abi=resolved.abi,
            client=client,
            is_proxy=metadata.is_proxy,
            implementation_address=metadata.implementation,
            facets=resolved.sources if metadata.is_diamond else (),
            missing_facets=resolved.missing,
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
        topics: list[str] | None = None
        if event_name:
            if not self.get_event_abi(event_name):
                raise ValueError(f"Event '{event_name}' not found in contract ABI")

            # Filter on the topic0 derived once when the lookup maps were built.
            topics = [self._event_topic_map[event_name]]

        # Traverse the client's paginated iterator. Passing the ABI lets the
        # client decode each page while retaining each original log mapping.
        count = 0
        async for log in self.client.iter_logs(
            self.address,
            abi=self.abi,
            from_block=from_block,
            to_block=to_block,
            batch_size=1000,
            topics=topics,
        ):
            if limit is not None and count >= limit:
                break

            decoded_data = log.get('decoded_data')
            if not isinstance(decoded_data, dict):
                # Structural clients may return raw logs even when they
                # expose the iterator. Do not fall back to a single page.
                decoded_data = (await asyncio.to_thread(decode_log_data, dict(log), self.abi)).get(
                    'decoded_data'
                )

            if isinstance(decoded_data, dict):
                decoded_event_name = decoded_data.get('event') or log.get('decoded_event', '')
                if event_name is not None and decoded_event_name != event_name:
                    continue
                event = DecodedEvent(
                    name=str(decoded_event_name),
                    args={k: v for k, v in decoded_data.items() if k != 'event'},
                    address=flat_address(log.get('address')) or '',
                    block_number=int_or_default(first_field(log, *BLOCK_NUMBER_KEYS), default=0),
                    tx_hash=first_field(log, *LOG_TRANSACTION_HASH_KEYS) or '',
                    log_index=int_or_default(first_field(log, *LOG_INDEX_KEYS), default=0),
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

        async for tx in self.client.iter_transactions(
            self.address,
            abi=self.abi,
            from_block=from_block,
            to_block=to_block,
            batch_size=1000,
        ):
            if limit is not None and count >= limit:
                break

            to_address = flat_address(first_field(tx, 'to', 'to_address')) or ''
            if to_address.lower() != self.address:
                continue

            block_num = int_or_default(first_field(tx, *BLOCK_NUMBER_KEYS), default=0)
            if block_num < from_block:
                continue
            if to_block is not None and block_num > to_block:
                continue

            decoded_tx = tx
            if not tx.get('decoded_func'):
                decode_payload = dict(tx)
                if 'input' not in decode_payload and 'raw_input' in decode_payload:
                    decode_payload['input'] = decode_payload['raw_input']
                decoded_tx = decode_transaction_input(decode_payload, self.abi)

            function_name = decoded_tx.get('decoded_func')
            if isinstance(function_name, str) and function_name:
                yield DecodedTransaction(
                    function_name=function_name,
                    args=_dict_field(decoded_tx.get('decoded_data', {})),
                    tx_hash=first_field(tx, *TRANSACTION_HASH_KEYS) or '',
                    from_address=flat_address(first_field(tx, 'from', 'from_address')) or '',
                    to_address=to_address,
                    value_wei=int_or_default(tx.get('value'), default=0),
                    block_number=block_num,
                    gas=int_or_default(first_field(tx, *GAS_KEYS), default=0),
                    gas_price_wei=int_or_default(first_field(tx, *GAS_PRICE_KEYS), default=0),
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
