# Providers: measured behaviour

Agent reference for per-provider facts. Read it before changing a scanner, its `SPECS`,
its network table, the chain registry, or the holder surface. Live counts (methods,
chains, caps, configured keys) come from `aiochainscan scanners`; the scanner
declarations in `aiochainscan/scanners/` win over this file when they differ. Every
dated measurement here has a shelf life — re-probe before trusting it.

## Scanner overview

| Scanner | Version | Key | Notes |
|---|---|---|---|
| `blockscout` | v1 | none | Etherscan-compatible `/api` minus portfolios, gas, `TOKEN_INFO`, holder count and top holders; plus `TOKEN_HOLDERS` (`token/getTokenHolders`, not Etherscan's `tokenholderlist`); `TX_BY_HASH`/`PROXY_*` via `/api/eth-rpc` |
| `blockscout` | v2 | none | Cursor-paginated (no result window). 11 methods: `ACCOUNT_BALANCE`, `ACCOUNT_TRANSACTIONS`, `ACCOUNT_INTERNAL_TXS`, `ACCOUNT_ERC20_TRANSFERS`, `ACCOUNT_TOKEN_PORTFOLIO`, `ACCOUNT_NFT_PORTFOLIO`, `CONTRACT_ABI`, `CONTRACT_SOURCE`, `BLOCK_BY_NUMBER`, `TOKEN_HOLDERS` (`/api/v2/tokens/{addr}/holders`), `TOKEN_HOLDER_COUNT` (token info `holders_count`) |
| `etherscan` | v2 | `ETHERSCAN_KEY` | All 34 `Method` values; `tokenholderlist`/`topholders`/`tokenholdercount` are PRO endpoints |
| `nodereal` | v1 | `NODEREAL_KEY` (free tier) | BSC-only subset (26), incl. the only keyless-free BSC route to `CONTRACT_ABI`/`CONTRACT_SOURCE`/`ACCOUNT_INTERNAL_TXS` |
| `routescan` | v2 | none (optional `ROUTESCAN_KEY`) | Etherscan-compatible; Ethereum, Avalanche C-Chain, Plasma, Corn; facts in `scanners/routescan_v2.py` |

## Token holders

- The unified item shape is `{'address': EIP-55 str, 'value': str}` (raw-unit quantity —
  never Int64) — the ONE Method with a normalized cross-scanner item shape. Everything
  else stays provider-native, so a caller switching providers for any other Method must
  expect the provider's own field names and nesting.
- Three providers serve the list to exhaustion (`result_window_for(TOKEN_HOLDERS) is
  None`): BlockScout V1, BlockScout V2 and NodeReal. Etherscan bounds it at 10_000.
- `TOKEN_HOLDER_COUNT` does NOT exist on BlockScout V1 (`getTokenHolderCount`,
  `tokenholdercount` and `getTokenHoldersCount` all answer `status=0` "Unknown action").
- `TOKEN_TOP_HOLDERS` is declared by Etherscan and NodeReal (`nr_getTokenHolders` with
  `topN`), not by either BlockScout leg: V2's holders endpoint documents no ordering, and
  V1's is *empirically* balance-ordered but documents no guarantee, so declaring it would
  sell an observation as a contract.
- Live verification (2026-09-02): BlockScout V1 and V2 end to end (V1: 33/33 unique
  holders for a token whose count V2 reports as 33; no result window at 11k/50k depth
  where the *account* endpoints reject `page=11&offset=1000`). NodeReal on `bsc-mainnet`
  (BSC-USD, CAKE): the list returns `{pageKey, details: [{accountAddress,
  tokenBalance}]}`, `pageKey` round-trips (3×100 holders, 300 distinct addresses, a fresh
  opaque cursor per page), and `topN` orders descending by balance. The plain list is NOT
  balance-ordered, which is why `TOKEN_TOP_HOLDERS` stays a separate declaration.
- **`nr_getTokenHolderCount` docs and live API disagree.** The docs show
  `{"result": "0x123"}`; the live API answers `{"result": {"result": "0x46b3f99"}}`. Read
  as documented, that yielded 0 holders for a token with 74 million.
  `_parse_token_holder_count` accepts both shapes and raises `ChainscanDataError` on any
  third one instead of counting zero. End-of-pagination is documented only by its
  complement ("If more results are available, a pageKey will be returned"), so treating an
  empty *or absent* `pageKey` as exhaustion is an inference — the code accepts both.
- NodeReal documents both holder methods as "BSC and ETH mainnet only" while
  `supported_networks` is BSC-only — deliberately not widened, since nothing establishes
  ETH support for the scanner's other methods.

## Credentials

Keys live in `~/.aiochainscan/.env` (machine-level, read by `ConfigurationManager` for
every cwd, so worktrees need no plumbing). A repo-local `./.env` overrides it, `./.env.local`
(loaded before `./.env`) overrides `./.env`, and `os.environ` outranks every file. A `.env`
that is not valid UTF-8 is warned about and its undecodable lines skipped, never fatal.
`ConfigurationManager` is a process-wide singleton; constructing it with a different
`config_dir` warns and keeps the original — rebind via `reset_instance()` / `reload()`.

## NodeReal v1

JSON-RPC 2.0 to `https://bsc-{mainnet,testnet}.nodereal.io/v1/{key}` (the `nr_*` Enhanced
API behind https://bsctrace.com) plus the BscScan-compatible verified-contract REST on
`open-platform.nodereal.io`. Networks: `bsc` / `bnb` / `binance` (mainnet) and
`bsc-testnet`.

- Honest `ValueError` for contract verify, gas oracle/estimate, price/supply stats, block
  reward/countdown.
- The public→wire mapping is DECLARED in `SPECS` and executed: `param_style`
  (`'rpc-positional'` / `'rpc-object'` / `'query'` for the contract REST) picks the wire
  shape, `param_map` carries every accepted public name (Etherscan-style input aliases
  included — first declared wins) and, for positional methods, the wire order.
  `_build_rpc_params` / `_build_transfer_filter` / `_resolve_window` /
  `_filter_transfer_items` read their param sources from that map, so
  `supports_block_range` and the consistency sweep read the same declarations that run.
  Specs declare no `path` — `_rpc_url()` / `_rest_contract()` own the URLs.
- Token holders page by an opaque `PageKey` (empty on the first request) with a
  hex-encoded `PageSize` capped at 100. `get_top_token_holders()` is a single call, so a
  `limit` above 100 is clamped to 100 — and the clamped size rides the wire twice, as
  `PageSize` and as `topN`, so a `limit` below 100 must reach both or the call answers a
  full 100-holder page.
- `nr_getTransactionByAddress` serves ≤1000 blocks per request and **silently returns
  empty pages for wider ranges** — `fetch_page` walks the requested range in 1000-block
  windows; an unbounded end block resolves the chain tip once. The walk is deliberately
  NodeReal-local (no engine equivalent), but its block-range inputs are the spec's
  declared `fromBlock`/`toBlock` sources.
- Holdings methods (`nr_getTokenHoldings`, `nr_getNFTHoldings`) page at 100 items with hex
  `totalCount` cursors.
- JSON-RPC `-32005` is **overloaded**. A usage limit is translated to
  `ChainscanRateLimitError` so the transport retry policy applies; the same code carrying
  a result-size refusal ("logs count exceeds the limit 50000") is deterministic — retrying
  burns the budget and cools a healthy provider — so it raises
  `ChainscanResultWindowExceededError` (FATAL `ChainscanClientError` carrying the limit).
  The translation lives in the scanner's `ResponseDialect` (`_NodeRealEnvelope`), i.e.
  inside `Network._send`, which puts the usage-limit meaning under the retry policy.
- `EVENT_LOGS` is capped at **50 000 logs per request**, refused rather than truncated
  (2026-09-05, bsc-mainnet: a 200-block span of BSC-USD `Transfer` served 26 841 logs;
  2000 and 20 000 blocks both answered `-32005`). Declared in `RESULT_WINDOW_OVERRIDES`;
  the guaranteed engine splits on the refusal (a single over-cap block still ends in
  `PaginationDataLossError(confirmed=True)`), and `scanners_serving_completely(EVENT_LOGS)`
  does not name NodeReal.

## Chain topology and registry sync

`STANDARD_CHAINS` is static and is the shipped truth: a fresh install resolves every chain
offline. Etherscan declares the 61 chains its keyless `GET /v2/chainlist` returned on
2026-09-11; `EtherscanV2.supported_networks` is bound to `ETHERSCAN_SCANNER_NETWORKS` (the
registry record's alias table), so the scanner cannot advertise a name
`resolve_chain_id` would not answer. `goerli` and `holesky` are absent from the chainlist
and refused at construction (the live endpoint answers them `[NOTOK] Missing or
unsupported chainid parameter`); their `URL_BUILDER_CHAIN_IDS` rows stay, so the ids
remain resolvable.

`aiochainscan.registry_sync.sync_etherscan_chains()` is the opt-in refresh: it re-reads the
live chainlist and registers anything the static tables lack. Additive and idempotent — a
known chain keeps its declared spelling and a taken name is never repointed. Chains the
list marks offline are skipped. `chainlist_alias` is the one naming rule both paths use.

**Only Etherscan syncs.** Its chains share one endpoint, so "listed" and "reachable" are
one fact. A BlockScout instance is a separate host per chain, and the instance directory
lists hosts that 404, only redirect, or serve a partial surface, so BlockScout instances
stay live-probed and static.

## BlockScout networks and instance probing

Both legs derive `supported_networks` from `BLOCKSCOUT_SCANNER_NETWORKS` (the shared
instance-host table minus `DROPPED_INSTANCE_ALIASES`), so a new instance registers for v1
and v2 at once and neither leg can advertise a network it cannot resolve. Both record the
resolved instance as `base_url` on the registry path, which `get_chain_info()` /
`validate_chain()` probe. The v2 leg derives its UrlBuilder kind (hence `client.currency`)
through the same `BLOCKSCOUT_CONFIG_IDS` mapping v1 uses, so **v2 currency always equals
v1 currency**; its requests are still built from the scanner's own `BASE_URLS`.

The host table is measured: `scripts/agent/probe_blockscout_hosts.py` (`make probe-hosts`)
is how a row earns its place or is re-verified — the `chains.blockscout.com` directory is
not evidence. It lists 747 chains, but only 92 explorers (49 mainnet) are hosted by
BlockScout itself; the sweep covers the self-hosted mainnet set only.

**`/api/eth-rpc` is rate-limited per client IP across every instance at once.** A sweep
can leave it answering 429 even for declared hosts whose REST answers 200 (2026-09-11,
`eth.blockscout.com` and `gnosisscan.io`, for over 45 minutes). A throttled probe is
INCONCLUSIVE — re-run later; never record a 429 as a dead host, and never declare a host
whose eth-rpc went unverified (it backs `TX_BY_HASH` and both `PROXY_*` methods).

Last full sweep 2026-09-11: v1 `/api`, v2 `/api/v2` and `/api/eth-rpc` confirmed on every
declared host. Ten candidates (Ethereum Classic, Celo, Unichain, Filecoin, Arbitrum Nova,
Neon, Creditcoin, Eden, BlackFort, DATA/Cross) answered REST but never got past the
eth-rpc IP limit — they stay undeclared. Gnosis, Optimism and Scroll serve BlockScout from
chain-branded hosts (`gnosisscan.io`, `explorer.optimism.io`, `scrollscan.com`) and only
301 the `*.blockscout.com` alias; the transport does not follow redirects, so the branded
host is the only working spelling. BSC and Linea have no BlockScout instance (both hosts
404), so `from_config('blockscout*', 'bsc'|'linea')` raises. Keyless BSC is NodeReal's job.

BlockScout's per-instance REST carries a deprecation notice for the Etherscan-compat `/api`
layer, yet every V1 endpoint used here answered correctly and keylessly (2026-09-02). Treat
V1 as working-but-on-notice: a V1 breakage should be answered by a V2 path.

### V1 proxy fallback (`/api/eth-rpc`)

BlockScout's REST answers `"Unknown module"` for `module=proxy`, so `blockscout` v1 routes
`TX_BY_HASH`, `PROXY_ETH_CALL`, `PROXY_GET_BALANCE` (and `PROXY_GET_STORAGE_AT`) through
`POST {base_url}/api/eth-rpc` — the keyless transport the chain-info probe uses. The
Network layer unwraps the JSON-RPC envelope and raises `ChainscanClientProxyError` for
reverts; a `null` result (unknown tx) comes back as `None`.

### V2 `TX_BY_HASH` — blocked by the transport

`GET /api/v2/transactions/{hash}` returns the full transaction dict, but its payload has a
top-level `result` field (the execution-status string `"success"`/`"error"`), and
`Network._handle_response` unwraps any top-level `result` (then `data`) as an Etherscan
envelope — a declared `TX_BY_HASH` would return the string `"success"`. `TOKEN_HOLDERS`
and the account endpoints (`{items, next_page_params}`) are unaffected; any future V2
endpoint with a top-level `result`/`data` key hits the same collision. Declaring it needs
the unwrapping scoped to the Etherscan dialect (or a spec opt-out) — a transport-contract
change. `EVENT_LOGS` is undeclared for another reason: `/addresses/{hash}/logs` has no
topic or block filter on the wire, so `topic0=` or a bounded range would be dropped.

## Etherscan free-key reach

Plan availability is per ENDPOINT, not per chain. Etherscan documents that "source code
and ABI endpoints are available on all chains for every API plan, including the Free
Tier", and that is measured: a free key refused `get_balance` on `base`/`bsc`/`optimism`
(`[NOTOK] Free API access is not supported for this chain`) while `get_contract_abi`
succeeded on all three; `ethereum`, `arbitrum`, `polygon`, `sepolia` and `sonic` served
normally (2026-09-11). So a free key reaches every chain for ABI/source and a subset for
the rest. NodeReal's free tier is the free route to BSC *balances and history*, not to BSC
ABIs.

## Doc-declared input limits

`getcontractcreation` takes at most `API_MAX_CONTRACT_CREATION_ADDRESSES` = 5 addresses,
`topholders` at most `API_MAX_TOP_HOLDERS` = 1000. Both raise `InputLimitExceededError`
from `EtherscanLikeScanner._perform_raw_request`, keyed on the `Method` enum (never a wire
action string) — the seam every Etherscan-dialect leg passes through, including BlockScout
V1, whose `_perform_request` delegates upward for non-JSON-RPC methods. Why it must be a
`ChainscanClientError`: see the error-ladder rule in [AGENTS.md](../../AGENTS.md).
