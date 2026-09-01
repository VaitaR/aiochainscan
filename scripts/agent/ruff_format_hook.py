#!/usr/bin/env python3
"""PostToolUse hook — auto-format edited Python files with ruff.

Reads tool-use JSON from stdin. If the edited file is a *.py inside this
repo, runs `uv run ruff format` on it so the model never has to spend a
round-trip on formatting. Silent and best-effort: never blocks the edit,
never fails the tool call.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_input = payload.get('tool_input') or {}
    file_path = tool_input.get('file_path')
    if not file_path:
        return

    path = Path(file_path)
    if path.suffix != '.py' or not path.exists():
        return

    # Only format files inside the repo.
    try:
        path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return

    try:
        subprocess.run(
            ['uv', 'run', 'ruff', 'format', str(path)],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return


if __name__ == '__main__':
    # Fail open: a hook crash must never block or corrupt the tool result.
    try:
        main()
    except Exception:
        sys.exit(0)
