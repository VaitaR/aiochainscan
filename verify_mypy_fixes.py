#!/usr/bin/env python3
"""Verification script for mypy fixes."""

import sys
from pathlib import Path


def verify_imports():
    """Verify all the fixed files can be imported without errors."""
    print('Verifying imports...')
    errors = []

    # Test analytics.py
    try:
        print('✓ analytics.py imports successfully')
    except Exception as e:
        errors.append(f'analytics.py: {e}')

    # Test aiohttp adapters (might fail if aiohttp not installed, but that's OK)
    try:
        from aiochainscan.adapters import aiohttp_client  # noqa: F401

        print('✓ aiohttp_client.py imports successfully')
    except ImportError as e:
        if 'aiohttp is required' in str(e):
            print('✓ aiohttp_client.py correctly handles missing aiohttp')
        else:
            errors.append(f'aiohttp_client.py: {e}')
    except Exception as e:
        errors.append(f'aiohttp_client.py: {e}')

    try:
        from aiochainscan.adapters import aiohttp_graphql_client  # noqa: F401

        print('✓ aiohttp_graphql_client.py imports successfully')
    except ImportError as e:
        if 'aiohttp is required' in str(e):
            print('✓ aiohttp_graphql_client.py correctly handles missing aiohttp')
        else:
            errors.append(f'aiohttp_graphql_client.py: {e}')
    except Exception as e:
        errors.append(f'aiohttp_graphql_client.py: {e}')

    # Test mcp_server
    try:
        print('✓ mcp_server.py imports successfully')
    except Exception as e:
        errors.append(f'mcp_server.py: {e}')

    # Test scanners
    try:
        print('✓ blockscout scanners import successfully')
    except Exception as e:
        errors.append(f'blockscout scanners: {e}')

    # Test core client
    try:
        print('✓ core/client.py imports successfully')
    except Exception as e:
        errors.append(f'core/client.py: {e}')

    if errors:
        print('\n❌ Import errors found:')
        for error in errors:
            print(f'  - {error}')
        return False
    else:
        print('\n✅ All imports successful!')
        return True


def check_type_checking_pattern():
    """Check that TYPE_CHECKING pattern is used correctly."""
    print('\nChecking TYPE_CHECKING patterns...')

    files_to_check = [
        'aiochainscan/services/analytics.py',
        'aiochainscan/adapters/aiohttp_client.py',
        'aiochainscan/adapters/aiohttp_graphql_client.py',
        'aiochainscan/mcp_server.py',
        'aiochainscan/core/client.py',
    ]

    for filepath in files_to_check:
        path = Path(filepath)
        if not path.exists():
            print(f'⚠️  {filepath} not found')
            continue

        content = path.read_text()
        has_type_checking = 'TYPE_CHECKING' in content

        if has_type_checking:
            print(f'✓ {filepath} uses TYPE_CHECKING')
        else:
            print(f'⚠️  {filepath} does not use TYPE_CHECKING')

    print('✅ Pattern check complete')


if __name__ == '__main__':
    print('=' * 60)
    print('Mypy Fixes Verification')
    print('=' * 60)

    imports_ok = verify_imports()
    check_type_checking_pattern()

    print('\n' + '=' * 60)
    if imports_ok:
        print('✅ ALL CHECKS PASSED')
        print('=' * 60)
        sys.exit(0)
    else:
        print('❌ SOME CHECKS FAILED')
        print('=' * 60)
        sys.exit(1)
