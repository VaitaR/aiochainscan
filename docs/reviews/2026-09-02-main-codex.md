---
artifact_id: "2026-09-02-main-codex"
date: "2026-09-02"
producer: "codex"
run_kind: "codex-adversarial"
verdict: "FAIL"
branch: "main"
base_ref: "origin/main"
base_sha: "7eb7be1"
head_sha: "f89dabd"
base_ref_source: "nearest-of-2"
worktree_dirty: false
redactions: 0
pr: null
session_id: null
agent_transcript_path: null
repo_root_source: "explicit_repo_arg"
files_reviewed:
  - "aiochainscan/core/mixins/account.py"
  - "docs/QUICK_REFERENCE.md"
  - "tests/test_method_consistency.py"
findings:
  - id: "F1"
    severity: "HIGH"
    file: "aiochainscan/core/mixins/account.py"
    line: 53
    claim: "get_transactions(start_block, end_block) bypasses the block-range guard; BlockScout V2 silently drops both fields (reproduced: params=None)"
    disposition: "accepted"
    disposition_note: "fixed in 051f6bb: _guard_direct_block_range on call()/fetch_page() seams"
  - id: "F2"
    severity: "MED"
    file: "tests/test_method_consistency.py"
    line: 495
    claim: "registry-derived sweep covers only STREAMING_SPECS; direct paginated calls cannot catch BlockScout V2 filtering bounded fields"
    disposition: "accepted"
    disposition_note: "fixed in 051f6bb: real-scanner/fake-Network bounded-range sweep (4 families x 3 methods)"
  - id: "F3"
    severity: "LOW"
    file: "docs/QUICK_REFERENCE.md"
    line: 30
    claim: "QUICK_REFERENCE.md still recommends the removed aiochainscan.core.method import"
    disposition: "accepted"
    disposition_note: "fixed in 051f6bb: repointed to aiochainscan.domain.method"
---

# codex review — main

> Captured automatically by `tools/hooks/review_capture.py` (agent-skills). The report below is the reviewer's verbatim output; the frontmatter above is parsed from it. Set each finding's `disposition` when you action it.

## Report (verbatim)

Verdict: **FAIL**

1. **HIGH** — [aiochainscan/core/mixins/account.py:53](/Users/andrew/Documents/projects/aiochainscan/aiochainscan/core/mixins/account.py:53)
   `get_transactions(start_block=100, end_block=200)` still bypasses the new range guard; BlockScout V2 drops both fields and sends its unbounded path-only request. This also affects `get_transactions_normalized`.
   Fix: apply the capability-derived range guard to direct paginated convenience methods, and cover the normalized wrapper.

2. **MED** — [tests/test_method_consistency.py:495](/Users/andrew/Documents/projects/aiochainscan/tests/test_method_consistency.py:495)
   The registry-derived sweep covers only `STREAMING_SPECS`; direct paginated calls are hand-listed and tested against a recording `call()`, so it cannot catch BlockScout V2 filtering bounded fields.
   Fix: add a real-spec/fake-network bounded-range sweep for direct paginated methods, asserting either transmitted bounds or `BlockRangeNotSupportedError`.

3. **LOW** — [docs/QUICK_REFERENCE.md:30](/Users/andrew/Documents/projects/aiochainscan/docs/QUICK_REFERENCE.md:30)
   The migration reference still recommends `from aiochainscan.core.method import Method`, but that module was removed in this arc.
   Fix: replace it with `from aiochainscan.domain.method import Method`.

Verified: pinned scope `7eb7be1..b9ce836`; worktree remained clean; `git diff --check` passed; targeted pagination, consistency, and pool tests passed (134). I also reproduced finding 1 with a real `BlockScoutV2Scanner` and fake network: the bounded direct call emitted `params=None`. The configured independent reviewer could not run because its CLI attempted to create a config temp file outside permitted writable paths.
