"""Deterministic self-audit of the harmonized store.

These are the checks that do not need an agent because they have a mechanical answer: a name
still in catalogue form, a status value from a source not entitled to assert it, two records
that are plainly the same place, a coordinate that cannot be where it says. Agent-based
verification (does this place really exist, is this really its date) is a separate wave.

Run: python src/audit.py        prints a report and writes data/out/audit.json
Exit code 1 if any HIGH finding is present, so it can gate a build.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import geo  # noqa: E402
import hebrew as he  # noqa: E402
import schema as sc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out"

findings: list[dict] = []


def add(severity, kind, msg, site=None, detail=None):
    findings.append({"severity": severity, "kind": kind, "message": msg,
                     "site_id": (site or {}).get("id"), "site_name": (site or {}).get("name"),
                     "detail": detail})


# --------------------------------------------------------------------------------------
# 1. names
# --------------------------------------------------------------------------------------
# Words that are a DESIGNATION, not a name. A record whose whole name is one of these has no
# real name and should not be a map point.
DESIGNATION_ONLY = {
    "מבנה לשימור", "בלוק מבנה לשימור", "אתר לשימור", "אתר/מתחם לשימור", "אתר מוכרז",
    "אתר עתיקות", "שטח עתיקות/הסטורי לשימור", "אתר עתיקות/אתר הסטורי", "שיקום/התחדשות",
    "רשת חלוקה", "שימור נופי", "ללא שם", "גן לאומי", "שמורת טבע",
}
# Common Hebrew place words, used to detect a name that was stored reversed. The source layer
# tmm_park_or_reserve ships a NAMEL column holding deliberately reversed text.
HEB_MARKERS = ("תל ", "חורבת", "בית ", "גן ", "לאומי", "שמורת", "נחל ", "עין ", "כפר ",
               "מערת", "קבר", "חירבת", "אתר", "מוזיאון", "ארכיון")
LATIN = re.compile(r"[A-Za-z]{4,}")
INVERTED_TAIL = re.compile(r",\s*(ח'|ח|תל|ע'|חר'|כ'|ג'|אל|מערת)\s*$")
TRAILING_NUM = re.compile(r"\s\d{3,6}$")


def reversed_looking(name: str) -> bool:
    """True when the reverse of the string looks more like Hebrew than the string does.

    Requires whole-word matches and at least two of them: matching on substrings flagged
    'פנטהריי - מקום לתנועה ויצירה' because its reverse happens to contain the letters of 'תל'
    inside a longer word.
    """
    def score(s: str) -> int:
        words = set(re.split(r"[\s\-־,.()]+", s))
        return sum(1 for m in HEB_MARKERS if m.strip() in words)
    return score(name[::-1]) >= 2 and score(name[::-1]) > score(name)


def audit_names(sites):
    counts = Counter()
    for s in sites:
        n = (s.get("name") or "").strip()
        if not n:
            add("high", "name_missing", "אין שם לאתר", s)
            counts["missing"] += 1
            continue
        # Compare on the display form, not on he.key: the key strips generic words, so a real
        # place name made of generic words ('שריד', the kibbutz) collided with 'אתר עתיקות'.
        if he.display(n) in {he.display(d) for d in DESIGNATION_ONLY}:
            add("high", "name_is_designation",
                f"השם הוא סוג ייעוד ולא שם אתר: {n!r}", s)
            counts["designation"] += 1
        if INVERTED_TAIL.search(n):
            add("medium", "name_inverted",
                f"השם נשאר בצורת הקטלוג ההפוכה: {n!r}", s)
            counts["inverted"] += 1
        m = TRAILING_NUM.search(n)
        # A trailing year is part of the name ('בית הילדים 1931'); a trailing site number is not.
        if m and not (1000 <= int(m.group(0)) <= 2100):
            add("medium", "name_trailing_number", f"מספר אתר נשאר בשם: {n!r}", s)
            counts["trailing_number"] += 1
        if reversed_looking(n):
            add("high", "name_reversed", f"השם נראה שמור בסדר הפוך: {n!r}", s)
            counts["reversed"] += 1
        if LATIN.search(n) and not re.search(r"[֐-׿]", n):
            add("medium", "name_latin_only", f"שם לטיני בשדה השם העברי: {n!r}", s)
            counts["latin_only"] += 1
        # A repeated 'בית' or 'עין' is ordinary Hebrew ('בית הקומתיים בית ביטחון'), so only a
        # repeated CONTENT word is worth reporting.
        toks = [t for t in n.split() if t not in ("בית", "עין", "כפר", "תל", "גן", "של", "ה")]
        if len(toks) >= 2 and len(set(toks)) < len(toks):
            add("low", "name_repeated_word", f"מילה כפולה בשם: {n!r}", s)
            counts["repeated_word"] += 1
        if len(n) > 90:
            add("low", "name_too_long", f"השם ארוך מדי ({len(n)} תווים), נראה כמו תיאור", s)
            counts["too_long"] += 1
    return dict(counts)


# --------------------------------------------------------------------------------------
# 2. missed duplicates
# --------------------------------------------------------------------------------------
def audit_duplicates(sites, max_m=400.0, min_sim=0.78):
    pts = [s for s in sites if s.get("lat") is not None]
    cell = 0.006
    grid = defaultdict(list)
    for s in pts:
        grid[(int(s["lat"] / cell), int(s["lon"] / cell))].append(s)
    seen = set()
    dupes = []
    for s in pts:
        ci, cj = int(s["lat"] / cell), int(s["lon"] / cell)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for t in grid.get((ci + di, cj + dj), ()):
                    if t is s:
                        continue
                    key = tuple(sorted((s["id"], t["id"])))
                    if key in seen:
                        continue
                    seen.add(key)
                    d = geo.haversine_m(s["lat"], s["lon"], t["lat"], t["lon"])
                    if d > max_m:
                        continue
                    sim = max(he.similarity(s.get("name"), t.get("name")),
                              max((he.similarity(a["name"], t.get("name"))
                                   for a in (s.get("names_alt") or [])), default=0.0))
                    if sim < min_sim:
                        continue
                    shared = set(x["source_id"] for x in s["sources"]) & \
                             set(x["source_id"] for x in t["sources"])
                    dupes.append({"a": s["id"], "a_name": s.get("name"),
                                  "b": t["id"], "b_name": t.get("name"),
                                  "distance_m": round(d, 1), "name_similarity": round(sim, 3),
                                  "same_source_only": bool(shared),
                                  "a_iaa": s.get("iaa_site_id"), "b_iaa": t.get("iaa_site_id")})
    # Only surface pairs a human would actually act on: close together, near-identical names, and
    # drawn from different sources so it is not just one source listing two sub-features. The
    # rest are counted, since a silently truncated list would read as "nothing to check".
    dupes.sort(key=lambda x: (-x["name_similarity"], x["distance_m"]))
    # Pairs already cross-linked as co-located are handled and not re-reported as duplicates.
    linked = set()
    for s in pts:
        for rel in (s.get("related_ids") or []):
            linked.add(tuple(sorted((s["id"], rel["id"]))))
    actionable = [x for x in dupes if x["name_similarity"] >= 0.88
                  and x["distance_m"] <= 250 and not x["same_source_only"]
                  and tuple(sorted((x["a"], x["b"]))) not in linked]
    for x in actionable[:30]:
        add("medium", "possible_duplicate",
            f"ייתכן שאותו מקום מופיע פעמיים: {x['a_name']!r} ו-{x['b_name']!r} "
            f"במרחק {x['distance_m']} מטר, דמיון שם {x['name_similarity']}", None, x)
    return {"candidate_pairs_examined": len(seen), "suspicious": len(dupes),
            "actionable": len(actionable), "surfaced": min(30, len(actionable)),
            "note": "actionable = same place likely, different sources, within 250 m"}


# --------------------------------------------------------------------------------------
# 3. status provenance
# --------------------------------------------------------------------------------------
def audit_provenance(sites):
    bad = Counter()
    for s in sites:
        prov = s.get("provenance") or {}
        for axis, allowed in sc.AUTHORITY_ONLY.items():
            val = s.get(axis)
            if val in (None, "unknown"):
                continue
            srcs = set(prov.get(axis) or [])
            if not srcs:
                add("high", "status_without_provenance",
                    f"לציר {axis} יש ערך {val!r} ללא מקור מתועד", s)
                bad["no_provenance"] += 1
            elif not srcs <= allowed:
                add("high", "status_wrong_authority",
                    f"לציר {axis} יש ערך {val!r} ממקור שאינו הסמכות: {sorted(srcs - allowed)}", s)
                bad["wrong_authority"] += 1
        # Every non-unknown value on any axis should trace to something.
        for axis in sc.STATUS_AXES:
            if s.get(axis) not in (None, "unknown") and not (prov.get(axis) or []):
                bad["untraced_any_axis"] += 1
    return dict(bad)


# --------------------------------------------------------------------------------------
# 4. geometry and jurisdiction
# --------------------------------------------------------------------------------------
def audit_geometry(sites):
    jur = None
    bp = ROOT / "data" / "raw" / "boundary_emek_yizrael.geojson"
    if bp.exists():
        jur = geo.Jurisdiction.from_geojson(bp)
    stats = Counter()
    for s in sites:
        lat, lon = s.get("lat"), s.get("lon")
        if lat is None:
            stats["no_coordinate"] += 1
            if s.get("in_council") is not None:
                add("medium", "jurisdiction_without_coordinate",
                    "אין קואורדינטה אבל נקבע שיוך לגבול", s)
            continue
        if not (geo.ISRAEL["lat"][0] <= lat <= geo.ISRAEL["lat"][1]
                and geo.ISRAEL["lon"][0] <= lon <= geo.ISRAEL["lon"][1]):
            add("high", "coordinate_outside_israel",
                f"הקואורדינטה מחוץ לישראל: {lat}, {lon}", s)
            stats["outside_israel"] += 1
            continue
        if jur is not None:
            d = jur.signed_distance_m(lat, lon)
            if (d > 0) != bool(s.get("in_council")):
                add("high", "jurisdiction_mismatch",
                    f"in_council={s.get('in_council')} אבל המרחק מהגבול הוא {d}", s)
                stats["jurisdiction_mismatch"] += 1
            if s.get("dist_to_boundary_m") is not None and abs(d - s["dist_to_boundary_m"]) > 2:
                add("medium", "distance_stale",
                    f"dist_to_boundary_m={s['dist_to_boundary_m']} אבל בחישוב מחדש {d}", s)
        ix, iy = s.get("itm_x"), s.get("itm_y")
        if ix is not None:
            try:
                rlat, rlon = geo.to_wgs84(ix, iy, "itm", geo.PLAUSIBLE)
                if geo.haversine_m(lat, lon, rlat, rlon) > 60:
                    add("high", "itm_disagrees_with_wgs84",
                        f"ITM ו-WGS84 באותה רשומה מצביעים על מקומות שונים "
                        f"({int(geo.haversine_m(lat, lon, rlat, rlon))} מטר)", s)
                    stats["itm_mismatch"] += 1
            except geo.CoordError as e:
                add("medium", "itm_implausible", f"ITM לא סביר: {e}", s)
    return dict(stats)


# --------------------------------------------------------------------------------------
# 5. classification coherence
# --------------------------------------------------------------------------------------
def audit_classification(sites):
    stats = Counter()
    for s in sites:
        cat = s.get("category")
        if cat not in sc.CATEGORIES:
            add("high", "bad_category", f"קטגוריה לא מוכרת: {cat!r}", s)
            continue
        if cat not in (s.get("categories") or []):
            add("medium", "category_not_in_categories",
                f"הקטגוריה הראשית {cat!r} אינה ברשימת הקטגוריות {s.get('categories')}", s)
        t = s.get("type")
        if t and t not in sc.SITE_TYPES:
            add("medium", "bad_type", f"טיפוס לא מוכר: {t!r}", s)
        bad_periods = [p for p in (s.get("periods") or []) if p not in sc.PERIOD_HE]
        if bad_periods:
            add("high", "bad_period", f"תקופות לא מוכרות: {bad_periods}", s)
        era_p = sc.era_from_periods(s.get("periods") or [])
        if era_p == "historic" and cat == "archaeological" and s.get("reg_antiquity") in (None, "unknown"):
            add("medium", "category_contradicts_periods",
                "מסווג ארכאולוגי אבל כל התקופות שלו אחרי 1700 ואין רישום עתיקות", s)
            stats["arch_without_pre1700"] += 1
        if era_p == "archaeological" and cat == "historic":
            add("medium", "historic_with_pre1700_periods",
                f"מסווג היסטורי אבל יש לו תקופות לפני 1700: {s.get('periods')}", s)
            stats["historic_with_pre1700"] += 1
        for axis, meta in sc.STATUS_AXES.items():
            if s.get(axis) in (None, "unknown"):
                continue
            if cat not in meta["applies_to"]:
                add("low", "status_axis_not_applicable",
                    f"לציר {axis} יש ערך אף שהוא אינו חל על קטגוריה {cat}", s)
                stats["axis_not_applicable"] += 1
            if s[axis] not in meta["values"]:
                add("high", "bad_status_value",
                    f"ערך לא מוכר בציר {axis}: {s[axis]!r}", s)
        expected = sc.registered_summary(s)
        if s.get("reg_summary") != expected:
            add("medium", "reg_summary_stale",
                f"reg_summary={s.get('reg_summary')!r} אבל החישוב נותן {expected!r}", s)
    return dict(stats)


# --------------------------------------------------------------------------------------
def main():
    sites = json.loads((OUT / "sites.json").read_text(encoding="utf-8"))
    report = {
        "sites": len(sites),
        "names": audit_names(sites),
        "duplicates": audit_duplicates(sites),
        "provenance": audit_provenance(sites),
        "geometry": audit_geometry(sites),
        "classification": audit_classification(sites),
    }
    sev = Counter(f["severity"] for f in findings)
    report["findings_by_severity"] = dict(sev)
    report["findings_by_kind"] = dict(Counter(f["kind"] for f in findings))
    report["findings"] = findings
    (OUT / "audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                    encoding="utf-8")

    print(json.dumps({k: v for k, v in report.items() if k != "findings"},
                     ensure_ascii=False, indent=1))
    print()
    for kind, n in Counter(f["kind"] for f in findings).most_common():
        ex = next(f for f in findings if f["kind"] == kind)
        print(f"  [{ex['severity']:6}] {kind:34} x{n:<5} e.g. {(ex['site_name'] or '')[:34]!r}: "
              f"{ex['message'][:90]}")
    return 1 if sev.get("high") else 0


if __name__ == "__main__":
    sys.exit(main())
