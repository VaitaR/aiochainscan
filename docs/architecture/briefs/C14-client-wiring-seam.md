---
kind: deepening-brief
id: C14
slug: client-wiring-seam
source: ../2026-09-05-review.md
status: done
base: c9943a2
merged: cf28d61
---

# A wiring seam for `ChainscanClient`

## Repo orientation

`aiochainscan` is an async Python wrapper over blockchain-explorer APIs. Domain terms
live in `CONTEXT.md`; the ones you need here:

- **ScannerTarget** — frozen dataclass + `resolve_scanner_target()` in
  `aiochainscan/chain_registry.py`. THE single resolution point turning
  `(scanner, network, api_key)` into names, credentials and a chain id. It is settled
  (a previous candidate established it) and this brief consumes it, never re-derives it.
- **Scanner** — per-explorer adapter in `aiochainscan/scanners/`.
- **Network** — the sole HTTP transport (`aiochainscan/network.py`). All HTTP goes
  through it; scanners never own sessions.

Entry point for users: `ChainscanClient.from_config(...)` in
`aiochainscan/core/client.py`. Tests are pytest under `tests/`. Full gate:
`make validate` (ruff, format check, import-linter, `mypy --strict`, pytest). One file:
`uv run pytest tests/test_scanner_fetch_page.py -q`.

## Task

Split resolution from wiring in `ChainscanClient`'s construction, so a caller can hand
in an already-built `Scanner` and `Network` instead of having them built inside
`__init__` — then convert the tests that currently bypass the constructor with
`ChainscanClient.__new__` to use the new seam, and collapse the eight copied
`FakeNetwork` doubles into one shared fixture.

## Why this is not cosmetic (read before starting)

`ChainscanClient.__init__` (`aiochainscan/core/client.py:100-249`) does two jobs. It
resolves a `ScannerTarget` (`:160-192`, with a carefully guarded `TypeError` contract),
and then it *constructs* three collaborators with no way to substitute them:

- `UrlBuilder` at `:207-209`
- `Network` at `:221-233`
- `Scanner` at `:238-246`

Only the leaf dependencies `rate_limiter` and `retry_policy` (`:112-113`) are
injectable, and they are threaded into a `Network` the client insists on building.

So tests skip the constructor entirely. `ChainscanClient.__new__(ChainscanClient)`
appears **11 times across 6 files** — `tests/test_scanner_fetch_page.py:99`,
`tests/test_token_holders.py:101,748`, `tests/test_iter_transactions_retry.py:61,78,227`,
`tests/test_blockscout_v2_coverage.py:191`, `tests/test_method_consistency.py:651,803,856`,
`tests/test_provider_pool.py:842` — each followed by hand-assignment of the private
attributes the skipped constructor would have set (`client._scanner = ...` at 15 sites).
Because `__new__` sets nothing, every such test carries only the attributes its own code
path happens to read, and a constructor change surfaces as an `AttributeError` in an
unrelated file.

The same missing seam is why the transport double is copied instead of shared: eight
test files each define their own `FakeNetwork` (`tests/test_blockscout_v1_ethrpc.py:28`,
`test_blockscout_v1_holders.py:22`, `test_blockscout_v2_coverage.py:160`,
`test_etherscan_input_limits.py:29`, `test_iter_transactions_retry.py:34`,
`test_new_spec_endpoints.py:20`, `test_scanner_fetch_page.py:36`,
`test_token_holders.py:51`) despite `tests/conftest.py` already existing and already
providing shared fixtures.

## Contract

A supported construction path taking a resolved target plus optional pre-built
collaborators. Shape (final signature is yours to choose; the guarantees are not):

```
ChainscanClient(target: ScannerTarget, *, scanner: Scanner | None = None,
                network: Network | None = None, ...existing kwargs...)
```

- `target` keeps its current meaning and is still trusted, not re-derived.
- `network=None` → the client builds one exactly as today (`client.py:221-233`),
  including the `first_request_guard` wiring when `target.expected_chain_id` is set.
- `scanner=None` → the client builds one exactly as today (`client.py:238-246`).
- When `network` is supplied and `scanner` is not, the built scanner receives the
  **supplied** network as its `network_client` — the connection-pooling relationship at
  `client.py:243` must hold whichever collaborator was injected.
- **Invariant: no partially-initialised instance is reachable through any supported
  path.** Every attribute `__init__` sets today (`client.py:192-249`:
  `_target`, `scanner_name`, `scanner_version`, `api_kind`, `network`, `api_key`,
  `base_url`, `chain_id`, `_expected_chain_id`, `_url_builder`, `_timeout`, `_proxy`,
  `_rate_limiter`, `_retry_policy`, `_network`, `_scanner`, `_ens_resolver`) is set on
  the new path too.
- **The existing public contract does not change.** `from_config`, the
  `chain`/`provider` keyword form, and every `TypeError` message at `client.py:160-192`
  behave exactly as before. Those messages are a deliberate migration contract.
- Supplying `scanner`/`network` together with the `chain`/`provider` resolution kwargs
  is allowed (resolution still happens first); supplying them is never *required*.

Then convert the callers:

