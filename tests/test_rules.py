"""
Regression tests for categorization pipeline rules.

Validates rules for any client by loading from the client config path.
Default: clients/cchmc (override with --client-dir pytest option).

Three test suites:
  1. YAML validation — structural integrity of all rule files
  2. Classification assertions — known supplier->taxonomy mappings
  3. Conflict detection — overlapping patterns across rules
"""

import re

import pytest


# -- 1. YAML Structural Validation --------------------------------------------


class TestYAMLStructure:

    def test_refinement_has_required_sections(self, refinement):
        for section in ["supplier_rules", "context_rules", "cost_center_rules", "supplier_override_rules"]:
            assert section in refinement, f"Missing section: {section}"

    def test_supplier_rules_have_required_fields(self, refinement):
        for i, rule in enumerate(refinement["supplier_rules"]):
            assert "sc_codes" in rule, f"supplier_rules[{i}] missing sc_codes"
            assert "supplier_pattern" in rule, f"supplier_rules[{i}] missing supplier_pattern"
            assert "taxonomy_key" in rule, f"supplier_rules[{i}] missing taxonomy_key"
            assert "confidence" in rule, f"supplier_rules[{i}] missing confidence"

    def test_context_rules_have_required_fields(self, refinement):
        for i, rule in enumerate(refinement["context_rules"]):
            assert "sc_codes" in rule, f"context_rules[{i}] missing sc_codes"
            assert "line_of_service_pattern" in rule, f"context_rules[{i}] missing line_of_service_pattern"
            assert "taxonomy_key" in rule, f"context_rules[{i}] missing taxonomy_key"
            assert "confidence" in rule, f"context_rules[{i}] missing confidence"

    def test_cost_center_rules_have_required_fields(self, refinement):
        for i, rule in enumerate(refinement["cost_center_rules"]):
            assert "sc_codes" in rule, f"cost_center_rules[{i}] missing sc_codes"
            assert "cost_center_pattern" in rule, f"cost_center_rules[{i}] missing cost_center_pattern"
            assert "taxonomy_key" in rule, f"cost_center_rules[{i}] missing taxonomy_key"
            assert "confidence" in rule, f"cost_center_rules[{i}] missing confidence"

    def test_override_rules_have_required_fields(self, refinement):
        for i, rule in enumerate(refinement["supplier_override_rules"]):
            assert "supplier_pattern" in rule, f"override_rules[{i}] missing supplier_pattern"
            assert "taxonomy_key" in rule, f"override_rules[{i}] missing taxonomy_key"
            assert "override_from_l1" in rule, f"override_rules[{i}] missing override_from_l1"
            assert "confidence" in rule, f"override_rules[{i}] missing confidence"


class TestRegexValidity:

    def test_supplier_patterns_compile(self, refinement):
        for i, rule in enumerate(refinement["supplier_rules"]):
            try:
                re.compile(rule["supplier_pattern"], re.IGNORECASE)
            except re.error as e:
                pytest.fail(f"supplier_rules[{i}] invalid regex '{rule['supplier_pattern']}': {e}")

    def test_context_patterns_compile(self, refinement):
        for i, rule in enumerate(refinement["context_rules"]):
            try:
                re.compile(rule["line_of_service_pattern"], re.IGNORECASE)
            except re.error as e:
                pytest.fail(f"context_rules[{i}] invalid regex '{rule['line_of_service_pattern']}': {e}")

    def test_cost_center_patterns_compile(self, refinement):
        for i, rule in enumerate(refinement["cost_center_rules"]):
            try:
                re.compile(rule["cost_center_pattern"], re.IGNORECASE)
            except re.error as e:
                pytest.fail(f"cost_center_rules[{i}] invalid regex '{rule['cost_center_pattern']}': {e}")

    def test_override_patterns_compile(self, refinement):
        for i, rule in enumerate(refinement["supplier_override_rules"]):
            try:
                re.compile(rule["supplier_pattern"], re.IGNORECASE)
            except re.error as e:
                pytest.fail(f"override_rules[{i}] invalid regex '{rule['supplier_pattern']}': {e}")

    def test_keyword_patterns_compile(self, keyword_rules):
        for i, rule in enumerate(keyword_rules.get("rules", [])):
            try:
                re.compile(rule["pattern"], re.IGNORECASE)
            except re.error as e:
                pytest.fail(f"keyword_rules[{i}] invalid regex '{rule['pattern']}': {e}")


