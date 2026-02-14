# Spend Categorization CLI — Project Guide

## What This Project Does

Config-driven CLI tool that classifies healthcare procurement transactions against Healthcare Taxonomy v2.9. Each client gets a YAML config + reference data — zero code changes per engagement.

## Architecture

### Engine (`src/categorize.py`)

Single-file engine, ~380 lines. Three layers:

1. **Config loader** (`load_config`) — reads client YAML, resolves relative paths, validates required fields
2. **Data loaders** (`load_sc_mapping`, `load_taxonomy`, `load_keyword_rules`, `load_refinement_rules`) — parse reference files
3. **Pipeline** (`main`) — 7-tier vectorized classification waterfall + Excel output

### 7-Tier Classification Waterfall

```
Input CSV
  ↓
Tier 1: SC Code Mapping (non-ambiguous) ─── deterministic lookup
  ↓ (unclassified rows only)
Tier 2: Supplier Refinement ──────────────── SC code + supplier regex
  ↓
Tier 3: Keyword Rules ────────────────────── supplier + line memo regex
  ↓
Tier 4: Context Refinement ───────────────── SC code + line-of-service regex
  ↓
Tier 5: Cost Center Refinement ───────────── SC code + cost center regex
  ↓
Tier 6: Ambiguous Fallback ───────────────── generic SC mapping, low confidence
  ↓
Tier 7: Supplier Override ────────────────── post-classification L1 corrections
  ↓
Output Excel (timestamped)
```

Tiers 1-6 are mutually exclusive (first match wins). Tier 7 can override any prior tier.

### Client Config (`clients/<name>/config.yaml`)

All client-specific values live here:
- **paths**: input CSV, SC mapping, taxonomy, rules, output directory
- **columns**: ERP field name mappings (spend_category, supplier, line_memo, etc.)
- **classification**: SC code regex pattern, confidence thresholds
- **aggregations**: dynamic Excel groupby sheets

All paths are relative to the config file's parent directory.

### Reference Data

| File | Scope | Description |
|------|-------|-------------|
| `sc_code_mapping.yaml` | Per-client | Spend category code → taxonomy key + confidence + ambiguity flag |
| `keyword_rules.yaml` | Per-client (can share) | Regex patterns on supplier + line memo text |
| `cchmc_refinement_rules.yaml` | Per-client | 4 sections: supplier_rules, context_rules, cost_center_rules, supplier_override_rules |
| `Healthcare Taxonomy v2.9.xlsx` | Shared | Universal taxonomy with Key, CategoryLevel1-5 columns |

### Test Suite (`tests/`)

- `conftest.py` — config-driven fixtures, `--client-dir` pytest option
- `test_rules.py` — 33 tests across 6 suites: YAML structure, regex validity, taxonomy key validation, SC code validation, confidence ranges, known-mapping assertions, conflict detection

Tests are client-agnostic: `python -m pytest tests/ --client-dir clients/<name>`

## Key Conventions

### Config-Driven Design
Every client-specific value comes from `config.yaml`. The engine reads config, never hardcodes client details. When adding new configurable behavior, add it to the config schema rather than branching on client names.

### Vectorized Operations
The classification pipeline uses pandas index-based assignment for performance. Pattern:
```python
cand_idx = candidate[candidate].index
match = series.loc[cand_idx].str.contains(pattern, case=False, na=False, regex=True)
hit_idx = cand_idx[match.values]
if len(hit_idx) > 0:
    target[hit_idx] = value
```
Never use `iterrows()` or boolean mask copy+assignment (`hit = mask.copy(); hit[mask] = result`).

### Path Resolution
All config paths are relative to the config file's parent directory. The `load_config()` function resolves them to absolute paths at startup. CLI overrides (`--input`, `--output-dir`) take absolute or CWD-relative paths.

### Output Columns
Two categories:
- **Passthrough columns**: from `config.columns.passthrough` — carried from input CSV to output unchanged
- **Classification columns**: fixed names (`CategoryLevel1-5`, `TaxonomyKey`, `ClassificationMethod`, `Confidence`, `ReviewTier`) — always present regardless of client

### Rule File Structure
Refinement rules YAML has 4 sections:
```yaml
supplier_rules:        # SC code + supplier regex → taxonomy
context_rules:         # SC code + line-of-service regex → taxonomy
cost_center_rules:     # SC code + cost center regex → taxonomy
supplier_override_rules:  # supplier regex + current L1 → corrected taxonomy
```

Each rule has a `confidence` field (0.0-1.0) that determines the review tier.

## Development Workflow

### Adding a New Client
1. `mkdir -p clients/<name>/data/{input,reference} clients/<name>/output`
2. Copy `clients/cchmc/config.yaml` → `clients/<name>/config.yaml`
3. Update paths, column names, SC code pattern, aggregations
4. Create client-specific `sc_code_mapping.yaml` and `refinement_rules.yaml`
5. Run: `python src/categorize.py --config clients/<name>/config.yaml`
6. Run tests: `python -m pytest tests/ -v --client-dir clients/<name>`

### Adding a New Rule
1. Edit the client's `refinement_rules.yaml`
2. Run tests to validate: `python -m pytest tests/ -v --client-dir clients/<name>`
3. Re-run pipeline to verify impact

### Modifying the Engine
1. Edit `src/categorize.py`
2. Run CCHMC pipeline to verify no regression
3. Run tests: `python -m pytest tests/ -v`
4. Verify: 594,807 AA, 1,989 QR (CCHMC baseline)

## Current State (v1)

### CCHMC Baseline Numbers
- Total: 596,796 rows, $3.51B spend
- Auto-Accept: 594,807 (99.7%)
- Quick Review: 1,989 (0.3%)
- Classification time: ~10 seconds
- Rules: 237 supplier + 8 context + 10 cost center + 11 override + 220 keyword

### Dependencies
- pandas, pyyaml, openpyxl (runtime)
- pytest (testing)
- Python 3.9+

### Files at a Glance
```
src/categorize.py          # Engine + CLI (~380 lines)
clients/cchmc/config.yaml  # CCHMC client config
tests/conftest.py          # Pytest fixtures
tests/test_rules.py        # 33 regression tests
docs/PRD.md                # Product requirements
docs/User_Guide.md         # Usage guide
```
