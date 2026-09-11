# Documentation

## Start here

1. [Getting started](GETTING_STARTED.md): install, first request, choosing a
   provider, the common recipes, and the limits to know before building on
   them.
2. [Examples](../examples/README.md): runnable scripts — the first three run
   against the published package with no checkout and no dev environment.
3. [Migration guide](MIGRATION_GUIDE.md): moving from the removed pre-1.0
   entrypoints to `ChainscanClient`.

## Guides

- [API reference](API_REFERENCE.md): providers, every common call, the
  normalized surface, self-hosted instances, value conversions, the CLI and the
  error taxonomy.
- [Pagination, completeness and failover](PAGINATION_AND_FAILOVER.md): what
  `guarantee_complete` promises, how ranges are split, and how `ChainscanPool`
  routes around a failing provider.
- [MCP server](MCP_SERVER.md): the 12 read-only agent tools and their response
  contract.
- [SmartContract API](SMART_CONTRACT_API.md): verified ABI loading, proxy
  metadata, and decoded event or transaction iteration.
- [ENS integration](ENS_INTEGRATION.md): forward resolution, reverse lookup,
  caching, and provider limitations.
- [Streaming pattern](STREAMING_PATTERN.md): processing large histories without
  collecting every item in memory.
- [Progress callbacks](PROGRESS_CALLBACKS.md): reporting progress during
  paginated operations.

## Reference

- [README](../README.md): what the library is for, installation, and the
  shortest end-to-end run.
- [Changelog](../CHANGELOG.md): released changes.
- [`skills/aiochainscan/`](../skills/aiochainscan/SKILL.md): the packaged
  Agent Skill — usage rules, [provider
  matrix](../skills/aiochainscan/references/provider-selection.md) and
  [recipes](../skills/aiochainscan/references/recipes.md). Install it with
  `npx skills add VaitaR/aiochainscan`; [SKILL_POINTER.md](SKILL_POINTER.md) is
  the pointer left behind by the move.
- [`context7.json`](../context7.json): what Context7 indexes for this
  repository and the API rules it hands to coding agents.

## Engineering and maintenance

These describe how the project is built and released, not how to use it.

- [`AGENTS.md`](../AGENTS.md): the contract for agents and contributors working
  *on* the codebase — architecture rules, provider measurements, invariants.
  The scanner declarations in `aiochainscan/scanners/` are authoritative when a
  doc and the implementation differ.
- [`CONTRIBUTING.md`](../CONTRIBUTING.md): contribution workflow.
- [PyPI publishing](PYPI_PUBLISHING.md): maintainer release procedure for the
  two distributions (`aiochainscan` + `aiochainscan-fastabi`).
- [V1_PLAN.md](V1_PLAN.md): v1 track plan — ground truth, decisions, open
  items.
- [ROADMAP.md](ROADMAP.md): forward-looking feature plan.
- `reviews/`: review artifacts appended by tooling; `INDEX.md` there is
  generated — do not edit by hand.

---

One-time engineering records (implementation summaries, bug-fix reports,
audits, QA snapshots) are removed once their findings land in the code and in
`AGENTS.md`; the originals remain recoverable from git history.
