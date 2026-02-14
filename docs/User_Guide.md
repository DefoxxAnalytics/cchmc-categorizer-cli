# User Guide

## Prerequisites

- Python 3.9+
- `pip install -r requirements.txt`

## Running the CLI

### Basic Usage

```bash
python src/categorize.py --config clients/cchmc/config.yaml
```

### CLI Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--config` | Yes | Path to client config YAML |
| `--input` | No | Override input CSV path from config |
| `--output-dir` | No | Override output directory from config |

### Examples

```bash
# Standard run
python src/categorize.py --config clients/cchmc/config.yaml

# Process a different input file
python src/categorize.py --config clients/cchmc/config.yaml --input data/new-export.csv

# Send output to a specific directory
python src/categorize.py --config clients/cchmc/config.yaml --output-dir C:/deliverables/cchmc
```

### Console Output

```
======================================================================
CCHMC TRANSACTION CATEGORIZATION
======================================================================

Loading resources...
  SC code mappings: 326
  Taxonomy categories: 441
  Keyword rules: 220
  Supplier refinement rules: 237
  Context refinement rules: 8
  Cost center rules: 10
  Supplier override rules: 11
  Ambiguous SC codes: 24

Loading CCHMC dataset...
  Loaded 596,796 rows, 46 columns

Classifying transactions (vectorized)...
  Tier 1 (SC code mapping): 541,637 rows
  Tier 2 (supplier refinement): 35,657 rows
  Tier 3 (keyword rules): 6,428 rows
  Tier 4 (context refinement): 10,519 rows
  Tier 5 (cost center refinement): 498 rows
  Tier 6 (ambiguous fallback): 2,057 rows
  Tier 7 (supplier override): 1,254 rows
  Classification completed in 10.4s

Building output Excel (596,796 rows)...

======================================================================
CLASSIFICATION COMPLETE
======================================================================
Total transactions:   596,796

Classification Methods:
  sc_code_mapping                 540,491 (90.6%)
  supplier_refinement              35,657 (6.0%)
  rule                              6,390 (1.1%)
  context_refinement               10,519 (1.8%)
  cost_center_refinement              496 (0.1%)
  sc_code_mapping_ambiguous         1,989 (0.3%)
  supplier_override                 1,254 (0.2%)

Review Tiers:
  Auto-Accept                     594,807 (99.7%)
  Quick Review                      1,989 (0.3%)
  Manual Review                         0 (0.0%)

Timing: classification 10.4s, total 166.0s
Output saved to: clients/cchmc/output/cchmc_categorization_results_20260213_213012.xlsx
```

## Config Reference

### Full Config Schema

```yaml
# --- Required ---

client:
  name: "Client Name"                    # Used in console banners
  description: "Optional description"    # Documentation only

paths:
  input: "data/input/transactions.csv"   # Input CSV (relative to config dir)
  sc_mapping: "data/reference/sc_code_mapping.yaml"
  taxonomy: "../../shared/reference/Healthcare Taxonomy v2.9.xlsx"
  keyword_rules: "data/reference/keyword_rules.yaml"
  refinement_rules: "data/reference/refinement_rules.yaml"
  output_dir: "output"                   # Output directory
  output_prefix: "client_results"        # Filename prefix (timestamp appended)

columns:
  spend_category: "Spend Category"       # Column with spend category codes
  supplier: "Supplier"                   # Column with supplier/vendor names
  line_memo: "Line Memo"                 # Column with line item descriptions
  line_of_service: "Line of Service"     # Column for context refinement
  cost_center: "Cost Center"             # Column for cost center refinement
  amount: "Invoice Line Amount"          # Column with monetary amounts
  passthrough:                           # Additional columns to carry to output
    - "Invoice Number"
    - "Invoice Date"
    - "Payment Status"

classification:
  sc_code_pattern: '((?:DNU\s+)?SC\d+)' # Regex to extract SC code from spend category
  confidence_high: 0.7                   # Threshold for Auto-Accept
  confidence_medium: 0.5                 # Threshold for Quick Review

# --- Optional ---

aggregations:                            # Additional groupby sheets in output
  - name: "Spend by Cost Center (Top 100)"
    column: "Cost Center"
    top_n: 100                           # null = no limit
  - name: "Spend by Department"
    column: "Department"
    top_n: null
```

