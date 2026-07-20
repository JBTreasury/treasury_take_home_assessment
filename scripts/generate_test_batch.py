"""
Generates a batch of synthetic label images plus the matching
application-data CSV, for stress-testing /verify/batch without
manually creating hundreds of files by hand.

Usage:
    python3 generate_test_batch.py [count]

    count defaults to 300 (matches Sarah's stated peak batch size and
    config.MAX_BATCH_SIZE).

Output:
    test_labels/label_0001.png ... label_NNNN.png
    test_labels_application_data.csv  -- select this as the CSV in the
        batch upload form; select all files in test_labels/ for the
        image file picker. Rows are matched to images by filename.
    test_labels_expected.csv          -- filename -> expected verdict and
        the specific defect injected. Diff this against the batch results
        to see whether the pipeline actually caught what was planted.

Deliberately injects a controlled mix of outcomes, not all clean passes --
useful for actually observing pass/review/fail counts at scale, not just
whether the batch endpoint completes without crashing:

    1/3 pass    -- application data matches the label
    1/3 review  -- exactly one fuzzy field is a near-miss, scoring inside
                   config's review band. Nothing else is wrong, so the
                   worst-of roll-up in overall_status lands on "review".
    1/3 fail    -- half from government warning defects (not bold, not all
                   caps, altered wording), half from other fields (brand,
                   ABV, net contents, class/type, country of origin).

Independently of that: 1/3 distilled spirits, 1/3 wine, 1/3 beer, and 20%
imports (which carry a country-of-origin statement on the label and in the
CSV -- the API only compares that field when the applicant filled it in).

Thresholds are NOT duplicated here. The near-miss perturbations are chosen
by running the API's own comparison.fuzzy_match and keeping the candidate
whose status is "review", so config.FUZZY_PASS_THRESHOLD and
config.FUZZY_REVIEW_THRESHOLD remain the single source of truth. Every
generated label is then run through the real comparison logic against a
simulated perfect extraction, and generation aborts if any label would not
produce its intended verdict.

That simulation assumes the vision model reads the label correctly. It is a
check on the fixtures, not on extraction quality -- a real run will differ
wherever the model misreads an image.

Requires Pillow: pip install Pillow --break-system-packages (or just
pip install Pillow inside your venv)
"""

import csv
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent / "backend"

COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 300

OUTPUT_DIR = SCRIPT_DIR / "test_labels"
APP_DATA_FILE = SCRIPT_DIR / "test_labels_application_data.csv"
EXPECTED_FILE = SCRIPT_DIR / "test_labels_expected.csv"

# Import the API's real comparison logic and thresholds. The generator picks
# and verifies its perturbations with these, so a threshold change in
# config.py reshapes the fixtures instead of silently invalidating them.
sys.path.insert(0, str(BACKEND_DIR))
from app import config  # noqa: E402
from app.comparison import (  # noqa: E402
    compare_abv,
    fuzzy_match,
    overall_status,
    verify_warning_statement,
)

CANONICAL_WARNING_TEXT = config.CANONICAL_WARNING_TEXT

# Wording violation: one clause reworded. Verbatim reproduction is the legal
# requirement (27 CFR 16), so a plausible paraphrase must still fail.
ALTERED_WARNING_TEXT = CANONICAL_WARNING_TEXT.replace(
    "may cause health problems.", "can cause other health problems."
)

