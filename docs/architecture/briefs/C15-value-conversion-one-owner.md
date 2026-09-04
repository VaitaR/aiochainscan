---
kind: deepening-brief
id: C15
slug: value-conversion-one-owner
source: ../2026-09-05-review.md
status: accepted
base: c9943a2
---

# Value conversion with one owner production actually uses

## Repo orientation

`aiochainscan` is an async Python wrapper over blockchain-explorer APIs. Explorers
return every numeric scalar as a **string in base units** — wei for the native asset,
raw token units otherwise. Domain terms live in `CONTEXT.md`.

- `aiochainscan/convert.py` is the declared owner of base-unit math: `to_decimal_amount`
  (`:76-109`) and `wei_to_ether` (`:112-132`) scale exactly via `Decimal.scaleb`, never
  through float.
- `aiochainscan/domain/normalize.py` owns the **Provider field dialect** — the accessor
  vocabulary (`first_field`, `flat_address`, `int_or_default`) that reads
  provider-native dicts whose key names differ per explorer.
- `aiochainscan/services/analytics.py` exports those dicts to Polars DataFrames.

`AGENTS.md` states the project rule in its Data Integrity table: *"Balance/value/supply
values are Wei strings — convert with `wei_to_ether()` / `to_decimal_amount()` (exact
`Decimal`), never `int(wei) / 10**18` float division."*

Tests are pytest under `tests/`. Full gate: `make validate`. One file:
`uv run pytest tests/test_analytics.py -q`.

## Task

Make `aiochainscan/services/analytics.py` obtain its scaled values from
`aiochainscan/convert.py` instead of doing base-unit division itself, **without changing
the published DataFrame schema**, and fold the duplicated hex-or-decimal integer parse
rule in `domain/normalize.py` onto the one in `convert.py`.

## Why this is not cosmetic (read before starting)

Two places in `analytics.py` do exactly the division `AGENTS.md` forbids:

- `analytics.py:125` — `'value_eth': int(value_wei) / 1e18`
- `analytics.py:173` — `'balance': value / (10**decimals) if decimals > 0 else float(value)`

Meanwhile `to_decimal_amount`, `wei_to_ether` and `format_ether` have **zero** callers
inside the package: `convert.py` is imported by `domain/normalize.py:72` (for
`to_datetime` only), by `scanners/nodereal.py:55` (for `hex_to_int` only) and by
`aiochainscan/__init__.py:3` (re-export for library users). The module is correct and
unused; the one path that needs it re-derived the rule and got it wrong.

`int(w) / 1e18` rounds **twice** — once converting the integer to a double, once
dividing — so it does not always produce the nearest double to the true amount. A
measured example, which is also your test case:

| wei | `int(w) / 1e18` (today) | exact-then-round (correct) |
|---|---|---|
| `946864788125462323` | `0.9468647881254623` | `0.9468647881254624` |

The chosen remedy is **non-breaking**: the columns stay `Float64`, and the float is
produced by narrowing an exact `Decimal` exactly once.

## Contract

### 1. `analytics.py` stops doing base-unit arithmetic

- `transactions_to_dataframe` (`analytics.py:68-132`): `value_eth` becomes
  `float(wei_to_ether(value_wei))`. `value_wei` is already an exact decimal string built
  at `:116`; keep that line as it is.
- `token_portfolio_to_dataframe` (`analytics.py:135-186`): `balance` becomes
  `float(to_decimal_amount(value, decimals))`. The `if decimals > 0 else float(value)`
  special case is deleted — `to_decimal_amount` handles `decimals == 0` and raises only
  on a **negative** `decimals` (`convert.py:103-104`).
- Schemas are untouched: `value_eth: pl.Float64` (`analytics.py:40`) and
  `balance: pl.Float64` (`analytics.py:183`) stay exactly as they are.
- Invariant after this brief: **no base-unit division outside `convert.py`.**

### 2. One hex-or-decimal integer parse rule

`convert.py:_parse_flexible_int:58-73` and `domain/normalize.py:int_or_default:164-179`
both implement `0x`-prefix detection and integer parsing. Their **error contracts differ
and both must survive**: `_parse_flexible_int` raises `ValueError`; `int_or_default`
returns the caller's `default`.

Fold the parse rule onto `_parse_flexible_int` — `int_or_default` calls it inside a
`try` and returns `default` on `ValueError`. `domain/normalize.py` already imports from
`..convert` (`:72`), so the direction is allowed; `make validate` runs `import-linter`
and will tell you if it is not.

Required behaviour parity for `int_or_default`, all of which it does today:

- `bool` → `default` (never `True` → `1`). This check must stay **before** the parse.
- `int` → itself.
- `''`, `None`, non-str/non-int → `default`.
- `'26'` → `26`; `'0x1a'` / `'0X1a'` → `26`; `'zz'` → `default`.

## Edge cases

