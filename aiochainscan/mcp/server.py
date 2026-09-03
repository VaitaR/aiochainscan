"""FastMCP wiring for the aiochainscan MCP server.

Registers the agent-facing tools from :mod:`aiochainscan.mcp.tools` on a
``FastMCP`` instance — every tool comes from ONE registration table
(``_TOOL_SPECS``: tool name, served docstring, MCP-visible parameters; the
``tools`` function of the same name is the dispatch target). The generated
wrapper reproduces exactly what FastMCP introspects (``__name__``,
``__doc__``, ``__signature__``), converts :class:`ToolResponse` envelopes
into MCP content blocks (compact ``content_text`` for text consumers + the
structured payload as ``structuredContent``), and pools one client per
``(scanner, chain)`` target for the lifetime of the server process.

This is the only module that imports ``mcp``; everything else in the package
works without the ``mcp`` extra.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

import orjson

try:
    from mcp.server.fastmcp import FastMCP
    from mcp.types import CallToolResult, TextContent

    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised via test_imports
    MCP_AVAILABLE = False

from . import tools
from .envelope import ToolResponse

__all__ = ['MCP_AVAILABLE', 'TOOL_NAMES', 'create_mcp_server']

_SERVER_INSTRUCTIONS = """\
aiochainscan MCP server — multi-scanner blockchain data for AI agents.

Conventions:
- Every tool returns an envelope: {data, notes, instructions, pagination}.
  `notes` carry limits/caveats, `instructions` suggest the next call, and
  `pagination.next_call` is a ready-to-execute follow-up when more pages exist.
- Values: Wei-scale amounts are exact strings; human-readable values sit next
  to `_wei`/`_raw` fields. Addresses are EIP-55 checksummed.
- `chain` accepts names ('ethereum', 'base'), numeric IDs (8453) or a
  self-hosted instance URL ('https://my-blockscout.internal').
- `scanner` overrides the data source: 'blockscout' (default, keyless),
  'blockscout_v2', 'etherscan' (needs ETHERSCAN_KEY), 'nodereal' (BSC).
- Tools are read-only and degrade honestly: missing scanner capabilities land
  in `notes` instead of failing the call.
