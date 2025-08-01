from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from aiochainscan.decode import decode_log_data, decode_transaction_input
from aiochainscan.exceptions import ChainscanClientApiError

if TYPE_CHECKING:
    from aiochainscan import Client

import logging
import heapq

# Add this line at the beginning of the file to initialize the logger
logger = logging.getLogger(__name__)


def _default_date_range(days: int = 30) -> tuple[date, date]:
    """Get default date range for API requests.

    Args:
        days: Number of days to go back from today (default: 30)

    Returns:
        Tuple of (start_date, end_date) where start_date is today-days and end_date is today
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date


class Utils:
    """Helper methods which use the combination of documented APIs."""

    def __init__(self, client: Client):
        self._client = client
        self.data_model_mapping: dict[str, Callable[..., AsyncIterator[dict]]] = {
            'internal_txs': self._client.account.internal_txs,
            'normal_txs': self._client.account.normal_txs,
            'get_logs': self._client.logs.get_logs,
            'tokentx': self._client.account.token_transfers,
        }
        self._logger = logging.getLogger(__name__)

    async def token_transfers_generator(
        self,
        address: str = None,
        contract_address: str = None,
        block_limit: int = 50,
        offset: int = 3,
        start_block: int = 0,
        end_block: int = None,
    ) -> AsyncIterator[dict]:
        if end_block is None:
            end_block = int(await self._client.proxy.block_number(), 16)

        for sblock, eblock in self._generate_intervals(start_block, end_block, block_limit):
            async for transfer in self._parse_by_pages(
                address=address,
                contract_address=contract_address,
                start_block=sblock,
                end_block=eblock,
                offset=offset,
            ):
                yield transfer

    async def token_transfers(
        self,
        address: str = None,
        contract_address: str = None,
        be_polite: bool = True,
        block_limit: int = 50,
        offset: int = 3,
        start_block: int = 0,
        end_block: int = None,
    ) -> list[dict]:
        kwargs = {k: v for k, v in locals().items() if k != 'self' and not k.startswith('_')}
        return [t async for t in self.token_transfers_generator(**kwargs)]

    async def is_contract(self, address: str) -> bool:
        try:
            response = await self._client.contract.contract_abi(address=address)
        except ChainscanClientApiError as e:
            if (
                e.message.upper() == 'NOTOK'
                and e.result.lower() == 'contract source code not verified'
            ):
                return False
            raise
        else:
            return bool(response)

    async def get_contract_creator(self, contract_address: str) -> str | None:
        try:
            response = await self._client.account.internal_txs(
                address=contract_address, start_block=1, page=1, offset=1
            )  # try to find first internal transaction
        except ChainscanClientApiError as e:
            if e.message.lower() != 'no transactions found':
                raise
            else:
                response = None

        if not response:
            try:
                response = await self._client.account.normal_txs(
                    address=contract_address, start_block=1, page=1, offset=1
                )  # try to find first normal transaction
            except ChainscanClientApiError as e:
                if e.message.lower() != 'no transactions found':
                    raise

        return next((i['from'].lower() for i in response), None) if response else None

    async def get_proxy_abi(self, address: str) -> str | None:
        abi_directory = 'abi'
        abi_chain = self._client._url_builder._api_kind
        abi_file_path = f'{abi_directory}/{abi_chain}_{address}.json'

        # Ensure the ABI directory exists
        if not os.path.exists(abi_directory):
            os.makedirs(abi_directory)

        # Check if ABI exists locally
        if os.path.exists(abi_file_path):
            with open(abi_file_path) as file:
                abi = file.read()
                self._logger.info(f'Retrieved ABI from local storage for {address}')
                return json.loads(abi)

        # Fetch ABI from the API if not found locally
        try:
            source_code = await self._client.contract.contract_source_code(address=address)
        except ChainscanClientApiError as e:
            self._logger.warning(f'Error fetching source code for {address}: {str(e)}')
            return None

        contract_address = next(
            (r['Implementation'] for r in source_code if r['Implementation']), None
        )
        if contract_address is not None:
            self._logger.info(f'Found proxy contract {contract_address} for {address}')
            # check proxy locally
            proxy_abi_file_path = f'{abi_directory}/{abi_chain}_{contract_address}.json'
            if os.path.exists(proxy_abi_file_path):
                with open(proxy_abi_file_path) as file:
                    abi = file.read()
                    self._logger.info(
                        f'Retrieved proxy({contract_address}) ABI from local storage for {address}'
                    )
                    return json.loads(abi)

            abi = await self._client.contract.contract_abi(address=contract_address)

            if abi:
                # Save the ABI to a file
                with open(proxy_abi_file_path, 'w') as file:
                    json.dump(abi, file, indent=4)
                    self._logger.info(
                        f'Saved proxy({contract_address}) ABI to local storage for {address}'
                    )
            return abi

        abi_status = next(
            (r['ABI'] for r in source_code if r['ABI'] != 'Contract source code not verified'),
            None,
        )
        if abi_status is None:
            self._logger.info(f'No ABI found for {address}')
            return None

        abi = await self._client.contract.contract_abi(address=address)
        if abi:
            # Save the ABI to a file
            with open(abi_file_path, 'w') as file:
                json.dump(abi, file, indent=4)
                self._logger.info(f'Saved ABI to local storage for {address}')
        else:
            self._logger.warning(f'No proxy contract found for {address}')

        return abi

    async def _decode_elements(self, elements, abi, address, function, decode_type):
        if (
            abi is None
            or function.__name__ in ['internal_txs', 'token_transfers']
            or decode_type != 'auto'
        ):
            self._logger.info(f'ABI is not available or decode not needed for {address}')
            return elements  # Early exit if ABI is not necessary or available

        self._logger.info(f'Decoding {len(elements)} elements for {address}...')
        abi = json.loads(abi)
        abi_decode_func = (
            decode_log_data if function.__name__ == 'get_logs' else decode_transaction_input
        )

        for i, element in enumerate(elements):
            try:
                elements[i] = abi_decode_func(element, abi)
            except Exception as e:
                elements[i] = element
                self._logger.warning(
                    f'Error decoding element {i} element {element} for {address}: {e}'
                )

        return elements

    async def _get_elements_batch(
        self, function, address, start_block, end_block, offset, **kwargs
    ):
        # for scanners like routscan, with limit 25 transactions per request
        if offset is None:
            offset = 1_000 if function.__name__ == 'get_logs' else 10_000

        elements = []
        start_batch_block = start_block
        end_batch_block = end_block

        # fetch elements from the current block
        while True:
            print(f'Fetching {offset} elements for {address} from block {start_batch_block}')
            try:
                txs = await function(
                    address=address,
                    start_block=start_batch_block,
                    end_block=end_batch_block,
                    page=1,
                    offset=offset,
                    **kwargs,
                )
            except (
                Exception
            ) as e:  # Ловим более общее исключение, поскольку точный тип может варьироваться
                print(f'Error fetching transactions for {address}: {e}')
                break

            elements.extend(txs)
            # finish if less then max transactions in batch bcs latest txs at all
            if len(txs) < offset:
                break

            if function.__name__ == 'get_logs':
                first_batch_block = int(txs[0]['blockNumber'], 16)
                last_batch_block = int(txs[-1]['blockNumber'], 16)

            else:
                first_batch_block = int(txs[0]['blockNumber'])
                last_batch_block = int(txs[-1]['blockNumber'])

            if start_block > last_batch_block:
                logging.warning(
                    f'End block is lower than start block for {address}, out of range of request'
                )
                break

            if last_batch_block == first_batch_block:
                # if first and last blocks are equal, offset is low and we can lose some txs
                logging.warning(f'First and last blocks are equal, offset is low for {address}')
                break

            # TODO check for sorting method and from part of all
            if first_batch_block > last_batch_block:
                # if scaner have another sorting method
                logging.warning(
                    f'First block is higher than current block for {address} can be problems with sorting, first_batch_block: {first_batch_block}, last_batch_block: {last_batch_block}'
                )
                end_batch_block = first_batch_block
            else:
                logging.warning(
                    f'Normal sorting, first_batch_block: {first_batch_block}, last_batch_block: {last_batch_block}'
                )
                start_batch_block = last_batch_block

            # clear last blockNumber from data from elements to avoid duplicates (TODO check for another sorting)
            elements = [
                element
                for element in elements
                if element['blockNumber'] != elements[-1]['blockNumber']
            ]

        print(f'Fetched {len(elements)} elements in total for {address}, {function.__name__}.')
        return elements

    # TODO for scanners like routscan with low txs fer request limit need to ckeck page pagination method
    # TODO for routscan migrate to their native method
    # TODO async for abi and base request still broke limits
    async def fetch_all_elements(
        self,
        address: str,
        data_type: str,
        start_block: int = 0,
        end_block: int | None = None,
        decode_type: str = 'auto',
        offset: int = None,
        *args,
        **kwargs,
    ) -> list[dict]:
        if end_block is None:
            end_block = 999999999

        # check if data_type is supported
        if data_type not in self.data_model_mapping:
            raise ValueError(f'Unsupported data type: {data_type}')

        # get function by data_type from mapping
        function = self.data_model_mapping[data_type]
        if decode_type == 'auto' and function.__name__ not in ['internal_txs', 'token_transfers']:
            tasks = [
                self._get_elements_batch(
                    function, address, start_block, end_block, offset, **kwargs
                ),
                self.get_proxy_abi(address),
            ]
            elements, abi = await asyncio.gather(*tasks)
            if len(elements) > 0:
                elements = await self._decode_elements(
                    elements, abi, address, function, decode_type
                )
        else:
            elements = await self._get_elements_batch(
                function, address, start_block, end_block, offset, **kwargs
            )

        return elements

    async def fetch_all_elements_optimized(
        self,
        address: str,
        data_type: str,
        start_block: int = 0,
        end_block: int | None = None,
        decode_type: str = 'auto',
        max_concurrent: int = 3,
        max_offset: int = 10000,
        *args,
        **kwargs,
    ) -> list[dict]:
        """
        Optimized fetching of all elements using priority queue and dynamic range splitting.
        
        Args:
            address: Target address
            data_type: Type of data to fetch ('normal_txs', 'internal_txs', 'token_transfers')
            start_block: Starting block number
            end_block: Ending block number (None for current)
            decode_type: Decoding type ('auto', 'manual', etc.)
            max_concurrent: Maximum concurrent requests (respects rate limits)
            max_offset: Maximum number of items per request
            
        Returns:
            List of all fetched elements
        """
        if end_block is None:
            end_block = int(await self._client.proxy.block_number(), 16)

        # Check if data_type is supported
        if data_type not in self.data_model_mapping:
            raise ValueError(f'Unsupported data type: {data_type}')

        # Get function by data_type from mapping
        function = self.data_model_mapping[data_type]
        
        # Priority queue for block ranges (negative size for max-heap behavior)
        # Format: (-range_size, range_id, start_block, end_block)
        range_queue = []
        range_counter = 0
        
        # Initialize with three ranges: left edge, center, right edge
        total_range = end_block - start_block
        if total_range <= 0:
            return []
            
        # Calculate initial ranges
        left_end = start_block + min(total_range // 4, 50000)
        right_start = max(end_block - total_range // 4, left_end + 1)
        center_start = (left_end + right_start) // 2
        
        # Add initial ranges to queue
        heapq.heappush(range_queue, (-(left_end - start_block), range_counter, start_block, left_end))
        range_counter += 1
        
        if center_start < right_start:
            heapq.heappush(range_queue, (-(right_start - center_start), range_counter, center_start, right_start))
            range_counter += 1
            
        if right_start < end_block:
            heapq.heappush(range_queue, (-(end_block - right_start), range_counter, right_start, end_block))
            range_counter += 1

        # Results storage
        all_elements = []
        completed_ranges = set()
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def worker(range_info):
            """Worker function to process a single block range."""
            _, range_id, block_start, block_end = range_info
            
            async with semaphore:
                try:
                    self._logger.debug(
                        f"Fetching {data_type} for {address}, blocks {block_start}-{block_end} "
                        f"(range {block_end - block_start + 1})"
                    )
                    
                    elements = await function(
                        address=address,
                        start_block=block_start,
                        end_block=block_end,
                        page=1,
                        offset=max_offset,
                        **kwargs,
                    )
                    
                    if not elements:
                        elements = []
                    
                    return range_id, block_start, block_end, elements
                    
                except Exception as e:
                    self._logger.warning(
                        f"Error fetching {data_type} for range {block_start}-{block_end}: {e}"
                    )
                    return range_id, block_start, block_end, []

        # Process ranges until queue is empty
        while range_queue:
            # Get batch of ranges to process
            current_batch = []
            batch_size = min(max_concurrent, len(range_queue))
            
            for _ in range(batch_size):
                if range_queue:
                    range_info = heapq.heappop(range_queue)
                    current_batch.append(range_info)
            
            if not current_batch:
                break
                
            # Process batch concurrently
            tasks = [worker(range_info) for range_info in current_batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    self._logger.error(f"Worker error: {result}")
                    continue
                    
                range_id, block_start, block_end, elements = result
                
                # Check if we got maximum results (need to split range)
                if len(elements) >= max_offset and block_end > block_start:
                    # Split range in half
                    mid_block = (block_start + block_end) // 2
                    
                    # Add both halves back to queue
                    heapq.heappush(
                        range_queue, 
                        (-(mid_block - block_start), range_counter, block_start, mid_block)
                    )
                    range_counter += 1
                    
                    heapq.heappush(
                        range_queue, 
                        (-(block_end - mid_block), range_counter, mid_block + 1, block_end)
                    )
                    range_counter += 1
                    
                    self._logger.debug(
                        f"Split range {block_start}-{block_end} into {block_start}-{mid_block} "
                        f"and {mid_block + 1}-{block_end} (got {len(elements)} elements)"
                    )
                else:
                    # Range is complete, add to results
                    all_elements.extend(elements)
                    completed_ranges.add(range_id)
                    self._logger.debug(
                        f"Completed range {block_start}-{block_end}: {len(elements)} elements"
                    )

        self._logger.info(f"Fetched {len(all_elements)} {data_type} elements for {address}")
        
        # Sort by block number and remove duplicates
        if all_elements:
            # Sort by block number, then by transaction index if available
            def sort_key(element):
                block_num = element.get('blockNumber', '0')
                if isinstance(block_num, str) and block_num.startswith('0x'):
                    block_num = int(block_num, 16)
                else:
                    block_num = int(block_num)
                
                tx_index = element.get('transactionIndex', '0')
                if isinstance(tx_index, str) and tx_index.startswith('0x'):
                    tx_index = int(tx_index, 16)
                else:
                    tx_index = int(tx_index) if tx_index else 0
                    
                return (block_num, tx_index)
            
            all_elements.sort(key=sort_key)
            
            # Remove duplicates based on transaction hash
            seen_hashes = set()
            unique_elements = []
            for element in all_elements:
                tx_hash = element.get('hash')
                if tx_hash and tx_hash not in seen_hashes:
                    seen_hashes.add(tx_hash)
                    unique_elements.append(element)
                elif not tx_hash:  # Keep elements without hash (like logs)
                    unique_elements.append(element)
            
            all_elements = unique_elements
            self._logger.info(f"After deduplication: {len(all_elements)} unique elements")

        # Apply decoding if requested
        if decode_type == 'auto' and function.__name__ not in ['internal_txs', 'token_transfers']:
            if len(all_elements) > 0:
                try:
                    abi = await self.get_proxy_abi(address)
                    all_elements = await self._decode_elements(
                        all_elements, abi, address, function, decode_type
                    )
                except Exception as e:
                    self._logger.warning(f"Error during decoding: {e}")

        return all_elements

    async def _parse_by_pages(
        self,
        start_block: int,
        end_block: int,
        offset: int,
        address: str = None,
        contract_address: str = None,
    ) -> AsyncIterator[dict]:
        page = 1

        while True:
            try:
                transfers = await self._client.account.token_transfers(
                    address=address,
                    contract_address=contract_address,
                    start_block=start_block,
                    end_block=end_block,
                    page=page,
                    offset=offset,
                )
            except ChainscanClientApiError as e:
                if e.message == 'No transactions found':
                    break
                raise
            else:
                for transfer in transfers:
                    yield transfer
                page += 1

    @staticmethod
    def _generate_intervals(
        from_number: int, to_number: int, count: int
    ) -> Iterator[tuple[int, int]]:
        for i in range(from_number, to_number + 1, count):
            yield i, min(i + count - 1, to_number)
