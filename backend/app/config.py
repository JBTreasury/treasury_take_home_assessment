"""Thresholds and constraints. Sources for each value: README.md."""

# Fuzzy match bands (brand name, class/type, net contents) -- ADR.md §9.
FUZZY_PASS_THRESHOLD = 0.90    # >= pass
FUZZY_REVIEW_THRESHOLD = 0.70  # >= review, below -> fail

# ABV, in percentage points.
ABV_TOLERANCE_STANDARD = 0.05
ABV_TOLERANCE_HIGH_ABV_WINE = 1.0  # wider federal tolerance, 27 CFR
HIGH_ABV_WINE_THRESHOLD = 14.0

# 27 CFR part 16. Must be reproduced verbatim.
CANONICAL_WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health "
    "problems."
)

# Upload limits match TTB's COLAs Online rules.
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}
MAX_IMAGE_SIZE_BYTES = 1_500_000

MAX_BATCH_SIZE = 300
MAX_CONCURRENT_EXTRACTIONS = 10  # one global semaphore, not per batch -- ADR.md §10

TARGET_LATENCY_SECONDS = 5  # documentation, not an enforced timeout
