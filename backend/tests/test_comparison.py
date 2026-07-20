"""
Tests built from the actual stakeholder scenarios in the discovery notes,
not generic cases. Run with: python3 tests/test_comparison.py
(no pytest needed -- keeps this runnable in a locked-down environment)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.comparison import compare_abv, fuzzy_match, overall_status, verify_warning_statement
from app.config import CANONICAL_WARNING_TEXT

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


print("Dave's 'STONE'S THROW' vs 'Stone's Throw' case (should NOT hard-fail):")
r = fuzzy_match("brand_name", "STONE'S THROW", "Stone's Throw")
check("status is pass (case/punctuation-only difference)", r.status == "pass")

print("\nJenny's title-case warning rejection case:")
title_case_warning = CANONICAL_WARNING_TEXT.replace("GOVERNMENT WARNING", "Government Warning")
r = verify_warning_statement(title_case_warning, reported_all_caps_bold=False)
check("status is fail (not all caps)", r.status == "fail")
check("issue mentions caps", "caps" in r.detail)

print("\nExact, correctly formatted warning statement:")
r = verify_warning_statement(CANONICAL_WARNING_TEXT, reported_all_caps_bold=True)
check("status is pass", r.status == "pass")

print("\nWarning statement with a missing comma (real rejection example from ttb.gov research):")
broken = CANONICAL_WARNING_TEXT.replace("birth defects.", "birth defects")
r = verify_warning_statement(broken, reported_all_caps_bold=True)
check("status is fail (wording altered)", r.status == "fail")

print("\nGenuine brand name mismatch (should fail, not just review):")
r = fuzzy_match("brand_name", "OLD TOM DISTILLERY", "NEW TOM DISTILLERY")
check("status is fail or review, not pass", r.status in ("fail", "review"))

print("\nStandard spirit ABV within tolerance:")
r = compare_abv(45.0, 45.02, is_wine=False)
check("status is pass (tiny rounding diff)", r.status == "pass")

print("\nStandard spirit ABV out of tolerance:")
r = compare_abv(45.0, 46.5, is_wine=False)
check("status is fail", r.status == "fail")

print("\nHigh-ABV wine within the wider federal tolerance (+/-1pp):")
r = compare_abv(15.0, 15.9, is_wine=True)
check("status is pass (within 1pp wine tolerance)", r.status == "pass")

print("\nHigh-ABV wine outside even the wider tolerance:")
r = compare_abv(15.0, 16.2, is_wine=True)
check("status is fail", r.status == "fail")

print("\nLow-ABV wine does NOT get the wide tolerance:")
r = compare_abv(9.0, 9.8, is_wine=True)
check("status is fail (0.8pp diff exceeds standard 0.05pp tolerance)", r.status == "fail")

print("\nOverall status rollup:")
from app.comparison import FieldResult
mixed = [
    FieldResult("brand_name", "pass", "a", "a"),
    FieldResult("class_type", "review", "a", "b"),
]
check("rolls up to review when one field needs review", overall_status(mixed) == "review")
all_pass = [FieldResult("brand_name", "pass", "a", "a")]
check("rolls up to pass when all pass", overall_status(all_pass) == "pass")
one_fail = [FieldResult("brand_name", "pass", "a", "a"), FieldResult("abv", "fail", "a", "b")]
check("rolls up to fail if any field fails", overall_status(one_fail) == "fail")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
