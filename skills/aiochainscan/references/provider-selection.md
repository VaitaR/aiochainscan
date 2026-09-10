# Provider selection

Four scanners, one interface. Pick by the method you need and by whether you
have a key. Generated from the scanner declarations in
`aiochainscan/scanners/` (aiochainscan 1.0.x) — those declarations are
authoritative if this table ever drifts.

## At a glance

| Scanner id | Version | API key | Methods | Pagination | Networks |
|---|---|---|---|---|---|
| `etherscan` | v2 | `ETHERSCAN_KEY` (required) | 33 / 33 | `page`/`offset`, capped | all 36 registry chains via the v2 multichain proxy |
| `blockscout` | v1 | none | 31 / 33 | `page`/`offset`, capped | 8 public instances (ethereum, sepolia, base, arbitrum, optimism, polygon, gnosis, scroll) |
| `blockscout_v2` | v2 | none | 11 / 33 | opaque server cursor, uncapped | same 8 instances |
| `nodereal` | v1 | `NODEREAL_KEY` | 25 / 33 | opaque `pageKey`, uncapped | BSC mainnet + testnet only |

`from_config` takes the scanner id and a network name, a numeric chain id, or
a base URL (`https://…`) for a self-hosted instance:

```python
ChainscanClient.from_config('blockscout_v2', 'ethereum')
ChainscanClient.from_config('etherscan', 8453)
ChainscanClient.from_config('blockscout_v2', 'https://blockscout.internal', expected_chain_id=100)
```

## Method coverage

| Method | `ChainscanClient` call | etherscan | blockscout | blockscout_v2 | nodereal |
|---|---|:-:|:-:|:-:|:-:|
| `ACCOUNT_BALANCE` | `get_balance` | ✅ | ✅ | ✅ | ✅ |
| `ACCOUNT_TRANSACTIONS` | `get_transactions` / `get_all_transactions` | ✅ | ✅ | ✅ | ✅ |
| `ACCOUNT_INTERNAL_TXS` | `get_internal_transactions` | ✅ | ✅ | ✅ | ✅ |
| `ACCOUNT_ERC20_TRANSFERS` | `get_token_transfers` | ✅ | ✅ | ✅ | ✅ |
| `ACCOUNT_ERC721_TRANSFERS` | `get_erc721_transfers` | ✅ | ✅ | — | ✅ |
| `ACCOUNT_ERC1155_TRANSFERS` | `get_erc1155_transfers` | ✅ | ✅ | — | ✅ |
| `ACCOUNT_TOKEN_PORTFOLIO` | `get_token_portfolio` | ✅ | ✅ | ✅ | ✅ |
| `ACCOUNT_NFT_PORTFOLIO` | `get_nft_portfolio` | ✅ | ✅ | ✅ | ✅ |
| `TX_BY_HASH` | `get_transaction` | ✅ | ✅ | — | ✅ |
| `TX_RECEIPT_STATUS` | `get_transaction_status` | ✅ | ✅ | — | ✅ |
| `TX_STATUS_CHECK` | `check_transaction_status` | ✅ | ✅ | — | ✅ |
| `BLOCK_BY_NUMBER` | `get_block` | ✅ | ✅ | ✅ | ✅ |
| `BLOCK_REWARD` | `get_block_reward` | ✅ | ✅ | — | — |
| `BLOCK_COUNTDOWN` | `get_block_countdown` | ✅ | ✅ | — | — |
| `BLOCK_NUMBER_BY_TIMESTAMP` | `get_block_by_timestamp` | ✅ | ✅ | — | ✅ |
| `CONTRACT_ABI` | `get_contract_abi` | ✅ | ✅ | ✅ | ✅ |
| `CONTRACT_SOURCE` | `get_contract_source` | ✅ | ✅ | ✅ | ✅ |
| `CONTRACT_CREATION` | `get_contract_creation` (≤5 addresses) | ✅ | ✅ | — | ✅ |
| `CONTRACT_VERIFY` | `call(Method.CONTRACT_VERIFY, …)` | ✅ | ✅ | — | — |
| `CONTRACT_VERIFY_STATUS` | `call(…)` / `wait_for_verification` | ✅ | ✅ | — | — |
| `TOKEN_BALANCE` | `get_token_balance` | ✅ | ✅ | — | ✅ |
| `TOKEN_SUPPLY` | `get_token_supply` | ✅ | ✅ | — | ✅ |
| `TOKEN_INFO` | `get_token_info` | ✅ | ✅ | — | ✅ |
| `TOKEN_HOLDERS` | `get_token_holders` / `get_all_token_holders` | ✅¹ | ✅ | ✅ | ✅ |
| `TOKEN_TOP_HOLDERS` | `get_top_token_holders` | ✅ | — | — | ✅² |
| `TOKEN_HOLDER_COUNT` | `get_token_holder_count` | ✅ | — | ✅ | ✅ |
| `GAS_ESTIMATE` | `get_gas_estimate` | ✅ | ✅ | — | — |
| `GAS_ORACLE` | `get_gas_oracle` | ✅ | ✅ | — | — |
| `EVENT_LOGS` | `get_logs` / `get_all_logs` | ✅ | ✅ | — | ✅³ |
| `ETH_SUPPLY` | `get_eth_supply` | ✅ | ✅ | — | — |
| `ETH_PRICE` | `get_eth_price` | ✅ | ✅ | — | — |
| `PROXY_ETH_CALL` | `eth_call` | ✅ | ✅⁴ | — | ✅ |
| `PROXY_GET_BALANCE` | `eth_get_balance` | ✅ | ✅⁴ | — | ✅ |

