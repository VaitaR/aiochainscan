"""
Tests for analytics service with Polars DataFrame support.

Focuses on data integrity, especially preventing integer overflow for Wei values.
"""

import pytest

# Skip all tests if Polars is not available
pytest.importorskip('polars')

import polars as pl  # noqa: E402

from aiochainscan.services.analytics import (  # noqa: E402
    is_polars_available,
    token_portfolio_to_dataframe,
    transactions_to_dataframe,
)


class TestTransactionsToDataframe:
    """Tests for transactions_to_dataframe function."""

    @pytest.mark.asyncio
    async def test_empty_transactions(self):
        """Test that empty list returns DataFrame with correct schema."""
        df = await transactions_to_dataframe([])

        assert df.is_empty()
        assert df.schema == {
            'hash': pl.Utf8,
            'block_number': pl.Int64,
            'from_address': pl.Utf8,
            'to_address': pl.Utf8,
            'value_wei': pl.Utf8,  # String to prevent overflow
            'value_eth': pl.Float64,
            'gas_used': pl.Utf8,  # String to prevent overflow
            'timestamp': pl.Utf8,
        }

    @pytest.mark.asyncio
    async def test_basic_transaction(self):
        """Test conversion of a basic transaction."""
        tx = {
            'hash': '0xabc123',
            'block_number': 12345678,
            'from': '0xsender',
            'to': '0xrecipient',
            'value': '1000000000000000000',  # 1 ETH in Wei
            'gas_used': '21000',
            'timestamp': '1234567890',
        }

        df = await transactions_to_dataframe([tx])

        assert len(df) == 1
        row = df.row(0, named=True)
        assert row['hash'] == '0xabc123'
        assert row['value_wei'] == '1000000000000000000'
        assert row['value_eth'] == pytest.approx(1.0, rel=1e-15)
        assert row['gas_used'] == '21000'

    @pytest.mark.asyncio
    async def test_value_wei_stored_as_string_prevents_overflow(self):
        """
        CRITICAL TEST: Verify that large Wei values don't overflow.

        Int64 max = 9,223,372,036,854,775,807 ≈ 9.22 ETH
        Any transaction > 9.22 ETH would overflow if stored as Int64.
        """
        # Test with 100 ETH (10x the Int64 limit for Wei)
        large_value = 100 * 10**18  # 100 ETH in Wei

        tx = {
            'hash': '0xwhale',
            'block_number': 12345678,
            'from': '0xwhale_sender',
            'to': '0xwhale_recipient',
            'value': str(large_value),
            'gas_used': '100000',
            'timestamp': '1234567890',
        }

        df = await transactions_to_dataframe([tx])

        # Verify value_wei is stored correctly as string
        row = df.row(0, named=True)
        assert row['value_wei'] == str(large_value)
        assert row['value_eth'] == pytest.approx(100.0, rel=1e-15)

        # Verify the column type is Utf8 (String), not Int64
        assert df.schema['value_wei'] == pl.Utf8

    @pytest.mark.asyncio
    async def test_extreme_whale_transaction(self):
        """
        Test with an extreme whale transaction (1 million ETH).

        This would be 1,000,000 * 10^18 = 10^24 Wei.
        Int64 max is ~9.22 * 10^18, so this is ~10^5x larger.
        """
        extreme_value = 1_000_000 * 10**18  # 1 million ETH

        tx = {
            'hash': '0xmega_whale',
            'block_number': 99999999,
            'from': '0xmega_sender',
            'to': '0xmega_recipient',
            'value': str(extreme_value),
            'gas_used': str(10**9),  # 1 billion gas (also large)
            'timestamp': '9999999999',
        }

        df = await transactions_to_dataframe([tx])

        row = df.row(0, named=True)
        assert row['value_wei'] == str(extreme_value)
        assert row['value_eth'] == pytest.approx(1_000_000.0, rel=1e-10)
        assert row['gas_used'] == str(10**9)

    @pytest.mark.asyncio
    async def test_int64_boundary_value(self):
        """
        Test with value exactly at Int64 boundary.

        This tests the edge case where the value is just above
        what Int64 can represent.
        """
        int64_max = 9_223_372_036_854_775_807
        value_just_over_int64 = int64_max + 1

        tx = {
            'hash': '0xboundary',
            'block_number': 12345678,
            'from': '0xsender',
            'to': '0xrecipient',
            'value': str(value_just_over_int64),
            'gas_used': '21000',
            'timestamp': '1234567890',
        }

        df = await transactions_to_dataframe([tx])

        row = df.row(0, named=True)
        # Stored as string, so no overflow
        assert row['value_wei'] == str(value_just_over_int64)

    @pytest.mark.asyncio
    async def test_blockscout_v2_format(self):
        """Test handling of BlockScout V2 nested address format."""
        tx = {
            'hash': '0xblockscout',
            'block_number': 12345678,
            'from': {'hash': '0xfrom_address'},
            'to': {'hash': '0xto_address'},
            'value': '5000000000000000000',  # 5 ETH
            'gas_used': '50000',
            'timestamp': '1234567890',
        }

        df = await transactions_to_dataframe([tx])

        row = df.row(0, named=True)
        assert row['from_address'] == '0xfrom_address'
        assert row['to_address'] == '0xto_address'
        assert row['value_wei'] == '5000000000000000000'

    @pytest.mark.asyncio
    async def test_etherscan_format_camelCase(self):  # noqa: N802
        """Test handling of Etherscan camelCase format."""
        tx = {
            'hash': '0xetherscan',
            'blockNumber': 12345678,
            'from': '0xsender',
            'to': '0xrecipient',
            'value': '2000000000000000000',  # 2 ETH
            'gasUsed': '42000',
            'timeStamp': '1234567890',
        }

        df = await transactions_to_dataframe([tx])

        row = df.row(0, named=True)
        assert row['block_number'] == 12345678
        assert row['value_wei'] == '2000000000000000000'
        assert row['gas_used'] == '42000'
        assert row['timestamp'] == '1234567890'

    @pytest.mark.asyncio
    async def test_missing_values_default_to_zero(self):
        """Test that missing value fields default to zero."""
        tx = {
            'hash': '0xminimal',
            'block_number': 12345678,
            'from': '0xsender',
            'to': '0xrecipient',
            # No 'value' or 'gas_used' fields
        }

        df = await transactions_to_dataframe([tx])

        row = df.row(0, named=True)
        assert row['value_wei'] == '0'
        assert row['value_eth'] == 0.0
        assert row['gas_used'] == '0'

    @pytest.mark.asyncio
    async def test_multiple_transactions(self):
        """Test conversion of multiple transactions."""
        txs = [
            {
                'hash': f'0xtx{i}',
                'block_number': 12345678 + i,
                'from': f'0xsender{i}',
                'to': f'0xrecipient{i}',
                'value': str(i * 10**18),  # i ETH
                'gas_used': str(21000 + i * 1000),
                'timestamp': str(1234567890 + i),
            }
            for i in range(10)
        ]

        df = await transactions_to_dataframe(txs)

        assert len(df) == 10
        # Check each row
        for i, row in enumerate(df.iter_rows(named=True)):
            assert row['hash'] == f'0xtx{i}'
            assert row['value_wei'] == str(i * 10**18)

    @pytest.mark.asyncio
    async def test_async_iterator_input(self):
        """Test that async iterators are properly handled."""

        async def tx_generator():
            for i in range(3):
                yield {
                    'hash': f'0xasync{i}',
                    'block_number': 12345678 + i,
                    'from': '0xsender',
                    'to': '0xrecipient',
                    'value': str(10**18),  # 1 ETH
                    'gas_used': '21000',
                    'timestamp': '1234567890',
                }

        df = await transactions_to_dataframe(tx_generator())

        assert len(df) == 3
        hashes = df['hash'].to_list()
        assert hashes == ['0xasync0', '0xasync1', '0xasync2']

    @pytest.mark.asyncio
    async def test_warns_on_large_materialization(self, monkeypatch, caplog):
        """Warn when too many rows are accumulated in memory before DataFrame build."""
        from aiochainscan.services import analytics as analytics_mod

        monkeypatch.setattr(analytics_mod, 'OOM_WARNING_THRESHOLD', 2)
        txs = [
            {
                'hash': '0x1',
                'block_number': 1,
                'from': '0xsender',
                'to': '0xrecipient',
                'value': '1',
                'gas_used': '21000',
                'timestamp': '1',
            },
            {
                'hash': '0x2',
                'block_number': 2,
                'from': '0xsender',
                'to': '0xrecipient',
                'value': '2',
                'gas_used': '21000',
                'timestamp': '2',
            },
        ]

        with caplog.at_level('WARNING'):
            _ = await transactions_to_dataframe(txs)

        assert 'Materializing 2 transactions in-memory' in caplog.text