# (brand, class_type, address, abv, net_contents)
DOMESTIC = {
    "distilled_spirits": [
        ("OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "Louisville, KY", 45.0, "750 mL"),
        ("SILVER OAK RIDGE", "Straight Bourbon Whiskey", "West Bloomfield, MI", 43.5, "750 mL"),
        ("BLUE HERON SPIRITS", "Kentucky Straight Rye Whiskey", "Frankfort, KY", 46.0, "750 mL"),
        ("STONE'S THROW", "Small Batch Bourbon Whiskey", "Bardstown, KY", 47.0, "375 mL"),
        ("IRON GATE DISTILLERY", "Straight Bourbon Whiskey", "Lexington, KY", 40.0, "1 L"),
    ],
    "wine": [
        ("CEDAR HOLLOW VINEYARDS", "Napa Valley Cabernet Sauvignon", "St. Helena, CA", 14.5, "750 mL"),
        ("MARSH AND MEADOW", "Willamette Valley Pinot Noir", "Dundee, OR", 13.5, "750 mL"),
        ("HARBORLIGHT CELLARS", "Finger Lakes Dry Riesling", "Geneva, NY", 12.0, "750 mL"),
        ("GOLDEN FURROW ESTATE", "Sonoma Coast Chardonnay", "Sebastopol, CA", 14.0, "1.5 L"),
        ("RED KITE WINERY", "Columbia Valley Merlot", "Prosser, WA", 13.8, "750 mL"),
    ],
    "beer": [
        ("COPPER KETTLE BREWING", "India Pale Ale", "Asheville, NC", 6.8, "12 fl oz"),
        ("NORTHGATE BREW WORKS", "Bohemian Style Pilsner", "Portland, ME", 5.0, "12 fl oz"),
        ("SALT FLATS BREWERY", "Belgian Style Witbier", "Ogden, UT", 4.9, "16 fl oz"),
        ("TIMBERWOLF ALE HOUSE", "American Amber Ale", "Missoula, MT", 5.6, "12 fl oz"),
        ("HOLLOW POINT BREWING", "Imperial Stout", "Milwaukee, WI", 8.2, "16 fl oz"),
    ],
}

# Same shape, plus the country-of-origin statement printed on the label.
IMPORTED = {
    "distilled_spirits": [
        ("GLEN CARRICK", "Single Malt Scotch Whisky", "Speyside, Scotland", 43.0, "750 mL", "Product of Scotland"),
        ("CASA DEL VIENTO", "Tequila Reposado", "Jalisco, Mexico", 40.0, "750 mL", "Product of Mexico"),
        ("BOISVERT FRERES", "Cognac VSOP", "Cognac, France", 40.0, "750 mL", "Product of France"),
    ],
    "wine": [
        ("CHATEAU BELLERIVE", "Bordeaux Red Wine", "Bordeaux, France", 13.0, "750 mL", "Product of France"),
        ("VILLA SANTORO", "Chianti Classico", "Tuscany, Italy", 13.5, "750 mL", "Product of Italy"),
        ("QUINTA DO VALE", "Vinho Verde", "Minho, Portugal", 11.0, "750 mL", "Product of Portugal"),
    ],
    "beer": [
        ("BRAUHAUS ADLER", "Munich Style Helles Lager", "Bavaria, Germany", 5.2, "500 mL", "Product of Germany"),
        ("ABBAYE SAINT ROCH", "Belgian Abbey Dubbel", "Namur, Belgium", 7.0, "330 mL", "Product of Belgium"),
        ("CERVECERIA DEL SOL", "Mexican Style Lager", "Yucatan, Mexico", 4.5, "355 mL", "Product of Mexico"),
    ],
}

# The bottling statement's verb varies by product class, so the label and the
# application data have to agree on it.
BOTTLER_VERB = {
    "distilled_spirits": "Bottled By",
    "wine": "Produced and Bottled By",
    "beer": "Brewed and Bottled By",
}

BEVERAGE_TYPES = ("distilled_spirits", "wine", "beer")
INTENTS = ("pass", "review", "fail")

# Half the failures come from the warning statement, half from other fields.
WARNING_FAIL_CAUSES = ("warning_not_bold", "warning_not_caps", "warning_wording")
FIELD_FAIL_CAUSES = ("brand_mismatch", "abv_out_of_tolerance", "net_contents_mismatch", "class_type_mismatch")


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# Font candidates by platform. The BOLD face must resolve to a real bold font:
# if it falls back to the default bitmap font, "GOVERNMENT WARNING" renders
# non-bold and every label fails comparison.verify_warning_statement's bold
# check. (The original code hardcoded Linux-only paths, so on Windows/macOS all
# fonts fell back to the non-bold default -- which is why every label failed.)
_REGULAR_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",   # Linux
    "C:/Windows/Fonts/arial.ttf",                        # Windows
    "/System/Library/Fonts/Supplemental/Arial.ttf",      # macOS
    "arial.ttf",
    "DejaVuSans.ttf",
]
_BOLD_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "arialbd.ttf",
    "DejaVuSans-Bold.ttf",
]


