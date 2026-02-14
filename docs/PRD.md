# Product Requirements Document: Spend Categorization CLI

## 1. Overview

**Product**: Spend Categorization CLI Tool
**Owner**: VTX Solutions / Defoxx Analytics
**Version**: 1.0
**Date**: 2026-02-13

### 1.1 Problem Statement

Healthcare organizations generate hundreds of thousands of procurement transactions annually across ERP systems (Workday, Oracle, SAP). These transactions carry vendor-assigned spend category codes that are too coarse for strategic spend analysis — a single code like "SC0250" (Professional Services) covers everything from legal counsel to janitorial services.

Manual categorization against a standardized taxonomy is prohibitively expensive at scale (600K+ rows per client). Existing tools either require extensive customization per client or sacrifice accuracy for speed.

### 1.2 Solution

A config-driven CLI tool that classifies procurement transactions against Healthcare Taxonomy v2.9 using a 7-tier classification waterfall. Each client engagement requires only a YAML configuration file and client-specific reference data — no code changes.

### 1.3 Business Context

- **Service model**: Repeatable consulting engagement across healthcare clients
- **First client**: Cincinnati Children's Hospital Medical Center (CCHMC) — 596,796 rows, $3.51B spend
- **Target market**: Mid-to-large healthcare systems with Workday/Oracle/SAP procurement data
- **Value proposition**: 99%+ automated classification accuracy, reducing manual review from 100% to <1% of transactions

## 2. Target Users

| User | Role | Usage |
|------|------|-------|
| VTX/Defoxx Analyst | Primary operator | Runs CLI per client engagement, writes client configs and rules |
| Client Stakeholder | Results consumer | Receives Excel deliverables, reviews Quick Review items |

## 3. Functional Requirements

### 3.1 CLI Interface

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | Accept `--config <path>` argument pointing to client YAML config | P0 |
| FR-02 | Accept optional `--input <path>` to override input CSV from config | P1 |
| FR-03 | Accept optional `--output-dir <path>` to override output directory from config | P1 |
| FR-04 | Validate config schema on startup, report missing/invalid fields with clear errors | P0 |
| FR-05 | Exit with non-zero code on any failure (missing files, invalid config, data errors) | P0 |

### 3.2 Configuration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-10 | All file paths in config are relative to the config file's parent directory | P0 |
| FR-11 | Column mapping: configurable names for spend_category, supplier, line_memo, line_of_service, cost_center, amount | P0 |
| FR-12 | Passthrough columns: configurable list of additional columns to include in output | P0 |
| FR-13 | SC code extraction pattern: configurable regex for extracting spend category codes | P0 |
| FR-14 | Confidence thresholds: configurable high (Auto-Accept) and medium (Quick Review) cutoffs | P0 |
| FR-15 | Aggregation tabs: configurable list of groupby dimensions with optional top_n limit | P1 |
| FR-16 | Output file prefix: configurable per client | P0 |
| FR-17 | Client name/description: used in console output banners | P1 |

### 3.3 Classification Engine (7-Tier Waterfall)

All tiers execute sequentially. Each row is classified by exactly one tier (first match wins, except Tier 7 which overrides).

| ID | Tier | Description | Priority |
|----|------|-------------|----------|
| FR-20 | Tier 1: SC Code Mapping | Deterministic lookup for non-ambiguous spend category codes | P0 |
| FR-21 | Tier 2: Supplier Refinement | Ambiguous SC code + supplier regex pattern → taxonomy key | P0 |
| FR-22 | Tier 3: Keyword Rules | Regex on combined supplier + line memo text → taxonomy key | P0 |
| FR-23 | Tier 4: Context Refinement | Ambiguous SC code + line-of-service regex → taxonomy key | P0 |
| FR-24 | Tier 5: Cost Center Refinement | Ambiguous SC code + cost center regex → taxonomy key | P0 |
| FR-25 | Tier 6: Ambiguous Fallback | Remaining ambiguous SC codes → generic taxonomy at low confidence | P0 |
| FR-26 | Tier 7: Supplier Override | Post-classification correction for known SC-supplier L1 mismatches | P0 |

### 3.4 Review Tier Assignment

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-30 | Auto-Accept: confidence >= high threshold (or >= 0.9 for sc_code_mapping/rule methods) | P0 |
| FR-31 | Quick Review: confidence >= medium threshold but below Auto-Accept | P0 |
| FR-32 | Manual Review: confidence below medium threshold | P0 |

### 3.5 Output

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-40 | Timestamped Excel file: `{prefix}_{YYYYMMDD_HHMMSS}.xlsx` | P0 |
| FR-41 | Sheet "All Results": every input row with classification columns appended | P0 |
| FR-42 | Sheet "Manual Review": filtered subset where ReviewTier = Manual Review | P0 |
| FR-43 | Sheet "Quick Review": filtered subset where ReviewTier = Quick Review | P0 |
| FR-44 | Sheet "Summary": transaction counts, method breakdown, tier breakdown, financial totals | P0 |
| FR-45 | Sheet "Spend by Category L1": groupby L1, with count/spend/suppliers/avg confidence | P0 |
| FR-46 | Sheet "Spend by Category L2": groupby L1+L2, with count/spend/suppliers | P0 |
| FR-47 | Dynamic aggregation sheets: one per entry in config `aggregations` list | P1 |
| FR-48 | Sheet "Unmapped SC Codes": only present if unmapped rows exist | P1 |
| FR-49 | Console output: tier-by-tier progress, final summary with method/tier counts and timing | P0 |

