"""
Spend Categorization CLI

Config-driven transaction categorization engine for healthcare procurement data.
Classifies transactions against Healthcare Taxonomy v2.9 using a 7-tier waterfall.

Usage:
    python src/categorize.py --config clients/cchmc/config.yaml
    python src/categorize.py --config clients/cchmc/config.yaml --input override.csv
    python src/categorize.py --config clients/cchmc/config.yaml --output-dir /tmp
"""

import sys
import re
import time
import argparse
import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')


class ConfigError(Exception):
    pass


def load_config(config_path: str, input_override: str = None, output_dir_override: str = None) -> dict:
    config_path = Path(config_path).resolve()
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    base_dir = config_path.parent

    required_sections = ['client', 'paths', 'columns', 'classification']
    for section in required_sections:
        if section not in config:
            raise ConfigError(f"Missing required config section: '{section}'")

    required_paths = ['input', 'sc_mapping', 'taxonomy', 'keyword_rules', 'refinement_rules', 'output_dir', 'output_prefix']
    for key in required_paths:
        if key not in config['paths']:
            raise ConfigError(f"Missing required path: 'paths.{key}'")

    required_columns = ['spend_category', 'supplier', 'line_memo', 'line_of_service', 'cost_center', 'amount']
    for key in required_columns:
        if key not in config['columns']:
            raise ConfigError(f"Missing required column mapping: 'columns.{key}'")

    required_class = ['sc_code_pattern', 'confidence_high', 'confidence_medium']
    for key in required_class:
        if key not in config['classification']:
            raise ConfigError(f"Missing required classification param: 'classification.{key}'")

    resolved = {}
    for key in ['input', 'sc_mapping', 'taxonomy', 'keyword_rules', 'refinement_rules']:
        resolved[key] = (base_dir / config['paths'][key]).resolve()
    resolved['output_dir'] = (base_dir / config['paths']['output_dir']).resolve()
    resolved['output_prefix'] = config['paths']['output_prefix']

    if input_override:
        resolved['input'] = Path(input_override).resolve()
    if output_dir_override:
        resolved['output_dir'] = Path(output_dir_override).resolve()

    config['_resolved_paths'] = resolved

    for key in ['input', 'sc_mapping', 'taxonomy', 'keyword_rules', 'refinement_rules']:
        if not resolved[key].exists():
            raise ConfigError(f"File not found: {resolved[key]} (from paths.{key})")

    return config


def load_sc_mapping(path: Path) -> dict[str, dict]:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    mapping = {}
    for sc_code, info in data.get('mappings', {}).items():
        sc_code_str = str(sc_code).strip()
        mapping[sc_code_str] = {
            'name': info['name'],
            'taxonomy_key': info['taxonomy_key'],
            'confidence': info.get('confidence', 0.85),
            'ambiguous': info.get('ambiguous', False),
        }
    return mapping


