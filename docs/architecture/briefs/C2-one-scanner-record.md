---
kind: deepening-brief
id: C2
slug: one-scanner-record
source: ../2026-09-03-review.md
status: accepted
base: 50d971e
---

# One per-scanner record in `chain_registry`; `config` derives

## Repo orientation

aiochainscan is an async Python wrapper for blockchain-explorer APIs. `chain_registry.py`
resolves `(scanner, network, api_key)` into a frozen `ScannerTarget` for
`ChainscanClient.from_config`; `config.py` (`ConfigurationManager`) resolves credentials/env
and builds scanner display definitions. Domain terms in `CONTEXT.md` — you need **Scanner**
and **ScannerTarget**. Tests: `uv run pytest tests/ -q`; type gate `uv run mypy aiochainscan
--strict`. The full gate is `make validate`.

## Task

Consolidate the seven name-keyed satellite tables in `aiochainscan/chain_registry.py` into
one frozen record per scanner, derive every lookup table from the records, validate
consistency at import, and make `config.py` stop hand-copying registry facts — while keeping
every public output byte-identical.

## Current state (all verified on `base`)

- Seven parallel tables keyed by scanner name: `DEFAULT_SCANNER_VERSIONS` (~:472),
  `SCANNER_CONFIG_IDS` (~:481), `BLOCKSCOUT_CONFIG_IDS` (~:486), `SCANNER_CONFIG_NETWORKS`
  (~:506), `SCANNER_NETWORK_ALIASES` (~:526), `SCANNER_API_KINDS` (~:552),
  `CUSTOM_BASE_URL_SCANNERS` (~:561).
- `BLOCKSCOUT_INSTANCE_HOSTS` (~:87-100) lists 12 instance aliases; `BLOCKSCOUT_HOSTS`
  (~:103-107) silently drops any whose `blockscout_*` key is missing from
  `URL_BUILDER_CURRENCIES` (~:55-81) — `zksync` is dropped today.
- `config.py:316-327` hand-copies 10 BlockScout display names; `config.py:331` raises a bare
  `KeyError` if a derived host id lacks a name. `config.py:278-312` hardcodes per-scanner
  domains that duplicate the hosts in `chain_registry.get_url_builder_profile` (~:113-251,
  11 code branches).
- `config.py:256-260` and `:527` lazily import from `chain_registry` (admitted cycle);
  `chain_registry.py:10` imports config at module level for credentials (delegation at
  `:588-605`).
- `core/client.py:246-249` calls `chain_registry.get_scanner_network_name` (~:817-846) — a
  second network-name translation, breaking `ScannerTarget`'s "client never re-derives"
  promise (`chain_registry.py:624-628`).

## Contract

1. **One record.** A frozen dataclass (e.g. `ScannerRecord`) in `chain_registry.py`, one
   instance per scanner kind, carrying: default version, config id, api kind, network alias
   map, supported networks, per-network hosts (BlockScout instances), custom-base-URL
   support, and the BlockScout display names. A module-level `SCANNER_RECORDS` holds them.
2. **Derive, don't duplicate.** The seven existing table names stay as module attributes
   (derived from the records) so no caller changes. `BLOCKSCOUT_HOSTS` derivation and
   `get_url_builder_profile`'s outputs must be byte-identical to today — the existing tests
   pin them. `get_url_builder_profile`'s 11 branches collapse into a per-kind profile table
   merged with the two computed families (V2, BlockScout), same outputs.
3. **Silent drops become declared.** Import-time validation: every `BLOCKSCOUT_INSTANCE_HOSTS`
   alias either lands in `BLOCKSCOUT_HOSTS` or is listed in an explicit
   `DROPPED_INSTANCE_ALIASES = frozenset({'zksync'})` with a one-line comment (today's zksync
   drop keeps the same behaviour — declared, not silent). Every derived host id must have a
   display name from the record — the `config.py:331` bare `KeyError` mode disappears.
4. **Break the cycle, one direction.** `config.py` keeps credential/env resolution and reads
   topology (hosts, display names, currencies) from the records; the `V2_QUERY_AUTH_API_KINDS`
   constant moves home to `chain_registry` (delete the lazy import at `config.py:527`);
   reduce the `config.py:256-260` lazy import to what genuinely remains, if anything. The
   registry's credential delegation to config (`chain_registry.py:588-605`) stays as is.
   Registry importing config at module level stays; config must not import registry at
   module level (lazy call-time only, ideally never).
5. **`ScannerTarget` carries `scanner_network`.** New field, populated in
   `resolve_scanner_target` with exactly what `get_scanner_network_name` computes today;
   `get_scanner_network_name` is deleted; `core/client.py:246-249` reads the field.

## Edge cases

- Behaviour must be byte-identical for every existing resolution: same URLs, same aliases,
  same api kinds, same versions, same custom-URL handling. The test suites
  (`tests/test_config.py`, `tests/test_scanner_target.py`) are the arbiter — do not weaken
  them.
- `zksync` stays dropped (declared) — do NOT make it live; that would change public surface.
- `blockscout_ethereum` alias maps to the same host as `eth` (both in `INSTANCE_HOSTS`) —
  preserve exactly whatever derivation produces today.
- `config.py`'s env-var credential priority order was recently unified — do not touch it.

## Files

**Change:** `aiochainscan/chain_registry.py`, `aiochainscan/config.py`,
`aiochainscan/core/client.py` (the one call site + `ScannerTarget` consumption),
`aiochainscan/core/types.py` only if `ScannerTarget` lives there (locate it first).
**Do not touch:** `aiochainscan/scanners/`, `aiochainscan/core/` beyond the named call site,
`aiochainscan/network.py`, `aiochainscan/mcp/`, credential resolution logic.

## Out of scope

- `MCP _SCANNER_HINTS` derivation (separate candidate C7 area); URL builder refactors beyond
  the profile table; any new public API.

## Verification

```bash
uv run pytest tests/test_config.py tests/test_scanner_target.py -q   # unchanged, green
uv run pytest tests/ -q                                               # full suite green
uv run mypy aiochainscan --strict
make validate
```

Add one test (in `tests/test_scanner_target.py` or a new `tests/test_chain_registry.py`):
every `BLOCKSCOUT_INSTANCE_HOSTS` alias is either derived into `BLOCKSCOUT_HOSTS` or listed
in `DROPPED_INSTANCE_ALIASES`; every derived host id has a display name. Prove it
non-vacuous: temporarily comment one currency entry out, show the test fails, restore.

## Definition of done

- `grep -n "SCANNER_CONFIG_IDS\s*[:=]" aiochainscan/chain_registry.py` shows a derivation
  from records, not a literal dict of scanner names.
- `grep -rn "get_scanner_network_name" aiochainscan/ tests/` is empty.
- `grep -n "from .chain_registry import" aiochainscan/config.py` — at most call-time lazy
  imports; `V2_QUERY_AUTH_API_KINDS` lives in `chain_registry.py`.
- All verification commands green; commit locally on the branch xworker created; no push,
  no PR.

## Decisions already made

- Records derive the existing tables; table names stay (zero caller churn) — source review C2.
- zksync drop is declared, not fixed (public surface unchanged).
- The cycle is broken in the topology direction only; credential delegation stays.

## Open questions

- If `ScannerRecord` collides with an existing name, pick a name from `CONTEXT.md`
  vocabulary and say which you chose.
