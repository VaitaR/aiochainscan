# GitHub Actions Workflows

## Overview

This project uses a simplified two-workflow strategy optimized for Python packages with Rust extensions.

## Workflows

### 1. ci.yml - Code Quality (Runs on every push/PR)

**Purpose**: Fast feedback on code quality

**Jobs**:
- **lint** - Pre-commit hooks, mypy type checking, import-linter
- **test** - Pytest across Python 3.12, 3.13 with coverage

**Does NOT**:
- Build wheels (too slow, not needed on every push)
- Publish to PyPI (only on release)

**Runtime**: ~3-5 minutes

---

### 2. wheels.yml - Build & Publish (Runs on release)

**Purpose**: Build production wheels and publish to PyPI

**Triggers**:
- On release creation (automatic)
- Manual workflow dispatch (for testing)

**Jobs**:
- **build_wheels** - Uses cibuildwheel for Linux, Windows, macOS
- **build_sdist** - Source distribution
- **publish** - Publishes to PyPI (only on release)

**Does**:
- Builds wheels with maturin (Rust extension)
- Tests each wheel after building
- Handles cross-platform builds
- Publishes to PyPI with trusted publishing

**Runtime**: ~20-30 minutes (cross-platform builds)

---

## Why This Structure?

### Problems with Previous Setup
- Had 3 workflows, 2 were failing with maturin errors
- Attempted to build wheels on every push (slow, unnecessary)
- Duplicated testing across workflows

### Current Benefits
1. **Fast CI** - Code quality checks in minutes, not hours
2. **Reliable** - No maturin builds in CI (only on release with proper tooling)
3. **Standard Practice** - Follows Python+Rust project conventions
4. **Clear Separation** - Code quality vs distribution packaging

## Development Workflow

### Daily Development
```bash
# Make changes
git commit -m "feat: add new feature"
git push

# CI runs:
# ✓ Lint (pre-commit, mypy, import-linter)
# ✓ Test (pytest on Python 3.12, 3.13)
# → ~3-5 minutes
```

### Creating a Release
```bash
# Create release on GitHub
gh release create v0.5.0 --generate-notes

# wheels.yml runs automatically:
# ✓ Build wheels (Linux, Windows, macOS)
# ✓ Build sdist
# ✓ Test wheels
# ✓ Publish to PyPI
# → ~20-30 minutes
```

## Testing Installation Locally

### Editable Install (Development)
```bash
# No wheel needed, no maturin required
pip install -e .
python -c "import aiochainscan"
```

### Test Wheel Build (Before Release)
```bash
# Requires Rust toolchain
pip install maturin
maturin develop
```

### Test From GitHub (Any Branch)
```bash
pip install git+https://github.com/VaitaR/aiochainscan.git@develop
```

## Troubleshooting

### CI Failing on Lint
- Run `pre-commit run --all-files` locally
- Fix issues, commit, push

### CI Failing on Tests
- Run `pytest` locally
- Check test output for failures

### Wheels Failing to Build
- Check Rust is installed: `rustc --version`
- Check maturin version: `pip show maturin` (should be ≥1.8)
- Test locally: `maturin build --release`

## Related Documentation

- [CI_SIMPLIFICATION.md](../../docs/CI_SIMPLIFICATION.md) - Why we simplified
- [PYPI_PUBLISHING.md](../../docs/PYPI_PUBLISHING.md) - Publishing guide
- [CONTRIBUTING.md](../../CONTRIBUTING.md) - Development guide
