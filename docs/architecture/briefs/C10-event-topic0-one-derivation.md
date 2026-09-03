---
kind: deepening-brief
id: C10
slug: event-topic0-one-derivation
source: ../2026-09-03-review.md
status: accepted
base: 3b7c05e
---

# Event topic0 through one derivation

## Repo orientation

aiochainscan is an async Python wrapper over blockchain explorer APIs. `domain/contract.py`
holds `SmartContract`, the high-level contract API (`iter_events`, `iter_transactions`,
`from_address` proxy detection). Event filtering needs the keccak topic0 of an event's
canonical signature (`name(type1,type2)` → `0x…`); `aiochainscan/crypto.py` provides
`keccak_hex`, `decode.py` canonicalizes ABI types (`canonical_abi_type`). Tests are pytest
under `tests/`; run `uv run pytest tests/test_contract_api.py -q`.

**Precondition: STOP if C9 (`briefs/C9-one-field-alias-dialect-owner.md`) is not merged
into your base — it rewrites the same file's field helpers. Report and stop.**

## Task

Derive each event's topic0 exactly once inside `SmartContract`, and make `iter_events`
obtain its filter topic by reading the map the constructor builds instead of recomputing
the derivation verbatim.

## Contract

- `_build_lookup_maps` (`contract.py:137-160`) remains the one place in the file that
  turns an event ABI entry into a topic0 hash (`:156-160` today).
- The map state stops being write-only: production code reads it. Shape is yours — keep
  `_event_signature_map` (topic → event) and add the reverse direction, or store
  name → topic; `tests/test_contract_api.py:127` currently asserts
  `len(sample_contract._event_signature_map) == 2` — keep that assertion meaningful
  (update the attribute it reads if you rename, do not delete the coverage).
- `iter_events` (`:320-332`) gets its `topics = [topic0]` by lookup against that state —
  the `','.join(canonical_abi_type(...))` + `keccak_hex` expression must not appear in
  `iter_events` anymore.
- Behavior is byte-identical: same topic strings, same filter results, same ValueError on
  an unknown event name (`:324`), same treatment of anonymous events as today (the current
  code computes a topic for a named anonymous event too — preserve that, do not "fix" it).
- `decode.py`'s own derivation inside `_build_abi_index` (`decode.py:279-287`) is a
  different cache with a different lifetime (process-wide, content-keyed) — it stays
  untouched and unmerged.

## Edge cases

- Event with no inputs: `Transfer()` → topic0 of the empty-paren signature — must equal
  what the current code produces (it does today via the same join; keep it that way).
- Duplicate event names with different signatures (overloads): today the LAST one wins in
  `_event_signature_map` and `get_event_abi` finds the first in `_event_map` — preserve
  today's behavior exactly, whatever it is; note it in the commit message if you had to
  think about it.
- Anonymous events are excluded from the map build (`:155`) — `iter_events('AnonymousThing')`
  then cannot find a topic; replicate today's outcome (ValueError from `get_event_abi`
  only if the name is absent from `_event_map`; an anonymous event IS in `_event_map`,
  so today it gets a computed topic — keep exactly this).

## Files

**Change:** `aiochainscan/domain/contract.py`, `tests/test_contract_api.py`.
**Do not touch:** `aiochainscan/decode.py`, `aiochainscan/crypto.py`,
`aiochainscan/core/mixins/logs.py`, anything under `scanners/`.

## Out of scope

`_function_map` and `_event_map` are fine as they are. Do not merge the per-contract maps
with decode's process-wide ABI index. Do not add caching layers.

## Verification

```bash
uv run pytest tests/test_contract_api.py -q
make validate
```

Add a test: for a known ABI (the module's existing fixtures), the topic `iter_events`
filters on equals the map entry for that event name — assert via the public path (stub
the client iterator and capture the `topics` argument), not by calling the private
derivation. Report command output verbatim.

## Definition of done

- `grep -n "keccak_hex\|canonical_abi_type" aiochainscan/domain/contract.py` shows the
  derivation in exactly one method.
- Production code reads the topic map (the only remaining non-read reference would be a
  test).
- All verification green; commit locally, no push, no PR.

## Decisions already made

- The derivation stays inside `contract.py` (one site); it does NOT move behind decode's
  index — different cache lifetimes, and C6 deliberately gave decode.py a narrow seam.
- No behavior changes; this is a locality refactor plus dead-state removal.

## Open questions

- If the reverse-direction map makes `_build_lookup_maps` awkward, a tiny
  `_topic_for_event_name(name)` accessor over existing state is acceptable — one lookup
  seam, still one derivation site. Say which shape you chose.
