"""Field comparison logic. Per-field strategies, not one generic score -- ADR.md §6.

  - brand_name, class_type, net_contents, name_address -> fuzzy match
  - abv                                                -> numeric tolerance
  - warning_text                                       -> strict exact match

Each function returns a FieldResult with status "pass" | "review" | "fail".
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from . import config
from .schemas import ApplicationData, ExtractedLabelData


@dataclass
class FieldResult:
    field: str
    status: str  # "pass" | "review" | "fail"
    application_value: str
    extracted_value: str
    detail: str = ""


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation. Fuzzy fields only --
    never the warning statement, where exact casing/punctuation is the point."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def fuzzy_match(field: str, application_value: str, extracted_value: str) -> FieldResult:
    """Compare two free-text fields with tolerance for cosmetic differences."""
    a = _normalize(application_value)
    b = _normalize(extracted_value)
    score = difflib.SequenceMatcher(None, a, b).ratio()

    if score >= config.FUZZY_PASS_THRESHOLD:
        status = "pass"
    elif score >= config.FUZZY_REVIEW_THRESHOLD:
        status = "review"
    else:
        status = "fail"

    return FieldResult(
        field=field,
        status=status,
        application_value=application_value,
        extracted_value=extracted_value,
        detail=f"similarity={score:.2f}",
    )


def compare_abv(application_abv: float, extracted_abv: float, is_wine: bool = False) -> FieldResult:
    """Numeric ABV comparison with the federal tolerance for high-ABV wine."""
    tolerance = config.ABV_TOLERANCE_STANDARD
    if is_wine and application_abv >= config.HIGH_ABV_WINE_THRESHOLD:
        tolerance = config.ABV_TOLERANCE_HIGH_ABV_WINE

    diff = abs(application_abv - extracted_abv)
    status = "pass" if diff <= tolerance else "fail"

    return FieldResult(
        field="abv",
        status=status,
        application_value=f"{application_abv}%",
        extracted_value=f"{extracted_abv}%",
        detail=f"diff={diff:.2f}pp, tolerance={tolerance}pp",
    )


def verify_warning_statement(extracted_text: str, reported_all_caps_bold: bool) -> FieldResult:
    """Strict verification: verbatim text + "GOVERNMENT WARNING" all-caps bold (27 CFR 16).

    `reported_all_caps_bold` comes from the vision step (font weight can't be read
    from OCR text) -- a known extraction-quality dependency, see README limitations.
    """
    issues = []

    # Normalize whitespace only -- casing and punctuation must match exactly.
    normalized_extracted = re.sub(r"\s+", " ", extracted_text.strip())
    normalized_canonical = re.sub(r"\s+", " ", config.CANONICAL_WARNING_TEXT.strip())

    if normalized_extracted != normalized_canonical:
        issues.append("text does not match the federally mandated wording exactly")

    if "GOVERNMENT WARNING" not in extracted_text:
        issues.append("'GOVERNMENT WARNING' not found in all caps")

    if not reported_all_caps_bold:
        issues.append("'GOVERNMENT WARNING' does not appear bolded")

    # Binary by law -- no "review" state here, unlike the fuzzy fields.
    status = "pass" if not issues else "fail"

    return FieldResult(
        field="warning_statement",
        status=status,
        application_value=config.CANONICAL_WARNING_TEXT,
        extracted_value=extracted_text,
        detail="; ".join(issues) if issues else "matches exactly",
    )


def compare_all(application: ApplicationData, extracted: ExtractedLabelData) -> list[FieldResult]:
    """Every field comparison for one label, in display order.

    Lives here rather than in the route so the batch generator can predict
    verdicts with the same policy it is testing (ADR.md §6).
    """
    results = [
        fuzzy_match("brand_name", application.brand_name, extracted.brand_name),
        fuzzy_match("class_type", application.class_type, extracted.class_type),
        fuzzy_match("net_contents", application.net_contents, extracted.net_contents),
        fuzzy_match("name_address", application.name_address, extracted.name_address),
        compare_abv(application.abv, extracted.abv, is_wine=(application.beverage_type == "wine")),
        verify_warning_statement(extracted.warning_text, extracted.warning_all_caps_bold),
    ]

    # Country of origin is imports-only, so compared only when the applicant filled it
    # in (blank = not applicable). Other type-conditional fields are out of scope -- ADR.md §11.
    if application.country_of_origin.strip():
        results.append(
            fuzzy_match("country_of_origin", application.country_of_origin, extracted.country_of_origin)
        )
    return results


def overall_status(results: list[FieldResult]) -> str:
    """Roll up field-level statuses into one label-level verdict."""
    statuses = {r.status for r in results}
    if "fail" in statuses:
        return "fail"
    if "review" in statuses:
        return "review"
    return "pass"
