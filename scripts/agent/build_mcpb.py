#!/usr/bin/env python3
"""Pack ``mcpb/`` into the ``.mcpb`` bundle Smithery distributes for stdio.

An ``.mcpb`` is a zip with ``manifest.json`` at the root. The bundle ships no
library code: ``mcpb/pyproject.toml`` pins a published ``aiochainscan[mcp]``
release and the host installs it with uv, so the only thing that can rot here
is the version pin — which is why packing refuses to run until every place
that states the version agrees.

Usage: ``make mcpb`` (or ``python scripts/agent/build_mcpb.py [--out DIR]``).
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = REPO_ROOT / 'mcpb'
SERVER_JSON = REPO_ROOT / 'server.json'

#: Never packed: build products of a local ``uv run --directory mcpb``.
EXCLUDED_DIRS = {'.venv', '__pycache__'}
#: ``.mcpbignore`` steers packing and is not part of the bundle — the
#: official ``mcpb pack`` leaves it out, and the archives must stay identical.
EXCLUDED_FILES = {'uv.lock', '.DS_Store', '.mcpbignore'}


def _dependency_pin(pyproject: dict[str, object]) -> str:
    """The ``aiochainscan[mcp]==X`` requirement the bundle installs."""
    project = pyproject['project']
    assert isinstance(project, dict)
    deps = [d for d in project['dependencies'] if str(d).startswith('aiochainscan[mcp]')]
    if len(deps) != 1:
        raise SystemExit(f'mcpb/pyproject.toml must declare exactly one aiochainscan pin: {deps}')
    return str(deps[0])


def collect_versions() -> dict[str, str]:
    """Every place that states the bundle's version, keyed by where it lives."""
    manifest = json.loads((BUNDLE_DIR / 'manifest.json').read_text())
    pyproject = tomllib.loads((BUNDLE_DIR / 'pyproject.toml').read_text())
    server = json.loads(SERVER_JSON.read_text())
    package = server['packages'][0]
    from_arg = next(arg for arg in package['runtimeArguments'] if arg.get('name') == '--from')
    return {
        'mcpb/manifest.json version': manifest['version'],
        'mcpb/pyproject.toml version': pyproject['project']['version'],
        'mcpb/pyproject.toml dependency': _dependency_pin(pyproject).split('==', 1)[1],
        'server.json version': server['version'],
        'server.json packages[0].version': package['version'],
        'server.json --from argument': str(from_arg['value']).split('==', 1)[1],
    }


def bundle_files() -> list[Path]:
    """Files packed into the bundle, manifest first."""
    files = []
    for path in sorted(BUNDLE_DIR.rglob('*')):
        if not path.is_file():
            continue
        if EXCLUDED_DIRS.intersection(path.relative_to(BUNDLE_DIR).parts):
            continue
        if path.name in EXCLUDED_FILES:
            continue
        files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=str(REPO_ROOT / 'dist'), help='Output directory')
    args = parser.parse_args()

    versions = collect_versions()
    distinct = set(versions.values())
    if len(distinct) != 1:
        print('Version disagreement — fix before packing:', file=sys.stderr)
        for where, value in versions.items():
            print(f'  {value}  <- {where}', file=sys.stderr)
        return 1
    version = distinct.pop()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f'aiochainscan-{version}.mcpb'

    files = bundle_files()
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(BUNDLE_DIR).as_posix())

    print(f'{target} ({target.stat().st_size} bytes)')
    for path in files:
        print(f'  {path.relative_to(BUNDLE_DIR).as_posix()}')
    print(
        '\nValidate and publish:\n'
        f'  npx @anthropic-ai/mcpb validate {BUNDLE_DIR / "manifest.json"}\n'
        f'  smithery mcp publish {target} -n <namespace>/aiochainscan'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