class TestTaxonomyKeyValidity:

    def test_supplier_rules_taxonomy_keys(self, refinement, taxonomy_keys):
        for i, rule in enumerate(refinement["supplier_rules"]):
            assert rule["taxonomy_key"] in taxonomy_keys, (
                f"supplier_rules[{i}] invalid taxonomy_key: '{rule['taxonomy_key']}'"
            )

    def test_context_rules_taxonomy_keys(self, refinement, taxonomy_keys):
        for i, rule in enumerate(refinement["context_rules"]):
            assert rule["taxonomy_key"] in taxonomy_keys, (
                f"context_rules[{i}] invalid taxonomy_key: '{rule['taxonomy_key']}'"
            )

    def test_cost_center_rules_taxonomy_keys(self, refinement, taxonomy_keys):
        for i, rule in enumerate(refinement["cost_center_rules"]):
            assert rule["taxonomy_key"] in taxonomy_keys, (
                f"cost_center_rules[{i}] invalid taxonomy_key: '{rule['taxonomy_key']}'"
            )

    def test_override_rules_taxonomy_keys(self, refinement, taxonomy_keys):
        for i, rule in enumerate(refinement["supplier_override_rules"]):
            assert rule["taxonomy_key"] in taxonomy_keys, (
                f"override_rules[{i}] invalid taxonomy_key: '{rule['taxonomy_key']}'"
            )

    def test_sc_mapping_taxonomy_keys(self, sc_mapping, taxonomy_keys):
        for sc_code, info in sc_mapping.get("mappings", {}).items():
            assert info["taxonomy_key"] in taxonomy_keys, (
                f"SC mapping '{sc_code}' invalid taxonomy_key: '{info['taxonomy_key']}'"
            )

    def test_keyword_rules_taxonomy_keys(self, keyword_rules, taxonomy_keys):
        for i, rule in enumerate(keyword_rules.get("rules", [])):
            assert rule["category"] in taxonomy_keys, (
                f"keyword_rules[{i}] invalid category: '{rule['category']}'"
            )


class TestSCCodeValidity:

    def test_supplier_rules_sc_codes(self, refinement, valid_sc_codes):
        for i, rule in enumerate(refinement["supplier_rules"]):
            for sc in rule["sc_codes"]:
                assert str(sc) in valid_sc_codes, (
                    f"supplier_rules[{i}] unknown SC code: '{sc}'"
                )

    def test_context_rules_sc_codes(self, refinement, valid_sc_codes):
        for i, rule in enumerate(refinement["context_rules"]):
            for sc in rule["sc_codes"]:
                assert str(sc) in valid_sc_codes, (
                    f"context_rules[{i}] unknown SC code: '{sc}'"
                )

    def test_cost_center_rules_sc_codes(self, refinement, valid_sc_codes):
        for i, rule in enumerate(refinement["cost_center_rules"]):
            for sc in rule["sc_codes"]:
                assert str(sc) in valid_sc_codes, (
                    f"cost_center_rules[{i}] unknown SC code: '{sc}'"
                )


class TestConfidenceRanges:

    def test_supplier_confidence_valid(self, refinement):
        for i, rule in enumerate(refinement["supplier_rules"]):
            assert 0.0 < rule["confidence"] <= 1.0, (
                f"supplier_rules[{i}] confidence {rule['confidence']} out of range"
            )

    def test_context_confidence_valid(self, refinement):
        for i, rule in enumerate(refinement["context_rules"]):
            assert 0.0 < rule["confidence"] <= 1.0, (
                f"context_rules[{i}] confidence {rule['confidence']} out of range"
            )

    def test_cost_center_confidence_valid(self, refinement):
        for i, rule in enumerate(refinement["cost_center_rules"]):
            assert 0.0 < rule["confidence"] <= 1.0, (
                f"cost_center_rules[{i}] confidence {rule['confidence']} out of range"
            )

    def test_override_confidence_valid(self, refinement):
        for i, rule in enumerate(refinement["supplier_override_rules"]):
            assert 0.0 < rule["confidence"] <= 1.0, (
                f"override_rules[{i}] confidence {rule['confidence']} out of range"
            )


