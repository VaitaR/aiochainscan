# CONTEXT.md — Domain Glossary

One-line entries for domain terms used across aiochainscan.

- **Network** — The sole HTTP transport layer (`aiochainscan/network.py`); uses httpx directly. All HTTP must go through it; scanners never own sessions.
- **Port** — Interface in `aiochainscan/ports/` defining a capability the domain needs; surviving ports: `cache`, `progress`, `rate_limiter`.
- **Adapter** — Concrete implementation of a port in `aiochainscan/adapters/`; surviving: `memory_cache`, `aiolimiter_adapter`, `simple_rate_limiter`, `retry_exponential`, `tenacity_retry`.
- **Scanner** — Per-explorer API adapter (`scanners/`) mapping `Method` enum values to `EndpointSpec` (path, params, parser) via a `SPECS` dict.
- **EndpointSpec** — Frozen dataclass in `core/endpoint.py` describing one scanner endpoint; `PARSERS` registry holds shared response parsers (`etherscan`, `raw`).
- **Streaming aggregation** — Pagination strategy behind `get_all_*`: pages are fetched and materialized via a streaming path so `iter_*_streaming` can run in constant memory.
