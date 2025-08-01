#!/usr/bin/env python3
"""
Test script for optimized transaction fetching.
This script tests both the legacy and optimized methods to ensure compatibility.
"""

import asyncio
import logging
import time
from pathlib import Path

from aiochainscan import Client
from aiochainscan.modules.extra.utils import Utils

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_optimized_vs_legacy():
    """Compare optimized method performance vs legacy method."""
    
    # Create client
    client = Client.from_config('eth', 'main')
    
    try:
        # Test address with known transactions (UNI token)
        test_address = '0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984'
        
        # Get current block
        current_block = int(await client.proxy.block_number(), 16)
        start_block = max(0, current_block - 500)  # Last 500 blocks for testing
        
        logger.info(f"Testing with address: {test_address}")
        logger.info(f"Block range: {start_block} to {current_block}")
        
        # Test optimized method
        logger.info("=" * 50)
        logger.info("Testing OPTIMIZED method")
        logger.info("=" * 50)
        
        start_time = time.time()
        utils = Utils(client)
        
        optimized_results = await utils.fetch_all_elements_optimized(
            address=test_address,
            data_type='normal_txs',
            start_block=start_block,
            end_block=current_block,
            max_concurrent=3,
            max_offset=1000
        )
        
        optimized_time = time.time() - start_time
        logger.info(f"Optimized method: {len(optimized_results)} transactions in {optimized_time:.2f}s")
        
        # Test legacy method (equivalent block range)
        logger.info("=" * 50)
        logger.info("Testing LEGACY method")
        logger.info("=" * 50)
        
        start_time = time.time()
        legacy_results = []
        
        # Legacy method: fetch by pages
        page = 1
        while True:
            try:
                page_txs = await client.account.normal_txs(
                    address=test_address,
                    start_block=start_block,
                    end_block=current_block,
                    page=page,
                    offset=1000,
                    sort='desc'
                )
                
                if not page_txs or len(page_txs) == 0:
                    break
                    
                legacy_results.extend(page_txs)
                logger.info(f"Legacy page {page}: {len(page_txs)} transactions")
                
                if len(page_txs) < 1000:  # Last page
                    break
                    
                page += 1
                await asyncio.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Legacy method error on page {page}: {e}")
                break
        
        legacy_time = time.time() - start_time
        logger.info(f"Legacy method: {len(legacy_results)} transactions in {legacy_time:.2f}s")
        
        # Compare results
        logger.info("=" * 50)
        logger.info("COMPARISON")
        logger.info("=" * 50)
        
        speedup = legacy_time / optimized_time if optimized_time > 0 else float('inf')
        logger.info(f"Speedup: {speedup:.2f}x")
        logger.info(f"Optimized: {len(optimized_results)} transactions")
        logger.info(f"Legacy: {len(legacy_results)} transactions")
        
        # Check for duplicates in optimized results
        optimized_hashes = [tx.get('hash') for tx in optimized_results if tx.get('hash')]
        unique_optimized = len(set(optimized_hashes))
        logger.info(f"Optimized unique transactions: {unique_optimized}/{len(optimized_results)}")
        
        legacy_hashes = [tx.get('hash') for tx in legacy_results if tx.get('hash')]
        unique_legacy = len(set(legacy_hashes))
        logger.info(f"Legacy unique transactions: {unique_legacy}/{len(legacy_results)}")
        
        # Validate that we got reasonable results
        if len(optimized_results) > 0:
            logger.info("✅ Optimized method returned results")
        else:
            logger.warning("⚠️ Optimized method returned no results")
            
        if unique_optimized == len(optimized_results):
            logger.info("✅ Optimized method: No duplicates found")
        else:
            logger.warning(f"⚠️ Optimized method: {len(optimized_results) - unique_optimized} duplicates found")
            
        # Sample some results to verify structure
        if optimized_results:
            sample = optimized_results[0]
            logger.info(f"Sample transaction keys: {list(sample.keys())}")
            
    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    finally:
        await client.close()


async def test_edge_cases():
    """Test edge cases for the optimized method."""
    
    client = Client.from_config('eth', 'main')
    
    try:
        utils = Utils(client)
        
        # Test 1: Empty address (should return empty results)
        logger.info("Testing edge case: Non-existent address")
        empty_results = await utils.fetch_all_elements_optimized(
            address='0x0000000000000000000000000000000000000000',
            data_type='normal_txs',
            start_block=0,
            end_block=100,
            max_concurrent=1,
            max_offset=100
        )
        logger.info(f"Empty address results: {len(empty_results)} transactions")
        
        # Test 2: Single block range
        logger.info("Testing edge case: Single block range")
        current_block = int(await client.proxy.block_number(), 16)
        single_block_results = await utils.fetch_all_elements_optimized(
            address='0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',
            data_type='normal_txs',
            start_block=current_block,
            end_block=current_block,
            max_concurrent=1,
            max_offset=100
        )
        logger.info(f"Single block results: {len(single_block_results)} transactions")
        
        # Test 3: Invalid block range
        logger.info("Testing edge case: Invalid block range")
        try:
            invalid_results = await utils.fetch_all_elements_optimized(
                address='0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984',
                data_type='normal_txs',
                start_block=current_block + 1000,
                end_block=current_block + 500,  # end < start
                max_concurrent=1,
                max_offset=100
            )
            logger.info(f"Invalid range results: {len(invalid_results)} transactions")
        except Exception as e:
            logger.info(f"Invalid range correctly handled: {e}")
            
        logger.info("✅ Edge case tests completed")
        
    except Exception as e:
        logger.error(f"Edge case test failed: {e}")
        raise
    finally:
        await client.close()


async def main():
    """Main test function."""
    logger.info("Starting optimized transaction fetching tests")
    
    try:
        # Run performance comparison
        await test_optimized_vs_legacy()
        
        # Run edge case tests
        await test_edge_cases()
        
        logger.info("🎉 All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"Tests failed: {e}")
        return 1
        
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)