### Path Resolution

All paths in the config are resolved relative to the config file's parent directory. For example, if your config is at `clients/cchmc/config.yaml`:

```yaml
paths:
  input: "data/input/file.csv"           # → clients/cchmc/data/input/file.csv
  taxonomy: "../../shared/reference/x.xlsx"  # → shared/reference/x.xlsx
```

CLI overrides (`--input`, `--output-dir`) can be absolute or relative to your current working directory.

### Column Mapping

The `columns` section maps your ERP's field names to the engine's internal names. Different ERPs use different column names:

| Engine Field | Workday Example | Oracle Example | SAP Example |
|-------------|-----------------|----------------|-------------|
| spend_category | Spend Category | Category Code | Material Group |
| supplier | Supplier | Vendor Name | Supplier Name |
| line_memo | Line Memo | Item Description | Short Text |
| line_of_service | Line of Service | Service Line | Business Area |
| cost_center | Cost Center | Department | Cost Center |
| amount | Invoice Line Amount | Line Amount | Net Value |

### SC Code Pattern

The `sc_code_pattern` regex extracts the spend category code from the spend category column. The pattern must have one capture group.

Examples:
- CCHMC (Workday): `'((?:DNU\s+)?SC\d+)'` — matches "SC0250", "DNU SC0175"
- Simple numeric: `'(\d{4,})'` — matches "1234", "56789"
- Prefixed: `'(CAT-\d+)'` — matches "CAT-001", "CAT-123"

### Confidence Thresholds

| Threshold | Review Tier | Meaning |
|-----------|-------------|---------|
| >= `confidence_high` | Auto-Accept | No human review needed |
| >= `confidence_medium` | Quick Review | Brief manual check |
| < `confidence_medium` | Manual Review | Full investigation needed |

Special case: `sc_code_mapping` and `rule` methods with confidence >= 0.9 are always Auto-Accept regardless of the high threshold.

## Reference Data Files

### SC Code Mapping (`sc_code_mapping.yaml`)

Maps spend category codes to taxonomy keys:

```yaml
mappings:
  SC0001:
    name: "Office Supplies"
    taxonomy_key: "Facilities > Office Supplies"
    confidence: 0.95
    ambiguous: false
  SC0250:
    name: "Professional Services"
    taxonomy_key: "Professional Services"
    confidence: 0.45
    ambiguous: true     # Routes to Tier 2-6 for refinement
```

- **ambiguous: false** — classified in Tier 1 (direct mapping, high confidence)
- **ambiguous: true** — skipped in Tier 1, refined by Tiers 2-6

### Refinement Rules (`refinement_rules.yaml`)

Four rule types in one file:

```yaml
# Tier 2: SC code + supplier pattern → taxonomy
supplier_rules:
  - sc_codes: [SC0250, SC0341]
    supplier_pattern: "epic systems"
    taxonomy_key: "IT & Telecoms > Software > Application Software"
    confidence: 0.88

# Tier 4: SC code + line-of-service pattern → taxonomy
context_rules:
  - sc_codes: [SC0250]
    line_of_service_pattern: "cardiology|cardiac"
    taxonomy_key: "Medical > Medical Services"
    confidence: 0.78

# Tier 5: SC code + cost center pattern → taxonomy
cost_center_rules:
  - sc_codes: [SC0004, SC0389]
    cost_center_pattern: "design.*construction|facilities.*mgmt"
    taxonomy_key: "Facilities > Furniture"
    confidence: 0.75

# Tier 7: Post-classification override
supplier_override_rules:
  - supplier_pattern: "stryker|zimmer"
    override_from_l1: ["Professional Services", "Facilities"]
    taxonomy_key: "Medical > Medical Devices & Equipment"
    confidence: 0.90
```

### Keyword Rules (`keyword_rules.yaml`)

Regex patterns matched against combined `supplier + line_memo` text:

```yaml
rules:
  - pattern: "microsoft|azure|office\\s*365"
    category: "IT & Telecoms > Software > Application Software"
    confidence: 0.95
  - pattern: "fedex|ups|freight"
    category: "Logistics > Freight & Shipping"
    confidence: 0.90
```

