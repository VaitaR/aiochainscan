---
artifact_id: "2026-09-01-competitive-backlog-zcode-subagent"
date: "2026-09-01"
producer: "zcode-subagent"
run_kind: "external-review"
verdict: "UNKNOWN"
branch: "feat/competitive-backlog"
base_ref: "origin/main"
base_sha: "156eea0"
head_sha: "4b7c499"
base_ref_source: "nearest-of-2"
worktree_dirty: false
redactions: 0
pr: null
session_id: null
agent_transcript_path: null
repo_root_source: "explicit_repo_arg"
files_reviewed:
  - "aiochainscan/convert.py"
  - "aiochainscan/core/mixins/blocks.py"
  - "aiochainscan/core/pool.py"
  - "aiochainscan/mcp/envelope.py"
  - "aiochainscan/mcp/tools.py"
  - "aiochainscan/network.py"
  - "aiochainscan/scanners/blockscout_v1.py"
  - "aiochainscan/scanners/etherscan_v2.py"
  - "blocks.py"
  - "contracts.py"
  - "convert.py"
  - "pool.py"
  - "scanners/base.py"
findings:
  - id: "F1"
    severity: "UNSPECIFIED"
    file: "aiochainscan/scanners/etherscan_v2.py"
    line: 45
    claim: "Etherscan v2 TOKEN_HOLDERS/TOKEN_TOP_HOLDERS always return ` ` in production — double envelope unwrap — , aiochainscan/network.py:576-577"
    disposition: "accepted"
    disposition_note: "Fixed in 7fb82f7: _parse_token_holders documents and handles the post-unwrap seam (bare item list; envelope tolerated defensively). Regression: tests/test_token_holders.py:183,260."
  - id: "F2"
    severity: "UNSPECIFIED"
    file: "scanners/base.py"
    line: 195
    claim: "Evidence: `Network._handle_response` already unwraps `response_json['result']` before `spec.parse_response` receives it , but `_parse_token_holders` expects the full envelope (`response.get('result')` on a dict) and returns ` ` for the raw list it actually receives. Tests mask this: `FakeNetwork.get` in tests/test_token_holders.py returns the full envelope that the real Network would have unwrapped"
    disposition: "accepted"
    disposition_note: "Same defect as F1 (evidence row). Test mocks moved to the real Network seam; tests/test_token_holders.py:260."
  - id: "F3"
    severity: "UNSPECIFIED"
    file: "aiochainscan/core/pool.py"
    line: 551
    end_line: 581
    claim: "ChainscanPool._pinned_stream` livelock (infinite loop) when the selected provider does not declare the method"
    disposition: "accepted"
    disposition_note: "Fixed in 7fb82f7: _pinned_stream iterates _candidates() with for-semantics and excludes a provider that cannot serve the operation (METHOD_UNDECLARED included) for that operation. Regression: tests/test_provider_pool.py:729."
  - id: "F4"
    severity: "UNSPECIFIED"
    file: "pool.py"
    line: 428
    claim: "Evidence: `while True` re-selects candidates via `_candidates ` which does not filter by method support; `FailureKind.METHOD_UNDECLARED` applies no cooldown and no exclusion (pool.py: `_cooldown_for` returns 0.0 for it), so the same provider is re-picked and re-fails forever. Reproduced with pool `[blockscout v1, blockscout v2]` + `iter_token_holders_streaming` — no suspension point, 100% CPU hang; provider B never tried. Pool tests mock `iter_*_streaming` directly, bypassing the real generator"
    disposition: "accepted"
    disposition_note: "Same defect as F3 (evidence row). Unbounded attempts growth gone with the loop."
  - id: "F5"
    severity: "UNSPECIFIED"
    file: "aiochainscan/core/mixins/blocks.py"
    line: 128
    claim: "wait_for_block` \"already pass\" detection reads only `exc.result` — broken on the default scanner"
    disposition: "accepted"
    disposition_note: "Fixed in 7fb82f7: probe matches api_error_text(exc), covering message and result. Regression: tests/test_wait_helpers.py:356."
  - id: "F6"
    severity: "UNSPECIFIED"
    file: "contracts.py"
    line: 151
    claim: "Evidence: probe checks `'already pass' in str(exc.result).lower `; live eth.blockscout.com (blockscout v1, default scanner) answers `{\"message\":\"Error! Block number already pass\",\"result\":null}` — text is in `message`, `str(None)`='none' → exception propagates instead of returning the documented `{'CountdownBlock': ..., 'RemainingBlock': '0'}`. Sibling `wait_for_verification` correctly checks `f'{exc.message} {exc.result}'`. Test hardcodes the text into `result`, masking"
    disposition: "accepted"
    disposition_note: "Same defect as F5 (evidence row); shared api_error_text convention now used by both wait_for_block and wait_for_verification."
  - id: "F7"
    severity: "UNSPECIFIED"
    file: "aiochainscan/convert.py"
    line: 162
    claim: "format_ether` raises `decimal.InvalidOperation` (not ValueError) on rounding carry"
    disposition: "accepted"
    disposition_note: "Fixed in 7fb82f7: decimal context precision accounts for rounding carry. Verified format_ether('9999999500000000000', 18, 6) == '10.000000'. Regression: tests/test_convert.py:168."
  - id: "F8"
    severity: "UNSPECIFIED"
    file: "convert.py"
    line: 233
    claim: "Evidence: `ctx.prec = max(value.adjusted + 1, 1) + precision` ignores carry propagation. Reproduced: `format_ether('9999999500000000000', 18, 6)` → `InvalidOperation` (9.9999995 ETH should round to '10.000000', 8 digits > prec 7). Related contract slip: `to_datetime('0x' + 'f'*16)` → `OverflowError` "
    disposition: "accepted"
    disposition_note: "Same defect as F7 (evidence row); the related to_datetime slip also fixed - to_datetime('0x'+'f'*16) raises ValueError('Unix timestamp out of range'). Regression: tests/test_convert.py:309."
  - id: "F9"
    severity: "UNSPECIFIED"
    file: "aiochainscan/network.py"
    line: 296
    end_line: 312
    claim: "first_request_guard`: one transient probe failure permanently bricks the client"
    disposition: "accepted"
    disposition_note: "Fixed in 7fb82f7: only non-transient failures are cached as fatal; GUARD_TRANSIENT_EXCEPTIONS leave the guard armed to re-probe. Regression: tests/test_network.py:520,540."
  - id: "F10"
    severity: "UNSPECIFIED"
    file: "blocks.py"
    line: 141
    end_line: 145
    claim: "Evidence: guard runs outside the retry policy; any error (`self._guard_error = e`, `_guard_done = True`) is re-raised from every subsequent request forever. A single HTTP 429/5xx/DNS failure during the chainlist/eth-rpc probe (same rate-limited transport) → permanent `ChainscanRateLimitError`/`ChainscanNetworkError`, no retry, no recovery. Amplifier: `wait_for_block` BLOCK_BY_NUMBER path catches broad `ChainscanClientError → (False, exc)` , so a fatal chain-mismatch config error is silently polled for 600s and reported as timeout"
    disposition: "accepted"
    disposition_note: "Same finding as F9 (evidence row); the wait_for_block amplifier is closed too - ChainscanDataError re-raises instead of being polled for the full budget (core/mixins/blocks.py)."
  - id: "F11"
    severity: "UNSPECIFIED"
    file: "aiochainscan/scanners/blockscout_v1.py"
    line: 30
    end_line: 34
    claim: "BlockScout v1 `get_block` (BLOCK_BY_NUMBER) still routed to dead `module=proxy"
    disposition: "accepted"
    disposition_note: "Fixed in 7fb82f7: Method.BLOCK_BY_NUMBER added to _JSON_RPC_ACTIONS, so get_block routes to /api/eth-rpc. Regression: tests/test_blockscout_v1_ethrpc.py:86."
  - id: "F12"
    severity: "UNSPECIFIED"
    file: "aiochainscan/mcp/envelope.py"
    line: 187
    end_line: 191
    claim: "format_units`: floor divmod is wrong for negative amounts"
    disposition: "accepted"
    disposition_note: "Fixed in 7fb82f7: sign is split off before divmod. Verified format_units(-1500, 3) == '-1.5'. Regression: tests/test_mcp_server.py:219-228."
  - id: "F13"
    severity: "UNSPECIFIED"
    file: "aiochainscan/mcp/tools.py"
    line: 437
    claim: "MCP cursors are unsigned and merged over request params — injection of arbitrary query parameters — ,605,719, aiochainscan/mcp/cursors.py:42-69"
    disposition: "accepted"
    disposition_note: "Accepted in part: tool binding and a cursor-key whitelist were added (decode_cursor_for_tool; rejects a cursor from another tool and any non-whitelisted key). Regression: tests/test_mcp_server.py:588. The HMAC half is deliberately declined for stdio hosting - rationale in the aiochainscan/mcp/cursors.py module docstring; revisit if remote MCP hosting ships."
