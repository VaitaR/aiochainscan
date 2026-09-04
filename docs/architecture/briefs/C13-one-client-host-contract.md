---
kind: deepening-brief
id: C13
slug: one-client-host-contract
source: ../2026-09-05-review.md
status: accepted
base: c9943a2
---

# One declared host contract for the client mixins

## Repo orientation

`aiochainscan` is an async Python wrapper over blockchain-explorer APIs (Etherscan,
BlockScout, NodeReal). Domain terms live in `CONTEXT.md`; the ones you need here:

- **Scanner** — per-explorer adapter in `aiochainscan/scanners/`, reached only through
  the injected **Network** transport (`aiochainscan/network.py`).
- **Port / Adapter** — interface in `aiochainscan/ports/`, implementation in
  `aiochainscan/adapters/`.

Two classes present the public surface, and both are built from the **same ten domain
mixins** in `aiochainscan/core/mixins/`:

- `ChainscanClient` (`aiochainscan/core/client.py:68-79`) — one provider.
- `ChainscanPool` (`aiochainscan/core/pool.py:256-267`) — failover across several
  `ChainscanClient`s.

Tests are pytest under `tests/`. Run the whole gate with `make validate` (ruff, ruff
format --check, import-linter, `mypy --strict`, full pytest). Run one file with
`uv run pytest tests/test_provider_pool.py -q`.

## Task

Replace the twelve partial, unenforced declarations of "what a mixin needs from its
host" with ONE `ClientHost` protocol that both `ChainscanClient` and `ChainscanPool`
are statically asserted to satisfy, and revert the `getattr` workaround in
`aiochainscan/services/ens_resolver.py` that the missing declaration forced.

## Why this is not cosmetic (read before starting)

`mypy --strict` currently checks none of this, and the repo's configuration
(`pyproject.toml:138-144`) has `files = ["aiochainscan"]`, so `tests/` are not
type-checked either. Two facts, both verified against this mypy configuration:

- `def method(self: _SomeProtocol)` is checked **at typed call sites only**. A host
  missing a member is reported where the method is *called*, not where the class is
  defined. Nothing inside `aiochainscan/` calls a pool mixin method, so the pool is
  checked nowhere.
- A bare class-level annotation on a mixin (`_scanner: Scanner`) is checked **nowhere
  at all** — it is inherited, so a host that never assigns the attribute type-checks
  clean.

That is how the live defect shipped: `ENSClient` (`services/ens_resolver.py:89-95`)
declares `network: str` as required; `ChainscanClient` assigns it (`core/client.py:199`);
`ChainscanPool` has no such member; and `ENSMixin` hands the resolver
`cast(Any, self)` (`core/mixins/ens.py:25`), erasing the declaration. Commit `8d4d839`
patched the resulting `AttributeError` with `getattr(self.client, 'network', None)` at
`services/ens_resolver.py:170`, `:217` and `:566`, so a pool user now reads
`Current network: None`. This brief must make the declaration true, then remove the
workaround.

## Contract

Add `ClientHost` — one protocol, one home. Suggested location:
`aiochainscan/core/host.py` (new). It must compose the existing streaming protocol
rather than restate it.

Members, all of them already provided by `ChainscanClient` and (after this brief) by
`ChainscanPool`:

| Member | Read by | Mutable? |
|---|---|---|
| `async def call(self, method: Method, **params: Any) -> Any` | all ten mixins (34 call sites) | n/a |
| `def supports_method(self, method: Method) -> bool` | `core/mixins/contracts.py` | n/a |
| `scanner_name: str` | `chain.py:78,82,86,94,144,145,146`, `account.py:27` | read-only |
| `scanner_version: str` | `chain.py:143` | read-only |
| `network: str` | `services/ens_resolver.py` (error text) | read-only |
| `chain_id: int \| None` | `chain.py:87,92,115`, `ens_resolver.py:146` | read-only |
| `_scanner: Scanner` | `chain.py:79,84,144,145`, `ens.py:41` | read-only |
| `_network: Network` | `chain.py:84,92` | read-only |
| `_expected_chain_id: int \| None` | `chain.py:113,131` | read-only |
| `_ens_resolver: ENSResolver \| None` | `ens.py:20,24,29` | **mutable** (assigned) |
| streaming surface | `account.py`, `logs.py`, `token.py` | compose `SupportsStreaming` (`core/streaming.py:503`) — do not restate its members |