def _font(bold, size):
    for path in (_BOLD_FONTS if bold else _REGULAR_FONTS):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_label_image(path, label):
    """Render what is physically printed on the label (the `label` dict)."""
    img = Image.new("RGB", (600, 800), color=(250, 245, 235))
    draw = ImageDraw.Draw(img)

    font_brand = _font(True, 32)
    font_normal = _font(False, 18)
    font_small = _font(False, 14)
    # Slightly larger than the 14px body so the bold face reads as clearly (and
    # cleanly) bold to the vision model -- no stroke needed.
    font_warning_bold = _font(True, 16)

    draw.rectangle([20, 20, 580, 780], outline=(80, 60, 40), width=3)

    y = 60
    draw.text((300, y), label["brand"], font=font_brand, fill=(40, 25, 10), anchor="ma")
    y += 60
    draw.text((300, y), label["class_type"], font=font_normal, fill=(40, 25, 10), anchor="ma")
    y += 40
    draw.text((300, y), f"{label['abv']}% Alc./Vol.", font=font_normal, fill=(40, 25, 10), anchor="ma")
    y += 30
    draw.text((300, y), label["net_contents"], font=font_normal, fill=(40, 25, 10), anchor="ma")
    y += 50
    draw.text((300, y), f"{label['verb']} {label['brand']}", font=font_small, fill=(40, 25, 10), anchor="ma")
    y += 20
    draw.text((300, y), label["address"], font=font_small, fill=(40, 25, 10), anchor="ma")
    if label["country"]:
        y += 20
        draw.text((300, y), label["country"], font=font_small, fill=(40, 25, 10), anchor="ma")

    y += 60
    prefix = "GOVERNMENT WARNING:" if label["warning_caps"] else "Government Warning:"
    body = label["warning_text"].split(":", 1)[1].strip()
    lines = [prefix] + wrap_text(draw, body, font_small, 500)
    for line in lines:
        bold_line = label["warning_bold"] and line == prefix
        f = font_warning_bold if bold_line else font_small
        draw.text((300, y), line, font=f, fill=(20, 20, 20), anchor="ma")
        y += 22 if bold_line else 18

    img.save(path)


def _printed_warning(label):
    """The warning statement as it actually appears on the rendered image."""
    prefix = "GOVERNMENT WARNING:" if label["warning_caps"] else "Government Warning:"
    return f"{prefix} {label['warning_text'].split(':', 1)[1].strip()}"


def near_miss(value, candidates):
    """Pick the first variant that the API's own fuzzy_match calls "review".

    Deliberately delegates the decision to comparison.fuzzy_match rather than
    hardcoding a similarity target, so config's thresholds stay authoritative.
    """
    for candidate in candidates:
        if candidate != value and fuzzy_match("x", candidate, value).status == "review":
            return candidate
    raise SystemExit(
        f"no near-miss variant of {value!r} lands in the review band "
        f"[{config.FUZZY_REVIEW_THRESHOLD}, {config.FUZZY_PASS_THRESHOLD}); "
        "add a candidate or adjust the thresholds"
    )


def hard_mismatch(value, candidates):
    """Pick the first variant fuzzy_match calls an outright "fail"."""
    for candidate in candidates:
        if fuzzy_match("x", candidate, value).status == "fail":
            return candidate
    raise SystemExit(f"no variant of {value!r} scores below the review threshold")


# Similarity is length-sensitive: appending k characters to a name of length L
# scores roughly 2L/(2L+k), so a suffix that leaves a short name in the review
# band leaves a long one comfortably passing. Each generator therefore yields a
# graduated ladder of realistic variants and lets near_miss() pick the one that
# actually lands in the band for this particular value.
def _brand_variants(brand):
    words = brand.split()
    yield brand + " CO"
    yield brand + " & SONS"
    yield brand + " COMPANY"
    yield brand + " TRADING COMPANY"
    if len(words) > 1:
        # Abbreviate or drop the trailing word ("DISTILLERY" -> "DIST").
        yield " ".join(words[:-1] + [words[-1][:4]])
        yield " ".join(words[:-1])
        yield " ".join([words[0][0]] + words[1:])
    yield brand.replace("DISTILLERY", "DISTILLERS").replace("BREWING", "BREW CO").replace(
        "VINEYARDS", "VINEYARD"
    ).replace("WINERY", "WINE CO").replace("BREWERY", "BREW HOUSE").replace("CELLARS", "CELLAR")


def _class_type_variants(class_type):
    words = class_type.split()
    if len(words) > 1:
        yield " ".join(words[1:])
        yield " ".join(words[:-1])
    yield class_type + " Reserve"
    yield class_type + " Special Reserve"
    yield "Small Batch " + class_type
    yield "Premium " + class_type


