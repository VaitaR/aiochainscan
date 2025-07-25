<!------------------------------------------------------------------------------------
---
inclusion: always            # load for every request
priority: 10                 # keep room for project overrides (higher wins)
---

- use Avaluable mcp if needed

## ✦ Language rules  
- All code, comments, commit messages, branch names and generated filenames **MUST be in English**.  
- Chat replies may follow the user’s language, but any artefact written to disk must respect English‑only.  
  - *Reject* or *ask* if compliance is impossible.

## ✦ File‑generation guardrails  
1. **NO speculative files**  
   - Do **NOT** create new `*.test.*`, `*.md`, or `*-copy.*` files unless the user request explicitly says so.
   - Prefer patching existing files.  
2. **One‑document policy**  
   - When context about changes crititcal, append laconic, as short as possible to `instructions.md`; do not spawn additional docs.  
3. **Directory hygiene**  
   - Keep all source under `/src` (or project‑specific path supplied later). 

## ✦ Python coding guidelines  (global)
- Follow **PEP 8**; format = **Black** (line length = 88).
- All new code must pass **ruff**, **mypy --strict**, **pytest -q**.
- Use **type hints everywhere**, including variables (`x: int = 0`).
- Public API objects have **Google‑style docstrings** with examples.
- Prefer `async` + `httpx.AsyncClient` for I/O; avoid sync I/O inside async flows.
- Log via **structlog** (JSON); forbid bare `print`.
- Raise custom exceptions (`class ProviderError(Exception): ...`) instead of generic `Exception`.
- When adding functionality, **first** extend tests, **then** implement. 

## ✦ Commit conventions  
- **English, imperative** (e.g. `Add input validation for UserDAO`).  
- ≤ 72 chars summary, blank line, wrapped body if needed.

## ✦ Security & secrets  
- Never embed real keys or passwords. Use `"YOUR_API_KEY"` placeholders.  
- If a new secret is referenced, automatically add the filename to `.gitignore`.  

## ✦ Autopilot safety switches  
- Treat shell commands as **untrusted** unless they match the project’s `trustedCommands` list.  
- Prompt for confirmation before any bulk delete / rename affecting >10 files.

## ✦ Testing & Quality  
- If the project has an existing testing practice, immediately create tests for any new functionality not covered by current tests.  
- Regularly run tests and linters when making changes to ensure nothing is broken.


## ✦ Default tool behaviour  
- Prefer existing MCP servers; do not create new MCP configs silently.  
- Respect project ESLint/Prettier settings if found; otherwise assume default industry presets.

<!-- End of global rules -->