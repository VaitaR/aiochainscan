#!/usr/bin/env python3
"""
Comprehensive test script for all aiochainscan scanner methods.

This script sequentially tests all available API methods for each supported
blockchain scanner to determine which methods work and which don't.

Generates detailed reports showing:
- Scanner availability and configuration
- Method-by-method test results
- Success/failure statistics
- Error analysis
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aiochainscan import Client
from aiochainscan.config import config_manager
from aiochainscan.exceptions import (
    ChainscanClientApiError,
    FeatureNotSupportedError,
    SourceNotVerifiedError,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('scanner_methods_test.log'), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


@dataclass
class MethodTestResult:
    """Result of testing a single method."""

    method_name: str
    module: str
    success: bool
    error_type: str | None = None
    error_message: str | None = None
    response_data: Any | None = None
    execution_time: float = 0.0


@dataclass
class ScannerTestResult:
    """Result of testing all methods for a scanner."""

    scanner_id: str
    scanner_name: str
    requires_api_key: bool
    api_key_configured: bool
    networks_tested: list[str] = field(default_factory=list)
    method_results: dict[str, list[MethodTestResult]] = field(default_factory=dict)
    total_methods: int = 0
    successful_methods: int = 0
    failed_methods: int = 0
    errors: list[str] = field(default_factory=list)


class ScannerMethodTester:
    """Comprehensive tester for all scanner methods."""

    def __init__(self, use_fixed_block: bool = False):
        self.results: list[ScannerTestResult] = []
        self.use_fixed_block = use_fixed_block
        self.test_addresses = {
            'eth': '0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045',  # Vitalik
            'bsc': '0x8894E0a0c962CB723c1976a4421c95949bE2D4E3',  # Binance hot wallet
            'polygon': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619',  # WETH on Polygon
            'arbitrum': '0x912CE59144191C1204E64559FE8253a0e49E6548',  # Arbitrum bridge
            'base': '0x4200000000000000000000000000000000000006',  # WETH on Base
            'optimism': '0x4200000000000000000000000000000000000006',  # WETH on Optimism
            'fantom': '0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83',  # WFTM
            'gnosis': '0x6A023CCd1ff6F2045C3309768eAd9E68F978f6e1',  # WETH on Gnosis
            'linea': '0xe5D7C2a44FfDDf6b295A15c148167daaAf5Cf34f',  # ETH bridge
            'blast': '0x4300000000000000000000000000000000000003',  # USDB
            'xlayer': '0x5A77f1443D16ee5761b7fcE5A0C0f2e78987e2Ed',  # Bridge
            'flare': '0x1D80c49BbBCd1C0911346656B529DF9E5c2F783d',  # WFLR
        }

        # Fixed historical blocks for reliable testing (well-known blocks that exist on all networks)
        self.fixed_test_blocks = {
            'eth': 10000,     # January 2024
            'bsc': 10000,     # January 2024
            'polygon': 10000, # January 2024
            'arbitrum': 10000, # January 2024
            'optimism': 10000, # January 2024
            'base': 10000,    # January 2024
            'fantom': 10000,  # January 2024
            'gnosis': 10000,  # January 2024
            'linea': 10000,    # Historical block
            'blast': 10000,    # Historical block
            'xlayer': 10000,    # Historical block
            'flare': 10000,    # Historical block
        }

        # Verified contract addresses for ABI/source testing
        self.verified_contracts = {
                "eth":       "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                "eth:sepolia":"0xb26b2de65D07ebB5E54C7f6282424d3bE670e1F0",
                "bsc":       "0xe9e7cEA3dEDca5984780Bafc599Bd69aDd087d56",
                "polygon":   "0x7cEB23fD6bC0adD59e62ac25578270cFf1b9f619",
                "arbitrum":  "0xfd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
                "optimism":  "0x0b2c639c533813f4aA9d7837cAF62653d097fF85",
                "base":      "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
                "linea":     "0xe5d7C2A44FfDDF6B295a15c148167dAAaF5CF34F",
                "gnosis":    "0x9C58BAcC331c9aa871AFD802DB6379a98e80CEdB",
                "blast":     "0x4300000000000000000000000000000000000003",
        }

    def get_test_address(self, scanner_id: str) -> str:
        """Get appropriate test address for scanner."""
        return self.test_addresses.get(scanner_id, self.test_addresses['eth'])

    def get_verified_contract(self, scanner_id: str) -> str:
        """Get appropriate verified contract address for scanner."""
        return self.verified_contracts.get(scanner_id, self.verified_contracts['eth'])

    def get_fixed_block(self, scanner_id: str) -> int:
        """Get appropriate fixed block number for scanner."""
        return self.fixed_test_blocks.get(scanner_id, self.fixed_test_blocks['eth'])

    async def _test_contract_abi(self, client: Client, contract_address: str):
        """Test contract ABI with proper exception handling."""
        try:
            return await client.contract.contract_abi(contract_address)
        except SourceNotVerifiedError:
            # Skip test if contract is not verified on this explorer
            return None

    async def _test_contract_source(self, client: Client, contract_address: str):
        """Test contract source with proper exception handling."""
        try:
            return await client.contract.contract_source(contract_address)
        except SourceNotVerifiedError:
            # Skip test if contract is not verified on this explorer
            return None

    async def _test_block_reward(self, client: Client, scanner_id: str):
        """Test block reward with optional fixed block."""
        if self.use_fixed_block:
            fixed_block = self.get_fixed_block(scanner_id)
            return await client.block.block_reward(fixed_block)
        else:
            return await client.block.block_reward()  # Use default (current - 1)

    async def _test_block_countdown(self, client: Client, scanner_id: str):
        """Test block countdown with optional fixed block."""
        if self.use_fixed_block:
            fixed_block = self.get_fixed_block(scanner_id)
            # Use fixed block + 1000 for countdown
            return await client.block.block_countdown(fixed_block + 1000)
        else:
            return await client.block.block_countdown()  # Use default (current + 1000)



    async def test_all_scanners(self):
        """Test all available scanners."""
        scanners = config_manager.get_supported_scanners()

        # TODO: Remove this limitation after testing - only first 5 scanners for now
        scanners = scanners[:5]

        logger.info(f'🚀 Starting comprehensive test of {len(scanners)} scanners')

        for scanner_id in scanners:
            await self.test_scanner(scanner_id)

        self.generate_reports()

    async def test_scanner(self, scanner_id: str):
        """Test all methods for a single scanner."""
        config = config_manager.get_scanner_config(scanner_id)

        logger.info(f'\n🔍 Testing {config.name} ({scanner_id})')
        logger.info(f'   Domain: {config.base_domain}')
        logger.info(f'   Requires API Key: {config.requires_api_key}')

        result = ScannerTestResult(
            scanner_id=scanner_id,
            scanner_name=config.name,
            requires_api_key=config.requires_api_key,
            api_key_configured=bool(config.api_key),
        )

        # Test main network primarily
        networks_to_test = ['main']
        if scanner_id == 'eth' and 'sepolia' in config.supported_networks:
            networks_to_test.append('sepolia')

        for network in networks_to_test:
            if network in config.supported_networks:
                await self.test_scanner_network(scanner_id, network, result)
                result.networks_tested.append(network)

        self.results.append(result)
        logger.info(
            f'   ✅ Completed: {result.successful_methods}/{result.total_methods} methods working'
        )

    async def test_scanner_network(self, scanner_id: str, network: str, result: ScannerTestResult):
        """Test all methods for a scanner on a specific network."""
        logger.info(f'   📡 Testing network: {network}')

        try:
            client = Client.from_config(scanner_id, network)
            test_address = self.get_test_address(scanner_id)
            verified_contract = self.get_verified_contract(scanner_id)

            # Define test methods by module
            test_methods = {
                'proxy': [
                    ('block_number', lambda c: c.proxy.block_number()),
                    ('get_balance', lambda c: c.proxy.balance(test_address)),
                    ('get_block_by_number', lambda c: c.proxy.block_by_number('latest')),
                ],
                'account': [
                    ('balance', lambda c: c.account.balance(test_address)),
                    (
                        'normal_txs',
                        lambda c: c.account.normal_txs(test_address, page=1, offset=10),
                    ),
                    (
                        'internal_txs',
                        lambda c: c.account.internal_txs(test_address, page=1, offset=10),
                    ),
                    (
                        'erc20_transfers',
                        lambda c: c.account.erc20_transfers(test_address, page=1, offset=10),
                    ),
                ],
                'stats': [
                    ('eth_supply', lambda c: c.stats.eth_supply()),
                    ('eth_price', lambda c: c.stats.eth_price()),
                    ('nodes_size', lambda c: c.stats.nodes_size()),
                ],
                'block': [
                    ('block_reward', lambda c: self._test_block_reward(c, scanner_id)),
                    ('block_countdown', lambda c: self._test_block_countdown(c, scanner_id)),
                    ('daily_block_count', lambda c: c.block.daily_block_count()),  # Always use fixed historical dates
                ],
                'transaction': [
                    (
                        'tx_receipt_status',
                        lambda c: c.transaction.tx_receipt_status('0x' + '0' * 64),
                    ),
                    ('check_tx_status', lambda c: c.transaction.check_tx_status('0x' + '0' * 64)),
                ],
                'logs': [
                    (
                        'get_logs',
                        lambda c: c.logs.get_logs(
                            address=test_address, start_block='latest', end_block='latest'
                        ),
                    ),
                ],
                'gas_tracker': [
                    (
                        'gas_estimate',
                        lambda c: c.gas_tracker.gas_estimate(20000000000),  # 20 Gwei
                    ),
                    ('gas_oracle', lambda c: c.gas_tracker.gas_oracle()),
                ],
                'token': [
                    ('token_supply', lambda c: c.token.token_supply(test_address)),
                    ('token_balance', lambda c: c.token.token_balance(test_address, test_address)),
                ],
                'contract': [
                    ('contract_abi', lambda c: self._test_contract_abi(c, verified_contract)),
                    ('contract_source', lambda c: self._test_contract_source(c, verified_contract)),
                ],
            }

            # Test each module
            for module_name, methods in test_methods.items():
                result.method_results[module_name] = []

                for method_name, method_call in methods:
                    await self.test_method(client, module_name, method_name, method_call, result)

                    # Rate limiting between calls
                    await asyncio.sleep(0.5)

            await client.close()

        except ValueError as e:
            error_msg = str(e)
            logger.info(f'      ❌ Configuration error: {error_msg}')
            result.errors.append(f'{network}: {error_msg}')

            # Special handling for API key issues
            if 'api key required' in error_msg.lower():
                logger.info('      🔑 API key required but not configured')
                suggestions = config_manager._get_api_key_suggestions(scanner_id)
                logger.info(f'      💡 Set: {suggestions[0]}')

        except Exception as e:
            error_msg = str(e)
            logger.info(f'      ❌ Setup error: {error_msg}')
            result.errors.append(f'{network}: {error_msg}')

    async def test_method(
        self,
        client: Client,
        module_name: str,
        method_name: str,
        method_call,
        result: ScannerTestResult,
    ):
        """Test a single method."""
        start_time = time.time()

        try:
            response = await method_call(client)
            execution_time = time.time() - start_time

            # Determine success based on response
            success = response is not None and response != ''

            method_result = MethodTestResult(
                method_name=method_name,
                module=module_name,
                success=success,
                response_data=str(response)[:200] if response else None,
                execution_time=execution_time,
            )

            result.method_results[module_name].append(method_result)
            result.total_methods += 1

            if success:
                result.successful_methods += 1
                logger.info(f'      ✅ {module_name}.{method_name} ({execution_time:.2f}s)')
            else:
                result.failed_methods += 1
                logger.info(f'      ❌ {module_name}.{method_name} - Empty response')

        except ChainscanClientApiError as e:
            execution_time = time.time() - start_time
            error_msg = str(e)

            method_result = MethodTestResult(
                method_name=method_name,
                module=module_name,
                success=False,
                error_type='API Error',
                error_message=error_msg,
                execution_time=execution_time,
            )

            result.method_results[module_name].append(method_result)
            result.total_methods += 1
            result.failed_methods += 1

            # Categorize API errors
            if any(
                keyword in error_msg.lower()
                for keyword in ['not found', 'no transactions', 'no records']
            ):
                logger.info(f'      ⚠️  {module_name}.{method_name} - No data available')
            elif any(keyword in error_msg.lower() for keyword in ['invalid', 'error']):
                logger.info(f'      ❌ {module_name}.{method_name} - {error_msg[:50]}...')
            else:
                logger.info(f'      ❌ {module_name}.{method_name} - API Error')

        except FeatureNotSupportedError as e:
            execution_time = time.time() - start_time
            error_msg = str(e)

            method_result = MethodTestResult(
                method_name=method_name,
                module=module_name,
                success=False,
                error_type='Feature Not Supported',
                error_message=error_msg,
                execution_time=execution_time,
            )

            result.method_results[module_name].append(method_result)
            result.total_methods += 1
            result.failed_methods += 1

            logger.info(f'      ⚠️  {module_name}.{method_name} - Feature not supported')

        except SourceNotVerifiedError as e:
            execution_time = time.time() - start_time
            error_msg = str(e)

            method_result = MethodTestResult(
                method_name=method_name,
                module=module_name,
                success=False,
                error_type='Source Not Verified',
                error_message=error_msg,
                execution_time=execution_time,
            )

            result.method_results[module_name].append(method_result)
            result.total_methods += 1
            result.failed_methods += 1

            logger.info(f'      ⚠️  {module_name}.{method_name} - Contract not verified')

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)

            method_result = MethodTestResult(
                method_name=method_name,
                module=module_name,
                success=False,
                error_type='Exception',
                error_message=error_msg,
                execution_time=execution_time,
            )

            result.method_results[module_name].append(method_result)
            result.total_methods += 1
            result.failed_methods += 1

            logger.info(f'      ❌ {module_name}.{method_name} - Exception: {error_msg[:50]}...')

    def generate_reports(self):
        """Generate comprehensive reports."""
        logger.info('\n📊 Generating reports...')

        # Generate summary report
        summary_report = self.generate_summary_report()
        summary_path = Path('scanner_methods_summary.md')
        summary_path.write_text(summary_report, encoding='utf-8')

        # Generate detailed report
        detailed_report = self.generate_detailed_report()
        detailed_path = Path('scanner_methods_detailed.md')
        detailed_path.write_text(detailed_report, encoding='utf-8')

        # Save raw results as JSON
        raw_results = {
            'test_timestamp': datetime.now().isoformat(),
            'scanners_tested': len(self.results),
            'results': [self.serialize_result(r) for r in self.results],
        }

        results_path = Path('scanner_methods_results.json')
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(raw_results, f, indent=2)

        logger.info('✅ Reports generated:')
        logger.info(f'   📄 Summary: {summary_path}')
        logger.info(f'   📋 Detailed: {detailed_path}')
        logger.info(f'   📊 Raw data: {results_path}')

    def serialize_result(self, result: ScannerTestResult) -> dict:
        """Convert result to JSON-serializable format."""
        return {
            'scanner_id': result.scanner_id,
            'scanner_name': result.scanner_name,
            'requires_api_key': result.requires_api_key,
            'api_key_configured': result.api_key_configured,
            'networks_tested': result.networks_tested,
            'total_methods': result.total_methods,
            'successful_methods': result.successful_methods,
            'failed_methods': result.failed_methods,
            'success_rate': result.successful_methods / max(result.total_methods, 1) * 100,
            'method_results': {
                module: [
                    {
                        'method_name': mr.method_name,
                        'success': mr.success,
                        'error_type': mr.error_type,
                        'error_message': mr.error_message,
                        'execution_time': mr.execution_time,
                    }
                    for mr in methods
                ]
                for module, methods in result.method_results.items()
            },
            'errors': result.errors,
        }

    def generate_summary_report(self) -> str:
        """Generate summary report."""
        total_scanners = len(self.results)
        working_scanners = len([r for r in self.results if r.successful_methods > 0])

        report = f"""# aiochainscan Scanner Methods Test Summary