### Taxonomy (`Healthcare Taxonomy v2.9.xlsx`)

Universal reference file with columns: `Key`, `CategoryLevel1`, `CategoryLevel2`, `CategoryLevel3`, `CategoryLevel4`, `CategoryLevel5`.

Shared across all clients in `shared/reference/`.

## Output Excel Sheets

### All Results

Every input row with these columns appended:

| Column | Description |
|--------|-------------|
| Spend Category (Source) | Original spend category text |
| SC Code | Extracted spend category code |
| CategoryLevel1-5 | Resolved taxonomy hierarchy |
| TaxonomyKey | Full taxonomy path |
| ClassificationMethod | Which tier classified this row |
| Confidence | 0.0 - 1.0 confidence score |
| ReviewTier | Auto-Accept, Quick Review, or Manual Review |

Plus all passthrough columns from config.

### Summary

| Metric | Example Value |
|--------|---------------|
| Total Transactions | 596,796 |
| Unique Suppliers | 12,847 |
| SC Code Mapping (direct) | 540,491 (90.6%) |
| Supplier Refinement | 35,657 (6.0%) |
| Auto-Accept | 594,807 (99.7%) |
| Quick Review | 1,989 (0.3%) |
| Total Invoice Line Amount | $3,510,234,567.89 |

### Dynamic Aggregation Sheets

Configured via `config.aggregations`. Each entry produces a sheet grouped by the specified column with TransactionCount and TotalSpend, sorted by spend descending.

## Client Onboarding Workflow

### Step 1: Set Up Client Directory

```bash
mkdir -p clients/newclient/data/{input,reference}
mkdir -p clients/newclient/output
cp clients/cchmc/config.yaml clients/newclient/config.yaml
```

### Step 2: Obtain Input Data

Get the client's AP/Procurement CSV export from their ERP (Workday, Oracle, SAP, etc.) and place it in `clients/newclient/data/input/`.

### Step 3: Map Spend Categories

Create `clients/newclient/data/reference/sc_code_mapping.yaml`:

1. Extract unique spend category codes from the CSV
2. For each code, determine the taxonomy key from Healthcare Taxonomy v2.9
3. Flag ambiguous codes (those covering multiple domains)
4. Set confidence levels (0.85-0.95 for direct, 0.40-0.50 for ambiguous)

### Step 4: Configure

Edit `clients/newclient/config.yaml`:

1. Update `client.name` and `client.description`
2. Set all `paths` to point to client files
3. Map `columns` to the client's ERP field names
4. Set `classification.sc_code_pattern` for the client's code format
5. Add relevant `aggregations` for the client's dimensions

### Step 5: First Run

```bash
python src/categorize.py --config clients/newclient/config.yaml
```

Check the Quick Review sheet — these are transactions the engine couldn't confidently classify.

### Step 6: Write Rules

Review Quick Review output and add refinement rules:

1. Identify high-volume suppliers in Quick Review
2. Research each supplier's business domain
3. Add supplier rules to `refinement_rules.yaml`
4. Re-run and check impact
5. Repeat until Quick Review < 1%

### Step 7: Validate

```bash
python -m pytest tests/ -v --client-dir clients/newclient
```

### Step 8: Deliver

Share the timestamped Excel file with the client stakeholder. The Summary sheet provides the executive overview.

## Troubleshooting

### "ERROR: Config file not found"
Check the `--config` path. It can be absolute or relative to your current working directory.

### "ERROR: File not found" for a reference file
Config paths are relative to the config file's directory, not your CWD. Check the `paths` section.

### "WARNING: N SC mappings point to invalid taxonomy keys"
Some SC code mappings reference taxonomy keys that don't exist in the taxonomy Excel. The rows will still be classified, but CategoryLevel1-5 columns will be empty. Fix the keys in `sc_code_mapping.yaml`.

### High Quick Review count on first run
Expected — you haven't written refinement rules yet. See "Step 6: Write Rules" above.

### "Column not found" errors
The column names in `config.columns` don't match the input CSV headers. Check exact spelling, capitalization, and whitespace.
