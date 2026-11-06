# ABI decoding and the Rust FFI (fastabi)

Agent reference for `decode.py`, `abi_pure.py` and `aiochainscan/fastabi/`. Read it before
touching any of them; `.claude/rules/fastabi.md` attaches the short invariant list
automatically in Claude Code.

## Backend chain

`decode.py` picks a backend per process: `fastabi` (Rust, `[fastabi]`) → `abi_pure.py`
(always available). There is no third tier — `abi_pure.py` covers the whole ABI spec, so a
bare `pip install aiochainscan` decodes transaction inputs, event logs,
`SmartContract.iter_events` and the MCP `read_contract` / `get_transaction_info` tools.
`eth-abi` is a **test oracle** in `[dev]`, never a runtime path.

## Two output conventions, one per entry point

- **Tier convention** — calldata and log decoding (`decode_transaction_input`,
  `decode_log_data`, `SmartContract.iter_events`), implemented in
  `decode.py:_to_rust_convention` and `lib.rs:convert_token_to_json`: ints inside int64
  stay `int`, ints outside become strings, `bytes`/`bytesN` as `0x` hex, arrays *and*
  tuples as `list`, `fixedMxN`/`ufixedMxN` as a fixed-point string (`format(v,'f')`, never
  scientific) so orjson/MCP never sees a `Decimal`. A decoded value must not change shape
  when a user adds or drops `[fastabi]`. `TIER_CONVENTION_CASES` in
  `tests/test_abi_pure.py` declares the rules once and drives both tiers.
