"""Cross-source harmonization: match, cluster, merge, score.

Input: one JSON array per source in data/interim/, each element a CLAIM RECORD emitted by
that source's adapter (see CLAIM_RECORD below). Output: data/out/sites.json, where each
element is one real-world site carrying its resolved values, the provenance of every
resolved value, every raw claim including the ones that lost, and a confidence breakdown.

The three decisions worth arguing about, made explicit here rather than buried:

1. WHEN ARE TWO ROWS THE SAME PLACE. Name similarity alone is hopeless in Hebrew heritage
   data and distance alone merges neighbouring ruins. So: a distance gate that depends on
   the category pair, a name score from src/hebrew.py that ignores generic toponym heads,
   and a linear blend of the two. Above 0.82 merge, 0.60 to 0.82 goes to a review queue a
   verification agent reads, below that no match. A shared strong identifier (IAA site
   number, Wikidata QID, OSM id, blue-sign number) merges regardless of score, and two
   DIFFERENT strong identifiers of the same kind block a merge regardless of score.

2. WHICH VALUE WINS. Per-field source precedence from schema.PRECEDENCE, not a global
   ranking, because the authority differs by field: the IAA table owns archaeological
   coordinates, the Conservation Council owns conservation status, the institution's own
   website owns whether it is open. Legal-status fields are AUTHORITY_ONLY: a value from
   any other source is discarded rather than used, since a wrong legal status is worse
   than an admitted gap.

3. HOW CONFIDENT WE ARE. Four components (existence, location, category, status) combined
   with fixed weights. Existence uses the complement of the product of source
   unreliabilities, so independent agreement raises it fast while one weak source cannot.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import geo
import hebrew as he
import paths
import schema as sc

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "out"

# The contract every adapter must satisfy.
CLAIM_RECORD = {
    "source_id": "key in schema.SOURCES",
    "record_id": "stable id within the source",
    "url": "source url for this specific record, or the source landing page",
    "retrieved": "YYYY-MM-DD",
    "name": "Hebrew name as the source gives it",
    "names_alt": "list of other names the source gives",
    "name_en": "optional",
    "lat/lon": "WGS84 or None",
    "itm_x/itm_y": "native projected coordinate or None",
    "location_precision": "key in schema.LOCATION_PRECISION",
    "category_hint": "archaeological|historic|culture|None",
    "type": "key in schema.SITE_TYPES or None",
    "periods": "list of keys in schema.PERIOD_HE",
    "year_from/year_to/date_text": "optional",
    "locality": "settlement name or None",
    "statuses": "dict of schema.STATUS_AXES key -> value, ONLY what the source states",
    "practical": "dict of address/phone/email/website/hours_text/admission/operator/founded_year",
    "ids": "dict of iaa_site_id/wikidata_qid/osm_id/blue_sign_number",
    "description": "optional free text",
    "extra": "dict of anything else worth showing",
    "raw": "the untouched source row",
}

STRONG_IDS = ("iaa_site_id", "wikidata_qid", "osm_id", "blue_sign_number")

# Distance gate in metres by category pair. Archaeological site records are centroids of
# areas and drift between sources; a museum has a street address and should not.
GATE = {
    ("culture", "culture"): 200.0,
    ("archaeological", "archaeological"): 400.0,
    ("historic", "historic"): 300.0,
    ("archaeological", "historic"): 350.0,
    ("archaeological", "culture"): 250.0,
    ("historic", "culture"): 250.0,
}
DEFAULT_GATE = 300.0
REVIEW_GATE_FACTOR = 3.0  # a strong name match this far out is a review item, not a merge

MERGE_AT = 0.82
REVIEW_AT = 0.60
NAME_ONLY_MERGE_AT = 0.93          # no geometry, but the locality agrees
NAME_ONLY_NO_LOCALITY_AT = 0.965   # no geometry and no locality either: a stricter bar

W_NAME, W_DIST = 0.60, 0.40

RELIABILITY = {1: 0.92, 2: 0.90, 3: 0.85, 4: 0.75, 5: 0.75, 6: 0.65}

PRECISION_CONF = {
    "exact": 0.90,
    "approx_100m": 0.80,
    "approx_500m": 0.60,
    "locality_centroid": 0.30,
    "unknown": 0.45,
}

# Confidence answers "is this a real place, is it here, and is it the era we say" and
# nothing else. Status completeness used to be blended in at 10%, which quietly punished a
# perfectly certain site for having an unrecorded opening time. Completeness is now reported
# separately, as `status_completeness`, and the map shows it as its own metric.
CONF_WEIGHTS = {"existence": 0.45, "location": 0.35, "category": 0.20}


# --------------------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------------------

def load_claims(interim: Path = INTERIM) -> list[dict]:
    """Read every adapter output. Adapters write <source_id>.claims.json."""
    claims = []
    for p in sorted(interim.glob("*.claims.json")):
        rows = json.loads(p.read_text(encoding="utf-8"))
        for i, r in enumerate(rows):
            r.setdefault("record_id", f"{p.stem}-{i}")
            if r.get("source_id") not in sc.SOURCES:
                raise ValueError(f"{p.name} row {i}: unknown source_id {r.get('source_id')!r}")
            claims.append(r)
    return claims


def _gate(a: dict, b: dict) -> float:
    ca = a.get("category_hint") or "archaeological"
    cb = b.get("category_hint") or "archaeological"
    return GATE.get((ca, cb)) or GATE.get((cb, ca)) or DEFAULT_GATE


def _dist(a: dict, b: dict) -> float | None:
    if a.get("lat") is None or b.get("lat") is None:
        return None
    return geo.haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])


def _names(r: dict) -> list[str]:
    out = [r.get("name")] + list(r.get("names_alt") or [])
    return [n for n in out if n]


def name_score(a: dict, b: dict) -> float:
    """Best similarity over the cross product of both records' names and aliases."""
    best = 0.0
    for na in _names(a):
        for nb in _names(b):
            best = max(best, he.similarity(na, nb))
            if best >= 0.999:
                return 1.0
    return best


