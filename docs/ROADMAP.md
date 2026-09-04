# aiochainscan Roadmap

Forward-looking plan. Released work (0.3.0 → 1.0.0) is history — see git tags and
the release notes; the current feature set is documented in `AGENTS.md`. Strategy
and the v1 track plan live in [V1_PLAN.md](V1_PLAN.md).

## Current state (1.0.0)

Pure-Python base install (`aiochainscan`) + separate Rust accelerator
(`aiochainscan-fastabi`); full Etherscan-v2 surface (33 `Method` values),
BlockScout v1/v2, NodeReal; guaranteed-complete pagination by default;
`ChainscanPool` failover; polling helpers; MCP server; exact `Decimal` value
helpers. 1000+ tests, mypy --strict clean.

## Open features

### 1. GraphQL Support Expansion (medium)
BlockScout GraphQL support is partial (tx-by-hash, token transfers, address
transactions). Cover full transaction history, contract interactions, and block
details.

### 2. Finality-Aware Caching (medium)
```python
class FinalityAwareCache:
    """Cache that respects blockchain finality depth."""

    SAFE_DEPTH = 32  # Blocks considered finalized

    async def set(self, key: str, value: Any, *, block_number: int | None = None):
        if block_number and self._is_finalized(block_number):
            ttl = 86400  # 24h for finalized data
        else:
            ttl = 5  # 5s for pending/recent
```
- Track current block number; implement finality depth checking
- Skip caching for `latest`/`pending` tags

### 3. Multi-Address Batch Queries (medium)
```python
async def get_balances_multi(
    addresses: list[str],
    *,
    concurrent: int = 10,
) -> dict[str, int]:
    """Fetch balances for multiple addresses efficiently."""
```
- Batch balance endpoint support where it exists; concurrent single-address
  fallback otherwise; progress callback for large batches

### 4. New Scanner Integrations
- **Alchemy** (high): enhanced metadata, NFT API, webhooks, tx simulation
- **Infura** (medium): JSON-RPC, IPFS

### 5. Advanced Features (long-term)
- **Real-time event subscriptions** (high): WebSocket adapter, event filtering,
  reconnection, backfill
- **Transaction simulation** (medium): `simulate_transaction(from, to, data, value)`
- **Gas estimation & prediction** (medium): EIP-1559-aware, slow/medium/fast

### 6. Redis Cache Adapter (low)
`RedisCacheAdapter` in `adapters/` for distributed deployments, with connection
pooling.

### 7. Developer Experience
- Generated API reference (MkDocs) + docstrings on all public methods
- CLI: interactive shell, `--format json|csv|table`
- Integration tests: VCR-style request recording, mock server, benchmarks
- Runtime type-checking option; protocol validation tests

## Priority Matrix (open items)

| Feature | Impact | Effort | Priority |
|---------|--------|--------|----------|
| Real-time Subscriptions | High | High | P2 |
| GraphQL Expansion | Medium | High | P1 |
| Finality-Aware Caching | Medium | Medium | P1 |
| Multi-Address Batch Queries | Medium | Low | P1 |
| Alchemy Scanner | High | High | P2 |
| Redis Cache | Low | Low | P2 |
| API Reference Docs | High | Medium | P1 |
| CLI Enhancements | Low | Medium | P3 |

Priority labels: **P0** critical path · **P1** important · **P2** nice to have ·
**P3** future consideration.

## Release Plan

- **v1.0.0** — publish both distributions to PyPI (Track B in
  [V1_PLAN.md](V1_PLAN.md)), real-time subscriptions, full API documentation,
  stable public API.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md).
