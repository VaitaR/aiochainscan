# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [Semantic Versioning](https://semver.org/).

## [1.0.4] — 2026-09-10

### Added

- **Plasma (chain id 9745)** in `chain_registry.STANDARD_CHAINS`, aliases `plasma` / `xpl`.
  Ids and aliases only: Plasma has no Blockscout instance and no Etherscan-family scanner,
  so no scanner target or URL-builder profile is claimed for it.
- `docs/GETTING_STARTED.md` — a user entry path (install → first request →
  provider choice → recipes → limits), linked first from `docs/README.md`, which
  now separates user guides from engineering documents.
- `SECURITY.md` and GitHub issue templates (bug report, provider/chain support,
  feature request).
- **MCPB bundle (`mcpb/`) and `make mcpb`** — the format Smithery distributes
  local stdio MCP servers in (its current flow accepts a hosted HTTPS URL or a
  `.mcpb` bundle; there is no `smithery.yaml` and no container build). The
  bundle carries no library code: it pins the published `aiochainscan[mcp]`
  release, which the host installs with uv, and exposes the two API keys and
  the default scanner as client-prompted settings. Packing refuses to run while
  the version stated in the bundle and in `server.json` disagrees.
- README sections for the normalized cross-provider surface and for the command
  line, plus PyPI badges and absolute links (relative README links 404 on PyPI).

### Fixed

- An empty `AIOCHAINSCAN_MCP_SCANNER` is treated as unset instead of as a
  scanner id. Launchers that substitute an unset optional setting (the MCPB
  bundle's `default_scanner` among them) export the variable as `''`, which
  left the MCP server with no usable default scanner.

### Changed

- **BREAKING (behaviour): ENS resolution propagates library errors instead of
  answering `None`.** A scanner that does not declare `eth_call` raises
  `MethodNotDeclaredError`; rate limits, transport failures and data-contract
  errors surface as themselves, in the batch helpers too. `None` now means only
  what it says: the name (or the reverse record) does not exist. An answered
  BlockScout address-info request is treated as authoritative for the reverse
  record, so an address with no ENS name is `None` without a contract call.
- **BREAKING: the BlockScout host table is live-verified** (2026-09-10). Gnosis,
  Optimism and Scroll moved to chain-branded hostnames (`gnosisscan.io`,
  `explorer.optimism.io`, `scrollscan.com`) and only 301 the `*.blockscout.com`
  alias there; the transport does not follow redirects, so those three chains
  answered `ChainscanClientContentTypeError` on every request. BSC and Linea have
  no BlockScout instance at all (both hosts 404) and are gone from the BlockScout
  topology — `from_config('blockscout'|'blockscout_v2', 'bsc'|'bnb'|'linea')` now
  raises instead of failing at request time. Keyless BSC goes through `nodereal`.
- **The CLI was rewritten against the real library.** It advertised 22 scanners
  and 10 API keys that do not exist; it now derives every fact from the scanner
  registry, the scanner classes and the configuration manager: `scanners`,
  `chains`, `check`, `generate-env`, `test`, `mcp`. `add-scanner` and `export`
  are gone — neither had an implementation behind it. Chain coverage passes both
  construction gates (registry resolution *and* the scanner class's
  `supported_networks`), so it cannot advertise a chain that cannot be built.
- Examples 01–03 run against the published package alone (no checkout, no dev
  environment, no key), and every example uses the public surface with exact
  `Decimal` conversion instead of `int(wei) / 1e18`.
- `pyproject.toml` declares Production/Stable, `Framework :: AsyncIO`,
  `Typing :: Typed`, keywords, and separate Documentation/Changelog project URLs;
  the sdist ships `docs`, `examples` and `CONTRIBUTING.md`.

### Fixed

- `examples/07_handling_whale_blocks.py` requested a bounded range from
  BlockScout v2, which cannot carry one, and expected `CompletenessUnavailableError`
  from an Etherscan holder endpoint that is PRO-only; both paths now run.
- `examples/smart_contract_demo.py` summed DAI transfers under the key `value`
  while DAI's ABI declares `wad`, and dropped every amount above int64 through an
  `isinstance(value, int)` filter — it reported 0.00 DAI for 50 transfers.
- `examples/ens_and_gas_dashboard.py` read `ETHERSCAN_KEY` from the environment
  itself and so skipped the gas dashboard for keys the library resolves from
  `.env` files.

### Note

- 1.0.2 was never released; the version was skipped.

## [1.0.3] — 2026-09-08

Packaging only. No library code changed.

### Fixed

- **`aiochainscan[fastabi]` was unusable on Python 3.14** and on Intel macOS:
  the accelerator shipped version-specific wheels for cp312/cp313 on arm64
  macOS, Linux and Windows only, so any other interpreter fell back to the
  sdist and demanded a Rust toolchain. `aiochainscan-fastabi` 1.0.3 builds one
  `cp312-abi3` wheel per platform (pyo3 `abi3-py312`), which serves 3.12, 3.13,
  3.14 and later CPythons. Intel macOS is cross-built on the arm64 runner —
  GitHub retired the last hosted x86_64 macOS image in December 2025.
- The `fastabi` extra pinned `aiochainscan-fastabi>=0.2.0` while
  `decode.py:_MIN_FASTABI_VERSION` refuses anything below 1.0.1, so an
  incompatible extension resolved successfully and then failed at import. The
  floor is now declared where the resolver can see it.

## [1.0.1] — 2026-09-08

Defect fixes from two post-release audits, plus internal consolidation. No
public API change.

### Fixed

- **ABI decode could abort the interpreter** on a malformed ABI type: the Rust
  tier now unwinds the parser instead of aborting, one input-naming convention
  covers both tiers (unnamed inputs keyed `param_{i}`, duplicates suffixed),
  fixed-point values serialize as JSON-safe strings, and a zero-size array
  element with a non-zero count is treated as a corrupted length word rather
  than looping. `aiochainscan-fastabi` below 1.0.1 is refused.
- **MCP token curation read an integer `0` as a missing field** and fell
  through to the next provider alias, so a zero balance could be reported as
  another field's value. Curation now reads the declared provider field
  dialect, which also settles nested-vs-flat keys in one place.
- **`.env` handling**: undecodable lines are skipped with a warning instead of
  being fatal, dotenv dialect and `.env.local` precedence are honoured, and a
  second `ConfigurationManager(config_dir=...)` warns instead of silently
  keeping the first directory. `ConfigurationManager.create_isolated()` builds
  a hermetic manager for tests without touching the process-wide singleton.
- **Registry**: declared scanner-network aliases all construct
  (`scanner_network` canonicalization), BlockScout v2 currency is resolved per
  network, stale instance hosts dropped.
- **NodeReal's result-window refusal** (`-32005` carrying a size limit) is
  classified as a window overflow and split, not retried as throttling.
- Various MCP envelope fixes: normalized pending is not an error, hex balance
  normalization, cursor hardening, `format_units` bounds.

### Changed

- One row per scanner id: the config manager's presentation rows are derived
  from the chain registry instead of a second table keyed by the same ids.
- One owner for failure classification — HTTP status and provider message →
  `FailureKind` now lives in `exceptions.py` and the network layer only picks
  the exception class.

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
[1.0.1]: https://github.com/VaitaR/aiochainscan/releases/tag/v1.0.1
[1.0.3]: https://github.com/VaitaR/aiochainscan/releases/tag/v1.0.3
[1.0.4]: https://github.com/VaitaR/aiochainscan/releases/tag/v1.0.4
