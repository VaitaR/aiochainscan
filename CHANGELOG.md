# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-09-04

First stable release, and the first PyPI release since 0.2.3. The public API is
`ChainscanClient` (plus `ChainscanPool` for failover); the legacy `Client`
facade from the 0.2 series is long gone — see
[docs/MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md).

### Added

- **Guaranteed-complete pagination** (`get_all_*` / `iter_*_streaming`,
  `guarantee_complete=True` by default): provider caps are scanner-declared
  (`result_window`, per-method `RESULT_WINDOW_OVERRIDES`, measured
  `max_page_size`), overflow triggers adaptive block-range bisection, and
  truncation that cannot be fixed by splitting raises
  `CompletenessUnavailableError` naming providers that can serve the method
  completely. Whale blocks raise `PaginationDataLossError`.
- **`ChainscanPool`** — multi-provider failover over the full `ChainscanClient`
  surface: sticky routing, per-failure-class cooldowns, pagination pinned to
  one provider per call, transparent provider switching with warnings.
- **Polling helpers** — `wait_for_transaction`, `wait_for_block`,
  `wait_for_verification` (loop-clock deadlines, pending-vs-final states
  returned rather than raised).
- **Custom base URLs + chain validation** — self-hosted BlockScout instances
  via a URL-shaped `network`; `expected_chain_id` validated once before the
  first request; `get_chain_info()` / `validate_chain()`.
- **Normalized accessors** — `get_all_*_normalized` /
  `iter_*_normalized` compose completeness with typed, provider-independent
  records (frozen slotted dataclasses, `provider_data` preserved).
- **MCP server** (`[mcp]` extra) — 12 read-only tools over stdio for AI
  agents, opaque cursors, curated field sets, scanner-override per call.
- **NodeReal / MegaNode scanner** — BSC analytics (25 `Method` values)
  including the only keyless-free alternative for BSC contract source and
  internal transactions.
- **Value-conversion helpers** — `wei_to_ether`, `to_decimal_amount`,
  `format_ether`, `hex_to_int`, `to_datetime` / `to_iso`: exact `Decimal`
  math, no float paths.
- **Streaming DataFrame exports** (`[data]` extra) — Polars DataFrames from
  the streaming iterators, Wei as `Utf8`.

### Changed

- **Distribution split**: `aiochainscan` is pure Python with four runtime
  dependencies (httpx, orjson, tenacity, aiolimiter); the Rust accelerator
  moved to the separate `aiochainscan-fastabi` distribution (`[fastabi]`
  extra). The base install decodes the full ABI spec and computes Keccak-256
  checksums with zero extras (`abi_pure.py`, `_keccak.py` fallback chains).
- ABI decoding is strict by contract across both tiers (padding, ranges,
  UTF-8, canonical offsets); unsupported Solidity types raise
  `AbiTypeNotSupportedError` instead of returning empty results.
- BlockScout V1 routes proxy methods through the instance's `/api/eth-rpc`
  JSON-RPC endpoint (the Etherscan-compat `module=proxy` is dead there).

### Fixed

- Etherscan v2's silent 1000-items-per-page clamp no longer truncates
  `get_all_*` under `guarantee_complete=True` (`Scanner.max_page_size`).
- BlockScout V1 `getLogs` page/offset ignoring (re-fetching page 1) —
  per-method result window declared instead.
- NodeReal `nr_getTokenHolderCount` double-nested envelope (0-holder
  miscounts) — both documented and live shapes accepted, unknown shapes
  raise.

## History (development releases, not published to PyPI)

- **0.6.0** (2026-09-01) — live-verified provider pagination caps; token
  holder surface across all four scanners; conversion helpers; polling
  helpers; failover pool.
- **0.5.0** (2026-02-25) — pagination-guarantee groundwork and scanner
  hardening.
- **0.4.0** (2026-02-23) — scanner-layer consolidation, legacy stack removal
  completed, mixin-based client API.
- **0.3.0** (2026-02) — legacy `Client` facade and `modules/` removed;
  `ChainscanClient` becomes the only public API.
- **0.2.x** (2025-10) — the last series previously published to PyPI; used
  the removed legacy API.

[1.0.0]: https://github.com/VaitaR/aiochainscan/releases/tag/v1.0.0