def shared_strong_id(a: dict, b: dict) -> str | None:
    ia, ib = a.get("ids") or {}, b.get("ids") or {}
    for k in STRONG_IDS:
        va, vb = ia.get(k), ib.get(k)
        if va and vb and str(va).strip() == str(vb).strip():
            return k
    return None


def conflicting_strong_id(a: dict, b: dict) -> str | None:
    ia, ib = a.get("ids") or {}, b.get("ids") or {}
    for k in STRONG_IDS:
        va, vb = ia.get(k), ib.get(k)
        if va and vb and str(va).strip() != str(vb).strip():
            return k
    return None


def pair_score(a: dict, b: dict) -> tuple[float, dict]:
    """Return (score, why). why is kept verbatim in the review queue so a human can judge."""
    ns = name_score(a, b)
    d = _dist(a, b)
    gate = _gate(a, b)
    why = {"name_score": round(ns, 4), "distance_m": None if d is None else round(d, 1), "gate_m": gate}

    # Two records whose types belong to different categories are probably not the same
    # thing even when they share a name and a spot: the moshav Beit She'arim as a designated
    # heritage layout is not Khirbat Beit She'arim the antiquities site. Never auto-merge
    # those; send them to review where a verifier can look.
    ta, tb = a.get("type"), b.get("type")
    cross_cat = False
    if ta in sc.SITE_TYPES and tb in sc.SITE_TYPES:
        ca, cb = sc.SITE_TYPES[ta]["cat"], sc.SITE_TYPES[tb]["cat"]
        cross_cat = bool(ca and cb and ca != cb)
    why["cross_category_types"] = cross_cat

    if d is None:
        # No geometry on either side, so the name has to carry the whole decision.
        # A locality that agrees lowers the bar; a locality that is simply unknown on one
        # side must not block the match, because the richest status source in this project
        # (the IAA conservation survey) has no locality column at all. An outright
        # DISAGREEMENT still blocks.
        la, lb = he.key(a.get("locality")), he.key(b.get("locality"))
        both = bool(la and lb)
        loc_sim = he.similarity(a.get("locality"), b.get("locality")) if both else None
        loc_ok = bool(both and loc_sim >= 0.85)
        loc_conflict = bool(both and loc_sim < 0.60)
        generic = he.is_generic_name(a.get("name")) or he.is_generic_name(b.get("name"))
        why["mode"] = "name_only"
        why["locality_agrees"] = loc_ok
        why["locality_unknown"] = not both
        why["generic_name"] = generic
        if loc_conflict or cross_cat:
            return min(ns, 0.59 if loc_conflict else 0.79), why

        # A generic name with no geometry may only merge when the locality POSITIVELY agrees.
        # Without this, 'בית העם' in Tel Adashim merged with 'בית העם' in Alonei Abba because
        # one side happened to carry no locality at all, and the valley has one in every moshav.
        if generic and not loc_ok:
            return min(ns, 0.79), why

        bar = NAME_ONLY_MERGE_AT if loc_ok else NAME_ONLY_NO_LOCALITY_AT
        if ns >= bar:
            why["merged_on_name_alone"] = True
            return 0.84, why
        return min(ns, 0.79), why

    if d > gate * REVIEW_GATE_FACTOR:
        why["mode"] = "too_far"
        return 0.0, why

    dist_score = max(0.0, 1.0 - d / gate)
    score = W_NAME * ns + W_DIST * dist_score
    why["mode"] = "blended"
    why["dist_score"] = round(dist_score, 4)
    if d > gate:
        # Outside the gate but a strong name match: never auto-merge, always review.
        why["mode"] = "beyond_gate"
        score = min(score, 0.79) if ns >= 0.85 else 0.0
    if cross_cat:
        score = min(score, 0.79)
    return round(score, 4), why


# --------------------------------------------------------------------------------------
# clustering
# --------------------------------------------------------------------------------------