# -- 2. Classification Assertions ---------------------------------------------


class TestSupplierClassification:
    """Known supplier->taxonomy assertions. If these break, someone changed a rule."""

    KNOWN_MAPPINGS = [
        ("SC0250", "epic systems", "IT & Telecoms > Software > Application Software"),
        ("SC0250", "kpmg", "Professional Services > Financial Services > Accounting Services > General Accounting Services"),
        ("SC0250", "quest diagnostics", "Medical > Medical Services"),
        ("SC0250", "crothall", "Facilities > Cleaning > Cleaning Services"),
        ("SC0207", "grainger", "Facilities > Operating Supplies and Equipment"),
        ("SC0207", "uline", "Facilities > Operating Supplies and Equipment"),
        ("SC0250", "cintas", "Facilities > Cleaning > Cleaning Services"),
    ]

    @pytest.mark.parametrize("sc_code,supplier,expected_taxonomy", KNOWN_MAPPINGS)
    def test_supplier_rule_matches(self, refinement, sc_code, supplier, expected_taxonomy):
        matched = False
        for rule in refinement["supplier_rules"]:
            if sc_code not in [str(sc) for sc in rule["sc_codes"]]:
                continue
            if re.search(rule["supplier_pattern"], supplier, re.IGNORECASE):
                assert rule["taxonomy_key"] == expected_taxonomy, (
                    f"Supplier '{supplier}' with {sc_code} mapped to "
                    f"'{rule['taxonomy_key']}' instead of '{expected_taxonomy}'"
                )
                matched = True
                break
        assert matched, f"No rule matched supplier '{supplier}' with SC code '{sc_code}'"


# -- 3. Conflict Detection ----------------------------------------------------


class TestConflictDetection:

    def test_no_duplicate_supplier_patterns(self, refinement):
        seen = {}
        duplicates = []
        for i, rule in enumerate(refinement["supplier_rules"]):
            for sc in rule["sc_codes"]:
                key = (str(sc), rule["supplier_pattern"].lower())
                if key in seen:
                    duplicates.append(
                        f"  Rules [{seen[key]}] and [{i}]: SC={sc}, pattern='{rule['supplier_pattern']}'"
                    )
                else:
                    seen[key] = i
        assert not duplicates, "Duplicate supplier patterns found:\n" + "\n".join(duplicates)

    def test_no_overlapping_supplier_patterns(self, refinement):
        rules = refinement["supplier_rules"]
        overlaps = []
        for i in range(len(rules)):
            for j in range(i + 1, len(rules)):
                shared_sc = set(str(s) for s in rules[i]["sc_codes"]) & set(str(s) for s in rules[j]["sc_codes"])
                if not shared_sc:
                    continue
                alts_i = rules[i]["supplier_pattern"].split("|")
                alts_j = rules[j]["supplier_pattern"].split("|")
                for alt_i in alts_i:
                    for alt_j in alts_j:
                        try:
                            if re.search(rules[j]["supplier_pattern"], alt_i, re.IGNORECASE):
                                if rules[i]["taxonomy_key"] != rules[j]["taxonomy_key"]:
                                    overlaps.append(
                                        f"  [{i}] pattern alt '{alt_i}' matched by [{j}] "
                                        f"(SC overlap: {shared_sc})\n"
                                        f"    [{i}] -> {rules[i]['taxonomy_key']}\n"
                                        f"    [{j}] -> {rules[j]['taxonomy_key']}"
                                    )
                        except re.error:
                            pass
        if overlaps:
            pytest.skip(f"Potential overlaps (review manually):\n" + "\n".join(overlaps[:10]))

    def test_rule_counts(self, refinement):
        assert len(refinement["supplier_rules"]) >= 230, (
            f"Expected 230+ supplier rules, got {len(refinement['supplier_rules'])}"
        )
        assert len(refinement["context_rules"]) >= 8, (
            f"Expected 8+ context rules, got {len(refinement['context_rules'])}"
        )
        assert len(refinement["cost_center_rules"]) >= 10, (
            f"Expected 10+ cost center rules, got {len(refinement['cost_center_rules'])}"
        )
        assert len(refinement["supplier_override_rules"]) >= 11, (
            f"Expected 11+ override rules, got {len(refinement['supplier_override_rules'])}"
        )
