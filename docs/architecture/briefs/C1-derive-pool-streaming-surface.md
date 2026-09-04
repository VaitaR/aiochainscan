---
kind: deepening-brief
id: C1
slug: derive-pool-streaming-surface
source: ../2026-09-03-review.md
status: done
base: a458aae
---

# Derive the pool's streaming surface from `STREAMING_SPECS` (and fix the four broken pool methods)

> **Done** — implemented on `feat/derive-pool-streaming-surface` (commit `f1af137`), merged to
> `main` as `8e9bf4a` (2026-09-03). Review gate: PASS-WITH-FINDINGS, LOW-only findings, none
> blocking. Naming choice from Open Questions: `stream_normalized_batches` (recorded in the
> module docstring and `__all__`).

## Repo orientation

aiochainscan is an async Python wrapper for blockchain-explorer APIs (Etherscan, BlockScout,
NodeReal). The public entry points are `ChainscanClient` (one provider) and `ChainscanPool`
(multi-provider failover, same surface). Domain terms live in `CONTEXT.md`; the ones this brief
needs are **Scanner** (per-explorer adapter behind the client), **Streaming aggregation** (the
`get_all_*` / `iter_*` pagination surface) and **StreamSpec** (the one-row-per-stream declaration
registry in `aiochainscan/core/streaming.py`). Tests are pytest under `tests/`; run with
`uv run pytest tests/ -q`. Type gate is `uv run mypy aiochainscan --strict`.

## Task

Make the four `iter_*_normalized` streaming methods first-class registry rows derived from their
`iter_*_streaming` siblings, add the four missing pool forwards, and replace the consistency
sweep's `_normalized` exemption with real enforcement — so the pool's streaming surface can never
again drift from the client's. Four public `ChainscanPool` methods crash with `AttributeError`
today; they must work when this brief is done.

## The defect (verified on `base`)

`ChainscanPool` composes the same ten domain mixins as `ChainscanClient` (`core/pool.py:255-266`),
so it inherits the `get_all_*_normalized` aggregators — but the `iter_*_normalized` generators
they call are defined on `ChainscanClient` only (`core/client.py:704,774,844,925`) and the pool
never forwarded them. `await pool.get_all_transactions_normalized(addr)` raises
`AttributeError: 'ChainscanPool' object has no attribute 'iter_transactions_normalized'`
(call site: `core/mixins/account.py:319`; same for internal txs, token transfers, logs). The
sweep cannot see the gap: `tests/test_method_consistency.py:387` excludes names ending in
`_normalized`, and its `_RecordingClient` double stubs exactly those methods
(`tests/test_method_consistency.py:249-252`).

Existing machinery to build on, do not re-invent:

- `StreamSpec` + `STREAMING_SPECS` (`core/streaming.py:241-328`): 7 rows; a row carries name,
  `Method`, operation noun, params builder, flags (`ranged`, `item_level`,
  `completeness_routed`), and the `get_all_*` aggregator name.
- `stream_batches(host, spec, **kwargs)` (`core/streaming.py:368-387`): THE shared streaming
  body every client streaming method is a thin declaration over.
- `ChainscanPool._forward_stream(spec, **kwargs)` (`core/pool.py:742-780`): THE pinned forward
  every pool streaming method is a one-liner over (pinning, progress stamping,
  `guarantee_complete` forwarding, completeness routing — all read from the row).
- `tests/test_method_consistency.py:440-463` (`test_pool_stream_forwards_mirror_client_signatures`):
  iterates `STREAMING_SPECS` and asserts client signature == pool forward signature. It will
  start covering the twins the moment rows exist.

## Contract

1. **Registry rows.** `STREAMING_SPECS` grows from 7 to 11 rows. Each twin row
   (`iter_transactions_normalized`, `iter_internal_transactions_normalized`,
   `iter_token_transfers_normalized`, `iter_logs_normalized`) derives from its
   `iter_*_streaming` sibling — same `Method`, operation, `build_params` object, `ranged`,
   `item_level=False`, `completeness_routed=False` — via `dataclasses.replace` (or an equivalent
   factory in `core/streaming.py`), never by re-typing the sibling's literals. New per-row facts:
   `name` (sibling name + `_normalized`), `aggregate` (e.g. `get_all_transactions_normalized`),
   and a new `StreamSpec.normalizer: Callable[[JSONDict], Any] | None = None` field carrying the
   per-item mapper — `normalize_transaction`, `normalize_internal_transaction`,
   `normalize_token_transfer`, `normalize_log`, all imported from
   `aiochainscan.domain.normalize` (the client already imports them, `core/client.py`).
   The 7 raw rows get `normalizer=None` by the default.
