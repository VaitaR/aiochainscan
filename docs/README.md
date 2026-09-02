# Documentation

User guides, plans, and reference material for `aiochainscan`. The canonical
project guide is [`AGENTS.md`](../AGENTS.md) at the repo root; the scanner
method declarations in `aiochainscan/scanners/` are authoritative when a doc
and the implementation differ.

## User guides

- [SmartContract API](SMART_CONTRACT_API.md): verified ABI loading, proxy
  metadata, and decoded event or transaction iteration.
- [ENS integration](ENS_INTEGRATION.md): forward resolution, reverse lookup,
  caching, and provider limitations.
- [Progress callbacks](PROGRESS_CALLBACKS.md): reporting progress during
  paginated operations.
- [Streaming pattern](STREAMING_PATTERN.md): processing large histories without
  collecting every item in memory.
- [Migration guide](MIGRATION_GUIDE.md): moving from removed legacy entrypoints
  to `ChainscanClient`.
- [PyPI publishing](PYPI_PUBLISHING.md): maintainer release procedure for the
  two distributions (`aiochainscan` + `aiochainscan-fastabi`).

## Plans

- [V1_PLAN.md](V1_PLAN.md): v1 track plan — ground truth, decisions, and open
  items (referenced from `AGENTS.md`).
- [ROADMAP.md](ROADMAP.md): forward-looking feature plan.

## Reference

- [skill.md](skill.md): AI-agent skill card — scanner matrix, method surface,
  and usage rules in one compressed page.

## Review log

[`reviews/`](reviews/): review artifacts appended by tooling
(`INDEX.md` is generated — do not edit by hand).

---

One-time engineering records (February 2026 implementation summaries, bug-fix
reports, audits, QA snapshots) were removed in the 2026-09-02 docs
consolidation: their durable facts live in `AGENTS.md` and the guides above,
and the originals remain recoverable from git history.