1. All 11 `ChainscanClient.__new__(ChainscanClient)` sites use the new seam.
2. One `FakeNetwork` in `tests/conftest.py` replaces the eight copies. Six of them are
   the same class (records `calls`, pops from a `responses` list, raises an `Exception`
   member instead of returning it, plus `get`/`post` wrappers that add `method=`); the
   variants in `test_blockscout_v1_ethrpc.py:28` and `test_blockscout_v1_holders.py:22`
   take a **single** response replayed for every call and define no `get`/`post`. The
   shared double must serve both: accept either a list (consumed in order) or a single
   response (replayed), and expose `request`, `get` and `post`.

## Edge cases

- `expected_chain_id` set + injected `network`: the injected transport does **not** get
  the `first_request_guard` retro-fitted. Decide and state it — the honest options are
  to leave the caller responsible (document it) or to refuse the combination with a
  `TypeError`. Do not silently drop the guard without saying so.
- `target.base_url` (self-hosted BlockScout) must still reach both the `UrlBuilder`
  (`client.py:208`) and the scanner (`client.py:245`) on the default path.
- `ChainscanPool.from_config` builds member clients (`core/pool.py:373-428`) — it must
  keep working unchanged; it is a caller of this constructor.
- Some `__new__` sites set only `_scanner` and never `_network`
  (e.g. `tests/test_token_holders.py:101-108`). Converting them to a real construction
  will now give them a real `Network`. If a converted test starts making a live request,
  that is a bug in the conversion, not a reason to keep `__new__` — inject a
  `FakeNetwork`.
- `tests/test_method_consistency.py:651,803,856` builds clients in a sweep over every
  registered scanner. It must still cover every scanner after conversion; check the
  collected test count before and after and report both numbers.
- A `__new__` site you cannot convert is a **finding, not a silent skip**: report it
  with file:line and what blocked it.

## Files

**Change:** `aiochainscan/core/client.py` (constructor only), `tests/conftest.py`, and
the eight test files listed above.

**Delete:** the eight per-file `FakeNetwork` class definitions.

**Do not touch:** `aiochainscan/chain_registry.py`, `aiochainscan/scanners/`,
`aiochainscan/network.py`, `aiochainscan/core/pool.py`, `aiochainscan/core/mixins/`,
`aiochainscan/core/streaming.py`, `aiochainscan/mcp/`.

## Out of scope

- **Renaming or publishing `_scanner` / `_network`.** They stay private. This brief
  removes the *need* to reach for them, it does not bless it.
- **Re-deriving resolution.** `ScannerTarget` is the single resolution point; the new
  path consumes one. Do not add a second way to compute a chain id, api kind or network
  name.
- **The mixin host contract.** A sibling candidate (C13) declares what mixins need from
  their host. Do not add or change protocols here.
- **Widening `mypy`'s `files` to include `tests/`** (`pyproject.toml:144`).

## Verification

```bash
uv run pytest tests/test_scanner_fetch_page.py tests/test_token_holders.py \
              tests/test_iter_transactions_retry.py tests/test_method_consistency.py \
              tests/test_blockscout_v2_coverage.py tests/test_provider_pool.py -q
make validate
```

The observable, which is a count and not an impression — on `base` these are 11-across-6
and 8 respectively:

```bash
rg -c 'ChainscanClient\.__new__' tests/     # must return nothing
rg -c '^class FakeNetwork' tests/           # must return exactly one file: tests/conftest.py
```

> **Note (post-implementation).** The second observable is anchored at column 0 and so
> never saw a **nested** double: `tests/test_method_consistency.py:797` defines a
> function-local `FakeNetwork`, and `tests/test_provider_pool.py:819` a `_ReplayNetwork`.
> Neither was in this brief's list of eight and neither was consolidated. That is a gap in
> the observable, not in the work.

Prove the invariant is non-vacuous rather than assuming it. Add a test that builds a
client through the new seam with an injected scanner and network and asserts **every**
attribute named in the Contract's invariant list is present — then delete one assignment
from the constructor once, show the test failing, and restore it. Paste both runs.

Report the pytest collected-count for `tests/test_method_consistency.py` before and
after conversion; they must match.

Report command output, not a summary of it.

## Definition of done

- The new construction path exists with the contract above; the two `rg -c` commands
  return what the Verification section says.
- The invariant test fails when the constructor is broken — demonstrated, with output
  pasted.
- `make validate` passes in full.
- Two commits on one local branch: (1) the constructor seam plus the `__new__`
  conversions, (2) the `FakeNetwork` consolidation. Do not push, do not open a PR.

## Decisions already made

- Resolution and wiring are separated behind the class's own interface; no new public
  factory function outside `ChainscanClient` (source review, C14).
- `ChainscanClient.__new__` is never a supported construction path.
- The `FakeNetwork` consolidation is in scope — without it the seam is added but the
  duplication it explains stays — but it is a separate commit.

## Open questions

- Whether injected collaborators arrive as `__init__` keywords or as a dedicated
  classmethod is yours to decide. State which you chose and why in one line. The only
  hard requirement is that the existing public forms and their `TypeError` messages are
  untouched.
- If a shared `FakeNetwork` cannot serve all eight call sites without growing options
  nobody uses, say so and leave the outliers alone rather than over-generalising the
  double. Report which files you left and why.

"I could not do X" is a valid answer. An unmet item must be reported as unmet, not
interpreted away.
