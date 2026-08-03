"""Smoke tests for the source-independent core. Run: python src/test_core.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import geo
import hebrew as he
import schema as sc

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got!r}")


def check_ge(label, got, floor):
    ok = got >= floor
    if not ok:
        fails.append(f"{label}: got {got!r}, want >= {floor}")
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got!r} (>= {floor})")


def check_lt(label, got, ceil):
    ok = got < ceil
    if not ok:
        fails.append(f"{label}: got {got!r}, want < {ceil}")
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got!r} (< {ceil})")


print("--- hebrew keys ---")
check("niqqud stripped", he.display("תֵּל שִׁמְרוֹן"), "תל שמרון")
check("ruin prefix folded", he.key("ח'ירבת אבו שושה"), he.key("חורבת אבו שושה"))
check("short ruin prefix folded", he.key("ח' זלפה"), he.key("חורבת זלפה"))
check("finals folded", he.key("בית שערים"), he.key("בית שערימ"))
check("arabic article dropped", he.key("תל אל-מוטסלים"), he.key("תל מוטסלים"))
check("quotes dropped", he.key('שיח" אבריק'), he.key("שיח אבריק"))

print("\n--- hebrew similarity ---")
check_ge("spelling variant", he.similarity("תל שמרון", "תל שימרון"), 0.85)
check_ge("ruin variants", he.similarity("ח'ירבת סמוניה", "חורבת שמוניה"), 0.70)
check_ge("qualifier tolerated", he.similarity("גן לאומי בית שערים", "בית שערים"), 0.85)
check_ge("extra qualifier word", he.similarity("מוזיאון תחנת הרכבת כפר יהושע", "תחנת הרכבת כפר יהושע"), 0.80)
check_ge("tel vs ruin, same specifier", he.similarity("תל שמרון", "חורבת שמרון"), 0.80)
check_lt("shared tel head only", he.similarity("תל שמרון", "תל מגידו"), 0.50)
check_lt("shared beit head only", he.similarity("בית שערים", "בית שאן"), 0.50)
check_lt("shared kfar head only", he.similarity("כפר יהושע", "כפר ברוך"), 0.50)
check_lt("shared ruin head only", he.similarity("חורבת זלפה", "חורבת סמוניה"), 0.50)
check_lt("unrelated stay apart", he.similarity("מוזיאון תחנת הרכבת", "חורבת זלפה"), 0.50)
check_lt("empty is not a match", he.similarity("", "בית שערים"), 0.01)
check("distinctive strips the head", he.distinctive("תל שמרון"), ["שמרונ"])
check("distinctive keeps a bare head", he.distinctive("תל"), ["תל"])

print("\n--- grids ---")
check("ITM detected", geo.detect_grid(217000, 733000), "itm")
check("ICS detected", geo.detect_grid(167000, 233000), "ics")
check("garbage refused", geo.detect_grid(35.2, 32.7), "unknown")

x, y = geo.to_itm(32.6963, 35.1972)
print(f"     Nahalal-ish WGS84 -> ITM = ({x}, {y})")
lat, lon = geo.to_wgs84(x, y)
check_lt("ITM round-trip error m", geo.haversine_m(32.6963, 35.1972, lat, lon), 1.0)
check("round-trip grid is ITM", geo.detect_grid(x, y), "itm")

try:
    geo.to_wgs84(x, y - 400_000)
    fails.append("implausible conversion was accepted")
    print("FAIL implausible conversion accepted")
except geo.CoordError as e:
    print(f"ok   implausible conversion refused: {str(e)[:60]}...")

print("\n--- schema ---")
check("era from byzantine", sc.era_from_periods(["byzantine"]), "archaeological")
check("era from ottoman_late", sc.era_from_periods(["ottoman_late"]), "historic")
check("reuse keeps antiquity", sc.era_from_periods(["roman", "mandate"]), "archaeological")
check("no periods is undecidable", sc.era_from_periods([]), None)
check("declared is registered", sc.registered_summary({"reg_antiquity": "declared"}), "registered")
check("recognized museum is registered", sc.registered_summary({"reg_institution": "recognized_museum"}), "registered")
check("all none is not registered", sc.registered_summary(
    {"reg_antiquity": "none", "reg_conservation": "none", "reg_institution": "none", "protected_area": "none"}
), "not_registered")
check("silence is unknown", sc.registered_summary({}), "unknown")
check("every status axis has unknown",
      all("unknown" in a["values"] for a in sc.STATUS_AXES.values()), True)
check("no em-dash in vocabularies",
      any("—" in str(v) for v in (sc.STATUS_AXES, sc.SITE_TYPES, sc.CATEGORIES, sc.SOURCES)), False)
check("every precedence source is registered",
      sorted({s for lst in sc.PRECEDENCE.values() for s in lst} - set(sc.SOURCES)), [])

print()
if fails:
    print(f"{len(fails)} FAILURES:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("all core tests passed")
