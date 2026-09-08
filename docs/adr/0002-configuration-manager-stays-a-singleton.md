# 0002 — ConfigurationManager stays a process-wide singleton

Status: accepted (2026-09-08)

## Context

`ConfigurationManager()` returns one process-wide instance, and a second
construction with a different `config_dir` warns and keeps the first binding.
The cost lands on tests: three test modules reset the singleton around each
case, and a forgotten reset leaks configuration into the next test.

Making construction hermetic would remove that cost, but `ConfigurationManager()`
returning the shared instance is public behaviour at 1.0.0: an embedder that
calls `register_scanner()` on one construction and reads it back from another
would silently stop seeing its own registration.

## Decision

The singleton is deliberate and stays. Hermetic construction is available as
`ConfigurationManager.create_isolated(config_dir)`, which never reads or becomes
the shared instance. Tests use it instead of resetting shared state;
`reset_instance()` and `reload()` remain the supported ways to rebind the
shared one.

## Consequences

- The `config_dir` mismatch warning stays — it is the singleton's contract, not
  a defect.
- A test needing its own configuration constructs one; no reset ritual, no
  cross-module leakage.
- Env precedence (`./.env.local` > `./.env` > `~/.aiochainscan/.env`, with
  `os.environ` outranking every file) is unchanged and applies to an isolated
  manager identically.