- **Signed hex is the one behaviour change.** `int_or_default('-0x10')` returns `default`
  today (`normalize.py:175-176` only tests a `0x` prefix, so `int('-0x10')` raises);
  `_parse_flexible_int` handles the sign and returns `-16`. Accept the change, pin it in
  a test, and say so in your report. Do not "fix" it back by re-adding a second parse.
- **`bool` before parse.** `isinstance(True, int)` is `True` in Python, so reordering the
  guards silently turns `True` into `1` in the DataFrame. `normalize.py:170-171` gets
  this right today; keep it right.
- **`float(Decimal)` may differ from today's value by one ULP.** That is the entire
  point — see the table above. `tests/test_analytics.py:60,89,118` use
  `pytest.approx(rel=1e-15)` and must keep passing unchanged; if one of them fails, stop
  and report it rather than loosening the tolerance.
- **`to_decimal_amount` raises on non-integer input.** In both call sites the value is
  already an `int` or an exact integer string built upstream (`analytics.py:116`, `:162`),
  so no new exception path is expected. If you find one that is reachable, report it
  instead of wrapping it in a bare `except`.
- **Empty-frame paths** (`analytics.py:104-106`, `:150-156`) construct from the schema
  and touch no arithmetic. Leave them alone.

## Files

**Change:** `aiochainscan/services/analytics.py`, `aiochainscan/domain/normalize.py`,
`tests/test_analytics.py` (added cases), `tests/test_convert.py` and/or the normalize
tests (added cases).

**Delete:** nothing.

**Do not touch:** `aiochainscan/convert.py`'s public behaviour (`to_decimal_amount`,
`wei_to_ether`, `format_ether`, `hex_to_int`, `to_datetime`, `to_iso` keep their exact
contracts — you may only add a caller), `aiochainscan/core/`,
`aiochainscan/scanners/`, `aiochainscan/mcp/`.

## Out of scope

- **Changing any column dtype.** The user chose the non-breaking option explicitly:
  `Float64` stays. Do not add exact string/`pl.Decimal` columns either — that was
  considered and declined.
- **`transactions_to_dataframe_arrow`** (`analytics.py:189-229`). Its values come from
  the Rust tier, not from this arithmetic.
- **The literal provider keys in `token_portfolio_to_dataframe`** (`'token'`,
  `'decimals'`, `'symbol'`, `'name'` at `analytics.py:160-170`). They are a separate
  question about the Provider field dialect, they need per-provider evidence this brief
  does not carry, and guessing accessor aliases would silently change which field is
  read. Leave them.
- **`services/chain_info.py:77`'s local hex parser.** It is deliberately hex-only and
  documents why.

## Verification

```bash
uv run pytest tests/test_analytics.py tests/test_convert.py -q
make validate
```

The grep observable — on `base` the first returns two hits:

```bash
rg -n '/ 1e18|/ \(10\*\*' aiochainscan/services/    # must return nothing
```

Add to `tests/test_analytics.py` a case that **fails on `base`** and passes after, using
the measured value from the table:

- a transaction with `value = '946864788125462323'` → assert
  `row['value_eth'] == 0.9468647881254624` (exact float equality, not `approx` — the
  point is the last bit). On `base` this yields `0.9468647881254623`.

Run that new test against `base` first (`git stash` the source change, or check out the
file), paste the failure, then restore and paste the pass. A test that cannot fail
proves nothing, and this is the only case in the suite that distinguishes the two
implementations — the existing largest case is 1,000,000 ETH at `rel=1e-10`
(`tests/test_analytics.py:118`), which float handles either way.

Add a signed-hex case pinning `int_or_default('-0x10')`, and a `bool` case pinning
`int_or_default(True, default=0) == 0`.

Report command output, not a summary of it.

## Definition of done

- `rg -n '/ 1e18|/ \(10\*\*' aiochainscan/services/` returns nothing.
- `int_or_default` delegates its parse to `convert._parse_flexible_int`; the parity list
  above is covered by tests, including the `bool` guard.
- The `946864788125462323` test is shown failing on `base` and passing after — both
  outputs pasted.
- `tests/test_analytics.py:60,89,118` pass **unchanged**.
- `make validate` passes in full.
- Commit locally on a branch. Do not push, do not open a PR.

## Decisions already made

- Non-breaking: `value_eth` and `balance` stay `pl.Float64`; the exactness is in how the
  float is produced, not in the column type. The user chose this over adding exact
  columns and over a dtype change.
- Both error contracts of the two integer parsers survive; only the parse rule is shared.
- The literal-key question in `token_portfolio_to_dataframe` is deferred, not forgotten.

## Open questions

- If folding `int_or_default` onto `_parse_flexible_int` trips an `import-linter`
  contract (`pyproject.toml:147-200`), **do not weaken the contract**. Report it, leave
  the two parsers alone, and ship part 1 only — that is a valid partial result, not a
  failure.

"I could not do X" is a valid answer. An unmet item must be reported as unmet, not
interpreted away.