class TestTokenPortfolioToDataframe:
    """Tests for token_portfolio_to_dataframe function."""

    @pytest.mark.asyncio
    async def test_empty_portfolio(self):
        """Test that empty portfolio returns DataFrame with correct schema."""
        df = await token_portfolio_to_dataframe([])

        assert df.is_empty()
        assert df.schema == {
            'symbol': pl.Utf8,
            'name': pl.Utf8,
            'contract_address': pl.Utf8,
            'balance': pl.Float64,
            'decimals': pl.Int64,
        }

    @pytest.mark.asyncio
    async def test_basic_token_holding(self):
        """Test conversion of a basic token holding."""
        tokens = [
            {
                'token': {
                    'symbol': 'USDC',
                    'name': 'USD Coin',
                    'address': '0xusdc_contract',
                    'decimals': 6,
                },
                'value': '1000000000',  # 1000 USDC (6 decimals)
            }
        ]

        df = await token_portfolio_to_dataframe(tokens)

        assert len(df) == 1
        row = df.row(0, named=True)
        assert row['symbol'] == 'USDC'
        assert row['name'] == 'USD Coin'
        assert row['balance'] == pytest.approx(1000.0, rel=1e-10)
        assert row['decimals'] == 6

    @pytest.mark.asyncio
    async def test_token_with_18_decimals(self):
        """Test handling of tokens with 18 decimals (like ETH)."""
        tokens = [
            {
                'token': {
                    'symbol': 'WETH',
                    'name': 'Wrapped Ether',
                    'address': '0xweth_contract',
                    'decimals': 18,
                },
                'value': str(50 * 10**18),  # 50 WETH
            }
        ]

        df = await token_portfolio_to_dataframe(tokens)

        row = df.row(0, named=True)
        assert row['balance'] == pytest.approx(50.0, rel=1e-10)

    @pytest.mark.asyncio
    async def test_blockscout_v2_address_hash(self):
        """Test handling of BlockScout V2 address_hash format."""
        tokens = [
            {
                'token': {
                    'symbol': 'TOKEN',
                    'name': 'Test Token',
                    'address_hash': '0xblockscout_address',
                    'decimals': 18,
                },
                'value': str(10**18),
            }
        ]

        df = await token_portfolio_to_dataframe(tokens)

        row = df.row(0, named=True)
        assert row['contract_address'] == '0xblockscout_address'


class TestPolarsAvailability:
    """Tests for is_polars_available function."""

    def test_polars_is_available(self):
        """Test that Polars is correctly detected as available."""
        # Since we're running these tests with Polars installed
        assert is_polars_available() is True
