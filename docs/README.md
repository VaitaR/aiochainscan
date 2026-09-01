# Documentation

This directory contains user guides, design notes, and historical engineering
records for `aiochainscan`.

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
- [PyPI publishing](PYPI_PUBLISHING.md): maintainer release procedure.

## Reference

The current public surface is defined by:

- `aiochainscan.ChainscanClient`
- `aiochainscan.Method`
- the scanner support declarations in `aiochainscan/scanners/`

The repository does not currently generate a versioned API reference site.
Method signatures and scanner declarations in the source are authoritative when
a guide and the implementation differ.

## Engineering records

Files named `*_IMPLEMENTATION*.md`, `*_SUMMARY.md`, `AUDIT_*.md`,
`QA_REPORT_*.md`, and bug-fix reports document earlier development work. They
are retained as historical records, not as current product claims or setup
instructions.

Other technical notes, including [Streaming decoder](STREAMING_DECODER.md), may
describe the implementation at the time they were written. Verify their paths,
benchmarks, and status claims against the current source before relying on them.

Start with the [project README](../README.md) for installation and the supported
public API.
