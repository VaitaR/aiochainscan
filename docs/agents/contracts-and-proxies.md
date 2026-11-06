# Contracts, proxies and decoding helpers

Agent reference for proxy resolution and ABI lookup. Read it before touching
`get_contract_abi(follow_proxy=...)`, `resolve_proxy_metadata`, `SmartContract`,
`decode_input` / `decode_transactions` / `decode_logs`, or the MCP ABI tools.

- `get_contract_abi()` returns the ABI the explorer stores **for that address**. For a
  proxy that is the PROXY's ABI, which decodes none of its traffic — every call reaching a
  proxy targets a selector the implementation declares. Pass `follow_proxy=True`, or use
  `get_contract()` / `SmartContract.from_address()`, which resolve unconditionally.
- **`proxy_strategy` picks where an implementation is looked for.** `'metadata'`
  (default) asks the explorer only — no extra request, blind to a proxy the explorer never
  flagged. `'auto'` falls through to the chain whenever metadata answers "not a proxy" or
  names at most one implementation, at up to five extra requests; `'chain'` skips the
  explorer. The default is not `'auto'` because the extra requests land on the common case
  (a plain contract) and on a keyless provider that rate-limits hard — a cost decision,
  pending a measured cheaper `eth_getCode` pre-filter.
- **No single storage slot is enough** (measured 2026-09-15): USDC holds ZERO at the
  EIP-1967 slot and keeps its implementation in the legacy `org.zeppelinos` slot, while
  stkAAVE and etherfi answer at EIP-1967. `_IMPLEMENTATION_SLOTS` is a ladder — EIP-1967 →
  EIP-1822 → zeppelinos → EIP-1967 beacon (one more `eth_call` for the beacon's
  `implementation()`) — first-non-zero-wins. A word whose upper 12 bytes are set holds
  something other than an address and is rejected rather than truncated into one.
  `Method.PROXY_GET_STORAGE_AT` makes this readable; a scanner that does not declare it
  leaves resolution on metadata instead of failing.
- **Explorer and chain disagree after an upgrade, and the chain wins**: explorers cache
  the implementation; the slot is the truth at `latest`. `ProxyMetadata.source` says which
  sources answered (`'metadata'` / `'chain'` / `'both'`).
- **Diamonds (EIP-2535) need no new `Method`.** `facets()` (`0x7a0ed627`) goes through
  `PROXY_ETH_CALL` and decodes with `abi_pure.decode_arguments`; a contract without the
  loupe reverts, which IS the detection. `SmartContract` merges every facet's ABI — sound
  because EIP-2535 gives each selector exactly one facet (events and errors dedupe by
  signature; constructors/fallbacks are dropped). `facets` records where the ABI came from
  and `missing_facets` names any facet with no verified ABI — a partial ABI must say it is
  partial. Live 2026-09-15, zkSync Era `0x3240…0324` on Etherscan: own ABI 0 functions,
  `follow_proxy=True` 15 (Etherscan names ONE implementation), `proxy_strategy='auto'`
  **90** across all four facets.
- **Two explorer dialects, one fact.** Etherscan v2 answers `Proxy`='1'/'0' +
  `Implementation`; BlockScout answers `IsProxy`='true' + `ImplementationAddress`, plus
  `ImplementationAddresses` listing EVERY implementation (a diamond's facets —
  live-verified 2026-09-15: the zkSync Era DiamondProxy lists the same four facets its
  `facets()` loupe returns). `resolve_proxy_metadata` reads both vocabularies; reading only
  Etherscan's reported every BlockScout proxy as a plain contract.
  `ProxyMetadata.implementation` is the first entry — one facet's ABI does NOT cover a
  diamond's selector table, which is what `is_diamond` and the facet merge are for.
- **Decoding needs no ABI plumbing**: `decode_transactions()` / `decode_logs()` /
  `decode_input()` resolve the deciding ABI themselves (proxy implementation, or a
  diamond's facets merged) and cache it per address. Pass `abi=` to skip the lookup. A
  record whose ABI cannot be fetched is kept with an empty `decoded_func`, never dropped,
  and the caller's list is never mutated.
