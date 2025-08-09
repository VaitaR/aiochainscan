from __future__ import annotations

from typing import Any, Protocol


class GraphQLQueryBuilder(Protocol):
    """Provider-specific GraphQL query builder and response mapper.

    The builder is responsible for producing provider-compatible GraphQL queries
    and mapping their responses back to the normalized, REST-like shapes that
    existing services expect.
    """

    # --- Logs ---
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
        """Return (query, variables) for fetching logs with optional cursor pagination."""

    def map_logs_response(self, data: Any) -> tuple[list[dict[str, Any]], str | None]:
        """Map GraphQL `data` into (items, next_cursor) using Etherscan-like fields."""

    # --- Transaction by hash ---
    def build_transaction_by_hash_query(self, *, txhash: str) -> tuple[str, dict[str, Any]]:
        """Return (query, variables) for fetching a transaction by hash."""

    def map_transaction_response(self, data: Any) -> dict[str, Any]:
        """Map GraphQL `data` into a dict compatible with proxy.eth_getTransactionByHash."""

    # --- Token transfers (paginated) ---
    def build_token_transfers_query(
        self,
        *,
        address: str | None,
        token_contract: str | None,
        after_cursor: str | None,
        first: int | None,
    ) -> tuple[str, dict[str, Any]]:
        """Return (query, variables) for fetching token transfers with cursor pagination.

        Implementations should support either Address.tokenTransfers or Root.tokenTransfers
        depending on which parameters are provided.
        """

    def map_token_transfers_response(self, data: Any) -> tuple[list[dict[str, Any]], str | None]:
        """Map GraphQL `data` into (items, next_cursor) using Etherscan-like field names."""

    # --- Address transactions (paginated) ---
    def build_address_transactions_query(
        self,
        *,
        address: str,
        after_cursor: str | None,
        first: int | None,
    ) -> tuple[str, dict[str, Any]]:
        """Return (query, variables) for fetching address transactions with cursor pagination."""

    def map_address_transactions_response(
        self, data: Any
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Map GraphQL `data` into (items, next_cursor) using Etherscan normal-tx field names."""
