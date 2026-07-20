"""
Tests for the batch CSV parser (filename-keyed, order-independent).
Run with: python3 tests/test_batch_csv.py  (no pytest required)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import parse_application_csv

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


HEADER = "filename,beverage_type,brand_name,class_type,abv,net_contents,name_address,is_imported,country_of_origin"

print("Rows keyed by filename, order irrelevant:")
csv_text = (
    HEADER + "\n"
    "b.jpg,wine,Beta,Table Wine,13.0,750 mL,Beta Winery,false,\n"
    "a.jpg,distilled_spirits,Alpha,Bourbon,45.0,750 mL,Alpha Distillery,true,Product of USA\n"
)
rows = parse_application_csv(csv_text)
check("both rows parsed, keyed by filename", set(rows) == {"a.jpg", "b.jpg"})
check("a.jpg present regardless of its row position", "a.jpg" in rows)
check("required value preserved", rows["a.jpg"]["brand_name"] == "Alpha")
check("filename column is not passed through as a field", "filename" not in rows["a.jpg"])

print("\nBlank optional cells are dropped so model defaults apply:")
check("blank country_of_origin dropped", "country_of_origin" not in rows["b.jpg"])
check("non-blank optional kept", rows["a.jpg"]["country_of_origin"] == "Product of USA")

print("\nA missing required column is a structural error (400 upstream):")
try:
    parse_application_csv("brand_name,abv\nX,45\n")
    check("missing required columns raises ValueError", False)
except ValueError:
    check("missing required columns raises ValueError", True)

print("\nRows without a filename are skipped, not errors:")
rows2 = parse_application_csv(HEADER + "\n,X,Y,Z,1,2,3,false,\n")
check("row with empty filename skipped", rows2 == {})

print("\nUnknown extra columns are ignored:")
rows3 = parse_application_csv(
    HEADER + ",notes\n"
    "c.png,beer,Gamma,Lager,5.0,355 mL,Gamma Brewing,false,,ignore me\n"
)
check("row parsed with extra column present", "c.png" in rows3)
check("extra column not carried into the row", "notes" not in rows3["c.png"])

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