**Test Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Total Scanners:** {total_scanners}
**Working Scanners:** {working_scanners}

## Scanner Status Overview

| Scanner | Name | API Key | Methods | Success Rate | Status |
|---------|------|---------|---------|--------------|--------|
"""

        for result in sorted(self.results, key=lambda r: r.successful_methods, reverse=True):
            status_icon = '✅' if result.successful_methods > 0 else '❌'
            key_icon = '🔑' if result.requires_api_key else '🆓'
            key_status = (
                '✅' if result.api_key_configured else '❌' if result.requires_api_key else 'N/A'
            )
            success_rate = result.successful_methods / max(result.total_methods, 1) * 100

            report += f'| `{result.scanner_id}` | {result.scanner_name} | {key_icon} {key_status} | {result.successful_methods}/{result.total_methods} | {success_rate:.1f}% | {status_icon} |\n'

        report += """
## Method Success by Module

"""

        # Aggregate results by module
        module_stats = {}
        for result in self.results:
            if result.successful_methods > 0:  # Only count working scanners
                for module_name, methods in result.method_results.items():
                    if module_name not in module_stats:
                        module_stats[module_name] = {'total': 0, 'success': 0}
                    for method in methods:
                        module_stats[module_name]['total'] += 1
                        if method.success:
                            module_stats[module_name]['success'] += 1

        for module_name, stats in sorted(module_stats.items()):
            success_rate = stats['success'] / max(stats['total'], 1) * 100
            report += (
                f'- **{module_name}**: {stats["success"]}/{stats["total"]} ({success_rate:.1f}%)\n'
            )

        report += f"""
