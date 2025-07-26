# aiochainscan Scanner Methods Detailed Report

**Test Date:** 2025-07-27 02:03:38

This report shows detailed method-by-method test results for each scanner.

## Arbiscan (`arbitrum`)

- **Domain:** arbiscan.io
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 72.7% (16/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.22s]
- **normal_txs**: ✅ [2.57s]
- **internal_txs**: ✅ [0.75s]
- **erc20_transfers**: ✅ [0.28s]

#### Block Module

- **block_reward**: ✅ [0.21s]
- **block_countdown**: ❌ (Exception) [0.20s]
- **daily_block_count**: ❌ (API Error) [0.20s]

#### Contract Module

- **contract_abi**: ✅ [0.21s]
- **contract_source**: ✅ [0.32s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Feature Not Supported) [0.00s]
- **gas_oracle**: ❌ (API Error) [0.20s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.85s]

#### Proxy Module

- **block_number**: ✅ [1.36s]
- **get_balance**: ✅ [1.25s]
- **get_block_by_number**: ✅ [0.21s]

#### Stats Module

- **eth_supply**: ✅ [0.53s]
- **eth_price**: ✅ [0.20s]
- **nodes_size**: ❌ [0.21s]

#### Token Module

- **token_supply**: ✅ [0.21s]
- **token_balance**: ✅ [0.21s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.20s]
- **check_tx_status**: ✅ [0.20s]

## BscScan (`bsc`)

- **Domain:** bscscan.com
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 63.6% (14/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.16s]
- **normal_txs**: ✅ [0.56s]
- **internal_txs**: ✅ [0.17s]
- **erc20_transfers**: ✅ [3.40s]

#### Block Module

- **block_reward**: ✅ [0.17s]
- **block_countdown**: ❌ (Exception) [0.16s]
- **daily_block_count**: ❌ (API Error) [0.16s]

#### Contract Module

- **contract_abi**: ✅ [0.17s]
- **contract_source**: ✅ [0.17s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Feature Not Supported) [0.00s]
- **gas_oracle**: ❌ (Feature Not Supported) [0.21s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.17s]

#### Proxy Module

- **block_number**: ✅ [0.63s]
- **get_balance**: ✅ [0.16s]
- **get_block_by_number**: ✅ [0.28s]

#### Stats Module

- **eth_supply**: ❌ (API Error) [0.17s]
- **eth_price**: ❌ (API Error) [0.16s]
- **nodes_size**: ❌ [0.16s]

#### Token Module

- **token_supply**: ✅ [0.17s]
- **token_balance**: ✅ [0.16s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.16s]
- **check_tx_status**: ✅ [0.16s]

## Etherscan (`eth`)

- **Domain:** etherscan.io
- **Networks:** main, sepolia
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 70.5% (31/44)

### Method Results

#### Account Module

- **balance**: ✅ [0.21s]
- **normal_txs**: ✅ [0.22s]
- **internal_txs**: ✅ [0.22s]
- **erc20_transfers**: ✅ [0.25s]

#### Block Module

- **block_reward**: ✅ [0.22s]
- **block_countdown**: ❌ (Exception) [0.21s]
- **daily_block_count**: ❌ (API Error) [0.21s]

#### Contract Module

- **contract_abi**: ❌ (API Error) [0.21s]
- **contract_source**: ❌ [0.21s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Feature Not Supported) [0.00s]
- **gas_oracle**: ❌ (API Error) [0.22s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.21s]

#### Proxy Module

- **block_number**: ✅ [0.42s]
- **get_balance**: ✅ [0.22s]
- **get_block_by_number**: ✅ [0.44s]

#### Stats Module

- **eth_supply**: ✅ [0.22s]
- **eth_price**: ✅ [0.21s]
- **nodes_size**: ❌ [0.21s]

#### Token Module

- **token_supply**: ✅ [0.21s]
- **token_balance**: ✅ [0.22s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.23s]
- **check_tx_status**: ✅ [0.28s]

## Optimism Etherscan (`optimism`)

- **Domain:** etherscan.io
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 68.2% (15/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.21s]
- **normal_txs**: ✅ [0.24s]
- **internal_txs**: ✅ [0.43s]
- **erc20_transfers**: ✅ [0.24s]

#### Block Module

- **block_reward**: ✅ [0.21s]
- **block_countdown**: ❌ (Exception) [0.21s]
- **daily_block_count**: ❌ (API Error) [0.22s]

#### Contract Module

- **contract_abi**: ✅ [0.21s]
- **contract_source**: ✅ [0.22s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Feature Not Supported) [0.00s]
- **gas_oracle**: ❌ (API Error) [0.21s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.22s]

#### Proxy Module

- **block_number**: ✅ [0.43s]
- **get_balance**: ✅ [0.22s]
- **get_block_by_number**: ✅ [0.32s]

#### Stats Module

- **eth_supply**: ❌ (Exception) [10.00s]
- **eth_price**: ✅ [0.22s]
- **nodes_size**: ❌ [0.21s]

#### Token Module

- **token_supply**: ✅ [0.22s]
- **token_balance**: ✅ [0.21s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.21s]
- **check_tx_status**: ✅ [0.21s]

## PolygonScan (`polygon`)

- **Domain:** polygonscan.com
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 72.7% (16/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.16s]
- **normal_txs**: ✅ [0.21s]
- **internal_txs**: ✅ [0.16s]
- **erc20_transfers**: ✅ [0.29s]

#### Block Module

- **block_reward**: ✅ [0.16s]
- **block_countdown**: ❌ (Exception) [0.16s]
- **daily_block_count**: ❌ (API Error) [0.20s]

#### Contract Module

- **contract_abi**: ✅ [0.17s]
- **contract_source**: ✅ [0.28s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Feature Not Supported) [0.00s]
- **gas_oracle**: ❌ (Feature Not Supported) [0.20s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.19s]

#### Proxy Module

- **block_number**: ✅ [0.67s]
- **get_balance**: ✅ [0.16s]
- **get_block_by_number**: ✅ [0.29s]

#### Stats Module

- **eth_supply**: ✅ [0.16s]
- **eth_price**: ✅ [0.16s]
- **nodes_size**: ❌ [0.16s]

#### Token Module

- **token_supply**: ✅ [0.16s]
- **token_balance**: ✅ [0.16s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.16s]
- **check_tx_status**: ✅ [0.16s]

