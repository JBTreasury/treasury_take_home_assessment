"""
Central config for thresholds and constraints.

Kept as named constants (not hardcoded inline) so reviewers can see the
reasoning and adjust without touching comparison logic. Every value here
traces back to either a stakeholder interview or ttb.gov guidance —
see README.md for the source of each.
"""

# --- Fuzzy match thresholds (brand name, class/type, net contents) ---
# Bands from Dave's "STONE'S THROW" vs "Stone's Throw" case -- exact-string
# equality produces false-positive rejections. See ADR.md §6.
FUZZY_PASS_THRESHOLD = 0.90   # >= this -> auto pass
FUZZY_REVIEW_THRESHOLD = 0.70  # >= this (but < pass) -> flag for human review
# below FUZZY_REVIEW_THRESHOLD -> fail

# --- ABV comparison ---
# Standard products: must match to within this many percentage points.
ABV_TOLERANCE_STANDARD = 0.05
# Wines >= 14% ABV get a wider federal tolerance (see ttb.gov / 27 CFR).
ABV_TOLERANCE_HIGH_ABV_WINE = 1.0
HIGH_ABV_WINE_THRESHOLD = 14.0

# --- Government warning statement ---
# Exact federally-mandated text (27 CFR part 16). Must be reproduced verbatim.
CANONICAL_WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should "
    "not drink alcoholic beverages during pregnancy because of the risk of "
    "birth defects. (2) Consumption of alcoholic beverages impairs your "
    "ability to drive a car or operate machinery, and may cause health "
    "problems."
)

# --- Upload constraints ---
# From TTB's COLAs Online requirements. Validated against the file's actual
# signature bytes (main.py _sniff_image_type), not the spoofable header.
ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png"}
MAX_IMAGE_SIZE_BYTES = 1_500_000  # 1.5 MB, matches TTB's own limit

# --- Batch constraints ---
# Sarah's peak-season batch size is 200-300 labels; cap slightly above that
# as a cost/abuse guard, not a hard business limit.
MAX_BATCH_SIZE = 300
# Enforced as a single GLOBAL semaphore in main.py, not one pool per batch -- ADR.md §7.
MAX_CONCURRENT_EXTRACTIONS = 10

# --- Latency budget ---
# Sarah: "if we can't get results back in about 5 seconds, nobody's going to
# use it." Documentation, not an enforced timeout -- see README limitations.
TARGET_LATENCY_SECONDS = 5