¹ PRO endpoint, and capped at 10 000 holders — see below.
² `limit` is clamped to 100 by the provider's page size.
³ Capped at 50 000 logs per request; NodeReal errors instead of truncating.
⁴ Served through the instance's JSON-RPC endpoint, not the Etherscan-compat REST.

Anything marked `—` raises `MethodNotDeclaredError` (a `ValueError`) at call
time. Nothing returns empty data to signal "unsupported".

## Pagination caps that change behaviour

| Scanner | `page * offset` cap | Max items per page | Notes |
|---|---|---|---|
| `etherscan` v2 | 10 000 | 1000 (silent) | asking for `offset=5000` returns 1000 items with `status=1` |
| `blockscout` v1 | 10 000 (accounts) | 10 000 | `getLogs` ignores paging entirely and caps at 1000 |
| `blockscout_v2` | none | cursor | runs to exhaustion |
| `nodereal` v1 | none | cursor | `EVENT_LOGS` refuses above 50 000 logs; transaction queries walk in 1000-block windows |

With `guarantee_complete=True` (the default) these caps are handled for you:
the range is split adaptively and the call either returns everything or
raises. The caps matter when you choose a provider for a wide query.

## Rules of thumb

- **No key available** → `blockscout` v1 for the widest surface;
  `blockscout_v2` when you need complete token-holder lists or cursor
  pagination.
- **Need everything, have a key** → `etherscan` v2 (all 33 methods, all
  chains) — but not for holder lists above 10 000, which it cannot serve
  completely.
- **BSC without any key budget** → `nodereal` (needs its own free key) is the
  only alternative source for contract ABI/source and internal transactions.
- **Production reliability** → `ChainscanPool.from_config([...])`, priority
  order first. It fails over on rate limits, 5xx, missing keys, plan
  restrictions and undeclared methods; it does not retry your own bad
  arguments.

## Keys and configuration

Read from `os.environ` first, then `./.env.local`, then `./.env`, then
`~/.aiochainscan/.env`. Nothing needs to be passed in code:

```bash
ETHERSCAN_KEY=...
NODEREAL_KEY=...
```

`ChainscanClient.from_config(..., api_key='...')` exists for tests and
multi-tenant callers; do not hardcode keys in application code.
