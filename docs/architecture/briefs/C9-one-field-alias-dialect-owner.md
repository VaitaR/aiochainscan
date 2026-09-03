---
kind: deepening-brief
id: C9
slug: one-field-alias-dialect-owner
source: ../2026-09-03-review.md
status: accepted
base: 3b7c05e
---

# One owner for the provider field-alias dialect

## Repo orientation

aiochainscan is an async Python wrapper over blockchain explorer APIs (Etherscan v2,
BlockScout v1/v2, NodeReal). Provider-native item dicts come in two shapes: Etherscan-style
camelCase keys with flat address strings (`blockNumber`, `timeStamp`, `from`), and
BlockScout-V2-style snake_case keys with nested address objects
(`block_number`, `timestamp`, `from: {'hash': ...}`). `domain/normalize.py` maps both onto
frozen dataclasses (`domain/normalized.py`); `CONTEXT.md` calls the accessor vocabulary the
**Provider field dialect**. Tests are pytest under `tests/`, run with
`uv run pytest <paths> -q`; the full gate is `make validate`.

## Task

Make `domain/normalize.py`'s field-access primitives the single owner of the provider
field-alias dialect, and turn the three satellite re-derivations (`services/analytics.py`,
`domain/contract.py`, `mcp/tools.py`) into consumers that import them.

## Contract

The shared primitives (today private in `normalize.py:84-124`) become the dialect's one
interface, exported from `domain/normalize.py`:

- alias-first lookup — first key whose value is not `None` and not `''`; a falsy `0`
  **survives** (today `_first`, `:84-89`)
- nested-address flattening — dict values tried against `('hash', 'address_hash',
  'address')`, flat strings pass through, everything else is `None` (today
  `_flat_address`, `:92-100`)
- int coercion — int passes, decimal-string and `0x`-hex-string parse, `bool` and
  unparseable yield a caller-supplied default (today `_int_or_none` `:113-124` plus the
  `default` parameter shape already used by `mcp/tools.py:177`)

Consumers:

- `services/analytics.py` builds DataFrame rows through the primitives. The schema dict
  written twice in one function (`:85-96` and `:124-133`) becomes one module-level
  constant used by both the empty-case and the populated-case return.
- `domain/contract.py` deletes its local `_string_field`/`_address_field`/`_int_field`
  (`:18-44`) and the inline alias pairs in `iter_events` (`:363-370`) / `iter_transactions`
  (`:419-447`), reading fields through the shared primitives instead.
- `mcp/tools.py` deletes its second `_int_field` (`:177`) and the hand-copied three-key
  loop (`:169-175`) and alias pairs (`:233-234`, `:246-259`, `:629`), importing the
  primitives.

Intended behavior changes — exactly these four, nothing else:

1. `analytics.py:111` and `:116` (`or`-fallthrough) → alias-first lookup: a
   BlockScout-V2 row with `block_number: 0` / `gas_used: 0` (int zero, falsy) keeps its
   zero instead of falling through to a missing key and yielding `None`.
2. `analytics.py:117` timestamp: missing-key-default → alias-first lookup; an absent-or-
   empty timestamp still lands as `''` (consumer default), an Etherscan pending row's
   `blockNumber: ''` becomes absent (`None`), not `''`.
3. `analytics.py:105-106`: single-key nested flatten → the three-key flatten (strictly
   wider, same result on real provider data).
4. The two files stop owning copies; grep-able: exactly one definition of each primitive
   in `aiochainscan/`, and the alias key-order `blockNumber`/`block_number` appears in
   code exactly once (inside `domain/normalize.py`).

All other outputs are byte-stable: MCP envelope dicts (golden registration test),
`DecodedEvent` field values (contract.py keeps its `0`/`''` defaults via the default
parameter), normalized dataclass models.

## Edge cases

- BlockScout V2 tx `{'block_number': 0, 'gas_used': 0, 'value': 123}` → DataFrame row
  keeps `0`, `0` (red today — write this test first).
- Etherscan pending tx `{'blockNumber': ''}` → `block_number` column null, not `''`.
- Contract-creation tx: Etherscan `to` is `''` or absent → `to_address` `''`; BlockScout
  V2 `to: null` → `''`.
- `value` given as `0x`-hex string parses (BlockScout V2 sends int, Etherscan decimal
  string; hex is tolerated, not required).
- `token_portfolio_to_dataframe` (`analytics.py:161-177`): `address_hash` vs `address`
  key pair tried in that order, `''` fallback — same result, now via the primitive.
- `bool` value where an int is expected yields the default, never `True`→`1`.

## Files

**Change:** `aiochainscan/domain/normalize.py` (export the primitives; no mapper logic
changes), `aiochainscan/services/analytics.py`, `aiochainscan/domain/contract.py`,
`aiochainscan/mcp/tools.py`, plus the matching test files.
**Delete:** nothing whole-file; the local helper definitions listed above.
**Do not touch:** `domain/normalized.py`, `core/streaming.py`, `services/pagination.py`,
scanner parsers under `scanners/` (provider-specific extraction, settled by the C3
holder-item work), `tests/mcp_registration_golden.json`.

## Out of scope

- `value_eth` as `Float64` (`analytics.py:92,115`) is a schema decision — leave it; the
  Wei columns already follow the string rule.
- Do not force one output type across mappers: dataclasses, DataFrame rows and envelope
  dicts share the accessor seam only.
- `mcp/server.py` and the registration table are C7 territory — untouched.

## Verification

```bash
uv run pytest tests/test_normalized_models.py tests/test_analytics.py \
  tests/test_contract_api.py tests/test_mcp_server.py tests/test_mcp_registration.py -q
uv run mypy aiochainscan --strict
make validate
```

Add to `tests/test_analytics.py`: a BlockScout-V2-shaped fixture tx with
`block_number: 0`, `gas_used: 0`, nested `from`/`to` objects, asserting the row keeps
both zeros and flattens both addresses. Prove it non-vacuous: it must fail against the
current `or`-fallthrough (state that you ran it red first, or show the failure output).
Report command output verbatim, not a summary.

## Definition of done

- `grep -rn "def _int_field\|def _int_or_none\|def int_or" aiochainscan/` finds exactly
  one definition, in `domain/normalize.py`.
- `grep -rn "blockNumber" aiochainscan/ | grep -v normalize.py` is empty.
- `analytics.py` declares its schema once.
- The new zero-survival test exists and passes; all verification green.
- Commit locally on the branch, no push, no PR.

## Decisions already made

- The primitives stay in `domain/normalize.py` — no new module (a bare re-export module
  would be a shallow seam).
- Naming: public (no leading underscore) with an `__all__`-style export list, or
  package-internal import — your choice, but pick names from `CONTEXT.md` vocabulary
  ("Provider field dialect") and stay consistent; say which you chose.
- `checksumming` (`_checksum_or_none`) stays a normalize-mapper concern — not part of the
  exported seam; analytics does not checksum today and must not start.

## Open questions

- If a consumer needs a subtly different absence rule than the primitive provides, do not
  fork the primitive — bring the rule into it and note the blast radius in the commit
  message.
