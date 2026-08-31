#!/usr/bin/env bash
set -euo pipefail

# rm-worktree.sh — safely tear down agent-session worktrees created by
# new-worktree.sh. Removes ONLY worktrees that are clean AND fully merged into
# an integration branch (origin/main). Dirty or unmerged worktrees are skipped
# with a reason. Never uses --force, so unsaved work cannot be destroyed.
# `branch -D` is used only for branches PROVEN squash-merged; ancestry-merged
# branches go through the safe `branch -d`.
#
# Usage:
#   scripts/agent/rm-worktree.sh                  list all worktrees + status (dry-run)
#   scripts/agent/rm-worktree.sh <slug>           preview removal of one worktree
#   scripts/agent/rm-worktree.sh <slug> --yes     remove that worktree (if clean+merged)
#   scripts/agent/rm-worktree.sh --prune-merged   preview removal of every clean+merged wt
#   scripts/agent/rm-worktree.sh --prune-merged --yes   remove every clean+merged wt
#
# Env:
#   AIO_MERGE_BASES        refs a branch must be merged into to count as merged
#                          (default: "origin/main")
#   AIO_SQUASH_SCAN_LIMIT  base commits the local squash probe scans, newest first
#                          (default 500; 0 disables the local probe)
#
# Exit status:
#   0  ran to completion (dry-run listing, or the removals it reported)
#   1  the named <slug> is not a worktree
#   2  usage error, or the worktree list could not be read (state UNKNOWN)
#
# An integration branch (main/master) is NEVER removed, even when a worktree
# sits on one — see PROTECTED_BRANCHES below.
#
# "merged" == branch tip is an ancestor of a base ref (so unpushed commits also
# count as unmerged and are skipped), OR the branch was squash-merged into a
# base, proven two ways in order of cost:
#   1. Local probe: patch-id shortlist over a bounded window of the base, then
#      an EXACT proof — replay the branch onto the candidate commit's real
#      parent with `git merge-tree --write-tree` and require a conflict-free
#      result byte-identical to the candidate's tree. (patch-id alone is NOT
#      proof: it normalizes whitespace, so a spacing-only difference compares
#      equal and could green-light deleting a branch whose content never landed.)
#   2. Forge probe: when the base has drifted past the fork point, the local
#      anchor is contaminated, so ask GitHub (`gh pr list --state merged --head
#      <branch>`) for the actual merge commit, require it reachable from a base,
#      and apply the same exact merge-tree proof.
#   Any ambiguity (gh missing/unauthenticated/erroring, zero or multiple merged
#   PRs, unreachable merge commit, conflicts, tree mismatch) makes the probe
#   report "not proven" — the branch reports unmerged and is SKIPPED, never
#   assumed merged. Every failure mode here fails closed toward keeping work.
#
# Adapted from lombard-data-analytics scripts/agent/rm-worktree.sh.

usage() {
	awk 'NR<=3 {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
}

MODE="list"          # list | one | prune
TARGET=""
CONFIRM=0

for arg in "$@"; do
	case "$arg" in
		-h|--help) usage; exit 0 ;;
		--yes) CONFIRM=1 ;;
		--prune-merged) MODE="prune" ;;
		--*) echo "ERROR: unknown flag $arg" >&2; usage; exit 2 ;;
		*)
			if [[ -n "$TARGET" ]]; then
				echo "ERROR: only one slug allowed (got '$TARGET' and '$arg')" >&2
				exit 2
			fi
			TARGET="$arg"; MODE="one"
			;;
	esac
done

MERGE_BASES="${AIO_MERGE_BASES:-origin/main}"

# How many base commits the local squash probe scans for a patch-id candidate,
# newest first. The bound exists because the scan is O(diff) per commit; running
# out of window makes the probe report "not proven" (an extra SKIP, announced),
# never a removal. 0 disables the local probe entirely.
SQUASH_SCAN_LIMIT="${AIO_SQUASH_SCAN_LIMIT:-500}"
case "$SQUASH_SCAN_LIMIT" in
	''|*[!0-9]*)
		echo "ERROR: AIO_SQUASH_SCAN_LIMIT must be a non-negative integer (got '$SQUASH_SCAN_LIMIT')" >&2
		echo "  An unvalidated value here silently turns the scan into a no-op or an unbounded walk." >&2
		exit 2 ;;
