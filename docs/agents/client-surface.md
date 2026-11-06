# ChainscanClient surface

Agent reference for the public client. Read it when adding or changing a convenience
method, or when you need the exact name and return shape of one. Which scanner declares
which method: `aiochainscan scanners` and [providers.md](providers.md).

## Cheat sheet

```python
from aiochainscan import ChainscanClient

async with ChainscanClient.from_config('etherscan', 'ethereum') as client:
    # ── Account ──────────────────────────────────────────────
    balance = await client.get_balance('0x...')                   # Wei string
    txs     = await client.get_transactions('0x...')              # single page
    all_txs = await client.get_all_transactions('0x...')          # ALL (streaming aggregation → list)
    itxs    = await client.get_internal_transactions('0x...')     # single page
    erc20   = await client.get_token_transfers('0x...')           # single page
    erc721  = await client.get_erc721_transfers('0x...')          # single page
    erc1155 = await client.get_erc1155_transfers('0x...')         # single page
    tokens  = await client.get_token_portfolio('0x...')           # ERC-20 holdings
    nfts    = await client.get_nft_portfolio('0x...')             # NFT holdings

    # ── Transactions ─────────────────────────────────────────
    tx     = await client.get_transaction('0xHASH...')            # by hash
    status = await client.get_transaction_status('0xHASH...')     # receipt status
    check  = await client.check_transaction_status('0xHASH...')   # execution status
    final  = await client.wait_for_transaction('0xHASH...')       # poll until mined (120s/10s)

    # ── Blocks ───────────────────────────────────────────────
    block     = await client.get_block(12345678)                  # by number
    reward    = await client.get_block_reward(12345678)           # mining reward
    countdown = await client.get_block_countdown(99999999)        # ETA to block
    by_ts     = await client.get_block_by_timestamp(1609459200)   # nearest block
    reached   = await client.wait_for_block(20_000_000)           # poll until reached (600s/10s)

    # ── Contracts ────────────────────────────────────────────
    abi     = await client.get_contract_abi('0x...')              # JSON ABI (this address)
    impl    = await client.get_contract_abi('0x...', follow_proxy=True)  # proxy -> implementation ABI
    deep    = await client.get_contract_abi(                           # + storage slots / diamond loupe
        '0x...', follow_proxy=True, proxy_strategy='auto'
    )
    source  = await client.get_contract_source('0x...')           # verified source
    created = await client.get_contract_creation(['0x...'])       # creator + tx
    verdict = await client.wait_for_verification(guid)            # poll Pass/Fail (300s/10s)

    # ── Decoding (ABI resolved for you, proxies followed) ────
    call   = await client.decode_input(tx['input'], address=tx['to'])   # {'decoded_func', 'decoded_data'}
    calls  = await client.decode_transactions(txs)                      # ABI per tx['to'], once each
    events = await client.decode_logs(logs)                             # ABI per log['address']

    # ── Tokens ───────────────────────────────────────────────
    bal     = await client.get_token_balance('0xWALLET', '0xTOKEN')  # raw units
    supply  = await client.get_token_supply('0xTOKEN')               # total supply
    info    = await client.get_token_info('0xTOKEN')                 # name/symbol/decimals
    holders = await client.get_token_holders('0xTOKEN')              # single page
    all_hld = await client.get_all_token_holders('0xTOKEN')          # ALL (streaming aggregation → list)
    top_hld = await client.get_top_token_holders('0xTOKEN', limit=100)  # top-N by balance
    count   = await client.get_token_holder_count('0xTOKEN')         # int

    # ── Gas & Stats ──────────────────────────────────────────
    price   = await client.get_eth_price()                        # USD/BTC
    gas     = await client.get_gas_oracle()                       # safe/propose/fast
    est     = await client.get_gas_estimate(2_000_000_000)        # ETA in seconds
    eth_sup = await client.get_eth_supply()                       # total ETH supply

    # ── Event Logs ───────────────────────────────────────────
    logs     = await client.get_logs('0x...', from_block=0)       # single page (≤1000)
    all_logs = await client.get_all_logs('0x...', from_block=0)   # ALL (streaming aggregation → list)

    # ── Proxy / JSON-RPC ─────────────────────────────────────
    result  = await client.eth_call('0xTO', '0xDATA')             # eth_call
    bal_hex = await client.eth_get_balance('0x...')                # hex Wei

    # ── High-level APIs ──────────────────────────────────────
    contract = await client.get_contract('0x...')                  # SmartContract (follows proxies)
    async for event in contract.iter_events("Transfer", limit=100):
        print(event.args['from'], event.args['to'], event.args['value'])

    name    = await client.lookup_address('0x...')                 # ENS reverse
    address = await client.resolve_name('vitalik.eth')             # ENS forward
    # Three-way ENS contract: `None` means the record does not exist. A
    # scanner that does not declare eth_call raises MethodNotDeclaredError
    # (forward resolution reads the ENS registry). A scanner/network
    # combination that cannot serve ENS at all (anything off Ethereum
    # mainnet) raises ENSScannerUnavailableError (a ValueError subclass) —
    # from resolve_names()/lookup_addresses() too, not just the singles.
    # Rate limits and transport failures surface as themselves.

    # ── Streaming (large datasets, constant ~10MB RAM) ───────
    async for batch in client.iter_transactions_streaming('0x...', batch_size=1000):
        process(batch)
    async for batch in client.iter_token_holders_streaming('0xTOKEN', batch_size=1000):
        process(batch)

    # ── DataFrame export ─────────────────────────────────────
    df = await client.get_transactions_df('0x...')                 # Polars (ALL txs!)
    df = await client.get_token_portfolio_df('0x...')              # Polars

    # ── Self-hosted / custom instances ───────────────────────
    # A URL-shaped `network` targets any BlockScout instance (no API key):
    async with ChainscanClient.from_config(
        'blockscout_v2', 'https://my-blockscout.internal', expected_chain_id=100
    ) as selfhosted:
        info = await selfhosted.get_chain_info()    # ChainInfo (cached 1h)
        ok = await selfhosted.validate_chain(100)   # ChainscanDataError on mismatch
    # Etherscan v2 proxy: api_key still required + expected_chain_id mandatory:
    client = ChainscanClient.from_config(
        'etherscan', 'https://eth-proxy.internal', api_key='...', expected_chain_id=137
    )

    # ── Value conversion helpers (module-level, float-free) ──
    from aiochainscan import format_ether, hex_to_int, to_iso, to_decimal_amount, wei_to_ether

    ether = wei_to_ether('1500000000000000000')      # Decimal('1.5') — exact, never float
    nice  = format_ether('1500000000000000000')      # '1.500000' (half-up, any magnitude)
    usdc  = to_decimal_amount('1500000', decimals=6) # Decimal('1.5') — any token precision
    n     = hex_to_int('0x1a')                       # 26 — hex str | decimal str | int
    iso   = to_iso('1609459200')                     # '2021-01-01T00:00:00+00:00'
```