### 3.6 Reference Data

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-50 | SC Code Mapping: YAML file mapping spend category codes → taxonomy keys with confidence and ambiguity flag | P0 |
| FR-51 | Taxonomy: Excel file with Key, CategoryLevel1-5 columns (Healthcare Taxonomy v2.9 format) | P0 |
| FR-52 | Keyword Rules: YAML file with pattern/category/confidence per rule | P0 |
| FR-53 | Refinement Rules: YAML file with 4 sections — supplier_rules, context_rules, cost_center_rules, supplier_override_rules | P0 |
| FR-54 | Taxonomy validation: on startup, warn about SC mappings pointing to invalid taxonomy keys | P0 |

## 4. Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-01 | Classification speed | < 15 seconds for 600K rows |
| NFR-02 | Total runtime (incl. Excel I/O) | < 5 minutes for 600K rows |
| NFR-03 | Memory usage | < 4 GB for 600K rows |
| NFR-04 | Python version | 3.9+ |
| NFR-05 | Dependencies | pandas, pyyaml, openpyxl only (no heavy frameworks) |
| NFR-06 | Platform | Windows, macOS, Linux |
| NFR-07 | No network access required | Fully offline operation |

## 5. Config Schema Specification

```yaml
client:
  name: string          # Required. Used in console banners.
  description: string   # Optional. For documentation.

paths:
  input: string              # Required. CSV input file (relative to config dir).
  sc_mapping: string         # Required. SC code → taxonomy YAML.
  taxonomy: string           # Required. Healthcare Taxonomy Excel.
  keyword_rules: string      # Required. Keyword regex rules YAML.
  refinement_rules: string   # Required. Supplier/context/CC/override rules YAML.
  output_dir: string         # Required. Output directory.
  output_prefix: string      # Required. Output filename prefix.

columns:
  spend_category: string     # Required. Column containing spend category codes.
  supplier: string           # Required. Column containing supplier names.
  line_memo: string          # Required. Column containing line memo/description.
  line_of_service: string    # Required. Column for context refinement.
  cost_center: string        # Required. Column for cost center refinement.
  amount: string             # Required. Column containing monetary amount.
  passthrough: list[string]  # Optional. Additional columns to carry into output.

classification:
  sc_code_pattern: string    # Required. Regex with one capture group for SC code extraction.
  confidence_high: float     # Required. Threshold for Auto-Accept (0.0-1.0).
  confidence_medium: float   # Required. Threshold for Quick Review (0.0-1.0).

aggregations:                # Optional. List of additional groupby sheets.
  - name: string             # Sheet name in output Excel.
    column: string           # Column name to group by.
    top_n: int|null          # Limit rows (null = no limit).
```

## 6. Input/Output Contract

### 6.1 Input CSV

- Encoding: UTF-8 (with or without BOM)
- Must contain all columns specified in `config.columns` (spend_category, supplier, line_memo, line_of_service, cost_center, amount)
- Passthrough columns are optional — missing ones produce empty values
- No row limit — tested up to 600K rows

### 6.2 Output Excel

Fixed sheets (always present):
- **All Results**: input passthrough columns + Supplier, Line Memo, Spend Category (Source), SC Code, Cost Center, Line of Service + CategoryLevel1-5, TaxonomyKey, ClassificationMethod, Confidence, ReviewTier
- **Summary**: metric/value pairs

Conditional sheets (present if data exists):
- **Manual Review**: filtered All Results where ReviewTier = "Manual Review"
- **Quick Review**: filtered All Results where ReviewTier = "Quick Review"
- **Unmapped SC Codes**: SC codes not found in mapping

Fixed analysis sheets:
- **Spend by Category L1**: L1 groupby with count, spend, unique suppliers, avg confidence
- **Spend by Category L2**: L1+L2 groupby with count, spend, unique suppliers

Dynamic sheets (from config):
- One sheet per `aggregations` entry, grouped by specified column

## 7. Client Onboarding Workflow

To add a new client:

1. **Create client directory**: `clients/<client-name>/`
2. **Obtain input data**: Place CSV export in `clients/<client-name>/data/input/`
3. **Map spend categories**: Create `sc_code_mapping.yaml` from client's category codes
4. **Write config**: Create `config.yaml` with client-specific column names, SC code pattern, and paths
5. **Initial run**: `python src/categorize.py --config clients/<client-name>/config.yaml`
6. **Review Quick Review output**: Identify high-volume suppliers needing rules
7. **Write refinement rules**: Add supplier/context/cost center rules to `refinement_rules.yaml`
8. **Iterate**: Re-run until Quick Review < 1% of transactions
9. **Deliver**: Share timestamped Excel with client

Estimated onboarding time per client: 2-4 hours (excluding rule tuning iterations).

## 8. Success Criteria

| Metric | Target |
|--------|--------|
| CCHMC parity | Identical results to current pipeline (594,807 AA, 1,989 QR) |
| New client onboarding | Config + first run in < 1 hour (excluding rule writing) |
| Classification speed | < 15 seconds for 600K rows |
| Auto-Accept rate | > 95% after initial SC mapping (before refinement rules) |
| Auto-Accept rate | > 99% after full rule tuning |
| Zero code changes | Adding a new client requires only config + reference YAML files |

## 9. Future Considerations (Out of Scope for v1)

- Web-based UI for rule management
- Automated supplier enrichment via web APIs
- Multi-taxonomy support (beyond Healthcare Taxonomy v2.9)
- Incremental/delta processing (only new transactions)
- Database backend instead of CSV/Excel
- pip-installable package with `categorize` entry point
