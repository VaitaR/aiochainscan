# MCP server

<!-- mcp-name: io.github.VaitaR/aiochainscan -->

The `mcp` extra exposes the client to AI agents (Claude Desktop, Cursor, …)
over stdio with 12 read-only tools and an agent-friendly response contract.

```bash
pip install "aiochainscan[mcp]" && aiochainscan mcp   # installed
uvx --from "aiochainscan[mcp]" aiochainscan mcp       # without installing
```

In a client's config file that means `"command": "uvx"`, `"args":
["--from", "aiochainscan[mcp]", "aiochainscan", "mcp"]`.
`python -m aiochainscan.mcp_server` still works and starts the same server.

For clients that install extensions instead of editing config, `mcpb/` builds
an [MCPB bundle](https://github.com/modelcontextprotocol/mcpb) (`make mcpb`)
— the format [Smithery](https://smithery.ai/docs/build/publish) distributes
local stdio servers in. The bundle installs the pinned release with uv and
asks for the optional API keys in the client's UI.

## Tools

| Tool | What it does |
|---|---|
| `get_wallet_balance` | Native-coin balance (Wei string + human-readable) |
| `get_address_overview` | Composite snapshot: balance + newest txs + ERC-20 + NFTs (partial failures land in `notes`) |
| `get_transactions` | Curated transaction pages with opaque cursors |
| `get_transaction_info` | Tx details with the call input decoded via the verified ABI (fastabi) |
| `get_token_portfolio` | ERC-20 holdings (curated, paginated) |
| `get_token_info` | Token metadata, supply (raw + formatted), holder count |
| `get_token_holders` / `get_top_token_holders` | Holder pages with totals and human-readable balances |
| `get_contract_abi` | Verified-ABI summary (function/event signatures) |
| `read_contract` | `eth_call` with the ABI fetched automatically — no manual ABI input |
| `resolve_ens` | ENS in both directions |
| `list_chains` | Served chains with substring filter |

## Response contract

Every tool returns an envelope `{data, notes, instructions, pagination}` plus
a compact text summary. `notes` explain limits and caveats honestly (e.g. a
scanner that lacks an endpoint), `instructions` bridge to the next call, and
paginated tools ship a ready-to-execute `pagination.next_call` — the agent
never has to understand cursor internals.

Tools take a `chain` parameter (name, numeric ID, or a self-hosted instance
URL) and an optional `scanner` override. The default scanner is keyless
`blockscout` (`AIOCHAINSCAN_MCP_SCANNER` env override); `etherscan` covers
every chain but needs `ETHERSCAN_KEY`.

An agent that should *write code* against this library rather than query chains
wants the packaged Agent Skill instead — see the README section on writing code
with an AI agent.