Progress feedback threads through every `get_all_*` / `iter_*` call:

```python
from aiochainscan.utils.progress_helpers import console_progress

txs = await client.get_all_transactions(address, on_progress=console_progress())
```

## Custom base URLs

A `network` string containing `scheme://` is treated as a base URL; anything else
resolves through the chain registry (aliases never contain `://`). URLs are validated in
`aiochainscan/base_url.py`: https only (`http` requires `allow_http=True`), no
credentials/query/`..` segments, trailing slash normalized away. `expected_chain_id` is
validated once before the first request (Network-layer guard → `ChainscanDataError`).
`get_chain_info()` probes BlockScout via `POST {base}/api/eth-rpc` `eth_chainId` and
resolves Etherscan chains through the keyless `GET /v2/chainlist` registry — both cached
1h in a process-shared `chain:`-namespaced cache (chainlist downloaded once). NodeReal
rejects custom base URLs (its key rides in the URL path).

## Polling helpers

`wait_for_transaction` / `wait_for_verification` / `wait_for_block` are pure composition
over existing `Method` calls (no new enum values). They poll with `asyncio.sleep`, use a
loop-clock deadline (`ChainscanWaitTimeoutError(what, waited, last_state)` on expiry),
return pending-vs-final states (revert / `Fail` verdicts are returned, not raised) and
require only the methods they build on.

## Value conversion helpers (`convert.py`)

Module-level, stateless, stdlib-only utilities for the string scalars every explorer API
returns, all exported from the package root and enforced by `tests/test_convert.py`.

- Wei/token math is `Decimal`-exact (`to_decimal_amount` / `wei_to_ether`): integer
  str/int only. Rejected as corrupted data: fractional base-unit strings, scientific
  notation (`'1e18'`), `'1_000'`-style separators, full-width digits and `bool`.
  Negatives are valid; 10^30+ wei stays exact.
- `format_ether` renders fixed-precision strings (half-up, context precision sized to the
  value so 10^40 wei does not overflow).
- `hex_to_int` accepts hex `'0x1a'` / decimal `'26'` / int (the proxy-vs-REST dual mode);
  signed hex `-0x10` works; bare `'1a'` is ambiguous → `ValueError`; the
  underscore/full-width/`bool` rejections apply here too.
