from __future__ import annotations

from typing import Any

from aiochainscan.ports.graphql_query_builder import GraphQLQueryBuilder


def _hex(value: int | None) -> str | None:
    return hex(value) if value is not None else None


class BlockscoutGraphQLBuilder(GraphQLQueryBuilder):
    """Blockscout GraphQL queries and response mappers.

    Note: Query shapes are based on common Blockscout GraphQL schemas. Mapping
    functions are defensive and tolerate missing fields.
    """

    def build_logs_query(
        self,
        *,
        address: str,
        start_block: int | str,
        end_block: int | str,
        topics: list[str] | None,
        after_cursor: str | None,
        first: int | None,
    ) -> tuple[str, dict[str, Any]]:
        query = (
            'query($address: String!, $fromBlock: Long, $toBlock: Long, $after: String, $first: Int, '
            '$topics: [String!]) {'
            '  logs(addressHash: $address, '
            '       filter: {fromBlockNumber: $fromBlock, toBlockNumber: $toBlock, topics: $topics}, '
            '       after: $after, first: $first) {'
            '    pageInfo { endCursor hasNextPage }'
            '    edges { node { addressHash blockNumber transactionHash data topics } }'
            '  }'
            '}'
        )

        def to_int(v: int | str) -> int | None:
            if isinstance(v, int):
                return v
            if isinstance(v, str):
                if v == 'latest':
                    return None
                try:
                    return int(v, 0)
                except Exception:
                    return None
            return None

        variables: dict[str, Any] = {
            'address': address,
            'fromBlock': to_int(start_block),
            'toBlock': to_int(end_block),
            'after': after_cursor,
            'first': first,
            'topics': topics or None,
        }
        return query, variables

    def map_logs_response(self, data: Any) -> tuple[list[dict[str, Any]], str | None]:
        items: list[dict[str, Any]] = []
        next_cursor: str | None = None
        try:
            logs = data.get('logs', {}) if isinstance(data, dict) else {}
            page_info = logs.get('pageInfo', {}) if isinstance(logs, dict) else {}
            next_cursor = page_info.get('endCursor') if page_info.get('hasNextPage') else None
            edges = logs.get('edges') or []
            if isinstance(edges, list):
                for edge in edges:
                    node = edge.get('node') if isinstance(edge, dict) else None
                    if not isinstance(node, dict):
                        continue
                    address = node.get('addressHash') or ''
                    block_number = node.get('blockNumber')
                    tx_hash = node.get('transactionHash')
                    data_field = node.get('data')
                    topics = node.get('topics') or []
                    items.append(
                        {
                            'address': address,
                            'blockNumber': _hex(int(block_number)) if block_number is not None else None,
                            'transactionHash': tx_hash,
                            'data': data_field,
                            'topics': [str(t) for t in topics],
                        }
                    )
        except Exception:
            # Be defensive; return what we have
            pass
        return items, next_cursor

    def build_transaction_by_hash_query(self, *, txhash: str) -> tuple[str, dict[str, Any]]:
        # Blockscout v1 GraphQL commonly exposes: transaction(hash: FullHash!)
        query = (
            'query($h: FullHash!) {'
            '  transaction(hash: $h) {'
            '    hash blockNumber fromAddressHash toAddressHash value gas gasPrice input'
            '  }'
            '}'
        )
        return query, {'h': txhash}

    def map_transaction_response(self, data: Any) -> dict[str, Any]:
        tx: dict[str, Any] = {}
        try:
            tx = data.get('transaction', {}) if isinstance(data, dict) else {}
        except Exception:
            tx = {}
        if not isinstance(tx, dict):
            return {}
        # Convert numeric fields to hex-like strings to align with proxy format
        def to_hex(v: Any) -> str | None:
            try:
                if v is None:
                    return None
                if isinstance(v, str) and v.startswith('0x'):
                    return v
                return hex(int(v))
            except Exception:
                return None

        return {
            'hash': tx.get('hash'),
            'blockNumber': to_hex(tx.get('blockNumber')),
            'from': tx.get('fromAddressHash'),
            'to': tx.get('toAddressHash') or tx.get('createdContractAddressHash'),
            'value': to_hex(tx.get('value')),
            'gas': to_hex(tx.get('gas')),
            'gasPrice': to_hex(tx.get('gasPrice')),
            'input': tx.get('input'),
        }

    def build_token_transfers_query(
        self,
        *,
        address: str | None,
        token_contract: str | None,
        after_cursor: str | None,
        first: int | None,
    ) -> tuple[str, dict[str, Any]]:
        # Prefer Address.tokenTransfers when address is provided; otherwise Root.tokenTransfers
        if address:
            query = (
                'query($addr: AddressHash!, $after: String, $first: Int) {'
                '  address(hash: $addr) {'
                '    tokenTransfers(after: $after, first: $first) {'
                '      pageInfo { endCursor hasNextPage }'
                '      edges { node { transactionHash tokenContractAddressHash fromAddressHash toAddressHash amount logIndex blockNumber } }'
                '    }'
                '  }'
                '}'
            )
            return query, {'addr': address, 'after': after_cursor, 'first': first}

        # Root tokenTransfers requires tokenContractAddressHash (non-null)
        query = (
            'query($token: AddressHash!, $after: String, $first: Int) {'
            '  tokenTransfers(tokenContractAddressHash: $token, after: $after, first: $first) {'
            '    pageInfo { endCursor hasNextPage }'
            '    edges { node { transactionHash tokenContractAddressHash fromAddressHash toAddressHash amount logIndex blockNumber } }'
            '  }'
            '}'
        )
        return query, {'token': token_contract, 'after': after_cursor, 'first': first}

    def map_token_transfers_response(self, data: Any) -> tuple[list[dict[str, Any]], str | None]:
        # Detect whether response is from Address or Root level
        conn: Any | None = None
        if isinstance(data, dict):
            addr = data.get('address')
            if isinstance(addr, dict) and 'tokenTransfers' in addr:
                conn = addr.get('tokenTransfers')
            elif 'tokenTransfers' in data:
                conn = data.get('tokenTransfers')

        items: list[dict[str, Any]] = []
        next_cursor: str | None = None
        if isinstance(conn, dict):
            page = conn.get('pageInfo') or {}
            next_cursor = page.get('endCursor') if page.get('hasNextPage') else None
            edges = conn.get('edges') or []
            if isinstance(edges, list):
                for e in edges:
                    node = e.get('node') if isinstance(e, dict) else None
                    if not isinstance(node, dict):
                        continue
                    items.append(
                        {
                            'hash': node.get('transactionHash'),
                            'blockNumber': node.get('blockNumber'),
                            'from': node.get('fromAddressHash'),
                            'to': node.get('toAddressHash'),
                            'contractAddress': node.get('tokenContractAddressHash'),
                            'value': node.get('amount'),
                            'transactionIndex': None,
                            'gas': None,
                            'gasPrice': None,
                            'gasUsed': None,
                            'cumulativeGasUsed': None,
                            'input': None,
                            'confirmations': None,
                        }
                    )
        return items, next_cursor

    def build_address_transactions_query(
        self, *, address: str, after_cursor: str | None, first: int | None
    ) -> tuple[str, dict[str, Any]]:
        query = (
            'query($addr: AddressHash!, $after: String, $first: Int) {'
            '  address(hash: $addr) {'
            '    transactions(after: $after, first: $first) {'
            '      pageInfo { endCursor hasNextPage }'
            '      edges { node { hash blockNumber fromAddressHash toAddressHash gas gasPrice input } }'
            '    }'
            '  }'
            '}'
        )
        return query, {'addr': address, 'after': after_cursor, 'first': first}

    def map_address_transactions_response(self, data: Any) -> tuple[list[dict[str, Any]], str | None]:
        items: list[dict[str, Any]] = []
        next_cursor: str | None = None
        try:
            addr = data.get('address', {}) if isinstance(data, dict) else {}
            conn = addr.get('transactions', {}) if isinstance(addr, dict) else {}
            page = conn.get('pageInfo', {}) if isinstance(conn, dict) else {}
            next_cursor = page.get('endCursor') if page.get('hasNextPage') else None
            edges = conn.get('edges') or []
            if isinstance(edges, list):
                for e in edges:
                    node = e.get('node') if isinstance(e, dict) else None
                    if not isinstance(node, dict):
                        continue
                    items.append(
                        {
                            'blockNumber': node.get('blockNumber'),
                            'timeStamp': None,
                            'hash': node.get('hash'),
                            'nonce': None,
                            'blockHash': None,
                            'transactionIndex': None,
                            'from': node.get('fromAddressHash'),
                            'to': node.get('toAddressHash'),
                            'value': None,
                            'gas': node.get('gas'),
                            'gasPrice': node.get('gasPrice'),
                            'isError': None,
                            'txreceipt_status': None,
                            'input': node.get('input'),
                            'contractAddress': None,
                            'cumulativeGasUsed': None,
                            'gasUsed': None,
                            'confirmations': None,
                        }
                    )
        except Exception:
            pass
        return items, next_cursor


