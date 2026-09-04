---
kind: deepening-brief
id: C12
slug: merge-erc721-1155-twins
source: ../2026-09-03-review.md
status: done             # merged to local main as 0acc906 (2026-09-03); gate PASS-WITH-FINDINGS (2 LOW); lane commit e46d24b carries the normalize_items divergence note
base: 485b34c
---

# Merge the ERC-721/1155 twins

## Repo orientation

aiochainscan is an async Python wrapper over blockchain explorer APIs.
`core/mixins/account.py` carries the account-facing convenience methods on
`ChainscanClient`; each builds a params dict and calls `self.call(Method.…, **params)`.
`Method` is the enum of supported operations (`domain/method.py`); `Address`
(`domain/models.py`) validates and checksums an address string. Tests:
`uv run pytest tests/test_client_convenience.py tests/test_method_consistency.py -q`.

## Task

Replace the byte-identical 23-line bodies of `get_erc721_transfers`
(`account.py:150-172`) and `get_erc1155_transfers` (`account.py:174-196`) with one shared
implementation behind two one-line declarations, and align the pair with its siblings on
the two points where it has drifted.

## Contract

- Both public signatures stay EXACTLY as shipped — same names, params, defaults
  (`end_block: int | str = 99999999` is public API and does not change), same return type
  `JSONList`. Per-method docstrings stay.
- Sibling alignment, exactly two items (the wire-visible changes this brief intends):
  1. The `address` param is wrapped like the ERC-20 sibling does (`account.py:82-83`):
     `str(Address(address))`, and `contract_address` likewise when given
     (`:86`). Today the twins pass the raw string (`:162`, `:186`).
  2. The result coercion uses the shared `normalize_items` (as `get_nft_portfolio` does,
     `account.py:201`) instead of the inline `result if isinstance(result, list else []`.
- Everything else is behavior-neutral: same `Method` per method, same param names and
  conditional inclusion of `contract_address`, same page/offset/sort defaults.

## Edge cases

- `contract_address=None` → key omitted from params (as today, `:169-170`).
- `end_block=99999999` default → sent on the wire exactly as today (do NOT adopt the
  sibling's conditional-None shape — that would change the public default).
- Non-list API answer (error envelope already raised elsewhere) → `normalize_items`
  yields `[]`, same as the inline coercion did.
- A lowercase address input → forwarded checksummed (EIP-55); an invalid address raises
  from `Address()` exactly as it would on `get_token_transfers` today.

## Files

**Change:** `aiochainscan/core/mixins/account.py`, `tests/test_client_convenience.py`.
**Do not touch:** other mixins, `domain/method.py`, scanners, `core/streaming.py`,
`core/pool.py` (pool inherits the mixin; no pool code changes).

## Out of scope

No normalized/streaming variants for these two methods — new surface, not deepening. No
changes to the ERC-20 sibling or `get_transactions`. The `end_block` default asymmetry
stays (documented above); fixing it would be an API change.

## Verification

```bash
uv run pytest tests/test_client_convenience.py tests/test_method_consistency.py -q
make validate
```

Add one test: a stub client records forwarded params; call both methods with a
lowercase address and assert the wire param `address` is the EIP-55 checksummed form
(red today — the twins forward the raw string). Report command output verbatim.

## Definition of done

- The two method bodies are one-line delegations to a single private implementation;
  `diff`-ing the two method bodies shows no duplicated params-dict construction.
- The checksumming test exists, passes, and was shown red first.
- All verification green; commit locally, no push, no PR.

## Decisions already made

- Merge into a shared private helper on `AccountMixin` — not a decorator, not a spec
  table (these two methods are not streaming methods; `STREAMING_SPECS` does not apply).
- Keep both docstrings human-written per method; the helper gets its own one-liner.

## Open questions

- None material; if `normalize_items`'s coercion differs observably from the inline
  `isinstance` check on some fixture, keep the observable result of `normalize_items`
  and note the fixture in the commit message.
