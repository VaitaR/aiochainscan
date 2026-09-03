"""Registration guards for the table-generated MCP server.

Two independent guarantees:

- :class:`TestClientPoolCanonicalKey` — the pool keys clients on the
  registry-canonical network, so 'eth' / 'ethereum' share one client while
  URL-shaped instances and unknown names stay separate (offline, always run).
- :class:`TestGeneratedRegistrationSchema` — the served FastMCP surface
  (names, descriptions, JSON input schemas) stays byte-identical to the
  pre-generator hand-written contract recorded in
  ``tests/mcp_registration_golden.json``. Requires the ``mcp`` extra
  (same gating as ``TestFastMcpRegistration``); the golden was captured from
  that pre-generator surface, so any generator drift fails here.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from aiochainscan.mcp import tools as mcp_tools
from aiochainscan.mcp.server import TOOL_NAMES, create_mcp_server

_GOLDEN_PATH = Path(__file__).parent / 'mcp_registration_golden.json'


class _StubClient:
    """Minimal stand-in: schema listing never calls the tool; the dispatch
    tests either hit the unsupported-method guard path or a stubbed balance."""

    currency = 'ETH'
    scanner_name = 'stub'

    def supports_method(self, method: Any) -> bool:
        return False

    async def get_balance(self, address: str) -> str:
        return '1500000000000000000'

    async def close(self) -> None:
        return None


def _recording_pool(created: list[tuple[str, str]]) -> mcp_tools.ClientPool:
    def factory(scanner: str, network: str) -> _StubClient:
        created.append((scanner, network))
        return _StubClient()

    return mcp_tools.ClientPool(factory=factory)  # type: ignore[arg-type]


class TestClientPoolCanonicalKey:
    async def test_alias_spellings_share_one_client(self) -> None:
        created: list[tuple[str, str]] = []
        pool = _recording_pool(created)
        first = pool.get('blockscout', 'eth')
        second = pool.get('blockscout', 'ethereum')
        third = pool.get('blockscout', 'main')
        assert first is second is third
        assert created == [('blockscout', 'ethereum')]
        await pool.aclose_all()

    async def test_different_scanners_and_chains_pool_separately(self) -> None:
        created: list[tuple[str, str]] = []
        pool = _recording_pool(created)
        one = pool.get('blockscout', 'ethereum')
        two = pool.get('etherscan', 'ethereum')
        three = pool.get('blockscout', 'gnosis')
        assert len({one, two, three}) == 3
        assert len(created) == 3
        await pool.aclose_all()

    async def test_url_and_unknown_networks_stay_separate(self) -> None:
        """URL-shaped instances and names outside the chain registry pass
        through uncanonicalized — one pool entry per spelling, factory sees
        the caller's value verbatim."""
        created: list[tuple[str, str]] = []
        pool = _recording_pool(created)
        pool.get('blockscout', 'https://a.example')
        pool.get('blockscout', 'https://b.example')
        pool.get('blockscout', 'not-a-chain')
        assert created == [
            ('blockscout', 'https://a.example'),
            ('blockscout', 'https://b.example'),
            ('blockscout', 'not-a-chain'),
        ]
        await pool.aclose_all()


class TestGeneratedRegistrationSchema:
    def _dumped_tools(self) -> list[dict[str, Any]]:
        pytest.importorskip('mcp')
        server = create_mcp_server(pool=_recording_pool([]))
        return [tool.model_dump(mode='json') for tool in asyncio.run(server.list_tools())]

    def test_tools_register_in_table_order(self) -> None:
        names = [tool['name'] for tool in self._dumped_tools()]
        assert names == list(TOOL_NAMES)

    def test_served_surface_matches_golden(self) -> None:
        """Names, descriptions, input/output schemas — byte-identical to the
        pre-generator registration surface."""
        golden = json.loads(_GOLDEN_PATH.read_text())
        assert self._dumped_tools() == golden

    def test_dispatch_consumes_chain_and_scanner(self) -> None:
        """The generated wrapper routes ``chain``/``scanner`` into the pool
        and forwards the tool's own parameters — keyword shapes the real
        ``tools`` functions accept."""
        pytest.importorskip('mcp')
        server = create_mcp_server(pool=_recording_pool([]))

        balance = asyncio.run(
            server.call_tool('get_wallet_balance', {'address': '0x' + '11' * 20})
        )
        assert balance.structuredContent is not None

        transactions = asyncio.run(
            server.call_tool(
                'get_transactions', {'address': '0x' + '11' * 20, 'chain': 'ethereum'}
            )
        )
        assert transactions.structuredContent is not None
