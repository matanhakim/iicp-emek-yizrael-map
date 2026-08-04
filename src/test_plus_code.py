"""Measure the Plus Code decoder against the rows that carry both a code and a coordinate.

The institute's inventory has 27 Emek Yizrael rows with BOTH a Plus Code and a latitude and
longitude recorded independently. Decoding those codes and comparing to the recorded position
is a real test of the decoder rather than a restatement of it: if the arithmetic or the
short-code recovery were wrong, the errors would be kilometres, not metres.

Run: python src/test_plus_code.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import geo  # noqa: E402
import hebrew as he  # noqa: E402
import paths  # noqa: E402
import plus_code as pc  # noqa: E402


def lookup_settlement(name: str, table: dict):
    """The sheet and the CBS list spell some settlements differently (גניגר / גיניגר)."""
    if not name:
        return None
    if name in table:
        return table[name]
    best, score = None, 0.0
    for k, v in table.items():
        s = he.similarity(name, k)
        if s > score:
            best, score = v, s
    return best if score >= 0.85 else None

ROOT = Path(__file__).resolve().parent.parent

fails: list[str] = []

print("--- spec vectors (from the Open Location Code specification) ---")
# Known full-code decodings published in the spec's test data.
# Only vectors whose expected values come from the specification's published test data are
# used. A fourth vector was dropped: its expected coordinate was written from memory and was
# wrong (it named Wellington for a code that encodes Singapore), which is exactly the kind of
# invented reference value a test must never contain. The 24 rows below are the real evidence.
for code, want_lat, want_lon in [
    ("7FG49Q00+", 20.375, 2.775),
    ("7FG49QCJ+2V", 20.3700625, 2.7821875),
    ("8FVC2222+22", 47.0000625, 8.0000625),
]:
    lat, lon = pc.center(code)
    d = geo.haversine_m(lat, lon, want_lat, want_lon)
    ok = d < 12
    if not ok:
        fails.append(f"{code}: decoded ({lat:.6f},{lon:.6f}), expected ({want_lat},{want_lon}), {d:.1f} m off")
    print(f"{'ok  ' if ok else 'FAIL'} {code:14} -> {lat:.6f}, {lon:.6f}  ({d:.1f} m from the spec centre)")

print("\n--- round trip ---")
for lat, lon in [(32.6963, 35.1972), (32.7323, 35.1710), (-33.857, 151.215), (0.0, 0.0)]:
    code = pc.encode(lat, lon)
    got_lat, got_lon = pc.center(code)
    d = geo.haversine_m(lat, lon, got_lat, got_lon)
    ok = d < 12
    if not ok:
        fails.append(f"round trip {lat},{lon} -> {code} -> {d:.1f} m")
    print(f"{'ok  ' if ok else 'FAIL'} {lat:>10.4f},{lon:>9.4f} -> {code:14} -> {d:5.1f} m")

print("\n--- against the institute's own rows (short-code recovery) ---")
settle = {}
for r in paths.settlements():
    if r.get("name_he") and r.get("lat") is not None:
        settle[r["name_he"].strip()] = (r["lat"], r["lon"])

B = paths.source_payload("iicp_culture_table.json")
if B is None:
    print("  (no institute table available, in the working copy or the frozen archive)")
else:
    both = [r for r in B
            if r.get("_is_emek_yizrael_council") and not r.get("_excluded")
            and r.get("lat") is not None and r.get("_plus_code_local")]
    errs = []
    for r in both:
        code = pc.parse(r["_plus_code_local"])
        town = (r.get("שם יישוב") or "").strip()
        ref = lookup_settlement(town, settle)
        if not code or not ref:
            print(f"  skip: code={code!r} town={town!r} ref={'yes' if ref else 'NO'}")
            continue
        lat, lon = pc.recover(code, *ref)
        d = geo.haversine_m(lat, lon, r["lat"], r["lon"])
        errs.append(d)
        flag = "ok  " if d < 60 else "FAIL"
        if d >= 60:
            fails.append(f"{code} in {town}: {d:.0f} m from the recorded coordinate")
        print(f"  {flag} {code:10} {town:20} decoded {lat:.5f},{lon:.5f} vs recorded "
              f"{r['lat']:.5f},{r['lon']:.5f} -> {d:6.1f} m")
    if errs:
        errs.sort()
        print(f"\n  n={len(errs)}  median={errs[len(errs)//2]:.1f} m  "
              f"max={errs[-1]:.1f} m  under 30 m: {sum(1 for e in errs if e < 30)}/{len(errs)}")

print()
if fails:
    print(f"{len(fails)} FAILURES:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("plus code decoder verified")