Typing rule that makes both hosts satisfy it (verified against this mypy version):
**declare a read-only member as a `@property` in the protocol.** A plain mutable
attribute on `ChainscanClient` satisfies a read-only protocol property, and the pool's
existing read-only forwards satisfy it too. Only `_ens_resolver` needs to be declared as
a plain (mutable) attribute, because `ENSMixin.ens` assigns it — both hosts already
provide a setter.

Then:

1. **Every mixin annotates `self: ClientHost`**, including `ChainMixin` and `ENSMixin`,
   which today use bare class annotations (`chain.py:45-51`, `ens.py:14-16`). Delete
   those annotations and the eight private per-mixin protocols
   (`account.py:26-29`, `blocks.py:21-22`, `contracts.py:16-17`, `logs.py:21-22`,
   `proxy.py:10-11`, `stats.py:11-12`, `token.py:19-20`, `transactions.py:14-15`).
2. **`ENSResolver` takes `ClientHost`**, not `Any`. Delete `cast(Any, self)` at
   `core/mixins/ens.py:25`. `ENSClient` (`services/ens_resolver.py:89-95`) is then a
   duplicate of a subset of `ClientHost` — replace its use with `ClientHost` and delete
   it, unless the import direction forbids it (see *Open questions*).
3. **Revert the workaround**: `services/ens_resolver.py:170`, `:217`, `:566` go back to
   a plain `self.client.network` read.
4. **`ChainscanPool` gains `network`**, forwarding to `_active_client` like its
   neighbours in `core/pool.py:1107-1187`.
5. **Static conformance assertion for both hosts**, so a future missing member is a
   `mypy --strict` failure on the package and not an `AttributeError` in a user's
   process. A `TYPE_CHECKING`-guarded assignment is enough, e.g. at the bottom of
   `core/client.py` and `core/pool.py`:

   ```python
   if TYPE_CHECKING:  # pragma: no cover - static conformance only
       def _assert_client_host(c: ChainscanClient) -> None:
           _host: ClientHost = c
   ```

## Edge cases

- **Mixin-private helpers.** `ChainMixin._instance_label` (`chain.py:141-146`) and
  `ENSMixin._ens_address_info_scanner` (`ens.py:31-44`) are defined by a mixin and used
  only inside it. With `self: ClientHost` they are no longer visible on `self`. Make each
  a **module-level function taking the host** (`def _instance_label(host: ClientHost) -> str`)
  rather than adding it to the protocol — the protocol is the *host* contract, not a
  registry of mixin internals. Behaviour must not change.
- **`_StreamHost`** (`core/streaming.py:399-409`) is a third host protocol, declaring
  `_stream_fetch` and `_guard_block_range`. It is consumed by the shared streaming body,
  not by mixins. Leave it where it is; do not merge it into `ClientHost` and do not
  widen it.
- **Import cycles.** `core/host.py` importing `Scanner`, `Network` and `ENSResolver`
  for annotations must use `if TYPE_CHECKING:` imports, as `chain.py:15-19` already
  does. `import-linter` runs in `make validate` and will fail on a real cycle.
- **`ProviderPoolExhaustedError` paths.** Adding a `network` property to the pool must
  not change what `_active_client` returns before the first success — it is
  `self._providers[0].client` (`core/pool.py:1110-1114`). Do not alter that fallback.
- **`ENSResolver.__str__`** (`services/ens_resolver.py:566`) is exercised by tests;
  after the revert it must print the real network for both hosts.
- A member you find is needed but is not in the table above: **add it to `ClientHost`
  and say so in your report.** Do not reintroduce a per-mixin protocol for it.

## Files

