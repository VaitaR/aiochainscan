---
kind: deepening-brief
id: C4
slug: nodereal-inside-base-seams
source: ../2026-09-03-review.md
status: accepted
base: 50d971e
---

# Bring NodeReal's transport back inside the base seams

## Repo orientation

aiochainscan is an async Python wrapper for blockchain-explorer APIs. The `Scanner` base
class (`aiochainscan/scanners/base.py`) owns the seams: `Scanner.call()` applies the error
ladder (`translate_unexpected_errors`) exactly once and dispatches through one mechanism;
concrete scanners override only dialect hooks (`_perform_request`, `_request_url`,
`_transport_headers`, `_error_context`). AGENTS.md forbids overriding `call()`. NodeReal
(`aiochainscan/scanners/nodereal.py`, JSON-RPC dialect) violates that in three linked ways.
Domain terms in `CONTEXT.md` — you need **Scanner** and **EndpointSpec**. Tests:
`uv run pytest tests/ -q`; gate `make validate`.

## Task

Remove NodeReal's `call()` override, give its `fetch_page` the error ladder, make its input
validations raise a `ChainscanClientError`-family exception, and fold the JSON-RPC wire-name
table into `SPECS` — with zero changes to what goes on the wire.

## Current state (verified on `base`)

1. `nodereal.py:1047-1052` overrides `call()` purely to post-filter transfer results
   (`_filter_transfer_items`); the same filter is applied a second time at `:1171` inside
   `_fetch_transfer_page` (which bypasses `call()`).
2. `nodereal.py:1054-1087` `fetch_page` applies NO error ladder (contrast
   `blockscout_v2.py:600`, which wraps its whole body in `translate_unexpected_errors`).
3. Input validations raise bare `ValueError` at `:347-349` (`_timestamp_param`),
   `:352-357` (`_closest_param`), `:360-368` (`_contract_creation_param`), `:456`
   (`_build_transfer_filter`'s "address is required"). Under `call()` the base ladder
   masks such errors into fake `ChainscanNetworkError(retryable=False)`
   (`base.py:87-88`); from `fetch_page` they escape raw — same mistake, two exception
   identities. The pool then misclassifies caller bugs as provider faults (AGENTS.md
   documents this exact hazard for `InputLimitExceededError`, whose `failure_kind` is
   `FATAL` for this reason).
4. `_WIRE_METHODS` (`:548-572`) is a full dict keyed identically to `SPECS` (`:581-829`);
   specs deliberately carry no wire name (`path` empty, `:578-580`).

## Contract

1. **Delete the `call()` override.** Move `_filter_transfer_items` into
   `_perform_request` (it receives the method and params) or the single shared request
   path, so the filter applies exactly ONCE on every path (`call()`, `fetch_page`, the
   window walk). After the change: `grep -n "async def call" aiochainscan/scanners/nodereal.py`
   finds nothing.
2. **Ladder on `fetch_page`.** Wrap the `fetch_page` body the way `blockscout_v2.py:600`
   does, so the ladder contract documented at `base.py:265-270` holds for this scanner too.
3. **FATAL argument errors.** New exception `ScannerArgumentError(ChainscanClientError)`
   in `aiochainscan/exceptions.py` with `failure_kind = FailureKind.FATAL` (copy the
   `InputLimitExceededError` pattern); raise it at the four validation sites instead of
   bare `ValueError`. Export it from `exceptions.py` (and the package root error namespace
   if peers are exported there — match `InputLimitExceededError` exactly).
4. **Wire names into SPECS.** Add optional field `wire_method: str | None = None` to
   `EndpointSpec` (`aiochainscan/core/endpoint.py`, frozen dataclass, default keeps every
   existing construction valid). NodeReal's rpc-dialect specs declare it; `_rpc_url`/`_rpc`
   read it from the spec; `_WIRE_METHODS` is deleted. Every rpc-dialect spec MUST declare
   `wire_method` — enforce with one test.
5. **Wire behaviour byte-identical.** Same JSON-RPC methods, same params, same parsing, same
   pagination cursors. The intended, changelog-worthy change is exception identity only:
   an invalid argument now raises `ScannerArgumentError` from BOTH `call()` and
   `fetch_page()`, and the pool classifies it `FATAL` (no failover, no cooldown).

## Edge cases

- The 1000-block window walk (`_resolve_window`/`_fetch_transfer_page`, `:1093-1188`) stays
  scanner-local and untouched — its inputs are the spec's declared `fromBlock`/`toBlock`
  sources, preserve that.
- `translate_unexpected_errors` re-raises `ChainscanClientError` untouched — so the new
  `ScannerArgumentError` survives both ladders unchanged.
- The declaration-agreement tests (`tests/test_nodereal.py:733-811`) read SPECS param_maps —
  they must pass unmodified.
- Do not weaken `tests/test_provider_pool.py` classification tests.

## Files

**Change:** `aiochainscan/scanners/nodereal.py`, `aiochainscan/exceptions.py`,
`aiochainscan/core/endpoint.py` (one field).
**Do not touch:** `aiochainscan/scanners/base.py` (the seams are correct; this brief fixes
the caller, not the base), `aiochainscan/scanners/_etherscan_like.py`, other scanners,
`aiochainscan/services/`, `aiochainscan/core/pool.py`.

## Out of scope

The shared JSON-RPC helper for BlockScout V1 + NodeReal (candidate C8); any base-class
change; `EtherscanLikeScanner`'s `InputLimitExceededError` placement.

## Verification

```bash
uv run pytest tests/test_nodereal.py tests/test_nodereal_holders.py tests/test_provider_pool.py -q
uv run pytest tests/ -q
make validate
```

New tests (in `tests/test_nodereal.py`): (a) invalid `closest=` raises
`ScannerArgumentError` from `call()` AND from `fetch_page()` — same type both paths;
(b) `classify_failure(ScannerArgumentError(...))` is `FATAL`; (c) every NodeReal spec whose
`param_style` is rpc declares a `wire_method`. Prove (a) non-vacuous: before the fix the two
paths raise different types (`ChainscanNetworkError` vs bare `ValueError`) — record that
once with a scratch check if you can, else state it.

## Definition of done

- `grep -n "_WIRE_METHODS\|async def call" aiochainscan/scanners/nodereal.py` finds nothing.
- One filter application site; ladder present on `fetch_page`; four sites raise
  `ScannerArgumentError`.
- All verification green; commit locally; no push, no PR. Note the exception-identity
  change in the commit message body (user-visible).

## Decisions already made

- Filter folds into `_perform_request`, not a new hook — source review C4.
- New shared exception rather than reusing `InputLimitExceededError` (different meaning).
- `wire_method` on `EndpointSpec` rather than a parallel table.

## Open questions

- If folding the filter into `_perform_request` meets an obstruction (e.g. it lacks the
  parsed spec), apply it at the one seam that both `call()` and the window walk route
  through — but NEVER by re-adding a `call()` override. Report which seam you chose.
