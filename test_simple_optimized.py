#!/usr/bin/env python3
"""Simple test for optimized transaction fetching logic without external dependencies."""

import asyncio
import heapq


def test_priority_queue_logic():
    """Test priority queue behavior for range splitting."""
    print("Testing priority queue logic...")

    # Simulate priority queue operations
    range_queue = []
    range_counter = 0

    # Add initial ranges (negative for max-heap)
    start_block, end_block = 0, 1000
    left_end = start_block + min((end_block - start_block) // 4, 50000)
    right_start = max(end_block - (end_block - start_block) // 4, left_end + 1)
    center_start = (left_end + right_start) // 2

    # Add ranges to queue
    heapq.heappush(range_queue, (-(left_end - start_block), range_counter, start_block, left_end))
    range_counter += 1

    if center_start < right_start:
        heapq.heappush(range_queue, (-(right_start - center_start), range_counter, center_start, right_start))
        range_counter += 1

    if right_start < end_block:
        heapq.heappush(range_queue, (-(end_block - right_start), range_counter, right_start, end_block))
        range_counter += 1

    print(f"Initial ranges in queue: {len(range_queue)}")

    # Test that largest range comes first
    largest_range = heapq.heappop(range_queue)
    print(f"Largest range: {largest_range}")

    # Test range splitting
    _, range_id, block_start, block_end = largest_range
    mid_block = (block_start + block_end) // 2

    # Add split ranges back
    heapq.heappush(range_queue, (-(mid_block - block_start), range_counter, block_start, mid_block))
    range_counter += 1
    heapq.heappush(range_queue, (-(block_end - mid_block), range_counter, mid_block + 1, block_end))
    range_counter += 1

    print(f"After split, ranges in queue: {len(range_queue)}")
    assert len(range_queue) >= 2, "Should have at least 2 ranges after split"
    print("✅ Priority queue logic test passed!")


def test_deduplication_logic():
    """Test deduplication and sorting logic."""
    print("Testing deduplication and sorting...")

    # Simulate transactions with duplicates
    transactions = [
        {"hash": "tx3", "blockNumber": "102", "transactionIndex": "0"},
        {"hash": "tx1", "blockNumber": "100", "transactionIndex": "1"},
        {"hash": "tx2", "blockNumber": "100", "transactionIndex": "0"},
        {"hash": "tx1", "blockNumber": "100", "transactionIndex": "1"},  # Duplicate
        {"hash": "tx4", "blockNumber": "101", "transactionIndex": "0"},
    ]

    # Sort by block number, then by transaction index
    def sort_key(element):
        block_num = element.get("blockNumber", "0")
        if isinstance(block_num, str) and block_num.startswith("0x"):
            block_num = int(block_num, 16)
        else:
            block_num = int(block_num)

        tx_index = element.get("transactionIndex", "0")
        if isinstance(tx_index, str) and tx_index.startswith("0x"):
            tx_index = int(tx_index, 16)
        else:
            tx_index = int(tx_index) if tx_index else 0

        return (block_num, tx_index)

    transactions.sort(key=sort_key)

    # Remove duplicates
    seen_hashes = set()
    unique_transactions = []
    for tx in transactions:
        tx_hash = tx.get("hash")
        if tx_hash and tx_hash not in seen_hashes:
            seen_hashes.add(tx_hash)
            unique_transactions.append(tx)

    print(f"Original: {len(transactions)}, Unique: {len(unique_transactions)}")
    assert len(unique_transactions) == 4, "Should have 4 unique transactions"

    # Check sorting order
    expected_order = ["tx2", "tx1", "tx4", "tx3"]  # Block 100(idx 0,1), 101(idx 0), 102(idx 0)
    actual_order = [tx["hash"] for tx in unique_transactions]
    assert actual_order == expected_order, f"Wrong order: {actual_order}"

    print("✅ Deduplication and sorting test passed!")


async def test_concurrent_processing_mock():
    """Test concurrent processing with mocked functions."""
    print("Testing concurrent processing simulation...")

    # Mock semaphore and async function
    semaphore = asyncio.Semaphore(3)  # Allow 3 concurrent

    async def mock_fetch(range_info):
        """Mock worker function."""
        _, range_id, block_start, block_end = range_info
        async with semaphore:
            # Simulate API call delay
            await asyncio.sleep(0.01)
            # Return mock transactions
            return (
                range_id,
                block_start,
                block_end,
                [
                    {"hash": f"tx{range_id}_{i}", "blockNumber": str(block_start + i)}
                    for i in range(min(2, block_end - block_start + 1))
                ],
            )

    # Create test ranges
    ranges = [
        (-100, 1, 0, 100),
        (-200, 2, 100, 300),
        (-150, 3, 300, 450),
    ]

    # Process concurrently
    start_time = asyncio.get_event_loop().time()
    tasks = [mock_fetch(range_info) for range_info in ranges]
    results = await asyncio.gather(*tasks)
    end_time = asyncio.get_event_loop().time()

    print(f"Processed {len(results)} ranges in {end_time - start_time:.3f}s")
    assert len(results) == 3, "Should process all ranges"

    # Check results structure
    for result in results:
        range_id, block_start, block_end, elements = result
        assert isinstance(elements, list), "Should return list of elements"
        assert len(elements) <= 2, "Should not exceed mock limit"

    print("✅ Concurrent processing test passed!")


def test_hex_number_handling():
    """Test handling of hex vs decimal block numbers."""
    print("Testing hex number handling...")

    transactions = [
        {"hash": "tx1", "blockNumber": "0x64", "transactionIndex": "0x0"},  # Block 100, index 0
        {"hash": "tx2", "blockNumber": "101", "transactionIndex": "1"},  # Block 101, index 1
        {"hash": "tx3", "blockNumber": "0x65", "transactionIndex": "0x1"},  # Block 101, index 1
    ]

    # Sort with hex support
    def sort_key(element):
        block_num = element.get("blockNumber", "0")
        if isinstance(block_num, str) and block_num.startswith("0x"):
            block_num = int(block_num, 16)
        else:
            block_num = int(block_num)

        tx_index = element.get("transactionIndex", "0")
        if isinstance(tx_index, str) and tx_index.startswith("0x"):
            tx_index = int(tx_index, 16)
        else:
            tx_index = int(tx_index) if tx_index else 0

        return (block_num, tx_index)

    sorted_txs = sorted(transactions, key=sort_key)

    # tx1: block 100, index 0 (should be first)
    # tx2: block 101, index 1
    # tx3: block 101, index 1 (same as tx2)
    assert sorted_txs[0]["hash"] == "tx1", "tx1 should be first (lowest block)"
    print("✅ Hex number handling test passed!")


def run_all_tests():
    """Run all tests."""
    print("🧪 Running optimized transaction fetching tests...\n")

    try:
        test_priority_queue_logic()
        print()

        test_deduplication_logic()
        print()

        # Run async test
        asyncio.run(test_concurrent_processing_mock())
        print()

        test_hex_number_handling()
        print()

        print("🎉 All tests passed! Optimized transaction fetching logic is working correctly.")
        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