---

# zcode-subagent review — feat/competitive-backlog

> Captured automatically by `tools/hooks/review_capture.py` (agent-skills). The report below is the reviewer's verbatim output; the frontmatter above is parsed from it. Set each finding's `disposition` when you action it.

## Report (verbatim)

## Code review

Scope: 5a0dd6a..4b7c499 (feat/competitive-backlog, 6 commits: polling helpers, token holders, custom base_url + chain validation, MCP revamp, failover pool, conversion helpers)
Reviewer: zcode general-purpose subagent (external reviewer lane), adversarial correctness protocol
Verdict: NO

All 8 findings independently re-verified by the owning agent (code trace + local reproduction + live checks where applicable) before acceptance.

### Findings
- [P0] Etherscan v2 TOKEN_HOLDERS/TOKEN_TOP_HOLDERS always return `[]` in production — double envelope unwrap — aiochainscan/scanners/etherscan_v2.py:45, aiochainscan/network.py:576-577
  - Evidence: `Network._handle_response` already unwraps `response_json['result']` before `spec.parse_response` receives it (scanners/base.py:195), but `_parse_token_holders` expects the full envelope (`response.get('result')` on a dict) and returns `[]` for the raw list it actually receives. Tests mask this: `FakeNetwork.get` in tests/test_token_holders.py returns the full envelope that the real Network would have unwrapped.
  - Impact: entire token-holders feature (P0.3) silently returns empty lists on Etherscan — the only provider declaring these methods; pagination "completes" after one empty page. BlockScout v2 path works (different response shape), which is why live smoke missed it.
  - Validation: `scanner.call(Method.TOKEN_HOLDERS, ...)` against a Network mock returning the unwrapped list (as real Network does); fix mocks to sit at the correct seam.
