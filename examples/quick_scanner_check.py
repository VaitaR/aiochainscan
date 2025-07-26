#!/usr/bin/env python3
"""
Quick scanner connectivity test.

This script quickly tests basic connectivity to all scanners with a simple
block_number request to determine which scanners are working and which need
API key configuration.

Use this for a fast overview before running the comprehensive method tests.
"""

import asyncio
import logging
from datetime import datetime

from aiochainscan import Client
from aiochainscan.config import config_manager
from aiochainscan.exceptions import ChainscanClientApiError

# Simple console logging
logging.basicConfig(level=logging.WARNING)


async def quick_test_scanner(scanner_id: str) -> dict:
    """Quick test of scanner connectivity."""
    config = config_manager.get_scanner_config(scanner_id)

    result = {
        'scanner_id': scanner_id,
        'name': config.name,
        'requires_api_key': config.requires_api_key,
        'api_key_configured': bool(config.api_key),
        'status': 'unknown',
        'error': None,
        'response_time': 0.0,
    }

    try:
        start_time = asyncio.get_event_loop().time()
        client = Client.from_config(scanner_id, 'main')

        try:
            # Simple connectivity test
            block_number = await client.proxy.block_number()
            end_time = asyncio.get_event_loop().time()
            result['response_time'] = end_time - start_time

            if block_number and block_number.startswith('0x'):
                result['status'] = 'working'
            else:
                result['status'] = 'error'
                result['error'] = 'Invalid response'

        except ChainscanClientApiError as e:
            end_time = asyncio.get_event_loop().time()
            result['response_time'] = end_time - start_time
            result['status'] = 'api_error'
            result['error'] = str(e)[:100]

        except Exception as e:
            end_time = asyncio.get_event_loop().time()
            result['response_time'] = end_time - start_time
            result['status'] = 'error'
            result['error'] = str(e)[:100]

        finally:
            await client.close()

    except ValueError as e:
        result['status'] = 'no_api_key'
        result['error'] = str(e)[:100]

    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)[:100]

    return result


async def main():
    """Main quick test function."""
    print('🚀 Quick Scanner Connectivity Test')
    print('=' * 50)
    print(f'Test time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print()

    scanners = config_manager.get_supported_scanners()
    results = []

    # Test all scanners
    for scanner_id in sorted(scanners):
        result = await quick_test_scanner(scanner_id)
        results.append(result)

        # Print immediate feedback
        status_icon = {
            'working': '✅',
            'api_error': '⚠️',
            'no_api_key': '🔑',
            'error': '❌',
            'unknown': '❓',
        }.get(result['status'], '❓')

        key_icon = '🔑' if result['requires_api_key'] else '🆓'
        key_status = (
            '✅' if result['api_key_configured'] else '❌' if result['requires_api_key'] else ''
        )

        print(f'{status_icon} {result["name"]:<20} {key_icon}{key_status:<2} ', end='')

        if result['status'] == 'working':
            print(f'({result["response_time"]:.2f}s)')
        elif result['status'] == 'no_api_key':
            print('- Need API key')
        elif result['error']:
            print(f'- {result["error"][:30]}...')
        else:
            print()

    # Summary
    working = len([r for r in results if r['status'] == 'working'])
    need_keys = len([r for r in results if r['status'] == 'no_api_key'])
    errors = len([r for r in results if r['status'] in ['error', 'api_error']])

    print()
    print('📊 SUMMARY')
    print('=' * 50)
    print(f'✅ Working:      {working}/{len(results)}')
    print(f'🔑 Need API key: {need_keys}')
    print(f'❌ Errors:       {errors}')
    print()

    if need_keys > 0:
        print('🔑 Scanners needing API keys:')
        for result in results:
            if result['status'] == 'no_api_key':
                suggestions = config_manager._get_api_key_suggestions(result['scanner_id'])
                print(f'   {result["scanner_id"]} → Set {suggestions[0]}')
        print()

    if working > 0:
        print('✅ Working scanners:')
        for result in sorted(
            results, key=lambda r: r['response_time'] if r['status'] == 'working' else 999
        ):
            if result['status'] == 'working':
                print(
                    f'   {result["scanner_id"]} ({result["name"]}) - {result["response_time"]:.2f}s'
                )

    print()
    print('💡 For detailed method testing, run: python3 test_scanner_methods.py')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\n⚠️ Test interrupted')
    except Exception as e:
        print(f'\n💥 Error: {e}')