class Union:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def join(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.p[rj] = ri


def _cells(lat: float, lon: float, size_deg: float) -> list[tuple[int, int]]:
    ci, cj = int(lat / size_deg), int(lon / size_deg)
    return [(ci + di, cj + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1)]


def candidate_pairs(claims: list[dict]) -> list[tuple[int, int]]:
    """Spatial grid blocking plus a loose-name index, so records without coordinates still meet."""
    cell = 0.01  # about 1.1 km, comfortably larger than every gate
    grid: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, r in enumerate(claims):
        if r.get("lat") is not None:
            grid[(int(r["lat"] / cell), int(r["lon"] / cell))].append(i)

    pairs: set[tuple[int, int]] = set()
    for i, r in enumerate(claims):
        if r.get("lat") is None:
            continue
        for c in _cells(r["lat"], r["lon"], cell):
            for j in grid.get(c, ()):
                if j > i:
                    pairs.add((i, j))

    by_loose: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(claims):
        for n in _names(r):
            lk = he.loose_key(n)
            if len(lk) >= 3:
                by_loose[lk].append(i)
    for idxs in by_loose.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = sorted((idxs[a], idxs[b]))
                if i != j:
                    pairs.add((i, j))
    return sorted(pairs)


def cluster(claims: list[dict]) -> tuple[list[list[int]], list[dict], list[dict]]:
    """Return (clusters, review_queue, blocked).

    Merges are applied GREEDILY in descending score order under one structural constraint:
    a cluster may not end up holding two records from the same source unless those two look
    like duplicates of each other. Without that constraint union-find transitivity fuses
    unrelated places: five moshavim each have a hall called בית העם, none of them carries a
    coordinate, and all five match one OSM record called בית העם, so A-X and B-X quietly
    make A and B the same building. The constraint catches exactly that and sends the losing
    pair to review instead.
    """
    u = Union(len(claims))
    review, blocked = [], []
    forced: dict[tuple[int, int], str] = {}
    members: dict[int, list[int]] = {i: [i] for i in range(len(claims))}
    pair_cache: dict[tuple[int, int], float] = {}

    def same_source_ok(ri: int, rj: int) -> tuple[bool, str | None]:
        """Would joining these two roots put two non-duplicate rows of one source together?"""
        for a in members[ri]:
            for b in members[rj]:
                if claims[a]["source_id"] != claims[b]["source_id"]:
                    continue
                k = (min(a, b), max(a, b))
                if k not in pair_cache:
                    pair_cache[k] = pair_score(claims[a], claims[b])[0]
                if pair_cache[k] < 0.97:
                    return False, (f"would put two {claims[a]['source_id']} rows in one site: "
                                   f"{claims[a].get('name')!r} and {claims[b].get('name')!r}")
        return True, None

    def try_join(i: int, j: int, why_ctx: dict, *, force: bool = False) -> bool:
        ri, rj = u.find(i), u.find(j)
        if ri == rj:
            return True
        # A shared official identifier is definitive and overrides the same-source guard: a
        # declared antiquity site is published as several polygon parts in one layer, and all
        # of them carry its site number. The guard exists to stop transitive fusion of
        # unrelated places matched on a common name, not to argue with an id.
        ok, reason = (True, None) if force else same_source_ok(ri, rj)
        if not ok:
            review.append({"a": _brief(claims[i]), "b": _brief(claims[j]),
                           "score": why_ctx.get("score"), "why": why_ctx.get("why"),
                           "kind": "blocked_by_same_source_constraint", "reason": reason})
            return False
        u.join(i, j)                        # Union.join makes ri the surviving root
        members[ri] = members[ri] + members[rj]
        members.pop(rj, None)
        return True

    name_only_merges = []
    to_merge: list[tuple[float, int, int, dict, bool]] = []
    for i, j in candidate_pairs(claims):
        a, b = claims[i], claims[j]
        score, why = pair_score(a, b)

        # Same source first: a source's own two rows are two sites, so neither an id
        # conflict nor a high score between them is interesting. Checking this before the
        # conflict test keeps the blocked list free of same-source noise.
        if a["source_id"] == b["source_id"]:
            if score >= 0.97:
                review.append({"a": _brief(a), "b": _brief(b), "score": score, "why": why,
                               "kind": "possible_duplicate_within_source"})
            continue

        sid = shared_strong_id(a, b)
        conflict = conflicting_strong_id(a, b)

        if conflict and not sid:
            # A differing official identifier normally blocks a merge, because the state's
            # numbering is a fact and two adjacent declarations really are two declarations.
            # But at ten metres with the same name it is one place carried under two
            # declaration numbers, and refusing to merge just shows it twice. So the block is
            # narrowed to everything except that case, and both numbers are kept.
            d = why.get("distance_m")
            if d is not None and d <= 60 and why.get("name_score", 0) >= 0.93:
                to_merge.append((1.5, i, j, {**why, "merged_despite_id_conflict": conflict}, False))
                continue
            if score >= REVIEW_AT:
                blocked.append({"a": _brief(a), "b": _brief(b), "reason": f"different {conflict}",
                                "score": score, "why": why})
            continue

        if sid:
            forced[(i, j)] = sid
            # A shared strong identifier outranks the score, so it is queued at the top.
            to_merge.append((2.0, i, j, why, False))
            continue

        if score >= MERGE_AT:
            to_merge.append((score, i, j, why, bool(why.get("merged_on_name_alone"))))
        elif score >= REVIEW_AT:
            review.append({"a": _brief(a), "b": _brief(b), "score": score, "why": why,
                           "kind": "borderline_match"})

    # Strongest evidence first, so a confident merge claims the cluster before a weak one
    # can drag an unrelated record into it.
    to_merge.sort(key=lambda t: -t[0])
    for score, i, j, why, name_only in to_merge:
        joined = try_join(i, j, {"score": score, "why": why}, force=(score >= 2.0))
        if joined and name_only:
            name_only_merges.append((i, j))

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(claims)):
        groups[u.find(i)].append(i)
    # Mark the clusters that were joined without any geometry, so the verification wave and
    # the map both know the merge rests on a name alone.
    nameonly_roots = {u.find(i) for i, _ in name_only_merges}
    for root in nameonly_roots:
        for i in groups[root]:
            claims[i]["_merged_on_name_alone"] = True
    return list(groups.values()), review, blocked


def _brief(r: dict) -> dict:
    return {
        "source_id": r["source_id"], "record_id": r.get("record_id"), "name": r.get("name"),
        "lat": r.get("lat"), "lon": r.get("lon"), "locality": r.get("locality"),
        "category_hint": r.get("category_hint"), "url": r.get("url"),
    }