- [P0] `ChainscanPool._pinned_stream` livelock (infinite loop) when the selected provider does not declare the method — aiochainscan/core/pool.py:551-581
  - Evidence: `while True` re-selects candidates via `_candidates()` (pool.py:428) which does not filter by method support; `FailureKind.METHOD_UNDECLARED` applies no cooldown and no exclusion (pool.py: `_cooldown_for` returns 0.0 for it), so the same provider is re-picked and re-fails forever. Reproduced with pool `[blockscout v1, blockscout v2]` + `iter_token_holders_streaming` — no suspension point, 100% CPU hang; provider B never tried. Pool tests mock `iter_*_streaming` directly, bypassing the real generator.
  - Impact: any pool pagination (`iter_*_streaming`, all `get_all_*`, `get_transactions_df`) hangs forever when the first available provider lacks the method (blockscout v1 lacks TOKEN_HOLDERS/TOKEN_INFO; nodereal lacks 8 of 30). `attempts` also grows unboundedly.
  - Validation: counting mock of `scanner.fetch_page` + watchdog; fix = capability-filter candidates or for-semantics as in `_execute`.
- [P1] `wait_for_block` "already pass" detection reads only `exc.result` — broken on the default scanner — aiochainscan/core/mixins/blocks.py:128
  - Evidence: probe checks `'already pass' in str(exc.result).lower()`; live eth.blockscout.com (blockscout v1, default scanner) answers `{"message":"Error! Block number already pass","result":null}` — text is in `message`, `str(None)`='none' → exception propagates instead of returning the documented `{'CountdownBlock': ..., 'RemainingBlock': '0'}`. Sibling `wait_for_verification` (contracts.py:151) correctly checks `f'{exc.message} {exc.result}'`. Test hardcodes the text into `result`, masking.
  - Impact: `wait_for_block(<already mined block>)` raises `ChainscanClientApiError` on blockscout v1 — the common case for this helper.
  - Validation: unit test with `ChainscanClientApiError('Error! Block number already pass', None)` or live curl.
