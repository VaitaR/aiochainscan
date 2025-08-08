#!/bin/bash

echo "🔍 Running comprehensive code quality checks..."
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track errors
errors=0

echo -e "\n${YELLOW}1. Python syntax check...${NC}"
if python3 -m py_compile aiochainscan/modules/extra/utils.py examples/test_decode_functionality.py tests/test_utils_optimized.py test_simple_optimized.py; then
    echo -e "${GREEN}✅ Syntax check passed${NC}"
else
    echo -e "${RED}❌ Syntax errors found${NC}"
    ((errors++))
fi

echo -e "\n${YELLOW}2. Running ruff linter...${NC}"
if ~/.local/bin/ruff check .; then
    echo -e "${GREEN}✅ Ruff checks passed${NC}"
else
    echo -e "${RED}❌ Ruff errors found${NC}"
    ((errors++))
fi

echo -e "\n${YELLOW}2b. Checking ruff formatting...${NC}"
if ~/.local/bin/ruff format --check .; then
    echo -e "${GREEN}✅ Ruff formatting check passed${NC}"
else
    echo -e "${RED}❌ Ruff formatting issues found${NC}"
    ((errors++))
fi

echo -e "\n${YELLOW}3. Running flake8...${NC}"
if python3 -m flake8 aiochainscan/modules/extra/utils.py examples/test_decode_functionality.py tests/test_utils_optimized.py test_simple_optimized.py --max-line-length=120 --extend-ignore=E203,W503; then
    echo -e "${GREEN}✅ Flake8 checks passed${NC}"
else
    echo -e "${RED}❌ Flake8 errors found${NC}"
    ((errors++))
fi

# Skipping black check since we're using ruff format

echo -e "\n${YELLOW}5. Checking import sorting (isort)...${NC}"
if python3 -m isort --profile black --check-only --diff aiochainscan/modules/extra/utils.py examples/test_decode_functionality.py tests/test_utils_optimized.py test_simple_optimized.py; then
    echo -e "${GREEN}✅ Import sorting check passed${NC}"
else
    echo -e "${RED}❌ Import sorting issues found${NC}"
    ((errors++))
fi

echo -e "\n${YELLOW}6. Running targeted tests with facades forced...${NC}"
if AIOCHAINSCAN_FORCE_FACADES=1 python3 -m pytest -q tests/test_account.py tests/test_block.py tests/test_transaction.py tests/test_logs.py tests/test_token.py tests/test_stats.py > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Targeted tests (facades forced) passed${NC}"
else
    echo -e "${RED}❌ Targeted tests (facades forced) failed${NC}"
    ((errors++))
fi

echo -e "\n=================================================="
if [ $errors -eq 0 ]; then
    echo -e "${GREEN}🎉 All quality checks passed! Code is ready for CI/CD!${NC}"
    exit 0
else
    echo -e "${RED}❌ Found $errors error(s). Please fix before committing.${NC}"
    exit 1
fi