# --------------------------------------------------------------------------------------
# merging
# --------------------------------------------------------------------------------------

def _rank(source_id: str) -> int:
    return sc.SOURCES[source_id]["rank"]


def _ordered(members: list[dict], field_key: str) -> list[dict]:
    """Members sorted by the precedence rule for this field, strongest first."""
    order = sc.PRECEDENCE.get(field_key)
    if order:
        pos = {s: i for i, s in enumerate(order)}
        return sorted(members, key=lambda r: (pos.get(r["source_id"], 99), _rank(r["source_id"])))
    return sorted(members, key=lambda r: _rank(r["source_id"]))


def _resolve(members: list[dict], field_key: str, getter, *, authority_axis: str | None = None):
    """Pick a value by precedence. Returns (value, source_ids_agreeing, all_claims, conflicts)."""
    allowed = sc.AUTHORITY_ONLY.get(authority_axis) if authority_axis else None
    claims = []
    for r in _ordered(members, field_key):
        v = getter(r)
        if v in (None, "", [], {}):
            continue
        if allowed and r["source_id"] not in allowed:
            claims.append({"value": v, "source_id": r["source_id"], "record_id": r.get("record_id"),
                           "used": False, "reason": "not the naming authority for this field"})
            continue
        claims.append({"value": v, "source_id": r["source_id"], "record_id": r.get("record_id"), "used": None})
    usable = [c for c in claims if c["used"] is None]
    if not usable:
        for c in claims:
            c["used"] = False
        return None, [], claims, []
    winner = usable[0]["value"]
    agreeing, losing = [], []
    for c in usable:
        same = _same(c["value"], winner)
        c["used"] = same
        (agreeing if same else losing).append(c)
    conflicts = []
    if losing:
        conflicts.append({
            "field": authority_axis or field_key,
            "chosen": winner,
            "chosen_by": [c["source_id"] for c in agreeing],
            "rejected": [{"value": c["value"], "source_id": c["source_id"]} for c in losing],
            "rule": f"precedence {sc.PRECEDENCE.get(field_key) or 'source rank'}",
        })
    return winner, [c["source_id"] for c in agreeing], claims, conflicts


def _same(a, b) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    if isinstance(a, str) and isinstance(b, str):
        return he.key(a) == he.key(b) or a.strip() == b.strip()
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-6
    return a == b


ORDER = ["archaeological", "historic", "culture"]


def decide_category(members: list[dict]) -> tuple[str, list[str], str]:
    """Primary category, all applicable categories, and the basis for the era split.

    One place can honestly be several things at once, which is the normal case here rather
    than the exception: a 1930s settlement monument standing on a declared antiquity site, a
    museum inside an archaeological park. `categories` records all of them and drives the
    filters; `category` picks the one the marker wears.

    The precedence is legal, not chronological:

    1. If the Antiquities Authority registers the place, it IS an antiquities site under
       חוק העתיקות, whatever else was later built on it. A post-1700 date then makes it ALSO
       historic instead of replacing the classification. Deciding this by date alone let a
       stray 2017 on a blue sign reclassify Khirbat Tira, a declared site with Byzantine and
       Mamluk remains, as post-1700 heritage.
    2. An institution demonstrably operating today leads, because that is a present-tense
       fact about the place rather than a layer of its past.
    3. Otherwise the period vocabulary decides, then an explicit year, then source authority.
    """
    hints = [r.get("category_hint") for r in members if r.get("category_hint")]
    cats = set(hints)

    years = [r.get("year_from") for r in members if isinstance(r.get("year_from"), (int, float))]
    periods = sorted({p for r in members for p in (r.get("periods") or []) if p in sc.PERIOD_SPAN},
                     key=lambda p: sc.PERIOD_ORDER[p])

    era_periods = sc.era_from_periods(periods)
    era_year = None
    if years:
        era_year = "archaeological" if min(years) < sc.ANTIQUITY_CUTOFF_YEAR else "historic"

    iaa_registered = any(
        (r.get("statuses") or {}).get("reg_antiquity") in ("declared", "known") for r in members)
    active_institution = any(
        (r.get("statuses") or {}).get("activity") in ("active", "seasonal") for r in members)

    # `conf` is how sure we are of the classification, which is NOT the same as which rule
    # decided it. Registration by the Antiquities Authority together with a period vocabulary
    # that agrees is the strongest evidence available and scores accordingly; labelling that
    # case merely 'source_authority' and scoring it like a lone hint understated it badly.
    if iaa_registered:
        primary = "archaeological"
        cats.add("archaeological")
        if era_year == "historic" or era_periods == "historic":
            cats.add("historic")
        if era_periods == "archaeological":
            basis, conf = "authority_and_periods", 1.0
        else:
            basis, conf = "source_authority", 0.90
    elif active_institution and "culture" in cats:
        primary, basis, conf = "culture", "source_authority", 0.92
    elif cats == {"culture"}:
        primary, basis, conf = "culture", ("period_vocab" if era_periods else "site_type"), 0.88
    elif era_periods:
        primary, basis, conf = era_periods, "period_vocab", 0.95
    elif era_year:
        primary, basis, conf = era_year, "explicit_year", 0.95
    elif cats:
        primary, basis, conf = sorted(cats, key=ORDER.index)[0], "source_authority", 0.80
    else:
        primary, basis, conf = "archaeological", "unknown", 0.35

    cats.add(primary)
    return primary, sorted(cats, key=ORDER.index), basis, conf


