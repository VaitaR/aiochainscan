# Contributing to aiochainscan

Thank you for your interest in contributing to aiochainscan! This guide will help you set up your development environment and understand our workflow.

## Quick Start

### 1. Initial Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/aiochainscan.git
cd aiochainscan

# Run the setup script (installs dependencies + git hooks)
chmod +x scripts/setup-dev.sh
./scripts/setup-dev.sh
```

The setup script will:
- Install all dependencies via `uv`
- Install pre-commit and pre-push git hooks
- Validate your setup by running all checks
- Test imports to ensure no circular dependencies

### 2. Development Workflow

```bash
# Make your changes
vim aiochainscan/some_file.py

# Stage changes
git add .

# Commit (pre-commit hooks run automatically!)
git commit -m "feat: add new feature"
# ✅ Ruff format
# ✅ Ruff lint
# ✅ Import tests (catches circular deps!)
# ✅ Trailing whitespace check
# ✅ YAML validation

# Push (pre-push hooks run automatically!)
git push origin feature-branch
# ✅ Mypy strict type checking
# ✅ Quick test suite
```

## Quality Gates

We have **3 levels** of quality checks:

### Level 1: Pre-Commit (Fast - ~5 seconds)

Runs on **every commit**:
- ✅ Ruff code formatting
- ✅ Ruff linting
- ✅ **Import tests** (catches circular imports!)
- ✅ Trailing whitespace removal
- ✅ YAML syntax check

### Level 2: Pre-Push (Medium - ~30 seconds)

Runs before **every push**:
- ✅ Mypy strict type checking
- ✅ Quick test suite (excluding slow integration tests)

### Level 3: CI/CD (Full - ~5 minutes)

Runs on **GitHub**:
- ✅ Import tests (double-check)
- ✅ All pre-commit checks
- ✅ Full mypy
- ✅ Full test suite (338 tests)
- ✅ Wheel building

## Manual Commands

### Run specific checks

```bash
# Only import tests (fast!)
uv run pytest tests/test_imports.py -v

# All pre-commit checks
uv run pre-commit run --all-files

# Pre-push checks (mypy + tests)
uv run pre-commit run --hook-stage pre-push

# Full test suite
uv run pytest -v

# Type checking
uv run mypy --strict aiochainscan

# Code formatting
uv run ruff format .
uv run ruff check --fix .
```

## Why Import Tests?

**Problem**: In the past, circular imports and import blockers weren't caught until CI/CD.

**Solution**: `tests/test_imports.py` runs on **every commit** and catches:
- ❌ Circular imports
- ❌ Import blockers (missing optional deps)
- ❌ Side effects during import
- ❌ Heavy unexpected imports

**Speed**: ~1.5 seconds - fast enough for pre-commit!

## Code Style

We use:
- **Ruff** for linting and formatting (PEP 8)
- **Mypy** for strict type checking
- **Pydantic V2** for data validation
- **Type hints** everywhere

Example:
```python
from typing import Literal

async def get_balance(
    address: str,
    network: Literal["ethereum", "polygon", "arbitrum"],
) -> str:
    """Get balance in Wei."""
    ...
```

## Testing

### Running Tests

```bash
# All tests
uv run pytest -v

# Specific test file
uv run pytest tests/test_client.py -v

# Specific test
uv run pytest tests/test_client.py::test_basic_import -v

# With coverage
uv run pytest --cov=aiochainscan --cov-report=html
```

### Writing Tests

```python
import pytest
from aiochainscan import ChainscanClient

@pytest.mark.asyncio
async def test_my_feature():
    async with ChainscanClient.from_config("blockscout_v2", "ethereum") as client:
        result = await client.get_balance("0x...")
        assert result
```

## Architecture

We follow **Hexagonal Architecture** (Ports & Adapters):

```
core/          - Domain logic (ChainscanClient, Method)
scanners/      - Scanner implementations (Etherscan, BlockScout)
services/      - Business logic (account, transaction, etc.)
ports/         - Interfaces (HttpClient, RateLimiter, etc.)
adapters/      - Implementations (HttpxClient, AioLimiter, etc.)
domain/        - Domain models (DTOs, Value Objects)
```

**Dependency Rule**: Code can only depend on layers below, never above.

## Common Issues

### Git hooks not running?

```bash
# Reinstall hooks
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
```

### Import test failing?

```bash
# Check for circular imports
python -c "from aiochainscan import ChainscanClient"

# Run with traceback
uv run pytest tests/test_imports.py -v --tb=long
```

### Pre-commit slow?

```bash
# Skip hooks temporarily (NOT recommended!)
git commit --no-verify -m "WIP"

# Or fix the actual issue :)
```

## Pull Request Process

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feat/amazing-feature`)
3. **Make** your changes
4. **Commit** with conventional commits (`feat:`, `fix:`, `docs:`, etc.)
5. **Push** to your fork
6. **Open** a Pull Request

### PR Checklist

- [ ] All pre-commit hooks pass locally
- [ ] Import tests pass (`pytest tests/test_imports.py`)
- [ ] Type checking passes (`mypy --strict aiochainscan`)
- [ ] All tests pass (`pytest -v`)
- [ ] Documentation updated (if needed)
- [ ] Conventional commit messages

## Conventional Commits

We use conventional commits for automatic changelog generation:

```bash
feat: add new BlockScout V3 scanner
fix: resolve circular import in core.client
docs: update API examples in README
refactor: simplify rate limiter logic
test: add coverage for token transfers
chore: update dependencies
```

Types:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `refactor:` - Code refactoring
- `test:` - Adding tests
- `chore:` - Maintenance tasks

## Getting Help

- 📖 **Documentation**: See `docs/` folder
- 🐛 **Issues**: [GitHub Issues](https://github.com/yourusername/aiochainscan/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/yourusername/aiochainscan/discussions)
- 📧 **Email**: maintainer@example.com

## Code of Conduct

Please be respectful and constructive. We're all here to build something great together!

---

Thank you for contributing! 🚀
