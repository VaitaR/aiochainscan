---
kind: deepening-brief
id: C7
slug: generate-mcp-tool-layer
source: ../2026-09-03-review.md
status: accepted
base: 50d971e
---

# Generate the MCP tool layer from one spec

## Repo orientation

aiochainscan is an async Python wrapper for blockchain-explorer APIs. The MCP server
(`aiochainscan/mcp/`) exposes 12 tools as plain `client -> ToolResponse` functions in
`mcp/tools.py` (no mcp import — offline-testable), wired to FastMCP in `mcp/server.py`.
Domain terms in `CONTEXT.md` — you need **Scanner** and **Page cursor**. Tests:
`uv run pytest tests/test_mcp_server.py -q` (offline; FastMCP registration tests need the
`mcp` extra and are skipped in this worktree — that is expected). Gate: `make validate`.

## Task

Collapse the copy-pasted tool boilerplate into shared helpers, register the FastMCP layer
from one spec table, and canonicalize the ClientPool key — with the offline tool contract
byte-identical.

## Current state (verified on `base`)

- **Unsupported-method guard ×9** (`mcp/tools.py`): `_unsupported_notes` call sites at
  `:467, :515, :640, :685, :752, :839, :883, :959, :1031` — each a ~6-line
  `build_tool_response(data=None, notes=..., content_text='Cannot ...')` block. Two of the
  nine are inside `read_contract` (ABI and eth_call are separate capabilities).
- **Paginated skeleton ×3:** `:472-490` (`get_transactions`), `:644-663`
  (`get_token_portfolio`), `:764-816` (`get_token_holders`) — the same
  `clamp_page_size → params → decode_tool_cursor merge → client.fetch_page → curate
  items[:page_size] → _pagination(...) → '(more available).'/'(end of data).'` sequence.
- **ABI fetch-parse-degrade ×3:** `:609-617`, `:887-907`, `:963-979` (get ABI → orjson.loads
  if str → list check → degrade note), with three slightly different degrade messages.
- **Holder curation ×2:** `:774-783` and `:847-856` build the same
  `{'address': checksum, 'balance_raw': raw}` (+ optional formatted) entries.
- **`mcp/server.py:96-258`:** ~165 lines restating every tool's parameter list for FastMCP
  (compare `tools.py:453-461` vs `server.py:125-131`).
- **ClientPool keys on the caller's chain spelling:** `tools.py:129`
  `key = (resolved, network)` — `'eth'` vs `'ethereum'` vs `1` open parallel pools.

## Contract

1. **Shared helpers in `tools.py`** (private, no mcp import):
   - one unsupported-response helper replacing all nine guard blocks (parameterized by
     noun/method; `read_contract`'s two-capability case composes from it);
   - one paginated-fetch helper replacing the three skeletons — the trio's differences are
     exactly (Method, base params, curate function);
   - one `_fetch_verified_abi(client, contract) -> (abi, note)` used by the three sites —
     ONE degrade message wording for the same failure;
   - one holder-entry curator used by both loops.
2. **`server.py` registers from one table.** A module-level registration spec
   (tool name, the `tools.py` function, its params) replaces the ~165 lines of hand-written
   per-tool wrappers. FastMCP introspects signatures and docstrings for tool schemas — the
   generated registrations must expose EXACTLY today's tool names, parameter names, types
   and descriptions (FastMCP's `@mcp.tool()` decoration of the functions themselves, or an
   equivalent mechanism that preserves introspection, is acceptable — pick what keeps the
   registration tests' expectations).
3. **ClientPool canonical key.** Resolve the network to its canonical form (via
   `chain_registry`'s resolution — locate the existing canonical-alias function; do not
   build a new alias table) before keying; `'eth'`, `'ethereum'` and an alias map to one
   client pool.
4. **Offline contract byte-identical.** `tests/test_mcp_server.py` (96 tests, zero mocks,
   drives `mcp.tools` functions against a `StubClient`) must pass **unmodified**. Tool
   function signatures, curated field sets, caps, envelope payloads — unchanged.
5. **Curation policy centralized, values unchanged:** item caps (`:80-84`), page caps
   (`envelope.py:33-41`), truncation 512 — same numbers, fewer copies where duplication
   exists today.

## Edge cases

- `read_contract` needs TWO capability guards — the helper must compose, not assume one.
- The derived cursor whitelist `scanner_cursor_keys` (`:308-324`) is the pattern to imitate
  and must not be touched.
- Tools returning `notes` for unsupported methods must keep their scanner hints wording
  (tests pin it).
- If a tool's params genuinely differ per registration (e.g. optional enums), keep per-tool
  schema entries in the table — the table replaces copy-paste, not information.

## Files

**Change:** `aiochainscan/mcp/tools.py`, `aiochainscan/mcp/server.py`.
**Do not touch:** `aiochainscan/mcp/envelope.py` wire format, `aiochainscan/mcp/cursors.py`,
`aiochainscan/mcp_server.py`, `aiochainscan/core/`, `aiochainscan/scanners/`,
`tests/test_mcp_server.py` assertions.

## Out of scope

New tools; changing any tool's public parameters; `envelope.py` restructuring.

## Verification

```bash
uv run pytest tests/test_mcp_server.py -q          # unmodified, green
uv run pytest tests/ -q
make validate
```

FastMCP registration tests are `importorskip`-gated in this worktree — run them in the main
checkout only if the `mcp` extra is present there; otherwise state that they were not
executed (do not claim them).

## Definition of done

- `grep -c "_unsupported_notes(" aiochainscan/mcp/tools.py` — one definition, one call
  site (inside the helper).
- `server.py` shrinks by ~100+ lines; one registration table.
- Offline tests green unmodified; commit locally; no push, no PR.

## Decisions already made

- Helpers stay private in `tools.py`; tool functions remain plain functions (the runner
  wraps, never absorbs) — source review C7.
- ClientPool canonicalizes through the existing registry resolution, not a new table.

## Open questions

- If FastMCP's introspection rejects the generated registrations, fall back to keeping
  `server.py`'s explicit wrappers for the affected tool only and report it — do not change
  the tool's public schema to fit the generator.