2. **One shared implementation.** New `stream_normalized_batches(host, spec, **kwargs)` in
   `core/streaming.py`: `async for batch in stream_batches(host, spec, **kwargs): yield
   [spec.normalizer(item) for item in batch]`. Export it in `__all__`. The four client methods
   keep their exact signatures, return annotations (`AsyncIterator[list[Transaction]]` etc.) and
   docstrings, but their bodies become thin declarations over it, keyed by
   `STREAMING_SPECS_BY_NAME[<name>]` — same pattern as the raw streams
   (`core/client.py:692-702`).
3. **Pool forwards.** Four one-line forwards on `ChainscanPool`, exact mirrored signatures
   (copy the client's parameter list verbatim, `from __future__ import annotations` style
   already used in `pool.py`), each body `return self._forward_stream(
   STREAMING_SPECS_BY_NAME[<name>], **kwargs-by-name)`. Docstring: one line, "pinned per call",
   pointing at the client method. No other pool code changes.
4. **Sweep enforcement replaces the exemption.**
   - Delete `and not name.endswith('_normalized')` from
     `test_streaming_registry_declares_every_client_stream`
     (`tests/test_method_consistency.py:387`) and its docstring's exemption sentence.
   - Add the four names to `_STREAM_SWEEP_KWARGS` (`tests/test_method_consistency.py:482-494`)
     with the same kwargs as their siblings (`iter_logs_normalized` uses
     `{'address': CONTRACT_ADDRESS}`, the others `{'address': CHECKSUM_ADDRESS}`;
     `iter_token_transfers_normalized` also `contract_address`). The bidirectional guard at
     `:399` enforces exact set equality.
   - Add the four `get_all_*_normalized` aggregates to `_AGGREGATE_ARGS`
     (`tests/test_method_consistency.py:162-168`) with the same args as their raw counterparts.
     Without this the `INVOCATIONS` comprehension at `:173` raises `KeyError` at import — that
     is the guard doing its job; feed it.
5. **New parity test** in `tests/test_method_consistency.py`: enumerate the public instance
   callables (plain functions, coroutine functions, async-gen functions — the `vars()`-across-MRO
   walk, skipping `_`-prefixed names) of `ChainscanClient` and `ChainscanPool`, and assert
   (a) every client method exists on the pool and (b) `set(pool) - set(client)` equals exactly
   `{'provider_states', 'reset_cooldowns'}`. Classmethods are naturally outside this walk; do
   not widen it (`from_config` intentionally differs between the two classes).

Behaviour that must not change:

- Pinning semantics of the new forwards are whatever `_forward_stream` already does: provider
  chosen at generator start, failover only on first-page failure, mid-pagination errors cool the
  provider and propagate, `provider=<label>` stamped into `on_progress` (twins are batch-level,
  so stamping applies — correct).
- Wire behaviour: twins issue the same `fetch_page` params as their siblings (same
  `build_params`), so providers see identical requests.
- `guarantee_complete` accepted and forwarded by every new pool forward (asserted by the mirror
  test at `:461-463`).

## Edge cases

- `iter_transactions_normalized` has **no `abi` parameter** (unlike the item-level
  `iter_transactions`): its sibling is `iter_transactions_streaming`, whose builder is
  `_address_range_params`. Do not reuse `_transaction_item_params` (the item-level builder with
  the historical rangeless shortcut) for any twin.
- The `_RecordingClient` stubs at `tests/test_method_consistency.py:249-252` stay: the sweep
  double is not a `ChainscanClient` and legitimately fakes the streams. Real-class drift is the
  new parity test's job.
- `SupportsStreaming` (`core/streaming.py:414-543`) already declares the four twin members with
  typed returns — the pool satisfying the protocol afterwards is a consequence. Do not edit the
  protocol.
