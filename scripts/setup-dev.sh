#!/bin/bash
# Setup script for developers - installs git hooks and validates setup

set -e

echo "🔧 Setting up aiochainscan development environment..."
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ Error: 'uv' is not installed. Install it first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
uv sync --all-extras

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
uv run pre-commit install
uv run pre-commit install --hook-type pre-push

# Run pre-commit on all files to validate setup
echo "✅ Validating setup by running pre-commit on all files..."
if uv run pre-commit run --all-files; then
    echo ""
    echo "✅ All checks passed!"
else
    echo ""
    echo "⚠️  Some checks failed. Please fix the issues and run:"
    echo "   uv run pre-commit run --all-files"
    exit 1
fi

# Run import tests specifically
echo ""
echo "🧪 Testing imports to detect circular dependencies..."
if uv run pytest tests/test_imports.py -v; then
    echo "✅ Import tests passed!"
else
    echo "❌ Import tests failed!"
    exit 1
fi

# Quick sanity test
echo ""
echo "🧪 Running quick sanity test..."
python -c "
from aiochainscan import ChainscanClient, Method
print(f'✅ Version: {__import__(\"aiochainscan\").__version__}')
print(f'✅ ChainscanClient: {ChainscanClient.__name__}')
print(f'✅ Method enum: {len(list(Method))} methods')
"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Development environment setup complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Git hooks installed:"
echo "   • pre-commit: Runs linting, formatting, and import tests"
echo "   • pre-push: Runs mypy type checking and quick tests"
echo ""
echo "🚀 You're ready to contribute!"
echo ""
echo "Useful commands:"
echo "   uv run pre-commit run --all-files  # Run all checks manually"
echo "   uv run pytest tests/test_imports.py  # Test imports only"
echo "   uv run pytest -v  # Run full test suite"
echo "   uv run mypy aiochainscan  # Run type checking"
echo ""