**Change:** `aiochainscan/core/host.py` (new), `aiochainscan/core/mixins/*.py` (all ten
plus `__init__.py` if exports change), `aiochainscan/core/client.py` (conformance
assertion only), `aiochainscan/core/pool.py` (`network` property + conformance
assertion), `aiochainscan/services/ens_resolver.py`.

**Delete:** the eight private per-mixin protocols; the bare host annotations in
`chain.py` and `ens.py`; `ENSClient` if it becomes a duplicate.

**Do not touch:** `aiochainscan/scanners/`, `aiochainscan/network.py`,
`aiochainscan/services/pagination*.py`, `aiochainscan/mcp/`,
`core/streaming.py` beyond importing `SupportsStreaming`.

## Out of scope

- **The pool's routing behaviour.** Sticky selection, cooldowns, `classify_failure`,
  pinned pagination (`core/pool.py:106-690`) are settled and unrelated. The only pool
  change here is one new forwarding property plus the conformance assertion.
- **Making `_scanner` / `_network` public.** This brief *declares* them; it does not
  rename or publish them. A separate candidate (C14) covers construction.
- **Type-checking `tests/`.** Widening `files` in `pyproject.toml:144` is a bigger
  decision with its own fallout; do not do it here.

## Verification

```bash
uv run pytest tests/test_provider_pool.py tests/test_ens_resolver.py -q
make validate
```

Add `tests/test_client_host_contract.py` asserting the contract is real for the pool,
which is the host that was never checked:

1. Build a `ChainscanPool` (see `tests/test_provider_pool.py` for the existing
   construction pattern) and read **every** member of `ClientHost` off it, including
   `network` — that read raises `AttributeError` on `base` and must pass after.
2. Assert `ENSResolver`'s unsupported-network message contains the real network string
   for a pool host, not `None`. On `base` this test fails with `None` in the message;
   that is the non-vacuity proof for the revert.

Prove the static guard is non-vacuous rather than assuming it: temporarily delete the
`network` property from `ChainscanPool`, run `uv run mypy --strict aiochainscan`, and
confirm it now reports an error naming `ChainscanPool`. Restore it, re-run, confirm
clean. **Report both mypy outputs verbatim** — a conformance assertion that does not
fail when violated asserts nothing, and this is the one claim the whole brief rests on.

Report command output, not a summary of it.

## Definition of done

- `ClientHost` exists in one file; `rg -n 'ClientProtocol' aiochainscan/core/mixins/`
  returns nothing; `rg -n 'cast\(Any, self\)' aiochainscan/` returns nothing;
  `rg -n "getattr\(self\.client, 'network'" aiochainscan/` returns nothing.
- Both hosts carry a static conformance assertion, and removing a member from either
  one makes `mypy --strict` fail — demonstrated, with output pasted.
- `make validate` passes in full.
- Commit locally on a branch. Do not push, do not open a PR.

## Decisions already made

- One protocol for both hosts, not one per mixin (source review, C13).
- Read-only members are declared as protocol properties; this is what lets a plain
  attribute on the client and a read-only forward on the pool both satisfy it.
- Mixin-private helpers become module-level functions taking the host, rather than
  joining the protocol.
- `_StreamHost` and `SupportsStreaming` stay as they are; `ClientHost` composes the
  latter.

## Open questions

- If moving `ENSClient` to `ClientHost` would make `aiochainscan.services` import
  `aiochainscan.core` — forbidden by the import-linter contract at
  `pyproject.toml:191-200` ("Services do not import core or network") — then **keep
  `ENSClient` as the services-side protocol** and instead make it structurally identical
  to the subset of `ClientHost` it needs, with a comment naming `ClientHost` as the
  authority. Say in your report which of the two you did and why. Do not weaken the
  import-linter contract to get the merge.
- If a mixin needs a member that neither host provides, that is a finding, not a
  blocker: report it as unmet with the file:line, and do not invent a host attribute
  to satisfy it.

"I could not do X" is a valid answer. An unmet item must be reported as unmet, not
interpreted away.