def merge_cluster(members: list[dict], jur: geo.Jurisdiction | None) -> dict:
    primary, cats, era_basis, cat_conf = decide_category(members)
    geo_key = f"geometry.{primary}"
    name_key = f"name.{primary}"

    rec: dict = {"category": primary, "categories": cats, "era_basis": era_basis,
                 "_category_confidence": cat_conf}
    provenance: dict[str, list[str]] = {}
    all_claims: list[dict] = []
    conflicts: list[dict] = []

    def take(field, field_key, getter, *, axis=None):
        v, srcs, claims, cf = _resolve(members, field_key, getter, authority_axis=axis)
        rec[field] = v
        if srcs:
            provenance[field] = srcs
        for c in claims:
            all_claims.append({"field": field, **c})
        conflicts.extend(cf)

    take("name", name_key, lambda r: r.get("name"))
    take("name_en", name_key, lambda r: r.get("name_en"))
    take("description", name_key, lambda r: r.get("description"))
    take("type", "type", lambda r: r.get("type") if r.get("type") in sc.SITE_TYPES else None)
    take("locality", "locality", lambda r: r.get("locality"))
    take("year_from", "periods", lambda r: r.get("year_from"))
    take("year_to", "periods", lambda r: r.get("year_to"))
    take("date_text", "periods", lambda r: r.get("date_text"))

    # Geometry travels as a unit: lat and lon must come from the same source record.
    geo_src = None
    for r in _ordered(members, geo_key):
        if r.get("lat") is not None:
            rec["lat"], rec["lon"] = r["lat"], r["lon"]
            rec["itm_x"], rec["itm_y"] = r.get("itm_x"), r.get("itm_y")
            rec["location_precision"] = r.get("location_precision") or "unknown"
            geo_src = r["source_id"]
            provenance["lat"] = provenance["lon"] = [geo_src]
            break
    if geo_src is None:
        rec["lat"] = rec["lon"] = rec["itm_x"] = rec["itm_y"] = None
        rec["location_precision"] = "unknown"
    if rec["lat"] is not None and (rec.get("itm_x") is None):
        rec["itm_x"], rec["itm_y"] = geo.to_itm(rec["lat"], rec["lon"])
    for r in members:
        if r.get("lat") is not None:
            all_claims.append({"field": "lat/lon", "value": [r["lat"], r["lon"]],
                               "source_id": r["source_id"], "record_id": r.get("record_id"),
                               "used": r["source_id"] == geo_src})

    # Periods are a union, not a choice: sources see different phases of the same site.
    periods = sorted({p for r in members for p in (r.get("periods") or []) if p in sc.PERIOD_SPAN},
                     key=lambda p: sc.PERIOD_ORDER[p])
    rec["periods"] = periods
    if periods:
        provenance["periods"] = sorted({r["source_id"] for r in members if r.get("periods")})

    for axis in sc.STATUS_AXES:
        take(axis, axis, lambda r, a=axis: (r.get("statuses") or {}).get(a), axis=axis)
        if rec.get(axis) is None:
            rec[axis] = "unknown"
    rec["reg_summary"] = sc.registered_summary(rec)

    for f in ("address", "phone", "email", "website", "hours_text", "admission", "operator", "founded_year"):
        take(f, f, lambda r, k=f: (r.get("practical") or {}).get(k))
    for f in ("excavation_years", "excavation_licenses", "excavators"):
        vals = [v for r in members for v in ((r.get("extra") or {}).get(f) or [])]
        rec[f] = sorted({str(v) for v in vals}) if vals else []

    ids: dict = {}
    for k in STRONG_IDS + ("wikipedia_he", "image_url", "image_credit"):
        for r in _ordered(members, k):
            v = (r.get("ids") or {}).get(k) or (r.get("extra") or {}).get(k)
            if v:
                ids[k] = v
                provenance[k] = [r["source_id"]]
                break
    rec.update({k: ids.get(k) for k in
                ("iaa_site_id", "wikidata_qid", "osm_id", "blue_sign_number",
                 "wikipedia_he", "image_url", "image_credit")})
    # When one place is carried under several official numbers, all of them are kept: dropping
    # the losers would hide that the state holds more than one declaration for the site.
    all_iaa = sorted({str((m.get("ids") or {}).get("iaa_site_id"))
                      for m in members if (m.get("ids") or {}).get("iaa_site_id")})
    rec["iaa_site_ids"] = all_iaa if len(all_iaa) > 1 else []

    seen_names = {he.key(rec["name"])}
    alts = []
    for r in members:
        for n in _names(r):
            k = he.key(n)
            if k and k not in seen_names:
                seen_names.add(k)
                alts.append({"name": he.display(n), "source_id": r["source_id"]})
    rec["names_alt"] = alts

    rec["external_links"] = sorted(
        {(r.get("url") or "") for r in members if r.get("url")} - {""}
    )
    rec["sources"] = [{"source_id": r["source_id"], "source_he": sc.SOURCES[r["source_id"]]["he"],
                       "record_id": r.get("record_id"), "url": r.get("url"),
                       "retrieved": r.get("retrieved")} for r in members]
    rec["extra"] = {r["source_id"]: r.get("extra") or {} for r in members if r.get("extra")}
    rec["provenance"] = provenance
    rec["claims"] = all_claims
    rec["conflicts"] = conflicts

    if rec["lat"] is not None:
        nm, km, code = nearest_settlement(rec["lat"], rec["lon"])
        rec["nearest_settlement"] = nm
        rec["nearest_settlement_km"] = km
        rec["nearest_settlement_code"] = code

        # The coordinate is evidence about which settlement the place is in, and it outranks a
        # sourced locality that contradicts it. A blue sign for the Alonei Abba community hall
        # was catalogued under תל עדשים because the sign text mentions where the building STONES
        # came from; the position says otherwise and the position is right.
        if nm and km is not None and km <= 2.0 and rec.get("locality") \
                and he.similarity(rec["locality"], nm) < 0.60:
            agreeing = [c for c in all_claims
                        if c["field"] == "locality" and isinstance(c.get("value"), str)
                        and he.similarity(c["value"], nm) >= 0.85]
            if agreeing:
                was = rec["locality"]
                rec["locality"] = agreeing[0]["value"]
                provenance["locality"] = [c["source_id"] for c in agreeing]
                for c in all_claims:
                    if c["field"] == "locality":
                        c["used"] = c in agreeing
                conflicts.append({
                    "field": "locality",
                    "chosen": rec["locality"],
                    "chosen_by": [c["source_id"] for c in agreeing],
                    "rejected": [{"value": was, "source_id": "(precedence winner)"}],
                    "rule": (f"היישוב שנבחר לפי הקדימות ({was}) סותר את המיקום, שנמצא "
                             f"{km} ק\"מ מ{nm}; נבחרה טענה שמתאימה למיקום"),
                })
    else:
        rec["nearest_settlement"] = rec["nearest_settlement_km"] = rec["nearest_settlement_code"] = None

    if jur is not None and rec["lat"] is not None:
        rec.update(jur.report(rec["lat"], rec["lon"]))
    else:
        rec.update({"in_council": None, "in_council_method": "no_coordinate",
                    "dist_to_boundary_m": None, "near_boundary": None})

    rec["id"] = f"ey-{primary[:4]}-{he.slug(rec['name'] or rec['sources'][0]['record_id'])}"
    rec.update(score_confidence(rec, members))
    return rec