- A twin row's `build_params` must be the sibling's builder **object** (shared reference), so a
  future builder edit reaches both — that is the point of the derivation.

## Files

**Change:** `aiochainscan/core/streaming.py` (normalizer field, twin rows, shared
implementation, `__all__`), `aiochainscan/core/client.py` (4 method bodies → thin declarations),
`aiochainscan/core/pool.py` (4 forwards), `tests/test_method_consistency.py` (exemption removal,
2 table extensions, parity test), `tests/test_provider_pool.py` (regression test).
**Do not touch:** `aiochainscan/core/pool.py` routing engine (`_execute`, `_pinned_stream`,
`_guaranteed_pinned_stream`, cooldowns — `pool.py:489-686`), `aiochainscan/services/pagination*.py`,
`aiochainscan/core/mixins/` (the aggregators start working with zero mixin edits),
`aiochainscan/mcp/`, `aiochainscan/scanners/`, the 7 raw registry rows' behaviour.

## Out of scope

- Item-level normalized twins (`iter_transactions`/`iter_logs` have no normalized variant) —
  adding them is new surface, not drift repair.
- Signature generation for pool forwards from the registry — rejected deliberately: mypy
  `--strict` and IDE introspection need real, typed signatures; the registry drives behaviour
  and enforcement, not typing.
- `get_transactions_df`/`get_token_portfolio_df` pool restatements — separate concern, not this
  brief.

## Verification

```bash
# 1. the four methods exist on the pool (prints ok)
uv run python -c "from aiochainscan.core.pool import ChainscanPool as P; \
assert all(hasattr(P, n) for n in ('iter_transactions_normalized', \
'iter_internal_transactions_normalized', 'iter_token_transfers_normalized', \
'iter_logs_normalized')); print('ok')"

# 2. targeted suites green
uv run pytest tests/test_method_consistency.py tests/test_provider_pool.py \
  tests/test_normalized_streaming.py -q

# 3. full suite + gates (mirrors make ci-local)
uv run pytest tests/ -q
uv run mypy aiochainscan --strict
```

New tests to add (both must be shown failing on the unmodified tree first — run them before
implementing, record the output, then implement):

1. **Parity test** (see Contract §5). On the pre-fix tree it must fail listing exactly the four
   `iter_*_normalized` names — that failure output is the proof it is not vacuous.
2. **Pool regression test** in `tests/test_provider_pool.py`, parametrized over the four
   `get_all_*_normalized` aggregators: build a pool whose single member is a stubbed client
   (reuse the file's existing stub patterns), call the aggregator, assert it returns the
   normalized items instead of raising `AttributeError`. On the pre-fix tree it fails with the
   `AttributeError` quoted in this brief.

Report command outputs, not summaries of them.

## Definition of done

- `uv run python -c "from aiochainscan.core.streaming import STREAMING_SPECS; \
print(len(STREAMING_SPECS))"` prints `11`.
- `grep -n "endswith('_normalized')" tests/test_method_consistency.py` finds nothing.
- Twin rows carry the sibling's `build_params` by shared reference (assertable in the parity
  sweep or by inspection: same function object for sibling and twin).
- All verification commands green; parity + regression tests present and proven non-vacuous.
- Commit locally on a branch named `feat/derive-pool-streaming-surface`; do not push, do not
  open a PR.

## Decisions already made

- Twins become registry rows (not merely hand-added forwards): the registry is the checklist
  that lets the sweep exemption be deleted — that is the deepening, the forwards are the bug
  fix (source review, C1).
- Signatures stay hand-written on both classes; enforcement is by test, not by generation.
- Normalization happens per batch inside the member client's stream; the pool forwards kwargs
  verbatim and never normalizes.
- Contradicts nothing in `docs/adr/` (the directory does not exist).

## Open questions

- If `stream_normalized_batches` reads poorly next to `stream_batches`/`stream_items`,
  `stream_normalized` is an acceptable alternative — pick one and say which in the commit
  message.
- If the parity test's MRO walk surfaces a client method you believe should stay client-only,
  do not silently allowlist it: report it — the allowlist in Contract §5 is closed on purpose.
