"""Decode-domain API mixin for ``ChainscanClient``.

The decoders themselves live in :mod:`aiochainscan.decode`; what this mixin
adds is the step an agent otherwise writes by hand — resolving the ABI that
actually decodes traffic sent to an address (following proxies and diamonds)
and applying it to records the caller already holds.
"""

from __future__ import annotations

import json

from ...decode import (
    decode_log_data,
    decode_transaction_input,
    decode_transaction_inputs_batch,
)
from ...domain.contract import ProxyStrategy, fetch_resolved_abi, resolve_proxy_metadata
from ...domain.models import Address
from ...types import JSONDict, JSONList
from ..host import ClientHost

AbiInput = list[JSONDict] | str


def _as_abi(abi: AbiInput) -> list[JSONDict]:
    parsed = json.loads(abi) if isinstance(abi, str) else abi
    if not isinstance(parsed, list):
        raise ValueError('abi must be a list of ABI entries or its JSON encoding')
    return parsed


async def _abi_for_address(
    host: ClientHost,
    address: str,
    strategy: ProxyStrategy,
    cache: dict[str, list[JSONDict] | None],
) -> list[JSONDict] | None:
    """The ABI that decodes traffic sent to ``address``, or ``None``.

    ``None`` is the answer for an unverified contract and for an address the
    explorer has no ABI for: a record that cannot be decoded is kept
    undecoded, never dropped.
    """
    key = str(Address(address)).lower()
    if key in cache:
        return cache[key]
    try:
        metadata = await resolve_proxy_metadata(key, host, strategy=strategy)
        resolved: list[JSONDict] | None = (await fetch_resolved_abi(key, host, metadata)).abi
    except Exception:  # noqa: BLE001 - every failure means "no ABI for this address"
        resolved = None
    cache[key] = resolved
    return resolved


async def _abi_argument(
    host: ClientHost,
    abi: AbiInput | None,
    address: str | None,
    proxy_strategy: ProxyStrategy,
) -> list[JSONDict] | None:
    """The ABI a decode call was given, or the one its address resolves to."""
    if abi is not None:
        return _as_abi(abi)
    if address is None:
        raise ValueError('pass abi= to decode against a known ABI, or address= to fetch one')
    return await _abi_for_address(host, address, proxy_strategy, {})


def _destination(record: JSONDict, field: str) -> str | None:
    value = record.get(field)
    return value if isinstance(value, str) and value else None


class DecodeMixin:
    """Decode calldata and event logs against an automatically resolved ABI."""

    async def decode_input(
        self: ClientHost,
        input_data: str,
        *,
        address: str | None = None,
        abi: AbiInput | None = None,
        proxy_strategy: ProxyStrategy = 'metadata',
    ) -> JSONDict:
        """Decode one calldata string into ``{'decoded_func', 'decoded_data'}``.

        Pass ``abi`` to decode against a known ABI, or ``address`` to have the
        contract's ABI resolved first — through its proxy implementation, or
        every facet of a diamond, so calldata sent to a proxy decodes. Calldata
        that matches no selector comes back with an empty function name rather
        than as an error.

        Example:
            ```python
            tx = await client.get_transaction('0xHASH...')
            decoded = await client.decode_input(tx['input'], address=tx['to'])
            print(decoded['decoded_func'], decoded['decoded_data'])
            ```
        """
        resolved_abi = await _abi_argument(self, abi, address, proxy_strategy)
        if resolved_abi is None:
            return {'decoded_func': '', 'decoded_data': {}}
        decoded = decode_transaction_input({'input': input_data}, resolved_abi)
        return {
            'decoded_func': decoded.get('decoded_func', ''),
            'decoded_data': decoded.get('decoded_data', {}),
        }

    async def decode_transactions(
        self: ClientHost,
        transactions: JSONList,
        *,
        address: str | None = None,
        abi: AbiInput | None = None,
        proxy_strategy: ProxyStrategy = 'metadata',
    ) -> JSONList:
        """Decode a list of transactions, resolving each destination's ABI.

        Returns copies — the input list is never mutated. With no ``abi`` and
        no ``address`` the ABI is resolved per ``tx['to']`` (once per address,
        proxies followed); a transaction whose ABI cannot be fetched or whose
        selector the ABI does not declare keeps every original field with an
        empty ``decoded_func``, so a batch never loses rows to a contract
        nobody verified.

        Example:
            ```python
            txs = await client.get_all_transactions(wallet)
            decoded = await client.decode_transactions(txs)
            ```
        """
        if not transactions:
            return []
        copies = [dict(tx) for tx in transactions]

        if abi is not None or address is not None:
            resolved_abi = await _abi_argument(self, abi, address, proxy_strategy)
            if resolved_abi is None:
                return [_undecoded(tx) for tx in copies]
            return decode_transaction_inputs_batch(copies, resolved_abi)

        cache: dict[str, list[JSONDict] | None] = {}
        groups: dict[str, list[JSONDict]] = {}
        out: JSONList = []
        for tx in copies:
            destination = _destination(tx, 'to')
            if destination is None:
                out.append(_undecoded(tx))
                continue
            groups.setdefault(str(Address(destination)).lower(), []).append(tx)
            out.append(tx)
        for destination, group in groups.items():
            group_abi = await _abi_for_address(self, destination, proxy_strategy, cache)
            if group_abi is None:
                for tx in group:
                    _undecoded(tx)
                continue
            decode_transaction_inputs_batch(group, group_abi)
        return out

    async def decode_logs(
        self: ClientHost,
        logs: JSONList,
        *,
        address: str | None = None,
        abi: AbiInput | None = None,
        proxy_strategy: ProxyStrategy = 'metadata',
    ) -> JSONList:
        """Decode event logs, resolving each emitter's ABI.

        Returns copies. Without ``abi``/``address`` the ABI is resolved per
        ``log['address']``. A log whose event the ABI does not declare is
        returned unchanged (no ``decoded_data`` key), which is how
        :func:`aiochainscan.decode.decode_log_data` reports "no match".

        Example:
            ```python
            logs = await client.get_all_logs(token, from_block=0)
            decoded = await client.decode_logs(logs)
            ```
        """
        if not logs:
            return []
        copies = [dict(log) for log in logs]

        if abi is not None or address is not None:
            resolved_abi = await _abi_argument(self, abi, address, proxy_strategy)
            if resolved_abi is None:
                return copies
            return [decode_log_data(log, resolved_abi) for log in copies]

        cache: dict[str, list[JSONDict] | None] = {}
        for log in copies:
            emitter = _destination(log, 'address')
            if emitter is None:
                continue
            log_abi = await _abi_for_address(self, emitter, proxy_strategy, cache)
            if log_abi is not None:
                decode_log_data(log, log_abi)
        return copies


def _undecoded(record: JSONDict) -> JSONDict:
    record['decoded_func'] = ''
    record['decoded_data'] = {}
    return record