def _address_variants(verb, brand, address):
    """Near-misses on the bottling statement, not on the brand itself."""
    city = address.split(",")[0].strip()
    region = address.split(",")[-1].strip()
    yield f"{verb} {brand}, {region}"
    yield f"{verb} {brand}, {city}"
    yield f"{brand}, {address}"
    yield f"{verb} {brand}, {address}, USA"
    yield f"{verb} {brand}, {address}, United States"
    yield f"{verb} {brand} of {city}"


def _country_variants(country):
    yield country.replace("Product of", "Produced in")
    yield country.replace("Product of ", "")
    yield country.replace("Product of", "Imported Product of")
    yield country + " and Bottled Abroad"


def simulate_extraction(label):
    """What a perfect vision model would read off the rendered image."""
    return {
        "brand_name": label["brand"],
        "class_type": label["class_type"],
        "abv": label["abv"],
        "net_contents": label["net_contents"],
        "name_address": f"{label['verb']} {label['brand']}, {label['address']}",
        "warning_text": _printed_warning(label),
        "warning_all_caps_bold": label["warning_bold"],
        "country_of_origin": label["country"],
    }


def predict(app, extracted):
    """Mirror of main._verify_one's field list, using the same comparison code."""
    results = [
        fuzzy_match("brand_name", app["brand_name"], extracted["brand_name"]),
        fuzzy_match("class_type", app["class_type"], extracted["class_type"]),
        fuzzy_match("net_contents", app["net_contents"], extracted["net_contents"]),
        fuzzy_match("name_address", app["name_address"], extracted["name_address"]),
        compare_abv(float(app["abv"]), extracted["abv"], is_wine=(app["beverage_type"] == "wine")),
        verify_warning_statement(extracted["warning_text"], extracted["warning_all_caps_bold"]),
    ]
    if app["country_of_origin"].strip():
        results.append(
            fuzzy_match("country_of_origin", app["country_of_origin"], extracted["country_of_origin"])
        )
    return overall_status(results), results