# --------------------------------------------------------------------------------------
# confidence
# --------------------------------------------------------------------------------------

def score_confidence(rec: dict, members: list[dict]) -> dict:
    srcs = {r["source_id"] for r in members}
    p_wrong = 1.0
    for s in srcs:
        p_wrong *= (1.0 - RELIABILITY.get(_rank(s), 0.7))
    existence = min(0.99, 1.0 - p_wrong)

    location = PRECISION_CONF.get(rec.get("location_precision") or "unknown", 0.45)
    pts = [(r["lat"], r["lon"]) for r in members if r.get("lat") is not None]
    spread = 0.0
    if len(pts) >= 2:
        spread = max(geo.haversine_m(*a, *b) for i, a in enumerate(pts) for b in pts[i + 1:])
        if spread <= 60:
            location = min(0.98, location + 0.08)
        elif spread <= 200:
            location = min(0.95, location + 0.03)
        else:
            location = max(0.25, location - min(0.35, spread / 3000))
    if rec.get("lat") is None:
        location = 0.05

    category = rec.get("_category_confidence", 0.35)

    applicable = [a for a, m in sc.STATUS_AXES.items() if rec["category"] in m["applies_to"]]
    known = [a for a in applicable if rec.get(a) not in (None, "unknown")]
    completeness = round(len(known) / max(1, len(applicable)), 3)

    comps = {"existence": round(existence, 3), "location": round(location, 3),
             "category": round(category, 3)}
    overall = sum(comps[k] * w for k, w in CONF_WEIGHTS.items())

    # Two tiers. HARD reasons mean a human or a verification agent has to look before this
    # record can be trusted. SOFT reasons are worth showing but are ordinary gaps: flagging
    # every undated site as "needs review" would flag almost the whole map and mean nothing.
    hard, soft = [], []
    if rec.get("lat") is None:
        hard.append("no_coordinate")
    if rec.get("in_council") is False:
        hard.append("outside_council")
    if spread > 250:
        hard.append(f"sources_disagree_on_location_{int(spread)}m")
    if rec["conflicts"]:
        hard.append("field_conflicts")
    # A stated year on one side of the 1700 line and a period vocabulary on the other is a
    # real contradiction about what the place is, so it is surfaced rather than resolved away.
    era_p = sc.era_from_periods(rec.get("periods") or [])
    yf = rec.get("year_from")
    if era_p and isinstance(yf, (int, float)):
        era_y = "archaeological" if yf < sc.ANTIQUITY_CUTOFF_YEAR else "historic"
        if era_y != era_p:
            hard.append(f"stated_year_{int(yf)}_contradicts_periods")
    # 'Near the boundary' only needs a human when the decision could actually flip: either the
    # point is very close to the line, or its position is too coarse to trust near one. The
    # council's doughnut shape puts a large share of sites within 300 m of some boundary, so
    # flagging all of them would make the flag meaningless.
    if rec.get("near_boundary"):
        d = abs(rec.get("dist_to_boundary_m") or 0)
        coarse = rec.get("location_precision") in ("approx_500m", "locality_centroid", "unknown")
        (hard if (d <= 100 or coarse) else soft).append("near_council_boundary")
    if any(m.get("_merged_on_name_alone") for m in members) and len(srcs) > 1:
        hard.append("merged_on_name_without_geometry")
    if rec["era_basis"] == "unknown":
        soft.append("era_undetermined")
    if len(srcs) == 1 and _rank(next(iter(srcs))) >= 5:
        soft.append("single_weak_source")
    if rec["category"] == "culture" and rec.get("activity") == "unknown":
        soft.append("activity_unverified")

    return {
        "confidence": round(min(0.99, overall), 3),
        "confidence_components": comps,
        "status_completeness": completeness,
        "status_axes_known": len(known),
        "status_axes_applicable": len(applicable),
        "source_count": len(srcs),
        "location_spread_m": round(spread, 1),
        "needs_review": bool(hard),
        "review_reasons": hard + soft,
        "verification": {"status": "unverified", "by": [], "date": None, "notes": None},
    }


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------

