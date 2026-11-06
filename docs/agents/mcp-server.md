# MCP server (`aiochainscan/mcp/`)

Agent reference for the MCP adapter over `ChainscanClient`. Read it before touching
`aiochainscan/mcp/`, `mcp_server.py` or `mcpb/`. User-facing version:
[../MCP_SERVER.md](../MCP_SERVER.md). Run: `python -m aiochainscan.mcp_server` (requires
the `mcp` extra).

| File | Purpose |
|------|---------|
| `mcp/envelope.py` | `ToolResponse{data, notes, instructions, pagination, content_text}` + truncation (`{value_sample, value_truncated}`, 512 chars) + `format_units` (lossless int math; `decimals` clamped at 78 — the uint256 digit count — and float/non-int input returned unchanged) |
| `mcp/cursors.py` | Opaque Base64URL cursors wrapping `fetch_page` scanner cursors (`InvalidCursorError` with "start over" advice) |
| `mcp/tools.py` | Tools as plain `client -> ToolResponse` functions (**no mcp import** — offline-testable) + `ClientPool` (one client per `(scanner, chain)`, connection pooling across calls) |
| `mcp/server.py` | FastMCP wiring: envelope → `CallToolResult` (text + structuredContent), tool registration |
| `mcp_server.py` | Entry point (historical import path preserved) |
| `mcpb/` (repo root) | MCPB bundle for Smithery's local-stdio listing: manifest + `pyproject.toml` pinning the published `aiochainscan[mcp]` release + `src/server.py`. Ships no library code; `server.type = "uv"`, so the host installs the pin |

**Tools**: `get_wallet_balance`, `get_address_overview`, `get_transactions`,
`get_transaction_info` (decoded input via auto-ABI), `get_token_portfolio`,
`get_token_info`, `get_token_holders`, `get_top_token_holders`, `get_contract_abi`
(signature summary), `read_contract` (auto-ABI + eth_call, outputs decoded),
`resolve_ens`, `list_chains`.

## Contract rules

- Curation caps: ≤50 items/page (`clamp_page_size`), curated field sets per tool.
- Pagination = one `client.fetch_page` call per response; `next_call.params` carries the
  new cursor — agents never parse cursors.
- Cursor allow-lists are derived, never hand-listed: each Scanner declares the cursor-key
  vocabulary it may emit per method (`Scanner.cursor_keys` for a uniform dialect,
  `Scanner.CURSOR_KEYS` per `Method`, read via `cursor_keys_for`), and `mcp/tools.py`'s
  `scanner_cursor_keys` unions those declarations over the registered scanners serving the
  method. No scanner-private cursor key names (`__nr_window`, `pageKey`, `address_hash`,
  ...) appear as literals in `mcp/tools.py` — a new scanner's keys are accepted by
  registering the scanner alone.
- Unsupported scanner methods → envelope `notes` (with scanner hints), never a crash;
  primary-call failures still raise (clean MCP error).
- Every ABI-consuming tool (`get_contract_abi`, `read_contract`, `get_transaction_info`'s
  input decode) resolves a proxy to its implementation before fetching the ABI and says so
  in `notes`. The probe costs one `CONTRACT_SOURCE` call and is best effort: a scanner
  that does not declare it leaves the tool on the proxy's ABI rather than failing.
  `read_contract` still sends `eth_call` to the PROXY address — only the ABI comes from
  the implementation. A diamond arrives as every facet's ABI merged, with the facet list
  (and any facet without a verified ABI) in `notes`. The tools stay on the default
  `proxy_strategy='metadata'`: on the keyless BlockScout default that already yields a
  diamond's facet list via `ImplementationAddresses`, and chain probes would multiply
  every tool's request count.
- Default scanner `blockscout` (keyless, v1); override per call (`scanner=`) or via
  `AIOCHAINSCAN_MCP_SCANNER`.
- `mcp/cursors.py` and `mcp/envelope.py` import WITHOUT the `mcp` extra — a contract: the
  FastMCP dependency lives only in `mcp/server.py`, so `mcp/__init__.py` must never import
  it (nor `tools.py`, which pulls the client). The sibling `onchain-research` router
  imports `encode_cursor`/`decode_cursor` and depends on that; enforced by
  `test_lightweight_mcp_imports_need_no_extra`. The cursor format stays this library's: a
  consumer needing its own fields forks the codec on its side.
- Tests: `tests/test_mcp_server.py` (offline stubs; FastMCP registration tests need
  `uv run --extra mcp pytest`), `tests/test_blockscout_v1_ethrpc.py`.
