# aiochainscan Scanner Methods Detailed Report

**Test Date:** 2025-07-27 00:42:52

This report shows detailed method-by-method test results for each scanner.

## Arbiscan (`arbitrum`)

- **Domain:** arbiscan.io
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 50.0% (11/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.32s]
- **normal_txs**: ✅ [0.40s]
- **internal_txs**: ✅ [0.41s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.20s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ✅ [0.20s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ❌ (API Error) [0.20s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.33s]

#### Proxy Module

- **block_number**: ✅ [0.43s]
- **get_balance**: ✅ [0.20s]
- **get_block_by_number**: ✅ [0.20s]

#### Stats Module

- **eth_supply**: ✅ [0.60s]
- **eth_price**: ✅ [0.20s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.20s]
- **check_tx_status**: ✅ [0.20s]

## BaseScan (`base`)

- **Domain:** basescan.org
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 45.5% (10/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.20s]
- **normal_txs**: ✅ [0.33s]
- **internal_txs**: ✅ [2.43s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.20s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ✅ [0.20s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ❌ (API Error) [0.20s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.21s]

#### Proxy Module

- **block_number**: ✅ [0.60s]
- **get_balance**: ✅ [0.32s]
- **get_block_by_number**: ✅ [0.92s]

#### Stats Module

- **eth_supply**: ❌ (Exception) [10.00s]
- **eth_price**: ✅ [0.21s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.21s]
- **check_tx_status**: ✅ [0.20s]

## BlastScan (`blast`)

- **Domain:** blastscan.io
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 45.5% (10/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.21s]
- **normal_txs**: ✅ [0.22s]
- **internal_txs**: ❌ (API Error) [0.23s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.23s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ✅ [0.21s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ❌ (API Error) [0.21s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.21s]

#### Proxy Module

- **block_number**: ✅ [0.44s]
- **get_balance**: ✅ [0.21s]
- **get_block_by_number**: ✅ [0.22s]

#### Stats Module

- **eth_supply**: ✅ [6.73s]
- **eth_price**: ✅ [0.21s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.21s]
- **check_tx_status**: ✅ [0.21s]

## BscScan (`bsc`)

- **Domain:** bscscan.com
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 40.9% (9/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.16s]
- **normal_txs**: ✅ [1.95s]
- **internal_txs**: ✅ [0.21s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.16s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ❌ (API Error) [0.18s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ✅ [0.21s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.22s]

#### Proxy Module

- **block_number**: ✅ [0.63s]
- **get_balance**: ✅ [0.16s]
- **get_block_by_number**: ✅ [0.28s]

#### Stats Module

- **eth_supply**: ❌ (API Error) [0.16s]
- **eth_price**: ❌ (API Error) [0.16s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.16s]
- **check_tx_status**: ✅ [0.17s]

## Etherscan (`eth`)

- **Domain:** etherscan.io
- **Networks:** main, sepolia
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 47.7% (21/44)

### Method Results

#### Account Module

- **balance**: ✅ [0.20s]
- **normal_txs**: ✅ [0.21s]
- **internal_txs**: ✅ [0.20s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.20s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ❌ (API Error) [0.21s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ❌ (API Error) [0.21s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.21s]

#### Proxy Module

- **block_number**: ✅ [0.63s]
- **get_balance**: ✅ [0.20s]
- **get_block_by_number**: ✅ [0.67s]

#### Stats Module

- **eth_supply**: ✅ [0.22s]
- **eth_price**: ✅ [0.21s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.20s]
- **check_tx_status**: ✅ [0.20s]

## FtmScan (`fantom`)

- **Domain:** ftmscan.com
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 0.0% (0/22)

### Method Results

#### Account Module

- **balance**: ❌ (Exception) [0.00s]
- **normal_txs**: ❌ (Exception) [0.00s]
- **internal_txs**: ❌ (Exception) [0.00s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (Exception) [0.00s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ❌ (Exception) [0.00s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ❌ (Exception) [0.00s]

#### Logs Module

- **get_logs**: ❌ (Exception) [0.00s]

#### Proxy Module

- **block_number**: ❌ (Exception) [0.00s]
- **get_balance**: ❌ (Exception) [0.01s]
- **get_block_by_number**: ❌ (Exception) [0.00s]

#### Stats Module

- **eth_supply**: ❌ (Exception) [0.00s]
- **eth_price**: ❌ (Exception) [0.00s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ❌ (Exception) [0.00s]
- **check_tx_status**: ❌ (Exception) [0.00s]

## Flare Explorer (`flare`)

- **Domain:** flare.network
- **Networks:** main
- **API Key Required:** No
- **API Key Status:** N/A
- **Success Rate:** 45.5% (10/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.18s]
- **normal_txs**: ✅ [0.12s]
- **internal_txs**: ✅ [0.15s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.11s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ✅ [0.12s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ❌ (API Error) [0.11s]

#### Logs Module

- **get_logs**: ✅ [0.13s]

#### Proxy Module

- **block_number**: ❌ (API Error) [0.33s]
- **get_balance**: ✅ [0.18s]
- **get_block_by_number**: ❌ (API Error) [0.11s]

#### Stats Module

- **eth_supply**: ✅ [0.11s]
- **eth_price**: ✅ [0.12s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.11s]
- **check_tx_status**: ✅ [0.12s]

## GnosisScan (`gnosis`)

- **Domain:** gnosisscan.io
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 54.5% (12/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.21s]
- **normal_txs**: ✅ [0.30s]
- **internal_txs**: ✅ [0.21s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.21s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ✅ [0.21s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ✅ [0.33s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.27s]

#### Proxy Module

- **block_number**: ✅ [0.62s]
- **get_balance**: ✅ [0.22s]
- **get_block_by_number**: ✅ [0.34s]

#### Stats Module

- **eth_supply**: ✅ [0.21s]
- **eth_price**: ✅ [0.22s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.21s]
- **check_tx_status**: ✅ [0.21s]

## LineaScan (`linea`)

- **Domain:** lineascan.build
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 54.5% (12/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.21s]
- **normal_txs**: ✅ [0.26s]
- **internal_txs**: ✅ [0.27s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.21s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ✅ [0.21s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ✅ [0.28s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.21s]

#### Proxy Module

- **block_number**: ✅ [0.54s]
- **get_balance**: ✅ [0.21s]
- **get_block_by_number**: ✅ [0.33s]

#### Stats Module

- **eth_supply**: ✅ [0.24s]
- **eth_price**: ✅ [0.21s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.20s]
- **check_tx_status**: ✅ [0.20s]

## Optimism Etherscan (`optimism`)

- **Domain:** etherscan.io
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 45.5% (10/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.22s]
- **normal_txs**: ✅ [0.25s]
- **internal_txs**: ✅ [0.39s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.21s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ✅ [0.22s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ❌ (API Error) [0.21s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.22s]

#### Proxy Module

- **block_number**: ✅ [0.56s]
- **get_balance**: ✅ [0.25s]
- **get_block_by_number**: ✅ [0.32s]

#### Stats Module

- **eth_supply**: ❌ (Exception) [10.00s]
- **eth_price**: ✅ [0.26s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.22s]
- **check_tx_status**: ✅ [0.21s]

## PolygonScan (`polygon`)

- **Domain:** polygonscan.com
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ✅ Configured
- **Success Rate:** 54.5% (12/22)

### Method Results

#### Account Module

- **balance**: ✅ [0.17s]
- **normal_txs**: ✅ [0.22s]
- **internal_txs**: ✅ [0.16s]
- **erc20_transfers**: ❌ (Exception) [0.00s]

#### Block Module

- **block_reward**: ❌ (API Error) [0.16s]
- **block_countdown**: ❌ (Exception) [0.00s]
- **daily_block_count**: ❌ (Exception) [0.00s]

#### Contract Module

- **contract_abi**: ✅ [0.16s]
- **contract_source**: ❌ (Exception) [0.00s]

#### Gas_Tracker Module

- **gas_estimate**: ❌ (Exception) [0.00s]
- **gas_oracle**: ✅ [0.22s]

#### Logs Module

- **get_logs**: ❌ (API Error) [0.18s]

#### Proxy Module

- **block_number**: ✅ [0.51s]
- **get_balance**: ✅ [0.16s]
- **get_block_by_number**: ✅ [0.27s]

#### Stats Module

- **eth_supply**: ✅ [0.16s]
- **eth_price**: ✅ [0.16s]
- **nodes_size**: ❌ (Exception) [0.00s]

#### Token Module

- **token_supply**: ❌ (Exception) [0.00s]
- **token_balance**: ❌ (Exception) [0.00s]

#### Transaction Module

- **tx_receipt_status**: ✅ [0.17s]
- **check_tx_status**: ✅ [0.16s]

## OKLink X Layer (`xlayer`)

- **Domain:** oklink.com/api/v5/explorer/xlayer
- **Networks:** main
- **API Key Required:** Yes
- **API Key Status:** ❌ Missing
- **Success Rate:** 0.0% (0/0)

### Method Results

No methods tested (configuration error)

### Errors

- main: API key required for OKLink X Layer. Set one of these environment variables: OKLINK_X_LAYER_KEY, XLAYER_KEY, XLAYER_API_KEY, SCANNER_XLAYER_KEY