_SETTLEMENTS: list[dict] = []


def load_settlements() -> int:
    """Load the council's settlements with coordinates, for the derived nearest-settlement field."""
    _SETTLEMENTS.clear()
    for r in paths.settlements():
        # Only inhabited localities make a useful answer to "which settlement's land is this
        # on". Statistical open-area zones and industrial codes are not places anyone knows.
        if r.get("category") != "residential_locality":
            continue
        if r.get("lat") is None or not r.get("name_he"):
            continue
        _SETTLEMENTS.append({"name": r["name_he"], "lat": r["lat"], "lon": r["lon"],
                             "code": r.get("cbs_yishuv_code")})
    return len(_SETTLEMENTS)


def nearest_settlement(lat: float, lon: float) -> tuple[str | None, float | None, int | None]:
    """Nearest inhabited settlement and its distance in km. A DERIVED value, never a claim.

    Most archaeological sites here sit in open farmland and no source names a settlement for
    them, which left the locality facet answering 'unknown' for two thirds of the map. The
    nearest settlement is a computed orientation aid, kept in its own field so it can never be
    mistaken for something a source said.
    """
    if lat is None or not _SETTLEMENTS:
        return None, None, None
    best, bd = None, 1e9
    for s in _SETTLEMENTS:
        d = geo.haversine_m(lat, lon, s["lat"], s["lon"])
        if d < bd:
            best, bd = s, d
    return best["name"], round(bd / 1000, 2), best["code"]


def load_locality_heads() -> int:
    """Register the council's settlement names as generic heads for name matching.

    Prefers the official settlement list from the boundary extraction; falls back to the
    locality column of the claims themselves, which is sourced data either way.
    """
    names: set[str] = set()
    for r in paths.settlements():
        for k in ("name_he", "name", "shem_yishuv", "שם יישוב", "settlement"):
            if r.get(k):
                names.add(str(r[k]))
                break
    for f in sorted(INTERIM.glob("*.claims.json")):
        for r in json.loads(f.read_text(encoding="utf-8")):
            if r.get("locality"):
                names.add(r["locality"])
    return he.add_locality_heads(names)


def apply_statutory_overlay(sites: list[dict]) -> dict:
    """Assign conservation and protected-area status by location, not by name.

    The Planning Administration publishes 609 in-scope conservation designations for this
    council whose only names are the designation type and the plan they belong to, so they can
    never be matched to a site by name. What they DO say is spatial: a location falls inside a
    conservation designation in an approved plan. That is applied here, after merging, and only
    where the axis is still unknown, so a statement by the Conservation Council itself is never
    overwritten by a planning inference.
    """
    p = INTERIM / "_overlay_statutory.json"
    if not p.exists():
        return {"applied": 0}
    ov = json.loads(p.read_text(encoding="utf-8"))
    applied = defaultdict(int)
    for axis in ("reg_conservation", "protected_area"):
        feats = ov.get(axis) or []
        if not feats:
            continue
        for s in sites:
            if s.get("lat") is None or s.get(axis) not in (None, "unknown"):
                continue
            best, bd = None, 1e18
            for f in feats:
                d = geo.haversine_m(s["lat"], s["lon"], f["lat"], f["lon"])
                if d <= f["radius_m"] and d < bd:
                    best, bd = f, d
            if not best:
                continue
            s[axis] = best["value"]
            s["provenance"].setdefault(axis, []).append("heritage_official")
            s["claims"].append({
                "field": axis, "value": best["value"], "source_id": "heritage_official",
                "record_id": f"{best['record_type']}:{best.get('plan_number') or best.get('name')}",
                "used": True,
                "note": (f"נקבע לפי מיקום בתוך ייעוד סטטוטורי: {best.get('designation')}"
                         + (f", תוכנית {best.get('plan_name')}" if best.get("plan_name") else "")
                         + (f" ({best.get('plan_number')})" if best.get("plan_number") else "")
                         + f", מרחק {int(bd)} מטר ממרכז הייעוד"),
            })
            s.setdefault("overlay_notes", []).append(
                {"axis": axis, "designation": best.get("designation"),
                 "plan": best.get("plan_name") or best.get("plan"),
                 "plan_number": best.get("plan_number"), "distance_m": round(bd, 1),
                 "stage": best.get("stage"), "method": "point_within_designation_radius"})
            applied[axis] += 1
    for s in sites:
        s["reg_summary"] = sc.registered_summary(s)
    return dict(applied)


