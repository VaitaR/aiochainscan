---
kind: deepening-brief
id: C3
slug: holder-item-one-owner
source: ../2026-09-03-review.md
status: accepted
base: 50d971e
---

# Give the token-holder item contract one owner

## Repo orientation

aiochainscan is an async Python wrapper for blockchain-explorer APIs. `TOKEN_HOLDERS` is the
one `Method` with a normalized cross-scanner item shape: `{'address': EIP-55 str, 'value':
str}` (raw-unit quantity). Four scanner parsers each re-implement that tail today. Domain
terms in `CONTEXT.md` — you need **Scanner**. Tests: `uv run pytest tests/ -q`; gate
`make validate`.

## Task

Extract the shared item-shape construction into one factory in `aiochainscan/scanners/base.py`
so the four parsers keep only their provider-specific field extraction, and remove BlockScout
V2's duplicate second application.

## Current state (verified on `base`)

- `aiochainscan/scanners/etherscan_v2.py:26-59` `_parse_token_holders` — extraction of
  `TokenHolderAddress`/`TokenHolderQuantity`, then checksum + coerce + dict.
- `aiochainscan/scanners/blockscout_v1.py:44-67` — same tail, different source fields.
- `aiochainscan/scanners/blockscout_v2.py:112-141` — `_normalize_token_holder_entry` +
  `_parse_token_holders` (nested `address.hash`); AND the same normalization applied a
  second time inline in `fetch_page` at `:607-608` (comment at `:605-606` admits it).
- `aiochainscan/scanners/nodereal.py:176-198` — `accountAddress`/`tokenBalance` (hex →
  decimal conversion happens in extraction), same tail; docstring `:182-184` points at the
  other three as the reference.
- `aiochainscan/scanners/base.py:51-58` already shares `checksummed_holder_address`.

## Contract

1. **One factory.** New `holder_item(address: Any, value: Any) -> dict[str, Any]` in
   `scanners/base.py` next to `checksummed_holder_address`: returns
   `{'address': checksummed_holder_address(address), 'value': <value as str, None → '0'>}`.
   Match the existing coercion semantics EXACTLY — read all four current tails first and
   make the factory reproduce them; where they differ, keep each parser's behaviour by doing
   provider-specific coercion in its extraction and passing the resolved value to the factory.
2. **Parsers keep only extraction.** Each of the four parsers maps its provider fields and
   calls `holder_item`. Per-provider lenience (junk fields, missing keys) stays in the
   extraction, unchanged.
3. **BlockScout V2: one extraction.** The inline re-normalization in `fetch_page`
   (`:607-608`) is replaced by reuse of the same normalization entry point the SPECS parser
   uses — one code path for the endpoint, `call()` and `fetch_page()` outputs stay identical
   (the existing tests pin both).
4. **Byte-identical outputs.** Every existing test that pins holder items must pass
   unmodified. No wire/request changes.

## Edge cases

- Nodereal's hex `tokenBalance` → decimal-string conversion is extraction, not factory work.
- Etherscan's `TokenHolderQuantity` default-to-`'0'` behaviour must survive exactly.
- Do not touch `TOKEN_TOP_HOLDERS` semantics or `TOKEN_HOLDER_COUNT` parsing.
- Do not change the SPECS entries (parsers are referenced from specs; keep the same parser
  names/signatures so specs don't change).

## Files

**Change:** `aiochainscan/scanners/base.py` (factory + export),
`aiochainscan/scanners/etherscan_v2.py`, `aiochainscan/scanners/blockscout_v1.py`,
`aiochainscan/scanners/blockscout_v2.py`, `aiochainscan/scanners/nodereal.py` (parser
bodies only).
**Do not touch:** SPECS dicts, `fetch_page` cursor logic (beyond the V2 normalization reuse),
`core/`, `services/`, `mcp/`, `tests/` (unless a test imports a deleted private helper —
then update the import, not the assertion).

## Out of scope

Any other scanner-layer change (candidates C4/C8 own those files' other regions).

## Verification

```bash
uv run pytest tests/test_token_holders.py tests/test_nodereal_holders.py -q
uv run pytest tests/ -q
make validate
```

Add one test (extend `tests/test_token_holders.py`): `holder_item` directly — checksums the
address, stringifies the value, `None` value → `'0'`, and the four scanners' parsed outputs
still carry exactly the keys `{'address', 'value'}`.

## Definition of done

- `grep -rn "matching.*_parse_token_holders\|matching.*_normalize_token_holder" aiochainscan/scanners/`
  finds no docstring cross-references (the contract no longer needs pointers).
- BlockScout V2 normalizes a holder entry in exactly one place.
- All verification green; commit locally; no push, no PR.

## Decisions already made

- Factory on `scanners/base.py` beside `checksummed_holder_address` — source review C3.
- Behaviour byte-identical; no new public API beyond the module-level factory.

## Open questions

- If `holder_item` name collides, `token_holder_item` is the fallback — say which you chose.