- `hex_to_str` decodes data fields (utf-8; `'0x'` → `''`); `to_datetime` / `to_iso`
  convert unix seconds (hex tolerated) to tz-aware UTC datetime / ISO-8601.

## Method reference

Every `Method` enum value (34) maps to typed convenience methods on `ChainscanClient`:

| Method Enum | Convenience Method(s) | Returns |
|---|---|---|
| `ACCOUNT_BALANCE` | `get_balance(address)` | `str` (Wei) |
| `ACCOUNT_TRANSACTIONS` | `get_transactions(address)` / `get_all_transactions(address)` | `list[dict]` |
| `ACCOUNT_INTERNAL_TXS` | `get_internal_transactions(address)` / `get_all_internal_transactions(address)` | `list[dict]` |
| `ACCOUNT_ERC20_TRANSFERS` | `get_token_transfers(address)` / `get_all_token_transfers(address)` | `list[dict]` |
| `ACCOUNT_ERC721_TRANSFERS` | `get_erc721_transfers(address)` | `list[dict]` |
| `ACCOUNT_ERC1155_TRANSFERS` | `get_erc1155_transfers(address)` | `list[dict]` |
| `ACCOUNT_TOKEN_PORTFOLIO` | `get_token_portfolio(address)` | `list[dict]` |
| `ACCOUNT_NFT_PORTFOLIO` | `get_nft_portfolio(address)` | `list[dict]` |
| `TX_BY_HASH` | `get_transaction(tx_hash)` | `dict` |
| `TX_RECEIPT_STATUS` | `get_transaction_status(tx_hash)` | `dict` |
| `TX_STATUS_CHECK` | `check_transaction_status(tx_hash)` | `dict` |
| `BLOCK_BY_NUMBER` | `get_block(block_number)` | `dict` |
| `BLOCK_REWARD` | `get_block_reward(block_number)` | `dict` |
| `BLOCK_COUNTDOWN` | `get_block_countdown(target_block)` | `dict` |
| `BLOCK_NUMBER_BY_TIMESTAMP` | `get_block_by_timestamp(timestamp, closest)` | `dict` |
| `CONTRACT_ABI` | `get_contract_abi(address)` | `str` (JSON) |
| `CONTRACT_SOURCE` | `get_contract_source(address)` | `dict` |
| `CONTRACT_CREATION` | `get_contract_creation(addresses)` | `list[dict]` |
| `CONTRACT_VERIFY` | `client.call(Method.CONTRACT_VERIFY, ...)` | *(multi-step workflow)* |
| `CONTRACT_VERIFY_STATUS` | `client.call(Method.CONTRACT_VERIFY_STATUS, ...)` | *(multi-step workflow)* |
| `TOKEN_BALANCE` | `get_token_balance(address, contract_address)` | `str` |
| `TOKEN_SUPPLY` | `get_token_supply(contract_address)` | `str` |
| `TOKEN_INFO` | `get_token_info(contract_address)` | `dict` |
| `TOKEN_HOLDERS` | `get_token_holders(contract_address, page, offset)` / `get_all_token_holders(contract_address)` | `list[dict]` (`{'address', 'value'}`) |
| `TOKEN_TOP_HOLDERS` | `get_top_token_holders(contract_address, limit)` | `list[dict]` (Etherscan PRO + NodeReal `topN`; `limit` ≤ 1000 on Etherscan, clamped to 100 on NodeReal) |
| `TOKEN_HOLDER_COUNT` | `get_token_holder_count(contract_address)` | `int` |
| `GAS_ESTIMATE` | `get_gas_estimate(gas_price)` | `str` |
| `GAS_ORACLE` | `get_gas_oracle()` | `dict` |
| `EVENT_LOGS` | `get_logs(address, ...)` / `get_all_logs(address, ...)` | `list[dict]` |
| `ETH_SUPPLY` | `get_eth_supply()` | `str` |
| `ETH_PRICE` | `get_eth_price()` | `dict` |
| `PROXY_ETH_CALL` | `eth_call(to, data, tag)` | `str` |
| `PROXY_GET_BALANCE` | `eth_get_balance(address, tag)` | `str` |
| `PROXY_GET_STORAGE_AT` | `eth_get_storage_at(address, position, tag)` | `str` (32-byte word) |

### Single page vs everything

| Pattern | Use When | Memory |
|---|---|---|
| `get_transactions(address)` | Quick look, small wallets | Low |
| `get_all_transactions(address)` | Need ALL data (built via streaming aggregation) | Grows with data |
| `iter_transactions_streaming(address)` | Large wallets (1M+ txs) | Constant ~10MB |
| `get_transactions_df(address)` | Data analysis (Polars) | Grows with data |
