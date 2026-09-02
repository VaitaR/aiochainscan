# CONTEXT.md — Domain Glossary

One-line entries for domain terms used across aiochainscan.

- **Network** — The sole HTTP transport layer (`aiochainscan/network.py`); uses httpx directly. All HTTP must go through it; scanners never own sessions.
- **Port** — Interface in `aiochainscan/ports/` defining a capability the domain needs; surviving ports: `cache`, `progress`, `rate_limiter`.
- **Adapter** — Concrete implementation of a port in `aiochainscan/adapters/`; surviving: `memory_cache`, `aiolimiter_adapter`, `simple_rate_limiter`, `retry_exponential`, `tenacity_retry`.
- **Scanner** — Per-explorer API adapter (`scanners/`) mapping `Method` enum values to `EndpointSpec` (path, params, parser) via a `SPECS` dict.
- **EndpointSpec** — Frozen dataclass in `core/endpoint.py` describing one scanner endpoint; shared response parsers (e.g. `etherscan_parser`) are plain callables referenced directly from specs.
- **Streaming aggregation** — Pagination strategy behind `get_all_*`: pages are fetched and materialized via a streaming path so `iter_*_streaming` can run in constant memory.
- **Page cursor** — Opaque dict returned by `Scanner.fetch_page` next to the items; `None` means "no more pages", otherwise the caller merges it into the params of the next `fetch_page` call (e.g. BlockScout V2 `next_page_params`, Etherscan page/offset).
- **Pagination engine** — The single deep module owning every paginated loop (`aiochainscan/services/pagination.py`): `iter_pages`/`iter_items` (batches/items over `Scanner.fetch_page`, opaque cursor merge, `None` termination, cycle/advance guards, progress), `normalize_items` (response → items), `collect_all` (get_all_* materialization + 100k warning), `page_fetcher` (binds scanner+method).
- **AddressInfoProvider** — Scanner-port subset declared by `services/ens_resolver.py` (`get_address_info`); satisfied by BlockScout V2 and injected into `ENSResolver` at construction by `ENSMixin.ens` so ENS reverse lookup never reaches through `client._scanner`.
- **ScannerTarget** — Frozen dataclass + `resolve_scanner_target()` in `aiochainscan/chain_registry.py`: the single resolution point turning `(scanner, network, api_key)` into `(scanner_name, scanner_version, network, api_kind, api_key, chain_id)` for `ChainscanClient.from_config`; owns version defaulting, the `blockscout_v2` → `('blockscout', 'v2')` rename, network alias tables, and api-key defaults (config manager consulted lazily at call time).
- **KECCAK_BACKEND** — Backend selector exported by `aiochainscan/crypto.py` (`'fastabi'` | `'eth-utils'` | `'none'`), resolved once at import: the Rust `keccak256` first, eth-utils fallback via the `fallback` extra, else `ChainscanDependencyError` on first use. `crypto.py` is the single source of keccak-256/EIP-55/is_address for decode, domain, and ENS layers.