- **Agent-JSON convention** — `eth_call` output decoding (`abi_pure.decode_arguments`, used
  by MCP `read_contract`): EVERY integer becomes a string, named tuples become dicts keyed
  by component name, unnamed outputs are keyed by `str(index)` (not `param_{i}` — that is
  the tier convention's input naming).
- **Decoded-input naming is one convention on both tiers**
  (`decode.py:_resolved_input_names` mirrored by `lib.rs resolved_param_names`): unnamed
  inputs (missing/null/empty name) are keyed `param_{i}` by position; duplicate names —
  first keeps the plain spelling, later ones get `_2`, `_3`…; applies to function decodes,
  event decodes and Arrow columns. Without it, empty names folded onto one `''` key.

## Strictness

- **Unsupported Solidity type → `AbiTypeNotSupportedError`**, never an empty
  `decoded_data`: a gap in this library must not read as undecodable calldata. Non-spec
  widths (`int12`, `uint0`, `bytes0`) are validated at ABI-index build
  (`_validate_input_types`), so installing `[fastabi]` cannot soften the rejection.
- Malformed/truncated calldata stays non-fatal (empty result) — that is what
  `_MALFORMED_CALLDATA_ERRORS` is for: a spam transaction whose selector collides must not
  kill a decode loop. An array of zero-size elements with a non-zero count (e.g. `tuple[]`
  of empty tuples, count=2^63) is treated as a corrupted length word on both tiers.
- **Both tiers are strict about padding**: dirty `address`/`bytesN` padding, an
  out-of-range `uint<N>`/`int<N>`, a non-canonical `bool` and a dynamic offset pointing
  into the head area all raise. So does non-zero padding between a dynamic value and its
  32-byte boundary — but only the padding bytes actually present are checked (an absent
  final pad is a truncation the length checks own, and eth-abi accepts it). `ethabi` is
  lenient with no strict mode, so the Rust tier has a hand-written pass (`validate_sequence`
  in `lib.rs`) before `Function::decode_input`, on byte slices only. It must also validate
  `string` as UTF-8: `ethabi` converts lossily, so non-UTF-8 would decode to U+FFFD on Rust
  and raise on the floor. Never implement this by re-encoding and comparing — that rejects
  non-minimal but legal offsets.
- **Cost of strictness**: +14% end-to-end on the pure floor (`decode_transaction_input`,
  ERC-20 `transfer`; +48% on raw two-word `decode_values`; `-m benchmark` in
  `tests/test_abi_pure.py`), +2% single / +25% bulk on Rust (0.516→0.526 us/call,
  1.045→1.311 ms per 1000). Keep `validate_sequence` generic over the parameter iterator:
  materializing a `Vec<ParamType>` per call cost +99% single / +143% bulk.
- Bulk work (`decode_many`, streaming, DataFrames) belongs on `[fastabi]`;
  `decode_transaction_inputs_batch` says so once per process (`PureAbiDecodeWarning`) for
  batches of 50+. Log decoding has no Rust path (fastabi decodes *inputs* only), so it
  warns about nothing.
- **`fixedMxN` / `ufixedMxN` decode to `Decimal`** (`raw / 10**N`, exact via `scaleb`).
  Widths are validated at parse time: `int`/`uint` a multiple of 8 in 8..256, `bytesN`
  0<N≤32, fixed scale 0<N≤80. Every `scaleb` must be passed `_FIXED_CONTEXT` explicitly:
  `scaleb` is a context operation and the default `prec=28` silently rounds a full-width
  value (int256 needs 78 digits). The `Decimal(str)` constructor itself is exact.
- **The Rust tier falls through, not out**: `fastabi` answers an unimplemented type with
  an empty `function_name`, so `_decode_transaction_input_fast` and
  `decode_transaction_inputs_batch` retry on the pure floor whenever the Rust result is
  empty. Both retries are gated on `_declares_selector`, or every transaction with an
  undeclared selector would be re-decoded on the floor for the same empty answer.

## Performance shape of the floor

- The hot path is the glue, not the ABI walk: an ERC-20 `transfer` spends ~40% in
  `abi_pure` and the rest in `decode.py`, so conventions are applied in ONE traversal
  (`_to_rust_convention`) and hot functions avoid `typing.cast` (a real call at runtime).
  Arrays use `_decode_array`, not `_decode_sequence([elem] * count, ...)`. Splitting the
  traversal or reintroducing the casts costs ~30% end-to-end.
- **The ABI index is cached** (`_abi_index`): identity fast path, then a content digest,
  holding the function/event maps plus each selector's compiled decode plan. The index is
  built from a round-trip of the serialized ABI, so it shares no mutable state with any
  caller. Mutating a list in place still leaves *its own* cached index stale (the identity
  path never rehashes) — build a new list instead.

## Rust FFI (`fastabi/`)

- **Build is not automatic**: the base package builds with hatchling, so
  `uv sync --extra dev` installs no Rust extension. Build with `make fastabi` (or
  `cd aiochainscan/fastabi && uv run --with maturin maturin develop --release`), or pass
  `AIO_BUILD_FASTABI=1` to `make wt-new`. Without it `tests/test_crypto.py` skips 12 tests
  and decoding uses the pure floor; `scripts/agent/preflight.sh` reports which module (if
  any) is live.
- **Version floor**: the extension exports `__version__` from `CARGO_PKG_VERSION`, and
  `decode.py` refuses anything below `_MIN_FASTABI_VERSION` (1.0.1) — the release that
  removed `panic = "abort"` and unwinds the ethabi ABI parser (`catch_unwind`), so a
  malformed ABI type raises a catchable `ValueError` instead of aborting the process.
  `decode.py` degrades any surviving Rust panic (`PanicException`) to the pure floor via a
  coordinate-matched check — pyo3 never registers that class as importable. A stale local
  build is ignored with `PureAbiDecodeWarning`. Bump both `fastabi/Cargo.toml` and
  `fastabi/pyproject.toml` whenever decode semantics change, and raise the floor with them.
- **Cache**: LRU, 1000 entries max (~50MB); keys are content hashes, never raw pointers.
- **GIL**: released during computation AND serialization.
- **Return format**: JSON string → parsed by orjson in Python (never return PyDict/PyList —
  object creation under the GIL blocks the event loop); `keccak256` returns bytes.
- **Imports**: the canonical module is top-level `aiochainscan_fastabi` (the separate
  `aiochainscan-fastabi` distribution, `aiochainscan[fastabi]` extra). Every import site
  tries it first and falls back to the legacy `aiochainscan.aiochainscan_fastabi`, so an
  old-layout editable checkout keeps working.
- **Arrow**: `decode_many_to_arrow` / zero-copy Polars export is behind the off-by-default
  `arrow` cargo feature (a small win next to network time — `docs/V1_PLAN.md` Track A).
  `decode.py:ARROW_AVAILABLE` reflects whether the loaded extension has it; build with
  `maturin develop --release --features arrow`.
