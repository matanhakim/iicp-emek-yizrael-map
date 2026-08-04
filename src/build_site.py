"""Build the static site payload from the harmonized store.

The site never hardcodes vocabulary. Every label, status value, tone and period span is
emitted here from src/schema.py, so the Hebrew in the interface and the Hebrew in the
pipeline cannot drift apart.

Two payloads, because the map should paint before the audit trail finishes downloading:
  site/data/sites.json    every resolved field, no claims. This is what the map loads.
  site/data/claims.json   the per-field claim log keyed by site id, fetched lazily when a
                          visitor opens the evidence section of a detail panel.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import hebrew as he  # noqa: E402
import paths  # noqa: E402
import schema as sc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "out"
SITE_DATA = ROOT / "site" / "data"

# Fields the map needs on every point. Everything else rides along in `rest`.
CORE = [
    "id", "name", "name_en", "category", "categories", "type", "periods",
    "year_from", "year_to", "date_text", "era_basis", "lat", "lon",
    "locality", "in_council", "dist_to_boundary_m", "near_boundary",
    "nearest_settlement", "nearest_settlement_km", "location_precision",
    "confidence", "status_completeness", "needs_review", "source_count", "reg_summary",
    *sc.STATUS_AXES.keys(),
]

REST = [
    "names_alt", "description", "itm_x", "itm_y", "locality_code", "overlay_notes",
    "related_ids",
    "in_council_method", "excavation_years", "excavation_licenses", "excavators",
    "address", "phone", "email", "website", "hours_text", "admission", "operator",
    "founded_year", "wikidata_qid", "wikipedia_he", "image_url", "image_credit",
    "iaa_site_id", "blue_sign_number", "osm_id", "external_links",
    "sources", "provenance", "conflicts", "confidence_components",
    "status_axes_known", "status_axes_applicable",
    "location_spread_m", "verification", "review_reasons",
]

# A site whose resolved point lands outside the council is kept in the internal store as the
# record of an examined-and-excluded candidate, but only the genuinely arguable ones travel
# to the public payload. Beyond this distance the point is simply a neighbour's site, not a
# judgement call, and shipping hundreds of them would bloat the download and blur what the
# map is about.
PUBLISH_OUTSIDE_WITHIN_M = 300.0

# Contact details on a private-sector record can belong to a person rather than an
# institution. Under the Privacy Protection Law those stay in the internal store and are
# withheld from the published page; address and website still travel, since those identify
# the venue rather than the individual.
REDACT_WHEN_PRIVATE = ("phone", "email")


def vocab() -> dict:
    return {
        "categories": sc.CATEGORIES,
        "site_types": sc.SITE_TYPES,
        "periods": [
            {"key": k, "he": he, "from": a, "to": b,
             "era": "archaeological" if a < sc.ANTIQUITY_CUTOFF_YEAR else "historic"}
            for k, he, a, b in sc.PERIODS
        ],
        "antiquity_cutoff": sc.ANTIQUITY_CUTOFF_YEAR,
        "status_axes": {
            a: {"he": m["he"], "applies_to": m["applies_to"],
                "values": [{"key": v, "he": h, "tone": sc.tone(a, v)} for v, h in m["values"].items()]}
            for a, m in sc.STATUS_AXES.items()
        },
        "reg_summary": {
            "registered": "רשום או מוכרז",
            "not_registered": "אינו רשום",
            "unknown": "מצב הרישום לא ידוע",
        },
        "location_precision": sc.LOCATION_PRECISION,
        "era_basis": sc.ERA_BASIS,
        "sources": {k: v["he"] for k, v in sc.SOURCES.items()},
        "registered_positive": {k: sorted(v) for k, v in sc.REGISTERED_POSITIVE.items()},
    }


def run() -> dict:
    paths.ensure_writable()
    sites = json.loads((OUT / "sites.json").read_text(encoding="utf-8"))
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    # Settlement names must be registered before is_generic_name can recognise one.
    he.add_locality_heads(
        [s.get("locality") for s in sites if s.get("locality")]
        + [s.get("nearest_settlement") for s in sites if s.get("nearest_settlement")])

    slim, claims, detail = [], {}, {}
    dropped_far, redacted = 0, 0
    for s in sites:
        d = s.get("dist_to_boundary_m")
        if s.get("in_council") is False and d is not None and d < -PUBLISH_OUTSIDE_WITHIN_M:
            dropped_far += 1
            continue

        rec = {k: s.get(k) for k in CORE}

        # A generic name is not usable on its own in a list: the valley has a בית העם in every
        # moshav, and five rows reading 'בית העם' are indistinguishable even though they are five
        # different buildings. The settlement is appended for display only; `name` keeps what the
        # sources actually said.
        place = s.get("locality") or s.get("nearest_settlement")
        if s.get("name") and place and he.is_generic_name(s["name"]) \
                and he.key(place) not in he.key(s["name"]):
            rec["display_name"] = f"{s['name']}, {place}"
            rec["display_name_is_qualified"] = True
        else:
            rec["display_name"] = s.get("name")
        rec["rest"] = {k: s.get(k) for k in REST if s.get(k) not in (None, [], {}, "")}

        private = any((e or {}).get("contact_is_private_sector")
                      for e in (s.get("extra") or {}).values())
        if private:
            hit = False
            for f in REDACT_WHEN_PRIVATE:
                if rec["rest"].pop(f, None) is not None:
                    hit = True
            rec["rest"]["contact_withheld"] = True
            redacted += hit

        slim.append(rec)
        if s.get("claims"):
            claims[s["id"]] = s["claims"]
        # The per-source `extra` payload is the richest part of the record and the heaviest,
        # so it rides in the lazily fetched file next to the claim log rather than in the
        # payload the map needs before it can paint.
        if s.get("extra"):
            ex = {k: dict(v) for k, v in s["extra"].items() if v}
            for v in ex.values():
                v.pop("contact_is_private_sector", None)
            detail[s["id"]] = ex

    payload = {
        "generated": None,  # stamped by the caller; scripts must not read the clock
        "council": "מועצה אזורית עמק יזרעאל",
        "vocab": vocab(),
        "sites": slim,
    }
    (SITE_DATA / "sites.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (SITE_DATA / "claims.json").write_text(
        json.dumps({"claims": claims, "detail": detail}, ensure_ascii=False,
                   separators=(",", ":")), encoding="utf-8")

    # The CBS polygon is drawn at survey precision, 1.3 MB of vertices that no screen can
    # resolve. The published copy is simplified to a 10 m tolerance purely for DRAWING; every
    # point-in-polygon decision in the pipeline uses the untouched original, so simplifying
    # here cannot move a site in or out of the council.
    bnd = paths.boundary_file()
    bnd_stats = None
    if bnd:
        import geopandas as gpd
        from shapely.geometry import mapping
        from shapely.geometry import shape as shp_shape

        # geopandas cannot read a .gz GeoJSON directly, so the frozen copy is loaded as JSON.
        doc = paths.read_json(bnd)
        feats = doc["features"] if doc.get("type") == "FeatureCollection" else [doc]
        gdf = gpd.GeoDataFrame(
            geometry=[shp_shape(f["geometry"]) for f in feats if f.get("geometry")],
            crs=4326).to_crs(2039)
        simple = gdf.geometry.simplify(10, preserve_topology=True).to_crs(4326)
        before = sum(len(str(mapping(g))) for g in gdf.to_crs(4326).geometry)
        fc = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"note": "simplified to 10 m for display only"},
             "geometry": mapping(g)} for g in simple]}
        (SITE_DATA / "boundary.geojson").write_text(
            json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        bnd_stats = {"kb": round((SITE_DATA / "boundary.geojson").stat().st_size / 1024, 1),
                     "source": str(bnd.name)}
        del before

    stats_p = OUT / "harmonize_stats.json"
    if stats_p.exists():
        shutil.copyfile(stats_p, SITE_DATA / "stats.json")

    return {
        "sites_published": len(slim),
        "sites_in_store": len(sites),
        "dropped_far_outside_council": dropped_far,
        "contact_redacted_private_sector": redacted,
        "with_claims": len(claims),
        "sites_json_kb": round((SITE_DATA / "sites.json").stat().st_size / 1024, 1),
        "claims_json_kb": round((SITE_DATA / "claims.json").stat().st_size / 1024, 1),
        "boundary": bnd_stats,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=1))