def link_colocated(sites: list[dict], max_m: float = 200.0, min_sim: float = 0.85) -> int:
    """Link separate sites that share a place, without merging them.

    The pipeline refuses to merge two records that carry DIFFERENT antiquity site numbers, which
    is right: the IAA's numbering is a legal fact and two adjacent declarations are two
    declarations. But it leaves the map showing what looks like the same place twice with no
    hint that the records are connected. So they are cross-linked instead, and the detail panel
    says so. Merging them would erase a distinction the state actually makes; hiding the
    relationship would just look like a mistake.
    """
    pts = [s for s in sites if s.get("lat") is not None]
    cell = 0.004
    grid: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for s in pts:
        grid[(int(s["lat"] / cell), int(s["lon"] / cell))].append(s)
    n = 0
    seen: set[tuple[str, str]] = set()
    for s in pts:
        ci, cj = int(s["lat"] / cell), int(s["lon"] / cell)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for t in grid.get((ci + di, cj + dj), ()):
                    if t is s:
                        continue
                    k = tuple(sorted((s["id"], t["id"])))
                    if k in seen:
                        continue
                    d = geo.haversine_m(s["lat"], s["lon"], t["lat"], t["lon"])
                    if d > max_m:
                        continue
                    sim = he.similarity(s.get("name"), t.get("name"))
                    if sim < min_sim:
                        continue
                    seen.add(k)
                    why = "אותו שם באותו מקום"
                    if s.get("iaa_site_id") and t.get("iaa_site_id") and \
                            s["iaa_site_id"] != t["iaa_site_id"]:
                        why = (f"רשומות נפרדות ברשות העתיקות: מספרי אתר "
                               f"{s['iaa_site_id']} ו-{t['iaa_site_id']}")
                    for a, b in ((s, t), (t, s)):
                        a.setdefault("related_ids", []).append(
                            {"id": b["id"], "name": b.get("name"),
                             "distance_m": round(d, 1), "name_similarity": round(sim, 3),
                             "reason": why})
                    n += 1
    return n


def run(boundary_path: Path | None = None) -> dict:
    paths.ensure_writable()
    claims = load_claims()
    n_heads = load_locality_heads()
    n_settl = load_settlements()
    jur = None
    bp = boundary_path or paths.boundary_file()
    if bp and Path(bp).exists():
        jur = geo.Jurisdiction.from_geojson(bp)

    clusters, review, blocked = cluster(claims)
    sites = [merge_cluster([claims[i] for i in g], jur) for g in clusters]
    overlay_applied = apply_statutory_overlay(sites)
    n_linked = link_colocated(sites)
    # The overlay can raise the number of known status axes, so completeness is recomputed.
    for s in sites:
        applicable = [a for a, m in sc.STATUS_AXES.items() if s["category"] in m["applies_to"]]
        known = [a for a in applicable if s.get(a) not in (None, "unknown")]
        s["status_completeness"] = round(len(known) / max(1, len(applicable)), 3)
        s["status_axes_known"] = len(known)

    # Stable ids even when two clusters resolve to the same name.
    seen: dict[str, int] = {}
    for s in sorted(sites, key=lambda s: (s["name"] or "", s["lat"] or 0)):
        n = seen.get(s["id"], 0)
        seen[s["id"]] = n + 1
        if n:
            s["id"] = f"{s['id']}-{n + 1}"

    sites.sort(key=lambda s: (-s["confidence"], s["name"] or ""))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sites.json").write_text(json.dumps(sites, ensure_ascii=False, indent=1), encoding="utf-8")
    # Triage. In dense archaeological country hundreds of genuinely different sites sit
    # within a few hundred metres of each other, so a raw queue of every borderline pair is
    # thousands long and nobody reads it. Only pairs that could actually change the map are
    # surfaced; the rest are counted, because a silently truncated queue would read as "there
    # was nothing to check".
    SURFACE_AT = 0.70
    surfaced = [x for x in review
                if x["kind"] != "borderline_match" or (x.get("score") or 0) >= SURFACE_AT]
    surfaced.sort(key=lambda x: -(x.get("score") or 0))
    (OUT / "review_queue.json").write_text(json.dumps({
        "surfaced_threshold": SURFACE_AT,
        "totals": {
            "all_review_items": len(review),
            "surfaced": len(surfaced),
            "suppressed_low_score_borderline": len(review) - len(surfaced),
            "blocked_by_conflicting_id": len(blocked),
            "by_kind": {k: sum(1 for x in review if x["kind"] == k)
                        for k in sorted({x["kind"] for x in review})},
        },
        "surfaced_items": surfaced,
        "blocked_by_conflicting_id": blocked,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    stats = {
        "claim_records": len(claims),
        "locality_head_tokens": n_heads,
        "settlements_loaded": n_settl,
        "statutory_overlay_applied": overlay_applied,
        "colocated_links": n_linked,
        "sites": len(sites),
        "merged_sites": sum(1 for s in sites if s["source_count"] > 1),
        "by_category": {c: sum(1 for s in sites if s["category"] == c) for c in sc.CATEGORIES},
        "in_council": sum(1 for s in sites if s["in_council"] is True),
        "outside_council": sum(1 for s in sites if s["in_council"] is False),
        "no_coordinate": sum(1 for s in sites if s["lat"] is None),
        "needs_review": sum(1 for s in sites if s["needs_review"]),
        "review_queue_total": len(review),
        "review_queue_surfaced": len(surfaced),
        "blocked_pairs": len(blocked),
        "mean_confidence": round(sum(s["confidence"] for s in sites) / max(1, len(sites)), 3),
        "confidence_at_least_95": sum(1 for s in sites if s["confidence"] >= 0.95),
        "mean_status_completeness": round(
            sum(s["status_completeness"] for s in sites) / max(1, len(sites)), 3),
    }
    (OUT / "harmonize_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    return stats


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    print(json.dumps(run(), ensure_ascii=False, indent=1))