def load_taxonomy(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    df = df.fillna('')
    return df


def build_taxonomy_lookup(taxonomy_df: pd.DataFrame) -> dict[str, dict]:
    lookup = {}
    for _, row in taxonomy_df.iterrows():
        key = row['Key']
        lookup[key] = {
            'CategoryLevel1': row['CategoryLevel1'],
            'CategoryLevel2': row['CategoryLevel2'],
            'CategoryLevel3': row['CategoryLevel3'],
            'CategoryLevel4': row.get('CategoryLevel4', ''),
            'CategoryLevel5': row.get('CategoryLevel5', ''),
        }
    return lookup


def load_keyword_rules(path: Path) -> list[dict]:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    rules = data.get('rules', [])
    for i, rule in enumerate(rules):
        for key in ('pattern', 'category'):
            if key not in rule:
                raise ConfigError(f"keyword_rules[{i}] missing required key '{key}'")
        try:
            rule['_compiled'] = re.compile(rule['pattern'], re.IGNORECASE)
        except re.error as e:
            raise ConfigError(f"keyword_rules[{i}] invalid regex '{rule['pattern']}': {e}")
    return rules


def _validate_and_compile_rules(rules, section_name, required_keys, pattern_key):
    for i, rule in enumerate(rules):
        for key in required_keys:
            if key not in rule:
                raise ConfigError(f"{section_name}[{i}] missing required key '{key}'")
        try:
            rule['_compiled'] = re.compile(rule[pattern_key], re.IGNORECASE)
        except re.error as e:
            raise ConfigError(f"{section_name}[{i}] invalid regex '{rule[pattern_key]}': {e}")


def load_refinement_rules(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    supplier_rules = data.get('supplier_rules', [])
    _validate_and_compile_rules(
        supplier_rules, 'supplier_rules',
        ('sc_codes', 'supplier_pattern', 'taxonomy_key', 'confidence'),
        'supplier_pattern',
    )

    context_rules = data.get('context_rules', [])
    _validate_and_compile_rules(
        context_rules, 'context_rules',
        ('sc_codes', 'line_of_service_pattern', 'taxonomy_key', 'confidence'),
        'line_of_service_pattern',
    )

    cost_center_rules = data.get('cost_center_rules', [])
    _validate_and_compile_rules(
        cost_center_rules, 'cost_center_rules',
        ('sc_codes', 'cost_center_pattern', 'taxonomy_key', 'confidence'),
        'cost_center_pattern',
    )

    override_rules = data.get('supplier_override_rules', [])
    _validate_and_compile_rules(
        override_rules, 'supplier_override_rules',
        ('supplier_pattern', 'override_from_l1', 'taxonomy_key', 'confidence'),
        'supplier_pattern',
    )

    return {
        'supplier_rules': supplier_rules,
        'context_rules': context_rules,
        'cost_center_rules': cost_center_rules,
        'supplier_override_rules': override_rules,
    }


def main(config: dict):
    paths = config['_resolved_paths']
    cols = config['columns']
    classif = config['classification']
    client_name = config['client']['name']

    paths['output_dir'].mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_xlsx = paths['output_dir'] / f"{paths['output_prefix']}_{timestamp}.xlsx"

    t_start = time.perf_counter()

    print("=" * 70)
    print(f"{client_name} TRANSACTION CATEGORIZATION")
    print("=" * 70)

    print("\nLoading resources...")
    sc_mapping = load_sc_mapping(paths['sc_mapping'])
    print(f"  SC code mappings: {len(sc_mapping)}")

    taxonomy_df = load_taxonomy(paths['taxonomy'])
    taxonomy_keys_set = set(taxonomy_df['Key'].tolist())
    taxonomy_lookup = build_taxonomy_lookup(taxonomy_df)
    print(f"  Taxonomy categories: {len(taxonomy_keys_set)}")

    rules = load_keyword_rules(paths['keyword_rules'])
    print(f"  Keyword rules: {len(rules)}")

    refinement = load_refinement_rules(paths['refinement_rules'])
    print(f"  Supplier refinement rules: {len(refinement['supplier_rules'])}")
    print(f"  Context refinement rules: {len(refinement['context_rules'])}")
    print(f"  Cost center rules: {len(refinement['cost_center_rules'])}")
    print(f"  Supplier override rules: {len(refinement['supplier_override_rules'])}")
    ambiguous_codes = {sc for sc, info in sc_mapping.items() if info.get('ambiguous')}
    print(f"  Ambiguous SC codes: {len(ambiguous_codes)}")

    invalid_mappings = []
    for sc_code, info in sc_mapping.items():
        if info['taxonomy_key'] not in taxonomy_keys_set:
            invalid_mappings.append((sc_code, info['taxonomy_key']))
    if invalid_mappings:
        print(f"\n  WARNING: {len(invalid_mappings)} SC mappings point to invalid taxonomy keys:")
        for sc, key in invalid_mappings[:10]:
            print(f"    {sc} -> {key}")
        print("  These will still be used but won't resolve to L1-L5 breakdown.")

    print(f"\nLoading {client_name} dataset...")
    df = pd.read_csv(paths['input'], low_memory=False)
    total_rows = len(df)
    print(f"  Loaded {total_rows:,} rows, {len(df.columns)} columns")

    if total_rows == 0:
        raise ConfigError(f"Input CSV has 0 data rows: {paths['input']}")

    required_csv_cols = {
        'spend_category': cols['spend_category'],
        'supplier': cols['supplier'],
        'line_memo': cols['line_memo'],
        'line_of_service': cols['line_of_service'],
        'cost_center': cols['cost_center'],
        'amount': cols['amount'],
    }
    missing_csv_cols = [
        f"'{v}' (from columns.{k})"
        for k, v in required_csv_cols.items()
        if v not in df.columns
    ]
    if missing_csv_cols:
        raise ConfigError(f"Columns not found in input CSV: {', '.join(missing_csv_cols)}")

    # ── Vectorized classification ───────────────────────────────────────
    print("\nClassifying transactions (vectorized)...")
    t_classify = time.perf_counter()

    sc_pattern = classif['sc_code_pattern']
    conf_high = classif['confidence_high']
    conf_medium = classif['confidence_medium']

    spend_cat_str = df[cols['spend_category']].astype(str).str.strip()
    sc_extracted = spend_cat_str.str.extract(f'({sc_pattern})', expand=False)
    if isinstance(sc_extracted, pd.DataFrame):
        sc_extracted = sc_extracted.iloc[:, 0]
    sc_code = sc_extracted.fillna(spend_cat_str)

    supplier = df[cols['supplier']].fillna('').astype(str)
    line_memo = df[cols['line_memo']].fillna('').astype(str)
    line_of_service = df[cols['line_of_service']].fillna('').astype(str)
    cost_center = df[cols['cost_center']].fillna('').astype(str)
    combined_text = supplier + ' ' + line_memo

    taxonomy_key = pd.Series('', index=df.index, dtype='object')
    method = pd.Series('', index=df.index, dtype='object')
    confidence = pd.Series(0.0, index=df.index, dtype='float64')

    # Tier 1: Non-ambiguous SC code mapping
    non_amb_taxonomy = {sc: info['taxonomy_key'] for sc, info in sc_mapping.items() if not info.get('ambiguous')}
    non_amb_confidence = {sc: info['confidence'] for sc, info in sc_mapping.items() if not info.get('ambiguous')}
    tier1_mask = sc_code.isin(non_amb_taxonomy)
    taxonomy_key[tier1_mask] = sc_code[tier1_mask].map(non_amb_taxonomy)
    method[tier1_mask] = 'sc_code_mapping'
    confidence[tier1_mask] = sc_code[tier1_mask].map(non_amb_confidence)
    print(f"  Tier 1 (SC code mapping): {tier1_mask.sum():,} rows")

    unclassified = (method == '').copy()

    # Tier 2: Supplier refinement
    tier2_count = 0
    for rule in refinement['supplier_rules']:
        if not unclassified.any():
            break
        sc_match = sc_code.isin(rule['sc_codes'])
        candidate = unclassified & sc_match
        if not candidate.any():
            continue
        cand_idx = candidate[candidate].index
        supplier_match = supplier.loc[cand_idx].str.contains(
            rule['supplier_pattern'], case=False, na=False, regex=True
        )
        hit_idx = cand_idx[supplier_match.values]
        if len(hit_idx) > 0:
            taxonomy_key[hit_idx] = rule['taxonomy_key']
            method[hit_idx] = 'supplier_refinement'
            confidence[hit_idx] = rule['confidence']
            tier2_count += len(hit_idx)
            unclassified[hit_idx] = False
    print(f"  Tier 2 (supplier refinement): {tier2_count:,} rows")

    # Tier 3: Keyword rules
    tier3_count = 0
    for rule in rules:
        if not unclassified.any():
            break
        uncl_idx = unclassified[unclassified].index
        kw_match = combined_text.loc[uncl_idx].str.contains(
            rule['pattern'], case=False, na=False, regex=True
        )
        hit_idx = uncl_idx[kw_match.values]
        if len(hit_idx) > 0:
            taxonomy_key[hit_idx] = rule['category']
            method[hit_idx] = 'rule'
            confidence[hit_idx] = rule.get('confidence', 0.95)
            tier3_count += len(hit_idx)
            unclassified[hit_idx] = False
    print(f"  Tier 3 (keyword rules): {tier3_count:,} rows")

    # Tier 4: Context refinement (Line of Service)
    tier4_count = 0
    for rule in refinement['context_rules']:
        if not unclassified.any():
            break
        sc_match = sc_code.isin(rule['sc_codes'])
        candidate = unclassified & sc_match
        if not candidate.any():
            continue
        cand_idx = candidate[candidate].index
        los_match = line_of_service.loc[cand_idx].str.contains(
            rule['line_of_service_pattern'], case=False, na=False, regex=True
        )
        hit_idx = cand_idx[los_match.values]
        if len(hit_idx) > 0:
            taxonomy_key[hit_idx] = rule['taxonomy_key']
            method[hit_idx] = 'context_refinement'
            confidence[hit_idx] = rule['confidence']
            tier4_count += len(hit_idx)
            unclassified[hit_idx] = False
    print(f"  Tier 4 (context refinement): {tier4_count:,} rows")

    # Tier 5: Cost center refinement
    tier5_count = 0
    for rule in refinement['cost_center_rules']:
        if not unclassified.any():
            break
        sc_match = sc_code.isin(rule['sc_codes'])
        candidate = unclassified & sc_match
        if not candidate.any():
            continue
        cand_idx = candidate[candidate].index
        cc_match = cost_center.loc[cand_idx].str.contains(
            rule['cost_center_pattern'], case=False, na=False, regex=True
        )
        hit_idx = cand_idx[cc_match.values]
        if len(hit_idx) > 0:
            taxonomy_key[hit_idx] = rule['taxonomy_key']
            method[hit_idx] = 'cost_center_refinement'
            confidence[hit_idx] = rule['confidence']
            tier5_count += len(hit_idx)
            unclassified[hit_idx] = False
    print(f"  Tier 5 (cost center refinement): {tier5_count:,} rows")

    # Tier 6: Ambiguous SC fallback
    amb_taxonomy = {sc: info['taxonomy_key'] for sc, info in sc_mapping.items() if info.get('ambiguous')}
    amb_confidence = {sc: info['confidence'] for sc, info in sc_mapping.items() if info.get('ambiguous')}
    tier6_mask = unclassified & sc_code.isin(amb_taxonomy)
    taxonomy_key[tier6_mask] = sc_code[tier6_mask].map(amb_taxonomy)
    method[tier6_mask] = 'sc_code_mapping_ambiguous'
    confidence[tier6_mask] = sc_code[tier6_mask].map(amb_confidence)
    print(f"  Tier 6 (ambiguous fallback): {tier6_mask.sum():,} rows")

    # Unmapped
    still_unclassified = method == ''
    if still_unclassified.any():
        taxonomy_key[still_unclassified] = 'Unclassified'
        method[still_unclassified] = 'unmapped'
        confidence[still_unclassified] = 0.0
        print(f"  Unmapped: {still_unclassified.sum():,} rows")

    # Taxonomy level lookup
    tax_l1 = pd.Series({k: v['CategoryLevel1'] for k, v in taxonomy_lookup.items()})
    tax_l2 = pd.Series({k: v['CategoryLevel2'] for k, v in taxonomy_lookup.items()})
    tax_l3 = pd.Series({k: v['CategoryLevel3'] for k, v in taxonomy_lookup.items()})
    tax_l4 = pd.Series({k: v['CategoryLevel4'] for k, v in taxonomy_lookup.items()})
    tax_l5 = pd.Series({k: v['CategoryLevel5'] for k, v in taxonomy_lookup.items()})

    cat_l1 = taxonomy_key.map(tax_l1).fillna('')
    cat_l2 = taxonomy_key.map(tax_l2).fillna('')
    cat_l3 = taxonomy_key.map(tax_l3).fillna('')
    cat_l4 = taxonomy_key.map(tax_l4).fillna('')
    cat_l5 = taxonomy_key.map(tax_l5).fillna('')

    # Tier 7: Supplier override (post-classification)
    tier7_count = 0
    for rule in refinement['supplier_override_rules']:
        supplier_hit = supplier.str.contains(
            rule['supplier_pattern'], case=False, na=False, regex=True
        )
        l1_hit = cat_l1.isin(rule['override_from_l1'])
        hit = supplier_hit & l1_hit
        if hit.any():
            cat_info = taxonomy_lookup.get(rule['taxonomy_key'], {})
            taxonomy_key[hit] = rule['taxonomy_key']
            method[hit] = 'supplier_override'
            confidence[hit] = rule['confidence']
            cat_l1[hit] = cat_info.get('CategoryLevel1', '')
            cat_l2[hit] = cat_info.get('CategoryLevel2', '')
            cat_l3[hit] = cat_info.get('CategoryLevel3', '')
            cat_l4[hit] = cat_info.get('CategoryLevel4', '')
            cat_l5[hit] = cat_info.get('CategoryLevel5', '')
            tier7_count += hit.sum()
    print(f"  Tier 7 (supplier override): {tier7_count:,} rows")

    # Review tier assignment (vectorized)
    high_conf_methods = method.isin(['sc_code_mapping', 'rule'])
    review_tier = np.where(
        (high_conf_methods & (confidence >= 0.9)) | (confidence >= conf_high),
        'Auto-Accept',
        np.where(confidence >= conf_medium, 'Quick Review', 'Manual Review')
    )

    t_classify_end = time.perf_counter()
    print(f"  Classification completed in {t_classify_end - t_classify:.1f}s")

    # ── Build output DataFrame ──────────────────────────────────────────
    print(f"\nBuilding output Excel ({total_rows:,} rows)...")

    amount_col = cols['amount']

    output_columns = {
        cols['supplier']: supplier,
    }
    for col_name in cols.get('passthrough', []):
        if col_name not in output_columns:
            output_columns[col_name] = df.get(col_name, pd.Series('', index=df.index))

    output_columns[cols['line_memo']] = line_memo
    output_columns['Spend Category (Source)'] = spend_cat_str
    output_columns['SC Code'] = sc_code
    output_columns[cols['cost_center']] = df.get(cols['cost_center'], pd.Series('', index=df.index))
    output_columns[cols['line_of_service']] = df.get(cols['line_of_service'], pd.Series('', index=df.index))

    if amount_col not in output_columns:
        output_columns[amount_col] = df[amount_col]

    output_columns['CategoryLevel1'] = cat_l1
    output_columns['CategoryLevel2'] = cat_l2
    output_columns['CategoryLevel3'] = cat_l3
    output_columns['CategoryLevel4'] = cat_l4
    output_columns['CategoryLevel5'] = cat_l5
    output_columns['TaxonomyKey'] = taxonomy_key
    output_columns['ClassificationMethod'] = method
    output_columns['Confidence'] = confidence.round(3)
    output_columns['ReviewTier'] = review_tier

    results_df = pd.DataFrame(output_columns)

    method_counts = results_df['ClassificationMethod'].value_counts().to_dict()
    tier_counts = results_df['ReviewTier'].value_counts().to_dict()
    unmapped_sc = Counter()
    if method_counts.get('unmapped', 0) > 0:
        unmapped_rows = results_df[results_df['ClassificationMethod'] == 'unmapped']
        unmapped_sc = Counter(unmapped_rows['Spend Category (Source)'].tolist())

    with pd.ExcelWriter(output_xlsx, engine='openpyxl') as writer:
        results_df.to_excel(writer, sheet_name='All Results', index=False)

        manual_df = results_df[results_df['ReviewTier'] == 'Manual Review']
        if not manual_df.empty:
            manual_df.to_excel(writer, sheet_name='Manual Review', index=False)

        quick_df = results_df[results_df['ReviewTier'] == 'Quick Review']
        if not quick_df.empty:
            quick_df.to_excel(writer, sheet_name='Quick Review', index=False)

        all_methods = [
            'sc_code_mapping', 'supplier_refinement', 'rule',
            'context_refinement', 'cost_center_refinement',
            'sc_code_mapping_ambiguous', 'supplier_override', 'unmapped',
        ]
        method_labels = {
            'sc_code_mapping': 'SC Code Mapping (direct)',
            'supplier_refinement': 'Supplier Refinement',
            'rule': 'Keyword Rules',
            'context_refinement': 'Context Refinement (LoS)',
            'cost_center_refinement': 'Cost Center Refinement',
            'sc_code_mapping_ambiguous': 'SC Code Mapping (ambiguous fallback)',
            'supplier_override': 'Supplier Override (post-classification)',
            'unmapped': 'Unmapped',
        }
        method_rows = []
        method_values = []
        for m in all_methods:
            c = method_counts.get(m, 0)
            if c > 0:
                method_rows.append(method_labels[m])
                method_values.append(f"{c:,} ({c/total_rows*100:.1f}%)")

        summary_data = {
            'Metric': [
                'Total Transactions',
                f'Unique {cols["supplier"]}s',
                'Unique SC Codes',
                '--- Classification Methods ---',
                *method_rows,
                '--- Review Tiers ---',
                'Auto-Accept',
                'Quick Review',
                'Manual Review',
                '--- Financial ---',
                f'Total {amount_col}',
                f'Average {amount_col}',
            ],
            'Value': [
                f"{total_rows:,}",
                f"{results_df[cols['supplier']].nunique():,}",
                f"{results_df['SC Code'].nunique():,}",
                '',
                *method_values,
                '',
                f"{tier_counts.get('Auto-Accept', 0):,} ({tier_counts.get('Auto-Accept', 0)/total_rows*100:.1f}%)",
                f"{tier_counts.get('Quick Review', 0):,} ({tier_counts.get('Quick Review', 0)/total_rows*100:.1f}%)",
                f"{tier_counts.get('Manual Review', 0):,} ({tier_counts.get('Manual Review', 0)/total_rows*100:.1f}%)",
                '',
                f"${results_df[amount_col].sum():,.2f}",
                f"${results_df[amount_col].mean():,.2f}",
            ]
        }
        pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)

        spend_l1 = results_df.groupby('CategoryLevel1').agg(
            TransactionCount=(cols['supplier'], 'count'),
            TotalSpend=(amount_col, 'sum'),
            UniqueSuppliers=(cols['supplier'], 'nunique'),
            AvgConfidence=('Confidence', 'mean'),
        ).sort_values('TotalSpend', ascending=False)
        spend_l1['AvgConfidence'] = spend_l1['AvgConfidence'].round(3)
        spend_l1.to_excel(writer, sheet_name='Spend by Category L1')

        spend_l2 = results_df.groupby(['CategoryLevel1', 'CategoryLevel2']).agg(
            TransactionCount=(cols['supplier'], 'count'),
            TotalSpend=(amount_col, 'sum'),
            UniqueSuppliers=(cols['supplier'], 'nunique'),
        ).sort_values('TotalSpend', ascending=False)
        spend_l2.to_excel(writer, sheet_name='Spend by Category L2')

        for agg in config.get('aggregations', []):
            agg_col = agg['column']
            if agg_col not in results_df.columns:
                print(f"  WARNING: Aggregation column '{agg_col}' not found, skipping sheet '{agg['name']}'")
                continue
            agg_df = results_df.groupby(agg_col).agg(
                TransactionCount=(cols['supplier'], 'count'),
                TotalSpend=(amount_col, 'sum'),
            ).sort_values('TotalSpend', ascending=False)
            if agg.get('top_n'):
                agg_df = agg_df.head(agg['top_n'])
            agg_df.to_excel(writer, sheet_name=agg['name'])

        if unmapped_sc:
            unmapped_data = [
                {'SC Code': sc, 'Count': count}
                for sc, count in unmapped_sc.most_common()
            ]
            pd.DataFrame(unmapped_data).to_excel(writer, sheet_name='Unmapped SC Codes', index=False)

    t_end = time.perf_counter()

    print(f"\n{'='*70}")
    print("CLASSIFICATION COMPLETE")
    print(f"{'='*70}")
    print(f"Total transactions:   {total_rows:,}")
    print(f"\nClassification Methods:")
    for m in all_methods:
        count = method_counts.get(m, 0)
        if count > 0:
            print(f"  {m:30s} {count:>8,} ({count/total_rows*100:.1f}%)")
    print(f"\nReview Tiers:")
    for tier in ['Auto-Accept', 'Quick Review', 'Manual Review']:
        count = tier_counts.get(tier, 0)
        print(f"  {tier:30s} {count:>8,} ({count/total_rows*100:.1f}%)")
    if unmapped_sc:
        print(f"\nUnmapped SC Codes: {len(unmapped_sc)} unique codes, {sum(unmapped_sc.values()):,} total rows")
        for sc, count in unmapped_sc.most_common(10):
            print(f"  {sc:40s} {count:>6,}")
    print(f"\nTiming: classification {t_classify_end - t_classify:.1f}s, total {t_end - t_start:.1f}s")
    print(f"Output saved to: {output_xlsx}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Spend Categorization CLI — classify procurement transactions against Healthcare Taxonomy'
    )
    parser.add_argument('--config', required=True, help='Path to client config YAML')
    parser.add_argument('--input', default=None, help='Override input CSV path from config')
    parser.add_argument('--output-dir', default=None, help='Override output directory from config')
    args = parser.parse_args()

    try:
        config = load_config(args.config, args.input, args.output_dir)
        main(config)
    except ConfigError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