- [P1] `format_ether` raises `decimal.InvalidOperation` (not ValueError) on rounding carry — aiochainscan/convert.py:162
  - Evidence: `ctx.prec = max(value.adjusted() + 1, 1) + precision` ignores carry propagation. Reproduced: `format_ether('9999999500000000000', 18, 6)` → `InvalidOperation` (9.9999995 ETH should round to '10.000000', 8 digits > prec 7). Related contract slip: `to_datetime('0x' + 'f'*16)` → `OverflowError` (convert.py:233).
  - Impact: deterministic crash on valid wei values at a digit boundary (any precision); documented strict-ValueError contract violated, callers' `except ValueError` won't catch.
  - Validation: the two repro lines; fix = `prec = max(adjusted()+1, 1) + precision + 1` and catch overflow → ValueError.
- [P2] `first_request_guard`: one transient probe failure permanently bricks the client — aiochainscan/network.py:296-312
  - Evidence: guard runs outside the retry policy; any error (`self._guard_error = e`, `_guard_done = True`) is re-raised from every subsequent request forever. A single HTTP 429/5xx/DNS failure during the chainlist/eth-rpc probe (same rate-limited transport) → permanent `ChainscanRateLimitError`/`ChainscanNetworkError`, no retry, no recovery. Amplifier: `wait_for_block` BLOCK_BY_NUMBER path catches broad `ChainscanClientError → (False, exc)` (blocks.py:141-145), so a fatal chain-mismatch config error is silently polled for 600s and reported as timeout.
  - Impact: `expected_chain_id` configs (core of the base_url feature) degrade from fail-fast to fail-forever on one transient; wait_for_block hides the root cause for 10 minutes.
  - Validation: unit — guard raising `ChainscanRateLimitError` once, second `request()` must succeed (currently re-raises the cached error).
- [P2] BlockScout v1 `get_block` (BLOCK_BY_NUMBER) still routed to dead `module=proxy` — aiochainscan/scanners/blockscout_v1.py:30-34
  - Evidence: `_JSON_RPC_ACTIONS` reroutes TX_BY_HASH/PROXY_ETH_CALL/PROXY_GET_BALANCE to `/api/eth-rpc` but not BLOCK_BY_NUMBER; live `module=proxy&action=eth_getBlockByNumber&tag=0x1&boolean=true` → `{"message":"Unknown module"}` — the exact failure the reroute was introduced to fix.
  - Impact: `get_block()` on blockscout v1 (default MCP scanner, self-hosted instances) raises `ChainscanClientApiError('Unknown module')` although the method is declared in SPECS and the coverage matrix.
  - Validation: live curl above, or `from_config('blockscout','ethereum')` → `await client.get_block(1)`.
- [P2] `format_units`: floor divmod is wrong for negative amounts — aiochainscan/mcp/envelope.py:187-191
  - Evidence: `whole, remainder = divmod(amount, scale)` — reproduced: `format_units(-1500, 3)` → `'-2.5'` (correct `'-1.5'`); docstring promises "lossless".
  - Impact: exported helper applied to arbitrary explorer scalars (internal-tx values can be negative) — latent wrong-output mine for future MCP calls.
  - Validation: `format_units(-1500, 3)`; fix = handle sign before divmod.
- [P2] MCP cursors are unsigned and merged over request params — injection of arbitrary query parameters — aiochainscan/mcp/tools.py:437,605,719, aiochainscan/mcp/cursors.py:42-69
  - Evidence: `decode_cursor` is plain base64-JSON with only a version check — no HMAC, no tool binding, no key whitelist; `params.update(decode_cursor(cursor).get('cursor') or {})` merges attacker-controlled dict over computed params, and `EndpointSpec.map_params` passes unknown public names into the query. A crafted cursor can override `address`/`module`/`action` (redirect the request to another endpoint of the same API with the same key), then the answer is parsed by the wrong parser. Cursor from tool A is accepted by tool B.
  - Impact: not key leakage/SSRF (same host), but the "cursor is opaque, server controls the request shape" contract is broken; low risk for stdio hosting, real vector for remote MCP hosting.
  - Validation: `encode_cursor({'cursor': {'address': '0xattacker', 'module': 'account'}})` passed to `get_transactions`; fix = whitelist of cursor keys + tool binding + optional HMAC.

### Gaps
- Etherscan PRO endpoints (tokenholderlist/topholders) could not be live-verified without a PRO key; finding 1 was confirmed at the transport seam instead.
- Live checks performed against eth.blockscout.com (read-only GET/POST probes) by the reviewer.
