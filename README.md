# Spend Categorization CLI

Config-driven transaction categorization engine for healthcare procurement data. Classifies AP/Procurement transactions against Healthcare Taxonomy v2.9 using a 7-tier classification waterfall.

Built for repeatable consulting engagements — each client requires only a YAML config file and reference data, no code changes.

## Quickstart

```bash
# Install dependencies
pip install -r requirements.txt

# Run with a client config
python src/categorize.py --config clients/cchmc/config.yaml

# Override input file
python src/categorize.py --config clients/cchmc/config.yaml --input path/to/data.csv

# Override output directory
python src/categorize.py --config clients/cchmc/config.yaml --output-dir /tmp/results
```

## How It Works

The engine runs a 7-tier classification waterfall. Each row is classified by exactly one tier (first match wins), except Tier 7 which can override.

| Tier | Method | Description |
|------|--------|-------------|
| 1 | SC Code Mapping | Deterministic lookup for non-ambiguous spend category codes |
| 2 | Supplier Refinement | Ambiguous SC code + supplier regex pattern |
| 3 | Keyword Rules | Regex on combined supplier + line memo text |
| 4 | Context Refinement | Ambiguous SC code + line-of-service regex |
| 5 | Cost Center Refinement | Ambiguous SC code + cost center regex |
| 6 | Ambiguous Fallback | Remaining ambiguous SC codes at low confidence |
| 7 | Supplier Override | Post-classification correction for known mismatches |

After classification, each row is assigned a review tier:

| Review Tier | Criteria |
|-------------|----------|
| **Auto-Accept** | High confidence — no human review needed |
| **Quick Review** | Medium confidence — brief manual check |
| **Manual Review** | Low confidence — requires investigation |

## Output

Timestamped Excel file (`{prefix}_{YYYYMMDD_HHMMSS}.xlsx`) with these sheets:

| Sheet | Contents |
|-------|----------|
| All Results | Every row with classification columns appended |
| Manual Review | Filtered rows needing manual review |
| Quick Review | Filtered rows needing quick review |
| Summary | Transaction counts, method breakdown, financials |
| Spend by Category L1 | Grouped by top-level taxonomy category |
| Spend by Category L2 | Grouped by L1 + L2 categories |
| Dynamic aggregations | Configured per client (e.g., by Cost Center, Fund) |
| Unmapped SC Codes | SC codes not found in mapping (if any) |

## Project Structure

```
categorization-cli/
├── src/
│   └── categorize.py              # Classification engine + CLI
├── clients/
│   └── cchmc/                     # Example client
│       ├── config.yaml            # Client configuration
│       ├── data/
│       │   ├── input/             # Input CSV files
│       │   └── reference/         # SC mapping, rules, refinement YAMLs
│       └── output/                # Generated Excel results
├── shared/
│   └── reference/
│       └── Healthcare Taxonomy v2.9.xlsx
├── tests/
│   ├── conftest.py                # Pytest fixtures (config-driven)
│   └── test_rules.py             # 33 regression tests
├── docs/
│   ├── PRD.md                     # Product requirements
│   └── User_Guide.md             # Detailed usage guide
├── requirements.txt
├── .gitignore
├── CLAUDE.md
└── README.md
```

## Adding a New Client

1. Create `clients/<name>/config.yaml` (copy from `clients/cchmc/config.yaml`)
2. Place input CSV in `clients/<name>/data/input/`
3. Create client-specific reference files:
   - `sc_code_mapping.yaml` — spend category code to taxonomy mappings
   - `refinement_rules.yaml` — supplier, context, cost center, and override rules
   - `keyword_rules.yaml` — keyword regex patterns (can reuse from another client)
4. Update config paths and column mappings for the client's ERP schema
5. Run: `python src/categorize.py --config clients/<name>/config.yaml`
6. Iterate: review Quick Review output, add refinement rules, re-run

## Running Tests

```bash
# Test default client (CCHMC)
python -m pytest tests/ -v

# Test a specific client
python -m pytest tests/ -v --client-dir clients/other-client
```

## Performance

Benchmarked on CCHMC dataset (596,796 rows, $3.51B spend):

| Metric | Value |
|--------|-------|
| Classification time | ~10 seconds |
| Total runtime (incl. Excel I/O) | ~3 minutes |
| Auto-Accept rate | 99.7% |
| Quick Review rate | 0.3% |

## Dependencies

- Python 3.9+
- pandas, pyyaml, openpyxl (runtime)
- pytest (testing)

No network access required — fully offline operation.

## License

Proprietary — VTX Solutions / Defoxx Analytics
