---
paths:
  - "aiochainscan/fastabi/**"
  - "aiochainscan/decode.py"
---

# Rust FFI (fastabi) invariants

You are touching the Rust ABI-decoding path. These invariants come from AGENTS.md (Rust FFI Notes + Async Performance) and are the difference between a fast decode path and an event-loop stall:

- **Never return PyDict/PyList directly from Rust** — object creation under the GIL blocks the event loop. Return a JSON string; parse it with `orjson` on the Python side (`decode.py`).
- **Release the GIL** during computation AND serialization in `fastabi/src/lib.rs`.
- **Decode cache**: LRU with 1000 entries max (~50MB). Cache keys are content hashes, never raw pointers (Python reuses memory addresses).
- **Build**: `cd aiochainscan/fastabi && maturin develop --release` (or `make fastabi`). Without a built extension, `decode.py` falls back to the pure-Python path — tests must pass either way.
- Arrow support exists for zero-copy decoding (`9298b5f`) — keep both the JSON and Arrow paths working when touching decode signatures.
