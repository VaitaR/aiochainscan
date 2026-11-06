# Guaranteed-complete pagination

Agent reference for `guarantee_complete` and the measured provider caps behind it. Read it
before touching `services/pagination.py`, a scanner's `fetch_page`, `result_window`,
`max_page_size` or `RESULT_WINDOW_OVERRIDES`, or the completeness exceptions. User-facing
version: [../PAGINATION_AND_FAILOVER.md](../PAGINATION_AND_FAILOVER.md).

`get_all_*` / `iter_*_streaming` / `iter_transactions` / `iter_logs` accept
`guarantee_complete` (default `True`): *every matching record was returned, or an
exception was raised*. `guarantee_complete=False` restores the pre-1.0 behaviour (fewer
requests on wide ranges, silent truncation possible). `ChainscanPool` forwards the flag
to its member clients.

## Overflow detection is scanner-declared, never guessed

- `Scanner.result_window` is the provider's `page * offset` cap (`etherscan` v2 and
  `blockscout` v1 via `EtherscanLikeScanner`: `API_MAX_OFFSET_ETHERSCAN` = 10_000).
  `None` means the provider paginates by an opaque server cursor that runs to exhaustion
  (`blockscout_v2` `next_page_params`, `nodereal` `pageKey`) — nothing to overflow, the
  flag is inert, and those scanners ignore `page`/`offset`/`sort` page controls (e.g.
  `iter_token_holders_streaming`). A third-party scanner that has a cap but leaves
  `result_window = None` cannot be protected.
- `Scanner.RESULT_WINDOW_OVERRIDES` declares a **per-method** window where one endpoint is
  bounded tighter than the rest; `result_window_for(method)` is what the pagination
  binding reads.
- `Scanner.max_page_size` declares what a provider actually serves per page, and
  `fetch_page` clamps `offset` to it, so the page-full test compares against a number the
  provider agreed to.
- **The signal** is `collected >= result_window`, not an error string and not "the last
  page was full". A capped explorer answers a partial page that is indistinguishable from
  the end of the data, and the cap need not land on a page boundary.

## Measured caps

- **BlockScout V1** (live-verified 2026-09-02, `eth.blockscout.com`). Account endpoints:
  `page * offset <= 10_000` exactly — `page=11&offset=1000` and `page=2&offset=10000` both
  answer `status=0` "Result window is too large, PageNo x Offset size must be less than or
  equal to 10000", while an over-cap `offset=10001` is silently clamped to 10_000 items.
  `logs/getLogs` **ignores page/offset entirely**, answering at most 1000 logs with
  `status=1` "OK" — so its window is `API_MAX_OFFSET_LOGS` = 1000 (in
  `RESULT_WINDOW_OVERRIDES`), and `EtherscanLikeScanner.fetch_page` issues no cursor for a
  spec that maps neither `page` nor `offset`, because "the next page" there is the first
  page again.
- **Etherscan v2** (live-verified 2026-09-02, key-authenticated). `page * offset <= 10_000`
  is enforced with an error, but the per-page size is a separate, *silent* limit:
  `offset=5000` or `offset=10000` answers **1000** items with `status=1` "OK". Before
  `max_page_size` (Etherscan 1000, BlockScout V1 10_000, both measured) `batch_size=5000`
  returned 1000 of 2009 transactions under `guarantee_complete=True`. Cross-check:
  Etherscan and BlockScout V1 return byte-identical counts for the same range (1085 logs,
  2009 txs). Etherscan's docs are silent on both caps, and the 1000-per-page figure is a
  dated change (cut from 10_000 in July 2026).
- **Routescan v2** (live-verified 2026-09-30, Avalanche WAVAX): shares the 10_000
  `page * offset` window; serves up to 5000 per page (`txlist` with `offset=10000` answers
  HTTP 502). Details in `scanners/routescan_v2.py`.
- **NodeReal `EVENT_LOGS`**: 50 000 logs per request, refused rather than truncated — see
  [providers.md](providers.md#nodereal-v1).
- **Etherscan `getLogs` scan timeout**: a wide span is refused after a ~30s server-side
  scan ("select a smaller result dataset") — the refusal the engine splits on. A client
  `timeout` below ~35s aborts first, the same window is retried, and the call fails with
  `ChainscanNetworkError`; pass `timeout` above ~35s for `get_all_logs` on Etherscan.

Treat `max_page_size` as a measured constant with a shelf life: re-measure with
`make probe-caps` (`scripts/agent/probe_provider_caps.py` — asks each provider for pages
straddling its declared caps and exits non-zero on drift or on any unconfirmed
declaration, in both text and `--json` modes). Last run 2026-09-02: Etherscan v2 and
BlockScout V1 reproduced their declarations for `ACCOUNT_TRANSACTIONS` and `EVENT_LOGS`
(Etherscan serves 1000 per page and refuses `page*offset` at 11_000; BlockScout V1 serves
10_000 per page, refuses at 20_000, and answers `getLogs` page 2 with page 1's first
record). Cursor-paginated scanners declare no cap, so the probe reports "nothing to
verify" for them; a declared cap the probe cannot exercise counts as unverified, never as
a pass.

## Three cap signals

The error says which one fired:

1. The provider offered a continuation at the cap → records are definitely being cut off
   (`confirmed=True`).
2. The window came back exactly full with *no* continuation → possibly complete, possibly
   capped, and the API offers no way to tell (`confirmed=False`, message says "POSSIBLY
   truncated"). No probe can settle it: cursors are opaque and none was returned.
   The continuation has to be the *provider's* opaque server cursor. A `{page, offset}`
   cursor is this library's own arithmetic and is emitted whether or not more data exists;
   counting it reported data ending exactly on the cap as confirmed loss.
3. An outright provider refusal: NodeReal's result-size `-32005` raises
   `ChainscanResultWindowExceededError` (FATAL, carries the stated limit), which the
   guaranteed engine converts to the overflow outcome and splits — `confirmed=True`.

## Adaptive split, costs, failure types

- On overflow the block range is cut at the block of the last record the provider managed
  to serve (arithmetic bisect only when items carry no block number); each half is
  strictly narrower, so the recursion terminates.
- Costs: up to one extra pass over each overflowing window (the truncated attempt is
  discarded rather than yielded, so nothing duplicates), a buffer bounded by
  `result_window` items, and one unnecessary split for a range holding *exactly* the cap.
- `PaginationDataLossError` (`start_block` / `end_block` / `api_limit` / `items_fetched` /
  `confirmed`): a real block range was narrowed until a *single block* still exceeded the
  cap.
- `CompletenessUnavailableError` (`method` / `provider` / `alternatives` / `api_limit` /
  `items_fetched` / `confirmed`): the endpoint has **no splittable dimension** on this
  provider. Its message names the providers that *can* serve the method completely,
  computed by `scanners.scanners_serving_completely(method)` (a scanner qualifies by
  declaring the method with `result_window_for(method) is None`). The question is asked
  **per method, not per scanner**: BlockScout V1 caps its account endpoints at 10_000 and
  still serves the holder list to exhaustion.
- **Visible break: `get_all_token_holders` / `iter_token_holders_streaming` on Etherscan.**
  A holder list has no block range, so for a token with >=10_000 holders the call raises
  `CompletenessUnavailableError` instead of silently returning the first 10_000. The
  remedy is a provider switch (`blockscout/v1`, `blockscout/v2`, `nodereal/v1` serve the
  list to exhaustion) or `guarantee_complete=False`; the message states both.