## Key Findings

- **{working_scanners}/{total_scanners}** scanners have working methods
- **{len([r for r in self.results if r.requires_api_key and r.api_key_configured])}** scanners have API keys configured
- **{len([r for r in self.results if r.requires_api_key and not r.api_key_configured])}** scanners need API key setup

## Recommendations

"""

        # Add specific recommendations
        needs_keys = [r for r in self.results if r.requires_api_key and not r.api_key_configured]
        if needs_keys:
            report += '### API Keys Needed:\n'
            for result in needs_keys:
                suggestions = config_manager._get_api_key_suggestions(result.scanner_id)
                report += f'- `{result.scanner_id}` → Set `{suggestions[0]}`\n'

        working_scanners_list = [r for r in self.results if r.successful_methods > 0]
        if working_scanners_list:
            report += '\n### Working Scanners:\n'
            for result in working_scanners_list:
                report += f'- `{result.scanner_id}` ({result.scanner_name}): {result.successful_methods} working methods\n'

        return report

    def generate_detailed_report(self) -> str:
        """Generate detailed per-scanner report."""
        report = f"""# aiochainscan Scanner Methods Detailed Report

**Test Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This report shows detailed method-by-method test results for each scanner.

"""

        for result in sorted(self.results, key=lambda r: r.scanner_id):
            key_status = (
                '✅ Configured'
                if result.api_key_configured
                else '❌ Missing'
                if result.requires_api_key
                else 'N/A'
            )
            success_rate = result.successful_methods / max(result.total_methods, 1) * 100

            report += f"""## {result.scanner_name} (`{result.scanner_id}`)

