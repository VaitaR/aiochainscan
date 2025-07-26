from datetime import date

from aiochainscan.common import check_closest_value, get_daily_stats_params
from aiochainscan.modules.base import BaseModule
from aiochainscan.utils.date import default_range


class Block(BaseModule):
    """Blocks

    https://docs.etherscan.io/api-endpoints/blocks
    """

    @property
    def _module(self) -> str:
        return 'block'

    async def block_reward(self, block_no: int | None = None) -> dict | None:
        """Get Block And Uncle Rewards by BlockNo

        Args:
            block_no: Block number to get rewards for. If None, uses previous block (current - 1).

        Returns:
            Block reward data or None if no reward available (e.g., PoS block)

        Examples:
            >>> rewards = await client.block.block_reward()  # Previous block
            >>> rewards = await client.block.block_reward(15000000)  # Specific block
        """
        if block_no is None:
            # Get current block number and use previous block (guaranteed to have rewards if PoW)
            current_block_hex = await self._client.proxy.block_number()
            current_block = int(current_block_hex, 16)
            block_no = max(current_block - 1, 0)  # Ensure we don't go below 0

        data = await self._get(action='getblockreward', blockno=block_no)

        # Handle API responses
        if isinstance(data, dict) and data.get('status') == '0':
            return None  # No reward yet / PoS block / error

        return data

    async def block_countdown(self, block_no: int | None = None, *, offset: int = 1_000) -> dict | None:
        """Get Estimated Block Countdown Time by BlockNo

        Args:
            block_no: Future block number to get countdown for. If None, uses current_block + offset.
            offset: Number of blocks to add to current block when block_no is None (default: 1000)

        Returns:
            Block countdown data

        Raises:
            ValueError: If block_no is invalid or block difference exceeds limits

        Examples:
            >>> countdown = await client.block.block_countdown()  # current + 1000
            >>> countdown = await client.block.block_countdown(offset=500)  # current + 500
            >>> countdown = await client.block.block_countdown(20000000)  # specific block
        """
        # Get current block number
        current_block_hex = await self._client.proxy.block_number()
        current_block = int(current_block_hex, 16)

        if block_no is None:
            block_no = current_block + offset

        # Validate block number
        block_diff = block_no - current_block
        if block_diff <= 0:
            raise ValueError("Past block for countdown")

        if block_diff > 2_000_000:
            raise ValueError("Block number too large (max difference: 2,000,000 blocks)")

        response = await self._get(action='getblockcountdown', blockno=block_no)

        # Handle API errors with specific messages
        if (isinstance(response, dict) and
            response.get('status') == '0'):
            message = response.get('message', '')
            if 'Block number too large' in message:
                raise ValueError(message)
            elif message.startswith('No transactions found'):
                return None

        return response

    async def est_block_countdown_time(self, blockno: int) -> dict:
        """Get Estimated Block Countdown Time by BlockNo

        Deprecated: Use block_countdown instead
        """
        return await self.block_countdown(blockno)

    async def block_number_by_ts(self, ts: int, closest: str) -> dict:
        """Get Block Number by Timestamp"""
        return await self._get(
            action='getblocknobytime', timestamp=ts, closest=check_closest_value(closest)
        )

    async def daily_average_block_size(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict:
        """Get Daily Average Block Size"""
        return await self._get(
            **get_daily_stats_params('dailyavgblocksize', start_date, end_date, sort)
        )

    async def daily_block_count(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        sort: str | None = None,
    ) -> dict | None:
        """Get Daily Block Count and Rewards

        Args:
            start_date: Start date in YYYY-MM-DD format. If None, defaults to today-30d.
            end_date: End date in YYYY-MM-DD format. If None, defaults to today.
            sort: Sort direction ('asc' or 'desc')

        Returns:
            Daily block count data or None if no data found

        Examples:
            >>> data = await client.block.daily_block_count()  # Last 30 days
            >>> data = await client.block.daily_block_count(
            ...     start_date=date(2024, 1, 1),
            ...     end_date=date(2024, 1, 31)
            ... )
        """
        if start_date is None or end_date is None:
            start_date, end_date = default_range(days=30)

        # Make API request using stats module
        response = await self._get(
            module='stats',
            action='dailyblkcount',
            startdate=start_date.isoformat(),
            enddate=end_date.isoformat(),
            sort=sort,
        )

        # Handle "No transactions found" response
        if (isinstance(response, dict) and
            response.get('status') == '0' and
            response.get('message', '').startswith('No transactions found')):
            return None

        return response

    async def daily_block_rewards(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict:
        """Get Daily Block Rewards"""
        return await self._get(
            **get_daily_stats_params('dailyblockrewards', start_date, end_date, sort)
        )

    async def daily_average_time_for_a_block(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict:
        """Get Daily Average Time for A Block to be Included in the Ethereum Blockchain"""
        return await self._get(
            **get_daily_stats_params('dailyavgblocktime', start_date, end_date, sort)
        )

    async def daily_uncle_block_count(
        self, start_date: date, end_date: date, sort: str | None = None
    ) -> dict:
        """Get Daily Uncle Block Count and Rewards"""
        return await self._get(
            **get_daily_stats_params('dailyuncleblkcount', start_date, end_date, sort)
        )
