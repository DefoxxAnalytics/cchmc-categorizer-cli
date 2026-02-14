# Fix 10 Code Review Issues in categorize.py

## Context

Code review of `src/categorize.py` found 10 issues (3 critical, 5 high, 2 medium). These are defensive coding gaps — the engine works for CCHMC but will crash on edge cases for new clients with malformed configs, empty files, or bad regex.

## Target File

`src/categorize.py`

## Fixes

### 1. CRITICAL: amount_col not in output_columns
**Line 394-401** — `amount_col` is only in output if it happens to be in `passthrough`. If a client doesn't list it in passthrough, financial aggregations (`results_df[amount_col]`) crash with `KeyError`.

**Fix**: Explicitly add `amount_col` to `output_columns` after passthrough loop (line ~402).

### 2. CRITICAL: Empty YAML returns None
**Lines 85, 121, 127** — `yaml.safe_load()` returns `None` on empty file. `data.get(...)` then throws `AttributeError: 'NoneType' object has no attribute 'get'`.

**Fix**: Guard each loader — `data = yaml.safe_load(f) or {}` in `load_sc_mapping`, `load_keyword_rules`, `load_refinement_rules`.

### 3. CRITICAL: Missing keys in malformed rules
**Lines 88-95, 128-145** — If a rule dict is missing `name`, `taxonomy_key`, `supplier_pattern`, etc., raw `KeyError` with no context.

**Fix**: Validate required keys in each loader. Fail fast with clear error: `"supplier_rules[3] missing key 'taxonomy_key'"`.

### 4. HIGH: re.compile without try/except in refinement loader
**Lines 130, 133, 136, 139** — `re.compile(rule['supplier_pattern'])` crashes on invalid regex.

**Fix**: Wrap in try/except, fail with clear error: `"supplier_rules[3] invalid regex: ..."`.

### 5. HIGH: Keyword rules not pre-validated
**Lines 269-283** — Bad regex in keyword rules crashes mid-classification (after Tier 2 is already done), leaving results in partial state.

**Fix**: Pre-validate all keyword rule patterns in `load_keyword_rules` — compile and fail fast before classification starts.

### 6. HIGH: No CSV column validation
**Lines 218-227** — If CSV is missing a required column (e.g., `Spend Category`), raw pandas `KeyError`.

**Fix**: After `pd.read_csv`, validate that all required columns from config exist in `df.columns`. Fail with: `"Column 'Spend Category' (from columns.spend_category) not found in input CSV"`.

### 7. HIGH: ZeroDivisionError on empty CSV
**Lines 460, 484-489** — `total_rows` is 0 → division by zero in percentage calculations.

**Fix**: Guard `total_rows == 0` — exit early with message after loading CSV.

### 8. HIGH: sys.exit(1) prevents testability
**Lines 31, 42, 48, 54, 60, 78** — `sys.exit(1)` kills the process, making `main()` untestable.

**Fix**: Replace all `sys.exit(1)` calls with raising a custom `ConfigError` exception. CLI entry point (`if __name__`) catches it and calls `sys.exit(1)`.

### 9. MEDIUM: Dead get_review_tier function
**Lines 148-156** — `get_review_tier()` is defined but never called. Review tier assignment is done inline at line 381-386 using `np.where`.

**Fix**: Delete the function.

### 10. MEDIUM: Rule ordering (no guardrails)
First-match-wins semantics — rule order in YAML determines outcome when multiple rules match the same row.

**Fix**: No code change. First-match-wins is the correct design for performance. Document this behavior in CLAUDE.md.

## Implementation Order

1. Define `ConfigError` exception class (enables #8)
2. Replace all `sys.exit(1)` with `raise ConfigError(...)` (#8)
3. Add YAML empty-file guards (#2)
4. Add rule key validation in loaders (#3)
5. Add regex validation with try/except in loaders (#4, #5)
6. Add CSV column validation after `pd.read_csv` (#6)
7. Add `amount_col` to output_columns explicitly (#1)
8. Guard `total_rows == 0` (#7)
9. Delete dead `get_review_tier` function (#9)
10. Skip #10 — no code change, first-match-wins is intentional

## Verification

1. Run CCHMC pipeline: `python src/categorize.py --config clients/cchmc/config.yaml`
   - Must match: 594,807 AA, 1,989 QR, ~10s classification
2. Run tests: `python -m pytest tests/ -v --client-dir clients/cchmc`
   - Must pass: 32 passed, 1 skipped
3. Spot-check: output Excel `amount_col` column present in results