- **Domain:** {config_manager.get_scanner_config(result.scanner_id).base_domain}
- **Networks:** {', '.join(result.networks_tested) if result.networks_tested else 'None tested'}
- **API Key Required:** {'Yes' if result.requires_api_key else 'No'}
- **API Key Status:** {key_status}
- **Success Rate:** {success_rate:.1f}% ({result.successful_methods}/{result.total_methods})

### Method Results

"""

            if result.method_results:
                for module_name, methods in sorted(result.method_results.items()):
                    if methods:
                        report += f'#### {module_name.title()} Module\n\n'
                        for method in methods:
                            status = '✅' if method.success else '❌'
                            report += f'- **{method.method_name}**: {status}'
                            if method.error_type:
                                report += f' ({method.error_type})'
                            if method.execution_time:
                                report += f' [{method.execution_time:.2f}s]'
                            report += '\n'
                        report += '\n'
            else:
                report += 'No methods tested (configuration error)\n\n'

            if result.errors:
                report += '### Errors\n\n'
                for error in result.errors:
                    report += f'- {error}\n'
                report += '\n'

        return report


async def main():
    """Main test execution."""
    logger.info('🚀 Starting comprehensive scanner methods test')

    # Option to use fixed blocks for more reliable testing
    use_fixed_blocks = True  # Set to True to use fixed historical blocks instead of current blocks

    if use_fixed_blocks:
        logger.info('📌 Using fixed historical blocks for stable testing')
        tester = ScannerMethodTester(use_fixed_block=True)
    else:
        logger.info('🔄 Using current blocks (may have timezone/timing issues)')
        tester = ScannerMethodTester(use_fixed_block=False)

    try:
        # Original: test all scanners
        # await tester.test_all_scanners()

        # Testing with limited scanners for now
        await tester.test_all_scanners()

        # Print console summary
        total_scanners = len(tester.results)
        working_scanners = len([r for r in tester.results if r.successful_methods > 0])

        print('\n' + '=' * 80)
        print('SCANNER METHODS TEST SUMMARY')
        print('=' * 80)
        print(f'Total scanners tested: {total_scanners}')
        print(f'Scanners with working methods: {working_scanners}')
        print(f'Block testing mode: {"Fixed historical blocks" if use_fixed_blocks else "Current blocks"}')
        print('Reports generated in examples/')

    except Exception as e:
        logger.error(f'Test execution failed: {e}')
        return 1

    return 0


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        exit(exit_code)
    except KeyboardInterrupt:
        logger.info('Test interrupted by user')
        exit(1)
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        exit(1)