def build_plan(count, rng):
    """Assign intent / beverage type / import flag with exact proportions.

    Phased round-robin rather than independent random draws, so a 300-label run
    hits the requested thirds and 20% exactly instead of approximately, and the
    three axes stay uncorrelated with each other.
    """
    plan = [
        {
            "intent": INTENTS[i % 3],
            "beverage_type": BEVERAGE_TYPES[(i // 3) % 3],
            "is_imported": i % 5 == 0,
        }
        for i in range(count)
    ]
    rng.shuffle(plan)  # counts preserved; ordering no longer patterned
    return plan


def build_label(slot, rng):
    """Produce (label, app, cause) for one plan slot.

    `label` is what gets printed on the image; `app` is the CSV row (what the
    applicant claims). A defect is a deliberate divergence between the two --
    except the warning defects, which are printing errors on the label itself.
    """
    bev = slot["beverage_type"]
    verb = BOTTLER_VERB[bev]

    if slot["is_imported"]:
        brand, class_type, address, abv, net, country = rng.choice(IMPORTED[bev])
    else:
        brand, class_type, address, abv, net = rng.choice(DOMESTIC[bev])
        country = ""

    label = {
        "brand": brand,
        "class_type": class_type,
        "address": address,
        "abv": abv,
        "net_contents": net,
        "country": country,
        "verb": verb,
        "warning_text": CANONICAL_WARNING_TEXT,
        "warning_caps": True,
        "warning_bold": True,
    }
    app = {
        "beverage_type": bev,
        "brand_name": brand,
        "class_type": class_type,
        "abv": abv,
        "net_contents": net,
        "name_address": f"{verb} {brand}, {address}",
        "is_imported": "true" if slot["is_imported"] else "false",
        "country_of_origin": country,
    }

    cause = "clean"
    if slot["intent"] == "review":
        options = ["brand", "class_type", "name_address"]
        if country:
            options.append("country_of_origin")
        target = rng.choice(options)
        if target == "brand":
            app["brand_name"] = near_miss(brand, list(_brand_variants(brand)))
        elif target == "class_type":
            app["class_type"] = near_miss(class_type, list(_class_type_variants(class_type)))
        elif target == "name_address":
            app["name_address"] = near_miss(
                app["name_address"], list(_address_variants(verb, brand, address))
            )
        else:
            app["country_of_origin"] = near_miss(country, list(_country_variants(country)))
        cause = f"{target}_near_miss"

    elif slot["intent"] == "fail":
        # Alternate warning defects and field defects so both halves are
        # represented, then rotate within each half.
        if slot["index"] % 2 == 0:
            cause = WARNING_FAIL_CAUSES[(slot["index"] // 2) % len(WARNING_FAIL_CAUSES)]
            if cause == "warning_not_bold":
                label["warning_bold"] = False
            elif cause == "warning_not_caps":
                label["warning_caps"] = False
            else:
                label["warning_text"] = ALTERED_WARNING_TEXT
        else:
            # No country-of-origin entry here on purpose: every country
            # statement shares the "Product of " prefix, so claiming the wrong
            # country still scores inside the review band (France vs Ireland is
            # 0.80). A wrong country can only ever be a review fixture -- see
            # the country_of_origin_near_miss case above.
            causes = FIELD_FAIL_CAUSES
            cause = causes[(slot["index"] // 2) % len(causes)]
            if cause == "brand_mismatch":
                others = [p[0] for p in DOMESTIC[bev] if p[0] != brand]
                app["brand_name"] = hard_mismatch(brand, others)
            elif cause == "abv_out_of_tolerance":
                # 3pp clears both the standard tolerance and the wider
                # high-ABV wine tolerance.
                app["abv"] = round(abv - 3.0, 1)
            elif cause == "net_contents_mismatch":
                others = ["1.75 L", "375 mL", "22 fl oz", "500 mL"]
                app["net_contents"] = hard_mismatch(net, others)
            else:
                others = [p[1] for t in BEVERAGE_TYPES if t != bev for p in DOMESTIC[t]]
                app["class_type"] = hard_mismatch(class_type, others)

    return label, app, cause


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    rng = random.Random(42)  # reproducible runs

    plan = build_plan(COUNT, rng)
    rows, expected = [], []
    actual_counts = {"pass": 0, "review": 0, "fail": 0}
    type_counts = dict.fromkeys(BEVERAGE_TYPES, 0)
    import_count = 0
    mismatches = []

    for i, slot in enumerate(plan, start=1):
        slot["index"] = i
        label, app, cause = build_label(slot, rng)

        filename = f"label_{i:04d}.png"
        make_label_image(OUTPUT_DIR / filename, label)

        # Verify the fixture actually produces its intended verdict, assuming a
        # correct extraction. Catches perturbations that normalization erases
        # (e.g. a case-only "near-miss" scores 1.00 and quietly passes).
        predicted, results = predict(app, simulate_extraction(label))
        if predicted != slot["intent"]:
            offenders = ", ".join(f"{r.field}={r.status}" for r in results if r.status != "pass") or "none"
            mismatches.append(f"  {filename}: intended {slot['intent']}, predicted {predicted} ({cause}; {offenders})")

        actual_counts[predicted] = actual_counts.get(predicted, 0) + 1
        type_counts[slot["beverage_type"]] += 1
        import_count += slot["is_imported"]

        rows.append({"filename": filename, **app})
        expected.append({
            "filename": filename,
            "expected_status": slot["intent"],
            "cause": cause,
            "beverage_type": slot["beverage_type"],
            "is_imported": app["is_imported"],
        })

    if mismatches:
        raise SystemExit(
            "generated fixtures do not match their intended verdicts:\n" + "\n".join(mismatches)
        )

    with open(APP_DATA_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    with open(EXPECTED_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(expected[0].keys()))
        writer.writeheader()
        writer.writerows(expected)

    print(f"Generated {COUNT} labels in {OUTPUT_DIR}/")
    print(f"  verdicts:  " + ", ".join(f"{k}={v}" for k, v in actual_counts.items()))
    print(f"  types:     " + ", ".join(f"{k}={v}" for k, v in type_counts.items()))
    print(f"  imports:   {import_count} ({import_count / COUNT:.0%})")
    print(f"  thresholds: review>={config.FUZZY_REVIEW_THRESHOLD}, pass>={config.FUZZY_PASS_THRESHOLD}")
    print("All fixtures validated against the API's own comparison logic.")
    print(f"Application-data CSV written to {APP_DATA_FILE}")
    print(f"Expected verdicts written to {EXPECTED_FILE}")
    print("Select all files in test_labels/ for the batch upload, and")
    print(f"{APP_DATA_FILE} as the CSV in the batch upload form.")


if __name__ == "__main__":
    main()