esac
# Force base 10 before any comparison: `[[ 08 -gt 0 ]]` is an arithmetic ERROR
# (bash reads a leading zero as octal), and the failed test would have silently
# disabled the local probe rather than saying anything (Codex, 2026-08-21).
SQUASH_SCAN_LIMIT=$((10#$SQUASH_SCAN_LIMIT))

# Branch names that must never be deleted, whatever the merge probes say. A
# worktree sitting on an integration branch passes `is_merged` trivially
# (`refs/heads/main` IS an ancestor of `origin/main`), so without this guard it
# reported "clean + merged" and `--yes` ran `git branch -d dev` — deleting the
# production branch. That state is reachable in one step: `gh pr merge
# --delete-branch` switches the calling worktree onto the shared local `dev`
# before deleting the feature branch, which is why that flag is hook-blocked
# from inside a worktree in the first place.
PROTECTED_BRANCHES="dev main master"
for _base in $MERGE_BASES; do
	# `origin/main` -> `main`; `origin/release/1.2` -> `release/1.2`; a bare
	# `dev` is left alone. Only the remote prefix is stripped, so the
	# comparison below stays an exact branch-name match.
	PROTECTED_BRANCHES="$PROTECTED_BRANCHES ${_base#*/}"
done

# Exact-name match only: a feature branch merely CONTAINING an integration
# name (`dev-tooling`, `feat/main-menu`) is ordinary work and stays removable.
is_protected_branch() {
	local candidate="$1" p
	for p in $PROTECTED_BRANCHES; do
		[[ "$candidate" == "$p" ]] && return 0
	done
	return 1
}

GIT_COMMON_DIR="$(cd "$(git rev-parse --git-common-dir)" && pwd)"
MAIN_ROOT="$(dirname "$GIT_COMMON_DIR")"

echo "==> Fetching origin (prune) for accurate merge checks..."
# Advisory, not fatal: a stale base can only make the probes UNDER-report
# (a branch tip / squashed patch that is absent from an older `origin/main` is
# absent from every subset of the true one), so the failure direction is extra
# SKIPs, never an extra removal. Offline runs stay useful for that reason.
git -C "$MAIN_ROOT" fetch origin --prune >/dev/null 2>&1 || \
	echo "WARN: fetch failed — merge status may be stale (this can only cause extra SKIPs, never an unsafe removal)." >&2

# Is the worktree at $1 clean? (no staged/unstaged/untracked changes)
# Returns 0 clean, 1 dirty, 2 UNREADABLE. The read failing is not a cleanliness answer: a
# failed `git status` writes to stderr and leaves stdout EMPTY, so the old
# `[[ -z "$(git -C "$1" status --porcelain)" ]]` form reported every unreadable worktree as
# clean — a .git file pointing nowhere, a corrupted index, permissions. This gate precedes an
# irreversible `git worktree remove` + `git branch -d`, so it printed "clean + merged (would
# remove)" for a worktree whose contents it had just failed to look at, with `fatal: not a git
# repository` on stderr. `|| status=$?` is required under `set -e`, which would otherwise abort
# the whole script on the very failure this is here to detect.
is_clean() {
	local out status=0
	out=$(git -C "$1" status --porcelain 2>/dev/null) || status=$?
	if [[ "$status" -ne 0 ]]; then
		return 2
	fi
	[[ -z "$out" ]]
}

# Is branch $1 merged into any of the configured integration refs?
is_merged() {
	local branch="$1" base
	for base in $MERGE_BASES; do
		if git -C "$MAIN_ROOT" merge-base --is-ancestor "refs/heads/$branch" "$base" 2>/dev/null; then
			return 0
		fi
	done
	return 1
}

# Was branch $1 squash-merged into any of the integration refs?
# Tries the local (free) probe first, then the forge-anchored probe. Either
# one returning success is sufficient proof; neither guesses on ambiguity.
is_squash_merged() {
	local branch="$1"
	_is_squash_merged_local_probe "$branch" && return 0
	_is_squash_merged_forge_probe "$branch" && return 0
	return 1
}

# THE exactness proof, shared by both probes: is commit $1 this branch ($2)
# squashed onto $1's own first parent? Replays the branch's commits onto that
# parent with git's own merge machinery and requires a conflict-free result
# whose tree is byte-identical to $1's tree. Anchoring on the candidate's real
# parent (not on today's merge-base) is what makes it immune to unrelated churn
# the base picked up before or after the squash landed.
#
# Why this is not a patch-id comparison: `git patch-id` — and therefore `git
# cherry` — normalizes whitespace, so a base commit differing from the branch
# only in spacing compares EQUAL. That is not a hypothetical: the local probe
# used to accept exactly that and `--yes` then ran `branch -D` on a branch whose
# content had never landed (Codex review, 2026-08-21; reproduced).
_commit_is_squash_of_branch() {
	local commit="$1" branch="$2" parent commit_tree merged_tree
	parent=$(git -C "$MAIN_ROOT" rev-parse "${commit}^" 2>/dev/null) || return 1
	commit_tree=$(git -C "$MAIN_ROOT" rev-parse "${commit}^{tree}" 2>/dev/null) || return 1
	# --write-tree exits non-zero on conflicts; `||` treats that (or any other
	# failure) as "not proven", never "assume merged".
	merged_tree=$(git -C "$MAIN_ROOT" merge-tree --write-tree "$parent" "refs/heads/$branch" 2>/dev/null) || return 1
	[[ -n "$merged_tree" && "$merged_tree" == "$commit_tree" ]]
}

# Local probe: find candidate base commits cheaply by patch-id, then prove each
# one EXACTLY. Patch-id is used only to shortlist (one `git log -p | git
# patch-id` pipeline over a bounded window of the base), because a patch-id hit
# is evidence of "something very like this landed", not of "this landed".
# Requires no network. Reports "not proven" — an extra SKIP — when the window is
# exhausted, when the pipeline is unreadable, or when no candidate survives the
# exact proof.
_is_squash_merged_local_probe() {
	local branch="$1" base mb target_pid candidates pid commit total
	[[ "$SQUASH_SCAN_LIMIT" -gt 0 ]] || return 1
	for base in $MERGE_BASES; do
		mb=$(git -C "$MAIN_ROOT" merge-base "$base" "refs/heads/$branch" 2>/dev/null) || continue
		# Nothing on the branch beyond the merge-base -> nothing to prove here.
		[[ "$mb" == "$(git -C "$MAIN_ROOT" rev-parse "refs/heads/$branch")" ]] && continue

		target_pid=$(git -C "$MAIN_ROOT" diff "$mb" "refs/heads/$branch" 2>/dev/null \
			| git -C "$MAIN_ROOT" patch-id --stable 2>/dev/null | awk 'NR==1 {print $1}') || target_pid=""
		[[ -n "$target_pid" ]] || continue

		# One pipeline for the whole window: `git log -p` piped through patch-id
		# yields "<patch-id> <commit-sha>" per commit. A failure anywhere leaves
		# $candidates empty, which is "not proven", not "nothing to find".
		candidates=$(git -C "$MAIN_ROOT" log --max-count="$SQUASH_SCAN_LIMIT" \
			--format='commit %H' -p "$base" "^$mb" 2>/dev/null \
			| git -C "$MAIN_ROOT" patch-id --stable 2>/dev/null) || candidates=""

		while read -r pid commit; do
			[[ "$pid" == "$target_pid" && -n "$commit" ]] || continue
			_commit_is_squash_of_branch "$commit" "$branch" && return 0
		done <<< "$candidates"

		# Nothing proven for this base. Say so when the window, rather than the
		# history, is what ran out — silence there would read as "looked
		# everywhere and found nothing".
		total=$(git -C "$MAIN_ROOT" rev-list --count "$base" "^$mb" 2>/dev/null) || total=0
		if [[ "$total" =~ ^[0-9]+$ ]] && [[ "$total" -gt "$SQUASH_SCAN_LIMIT" ]]; then
			echo "WARN: local squash probe scanned only the newest $SQUASH_SCAN_LIMIT of $total $base commits for '$branch' (raise AIO_SQUASH_SCAN_LIMIT)." >&2
		fi
	done
	return 1
}

# Forge probe: ask GitHub which merge commit (if any) actually closed this
# branch's PR, then prove content equivalence with an EXACT 3-way merge
# instead of a patch-id guess. Diffing full trees against a drifted anchor
# (tried first, and dropped) is contaminated by every unrelated file dev
# picked up between the branch's fork point and the merge — the merge
# commit's tree is a full repo snapshot, not just "this PR's lines", so a
# direct tree/patch comparison against it spuriously disagrees the moment
# ANY other file changed on the base in between, even one this branch never
# touched. `git merge-tree --write-tree` sidesteps that: it replays the
# branch's own commits onto the merge commit's real parent using git's own
# merge machinery (which finds the branch's true, unchanging fork point
# itself) and returns the resulting tree. A clean merge (no conflicts) whose
# resulting tree is byte-identical to the merge commit's tree is exact proof
# that commit IS this branch, squashed onto its real parent — not a
# heuristic, and immune to unrelated churn elsewhere on the base. No branch
# name / PR number / SHA is special-cased — the branch under test and its
# merge commit are both looked up generically.
#
# Fails closed (returns 1, "not proven") on every ambiguity: gh missing or
# erroring (auth, rate limit, network), no jq, zero or more than one merged
# PR reported for this exact head branch, an empty/missing merge commit SHA,
# that SHA not reachable from the base being checked, a merge with conflicts,
# or a clean merge whose tree does not match. A "not proven" result here
# means the branch is reported unmerged and skipped — never treated as
# evidence to remove.
_is_squash_merged_forge_probe() {
	local branch="$1" base reachable=0 pr_json pr_count mc

	command -v gh >/dev/null 2>&1 || return 1
	command -v jq >/dev/null 2>&1 || return 1

	pr_json=$(gh pr list --state merged --head "$branch" --json mergeCommit 2>/dev/null) || return 1
	[[ -n "$pr_json" ]] || return 1

	pr_count=$(echo "$pr_json" | jq 'length' 2>/dev/null) || return 1
	# 0 = nothing to prove; >1 = ambiguous (which merge actually applies?).
	# Both fall through to "not proven" rather than guessing.
	[[ "$pr_count" == "1" ]] || return 1

	mc=$(echo "$pr_json" | jq -r '.[0].mergeCommit.oid // empty' 2>/dev/null) || return 1
	[[ -n "$mc" ]] || return 1
	git -C "$MAIN_ROOT" cat-file -e "${mc}^{commit}" 2>/dev/null || return 1

	for base in $MERGE_BASES; do
		if git -C "$MAIN_ROOT" merge-base --is-ancestor "$mc" "$base" 2>/dev/null; then
			reachable=1
			break
		fi
	done
	# gh saying "merged" proves nothing about which ref it landed on — only
	# trust a merge commit we can independently verify is IN the base.
	[[ "$reachable" == "1" ]] || return 1

	# Same exactness proof the local probe uses — one owner, two candidate
	# sources (a forge-reported merge commit here, a patch-id shortlist there).
	_commit_is_squash_of_branch "$mc" "$branch"
}

remove_one() {
	local path="$1" branch="$2" kind="$3"
	echo "    removing worktree $path"
	git -C "$MAIN_ROOT" worktree remove "$path"   # no --force: refuses if dirty
	echo "    deleting branch $branch"
	if [[ "$kind" == "squash" ]]; then
		# `branch -d` would refuse (tip is not an ancestor of the base), but
		# is_squash_merged already proved the branch content is in the base —
		# the exact evidence -d asks for, just for a squashed history.
		git -C "$MAIN_ROOT" branch -D "$branch"
	else
		git -C "$MAIN_ROOT" branch -d "$branch"    # refuses if unmerged
	fi
}

found_target=0
eligible=0
acted=0

# Enumerate BEFORE the loop so a failed enumeration is an error instead of an
# empty result: fed through `done < <(...)`, the exit status of the pipeline is
# discarded, so `git worktree list` failing looked exactly like "no worktrees
# here" — a clean exit 0 and "Removed 0 worktree(s)" in --prune-merged mode. An
# unreadable list is UNKNOWN, never "nothing to do".
if ! WT_PORCELAIN="$(git -C "$MAIN_ROOT" worktree list --porcelain 2>&1)"; then
	echo "ERROR: cannot enumerate worktrees in $MAIN_ROOT — state unknown, nothing was removed:" >&2
	printf '%s\n' "$WT_PORCELAIN" >&2
	exit 2
fi

WT_TABLE="$(printf '%s\n' "$WT_PORCELAIN" | awk '
	function flush(){ if (p != "") print p "\t" (b == "" ? "(detached)" : b) }
	/^worktree /{ flush(); p=$2; b="" }
	/^branch /{ b=$2 }
	END{ flush() }
')"

# The main clone itself is always listed, so an empty table means the output was
# unparseable (a git version whose porcelain format we do not understand), not
# an absence of worktrees.
if [[ -z "$WT_TABLE" ]]; then
	echo "ERROR: worktree list produced no parseable entries in $MAIN_ROOT — state unknown, nothing was removed." >&2
	exit 2
fi

while IFS=$'\t' read -r wt_path wt_ref; do
	[[ "$wt_path" == "$MAIN_ROOT" ]] && continue

	slug="$(basename "$wt_path")"
	if [[ "$MODE" == "one" && "$slug" != "$TARGET" ]]; then
		continue
	fi
	[[ "$MODE" == "one" ]] && found_target=1

	if [[ "$wt_ref" == "(detached)" ]]; then
		printf '  SKIP  %-28s detached HEAD (no branch)\n' "$slug"
		continue
	fi
	branch="${wt_ref#refs/heads/}"

	if is_protected_branch "$branch"; then
		printf '  SKIP  %-28s [%s] integration branch — never removed\n' "$slug" "$branch"
		continue
	fi

	clean_status=0
	is_clean "$wt_path" || clean_status=$?
	if [[ "$clean_status" -eq 2 ]]; then
		printf '  SKIP  %-28s [%s] UNREADABLE — git status failed; cleanliness unknown\n' \
			"$slug" "$branch"
		continue
	fi
	if [[ "$clean_status" -ne 0 ]]; then
		printf '  SKIP  %-28s [%s] dirty — uncommitted changes\n' "$slug" "$branch"
		continue
	fi
	if is_merged "$branch"; then
		kind="ancestor"; label="clean + merged"
	elif is_squash_merged "$branch"; then
		kind="squash"; label="clean + squash-merged"
	else
		printf '  SKIP  %-28s [%s] unmerged into {%s}\n' "$slug" "$branch" "$MERGE_BASES"
		continue
	fi

	eligible=$((eligible + 1))
	if [[ "$CONFIRM" == "1" && "$MODE" != "list" ]]; then
		printf '  REMOVE %-27s [%s] %s\n' "$slug" "$branch" "$label"
		remove_one "$wt_path" "$branch" "$kind"
		acted=$((acted + 1))
	else
		printf '  ready %-28s [%s] %s (would remove)\n' "$slug" "$branch" "$label"
	fi
done <<< "$WT_TABLE"

echo ""
if [[ "$MODE" == "one" && "$found_target" == "0" ]]; then
	echo "No worktree named '$TARGET' (expected dir basename under the worktree parent)."
	exit 1
fi

if [[ "$CONFIRM" == "1" && "$MODE" != "list" ]]; then
	echo "Done. Removed $acted worktree(s)."
else
	echo "Dry-run. $eligible worktree(s) eligible (clean + merged)."
	[[ "$MODE" == "list" ]] && echo "Re-run with a <slug> or --prune-merged, plus --yes, to remove."
	[[ "$MODE" != "list" ]] && echo "Add --yes to actually remove."
fi
# A dry-run that only reported SKIPs/eligibility completed successfully — never
# let the trailing `[[ cond ]] && echo` short-circuit set a nonzero exit status.
exit 0
