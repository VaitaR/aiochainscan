"""The MCPB bundle in ``mcpb/`` — Smithery's distribution format for stdio.

The bundle ships no library code: it pins a published ``aiochainscan[mcp]``
release and the host installs it with uv. What can rot is therefore the
metadata — the version stated in four places, and the tool list, which is a
copy of the registration table and must not outlive it.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from aiochainscan.mcp.server import TOOL_NAMES

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIR = REPO_ROOT / 'mcpb'
MANIFEST = json.loads((BUNDLE_DIR / 'manifest.json').read_text())
BUNDLE_PYPROJECT = tomllib.loads((BUNDLE_DIR / 'pyproject.toml').read_text())
SERVER_JSON = json.loads((REPO_ROOT / 'server.json').read_text())
PROJECT = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text())


def test_manifest_declares_the_uv_runtime_entry_point() -> None:
    server: dict[str, Any] = MANIFEST['server']
    assert server['type'] == 'uv'
    assert (BUNDLE_DIR / server['entry_point']).is_file()
    args = server['mcp_config']['args']
    assert args == ['run', '--directory', '${__dirname}', server['entry_point']]


def test_manifest_env_reads_only_declared_user_config() -> None:
    """Every ``${user_config.X}`` in the launch env is a declared option.

    An undeclared key substitutes to nothing, so the API key would silently
    never reach the server.
    """
    env: dict[str, str] = MANIFEST['server']['mcp_config']['env']
    declared = set(MANIFEST['user_config'])
    referenced = {
        value.removeprefix('${user_config.').removesuffix('}')
        for value in env.values()
        if value.startswith('${user_config.')
    }
    assert referenced
    assert referenced <= declared


def test_manifest_tool_list_matches_the_registration_table() -> None:
    assert tuple(tool['name'] for tool in MANIFEST['tools']) == TOOL_NAMES
    assert all(tool['description'] for tool in MANIFEST['tools'])


def test_every_stated_version_agrees() -> None:
    """The package, the bundle, its pin and ``server.json`` state one version.

    A bundle pinning a different release than the MCP Registry entry installs
    different code than the registry advertises — and a pin ahead of the
    package version names a release that does not exist on PyPI.
    """
    package = SERVER_JSON['packages'][0]
    from_argument = next(
        argument for argument in package['runtimeArguments'] if argument.get('name') == '--from'
    )
    (dependency,) = (
        requirement
        for requirement in BUNDLE_PYPROJECT['project']['dependencies']
        if requirement.startswith('aiochainscan[mcp]')
    )
    stated = {
        PROJECT['project']['version'],
        MANIFEST['version'],
        BUNDLE_PYPROJECT['project']['version'],
        dependency.split('==', 1)[1],
        SERVER_JSON['version'],
        package['version'],
        str(from_argument['value']).split('==', 1)[1],
    }
    assert len(stated) == 1, stated


def test_bundle_project_is_not_packaged() -> None:
    """uv must install the pinned release, not build the bundle directory."""
    assert BUNDLE_PYPROJECT['tool']['uv']['package'] is False