"""


def _envelope_result(response: ToolResponse) -> Any:
    """Convert an envelope into an MCP CallToolResult (text + structured)."""
    payload = response.to_payload()
    text = response.content_text or orjson.dumps(payload).decode()
    return CallToolResult(
        content=[TextContent(type='text', text=text)],
        structuredContent=payload,
    )


@dataclass(frozen=True)
class _ToolParam:
    """One MCP-visible parameter: name, type and default (``empty`` = required)."""

    name: str
    annotation: Any
    default: Any = inspect.Parameter.empty


@dataclass(frozen=True)
class _ToolSpec:
    """One registration-table entry: the FastMCP-visible schema of a tool.

    ``name`` is also the exact name of the ``aiochainscan.mcp.tools`` function
    the tool dispatches to, ``doc`` is the served description and ``params``
    the MCP-visible parameter list in registration order.
    """

    name: str
    doc: str
    params: tuple[_ToolParam, ...]


_ADDRESS = _ToolParam('address', str)
_TX_HASH = _ToolParam('tx_hash', str)
_TOKEN_ADDRESS = _ToolParam('token_address', str)
_NAME_OR_ADDRESS = _ToolParam('name_or_address', str)
_FUNCTION_NAME = _ToolParam('function_name', str)
_CURSOR = _ToolParam('cursor', str | None, None)
_CHAIN = _ToolParam('chain', str, 'ethereum')
_SCANNER = _ToolParam('scanner', str | None, None)

# ``doc`` literals are dedented to the exact served description: FastMCP
# serves the raw ``__doc__`` of the registered wrapper, so the dedented text
# below IS what agents see. Keep the wording verbatim when editing.
_TOOL_SPECS: tuple[_ToolSpec, ...] = (
    _ToolSpec(
        name='get_wallet_balance',
        doc=dedent(
            """\
            Get the native coin (ETH/BNB/MATIC...) balance of a wallet.

            Returns Wei (exact string) and a human-readable amount. For ERC-20 or
            NFT holdings use get_token_portfolio / get_address_overview instead.
            """
        ),
        params=(_ADDRESS, _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='get_address_overview',
        doc=dedent(
            """\
            Composite address snapshot: balance, newest transactions, ERC-20 tokens and NFT collections.

            Runs all sub-queries concurrently; partial failures are reported in
            `notes` without failing the call.
            """
        ),
        params=(_ADDRESS, _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='get_transactions',
        doc=dedent(
            """\
            Get one page of an address's transactions (newest first), curated for context economy.

            Use pagination.next_call from the response to fetch subsequent pages.
            """
        ),
        params=(_ADDRESS, _CURSOR, _ToolParam('limit', int, 50), _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='get_transaction_info',
        doc=dedent(
            """\
            Get transaction details with the call input decoded via the contract ABI (fastabi).

            When the recipient contract is verified, decoded_input replaces the raw
            calldata; otherwise raw_input is kept (truncated) with an honest note.
            """
        ),
        params=(_TX_HASH, _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='get_token_portfolio',
        doc='Get ERC-20 token holdings of an address (one curated page, paginated).',
        params=(_ADDRESS, _CURSOR, _ToolParam('limit', int, 20), _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='get_token_info',
        doc=(
            'Get token metadata: name, symbol, decimals, total supply '
            '(raw + formatted), holder count.'
        ),
        params=(_TOKEN_ADDRESS, _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='get_token_holders',
        doc='Get token holders (one curated page) with human-readable balances and total counts.',
        params=(_TOKEN_ADDRESS, _CURSOR, _ToolParam('limit', int, 50), _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='get_top_token_holders',
        doc=(
            'Get the top-N holders by balance (order guaranteed; '
            'Etherscan PRO — needs scanner "etherscan").'
        ),
        params=(_TOKEN_ADDRESS, _ToolParam('limit', int, 100), _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='get_contract_abi',
        doc=dedent(
            """\
            Get a curated summary of a verified contract ABI: function/event signatures.

            read_contract fetches and applies the full ABI automatically — this
            tool is for discovery.
            """
        ),
        params=(_ADDRESS, _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='read_contract',
        doc=dedent(
            """\
            Call a view/pure contract function via auto-fetched ABI + eth_call, outputs decoded.

            No manual ABI needed: the verified ABI is fetched, the function found
            by name, arguments encoded and outputs decoded automatically.
            `args` is a JSON array string, e.g. '["0xabc...", 5]'; numeric strings
            coerce to ints, 0x-hex strings pass through for bytes arguments.
            """
        ),
        params=(
            _ADDRESS,
            _FUNCTION_NAME,
            _ToolParam('args', str, '[]'),
            _ToolParam('block', str, 'latest'),
            _CHAIN,
            _SCANNER,
        ),
    ),
    _ToolSpec(
        name='resolve_ens',
        doc="Resolve ENS both directions: 'vitalik.eth' -> address, or address -> ENS name.",
        params=(_NAME_OR_ADDRESS, _CHAIN, _SCANNER),
    ),
    _ToolSpec(
        name='list_chains',
        doc='List chains served by these tools, filterable by name/alias/chain-ID substring.',
        params=(_ToolParam('query', str | None, None),),
    ),
)

#: Tool names in registration order — derived from the table, never re-listed.
TOOL_NAMES = tuple(spec.name for spec in _TOOL_SPECS)


def _register_tool(mcp: Any, client_pool: tools.ClientPool, spec: _ToolSpec) -> None:
    """Register one table entry as a FastMCP tool.

    The wrapper reproduces what FastMCP introspects — ``__name__`` (tool
    name), ``__doc__`` (served description) and ``__signature__`` (input
    schema) — exactly as the previous hand-written wrappers did. Dispatch:
    ``chain``/``scanner`` select the pooled client and are forwarded to the
    ``tools`` function only when its signature routes them (the
    cursor-paginated trio); every other parameter passes through.
    """
    fn = getattr(tools, spec.name)
    accepts = inspect.signature(fn).parameters
    routes_context = 'chain' in accepts
    needs_client = 'client' in accepts

    async def _run(**call_kwargs: Any) -> Any:
        chain = call_kwargs.pop('chain', 'ethereum')
        scanner = call_kwargs.pop('scanner', None)
        if routes_context:
            call_kwargs['chain'] = chain
            call_kwargs['scanner'] = scanner
        if needs_client:
            client = client_pool.get(scanner, chain)
            return _envelope_result(await fn(client, **call_kwargs))
        return _envelope_result(fn(**call_kwargs))

    _run.__name__ = spec.name
    _run.__qualname__ = spec.name
    _run.__doc__ = spec.doc
    _run.__annotations__ = {
        **{param.name: param.annotation for param in spec.params},
        'return': Any,
    }
    # __signature__ drives FastMCP's input schema; not in typeshed, hence the ignore.
    _run.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [
            inspect.Parameter(
                param.name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=param.default,
                annotation=param.annotation,
            )
            for param in spec.params
        ],
        return_annotation=Any,
    )
    mcp.tool()(_run)


def create_mcp_server(pool: tools.ClientPool | None = None) -> Any:
    """Build the FastMCP server with all aiochainscan tools registered."""
    if not MCP_AVAILABLE:
        raise ImportError(
            'MCP not installed. Install with: pip install aiochainscan[mcp] or pip install mcp'
        )

    mcp: Any = FastMCP('aiochainscan', instructions=_SERVER_INSTRUCTIONS)
    client_pool = pool if pool is not None else tools.ClientPool()
    for spec in _TOOL_SPECS:
        _register_tool(mcp, client_pool, spec)
    return mcp
