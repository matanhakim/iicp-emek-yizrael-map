"""Assemble data/interim/iaa_discover.json from the raw IAA payloads.

Record types produced (field `_record_type`):
  declared_site : hachraza  = declared antiquity site (IAA national DB)  [primary]
  excavation    : excavation event, with the declared site(s) it attaches to
  survey_site   : Archaeological Survey of Israel site (survey.iaa.org.il)

Everything from the source is kept under its original field name.
Derived fields are prefixed with `derived_`; provenance fields with `_`.
No value is ever invented: absent -> None.
"""
import os, sys, json, glob, re, collections
sys.stdout.reconfigure(encoding='utf-8')
from shapely import wkt as swkt
from shapely.geometry import box, shape as gshape
from pyproj import Transformer

RAW  = r"C:/Users/matan/OneDrive/Documents/projects/iicp-emek-yizrael-map/data/raw/iaa_discover"
OUT  = r"C:/Users/matan/OneDrive/Documents/projects/iicp-emek-yizrael-map/data/interim/iaa_discover.json"
HERE = os.path.dirname(os.path.abspath(__file__))
RETRIEVED = "2026-08-03"

WIN_ITM  = box(197000, 709000, 249000, 752000)          # generous ITM window
WIN_LL   = (32.55, 32.85, 35.05, 35.50)                  # stated WGS84 window (latmin,latmax,lonmin,lonmax)
T2039_4326 = Transformer.from_crs("EPSG:2039", "EPSG:4326", always_xy=True)

LIC_RE = re.compile(r'^([A-Za-z]+)-(\d+(?:/\d+)?)/(\d{4})(?:-(\d+))?$')   # A-4090/2004 , C-30/1956-1
YEAR_BRACKET = re.compile(r'\[(\d{4})\]')

# Period labels in the IAA thesaurus whose span reaches past 1700 CE, so the
# project's "archaeological = up to 1700" rule cannot be settled from the period
# label alone. Verbatim strings as they appear in the source, no normalisation.
POST_1700_PERIODS = {
    "עות'מנית", "ממלוכית-עותומנית", "ממלוכית-עותומנית-מודרנית",
    "מודרנית", "מנדט בריטי", "אסלאמית מאוחרת", "אסלאמית",
}


# ---------------------------------------------------------------- loaders
def load_query(pattern):
    """Load entities out of every POST /api/query payload matching pattern."""
    rows = []
    for fn in sorted(glob.glob(os.path.join(RAW, pattern))):
        try:
            d = json.load(open(fn, encoding='utf-8'))
        except Exception:
            continue
        if "entities" not in d:
            continue
        base = os.path.basename(fn)
        for e in d["entities"]:
            e = dict(e)
            e["_srcfile"] = base
            rows.append(e)
    return rows


def dedupe(rows):
    out = {}
    for e in rows:
        out.setdefault((e["entityType"], e["entityId"]), e)
    return out


def shapes_geom(e):
    gs = []
    for s in (e.get("shapes") or []):
        try:
            gs.append((swkt.loads(s["wkt"]), s))
        except Exception:
            pass
    return gs


def itm_to_wgs(x, y):
    lon, lat = T2039_4326.transform(x, y)
    return round(lat, 7), round(lon, 7)


def geom_summary(gs):
    """Centroid + bbox of the union of an entity's ITM shapes, plus WGS84."""
    if not gs:
        return dict(derived_itm_x=None, derived_itm_y=None, lat=None, lon=None,
                    derived_itm_xmin=None, derived_itm_ymin=None,
                    derived_itm_xmax=None, derived_itm_ymax=None,
                    derived_bbox_width_m=None, derived_bbox_height_m=None,
                    derived_position_uncertainty_m=None, derived_n_shapes=0,
                    derived_shape_is_rectangle=None, derived_shape_wkt_itm=None)
    geoms = [g for g, _ in gs]
    xs = [g.bounds for g in geoms]
    xmin = min(b[0] for b in xs); ymin = min(b[1] for b in xs)
    xmax = max(b[2] for b in xs); ymax = max(b[3] for b in xs)
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    lat, lon = itm_to_wgs(cx, cy)
    w = xmax - xmin; h = ymax - ymin
    rect = None
    if len(geoms) == 1:
        g = geoms[0]
        try:
            rect = (len(list(g.exterior.coords)) == 5 and
                    abs(g.area - (g.bounds[2]-g.bounds[0]) * (g.bounds[3]-g.bounds[1])) < max(1.0, 0.02*g.area))
        except Exception:
            rect = None
    return dict(
        derived_itm_x=round(cx, 2), derived_itm_y=round(cy, 2), lat=lat, lon=lon,
        derived_itm_xmin=round(xmin, 2), derived_itm_ymin=round(ymin, 2),
        derived_itm_xmax=round(xmax, 2), derived_itm_ymax=round(ymax, 2),
        derived_bbox_width_m=round(w, 1), derived_bbox_height_m=round(h, 1),
        derived_position_uncertainty_m=round(max(w, h) / 2.0, 1),
        derived_n_shapes=len(gs),
        derived_shape_is_rectangle=rect,
        derived_shape_wkt_itm=gs[0][1]["wkt"] if len(gs) == 1 else None,
    )


def in_window_itm(gs):
    return any(g.intersects(WIN_ITM) for g, _ in gs)


def parse_licence(long_name):
    """'A-4090/2004' -> (prefix, number, year). Returns (None,None,None) if unparseable."""
    if not long_name:
        return None, None, None
    m = LIC_RE.match(long_name.strip())
    if not m:
        return None, None, None
    return m.group(1), m.group(2), int(m.group(3))


# ---------------------------------------------------------------- load everything
print("loading query payloads ...", flush=True)
allrows = load_query("05_query_*.json") + load_query("07_query_hachrazot_sett5_*.json") \
        + load_query("06_query_*_settbatch12.json") \
        + load_query("25_query_licenses_byid_*.json")   # licence backfill by licenseId
uniq = dedupe(allrows)
print("  unique entities:", len(uniq), flush=True)

by_type = collections.defaultdict(dict)
for (t, i), e in uniq.items():
    by_type[t][i] = e
print("  by type:", {k: len(v) for k, v in by_type.items()}, flush=True)

# hachraza detail records, keyed by hachrazaId ('2500/0')
details = {}
for fn in glob.glob(os.path.join(RAW, "hachraza_details", "*.json")):
    try:
        d = json.load(open(fn, encoding='utf-8'))
    except Exception:
        continue
    details[d["hachrazaId"]] = d
print("  hachraza detail records:", len(details), flush=True)

# AGOL HACRAZOT_PUBLIC attributes, keyed by atar_number ('3450/0')
agol = {}
agol_geom = {}
for fn in sorted(glob.glob(os.path.join(RAW, "12_agol_hacrazot_public_window_off*.geojson"))):
    try:
        d = json.load(open(fn, encoding='utf-8'))
    except Exception:
        continue
    for f in d.get("features", []):
        num = f["properties"]["atar_number"]
        agol[num] = f["properties"]
        try:
            agol_geom[num] = gshape(f["geometry"])
        except Exception:
            pass
print("  AGOL window features:", len(agol), flush=True)

# ---------------------------------------------------------------- cross-links
# licenceId -> the license entity that represents it
lic_entity = {}
for i, e in by_type.get("license", {}).items():
    try:
        lic_entity[int(e["originEntityId"])] = e
    except Exception:
        pass

# licenceId -> excavation / survey / expedition / publication entities carrying it
lic_to = collections.defaultdict(lambda: collections.defaultdict(list))
for t in ("excavation", "survey", "expedition", "publication", "conservation_report"):
    for i, e in by_type.get(t, {}).items():
        for l in (e.get("licenses") or []):
            lic_to[l["licenseId"]][t].append(e)

# --- the authoritative licence relation -------------------------------------
# A license entity states, in its own parentEntities, which declared sites,
# excavations, surveys and expeditions it pertains to. That statement is the
# IAA's own and is bidirectionally consistent, so we use ONLY it.
# licenceId -> {parentType -> set(parentEntityId)}
lic_parents = collections.defaultdict(lambda: collections.defaultdict(set))
for lid, le in lic_entity.items():
    for p in (le.get("parentEntities") or []):
        lic_parents[lid][p["parentType"]].add(p["parentEntityId"])

# --- second route to classify a licence -------------------------------------
# Many licences referenced by a site have no retrievable license entity, but
# POST /api/query with EntityTypes=["excavations"|"surveys"|"expeditions"] and
# Licenses=[id] DOES return the activity that holds the licence. That answers
# "is this an excavation licence?" without the licence record itself.
# licenceId -> {"excavation"|"survey"|"expedition" -> set(entityId)}
lic_activity = collections.defaultdict(lambda: collections.defaultdict(set))
_n_act = 0
for fn in sorted(glob.glob(os.path.join(RAW, "26_query_activities_bylicence_*.json"))):
    try:
        d = json.load(open(fn, encoding='utf-8'))
    except Exception:
        continue
    for e in d.get("entities", []):
        _n_act += 1
        for l in (e.get("licenses") or []):
            lic_activity[l["licenseId"]][e["entityType"]].add(e["entityId"])
print("  licence-classification rows:", _n_act,
      "covering", len(lic_activity), "licence ids", flush=True)

# hachraza entityId -> entities whose parentEntities point at it
parent_to_children = collections.defaultdict(lambda: collections.defaultdict(list))
for (t, i), e in uniq.items():
    for p in (e.get("parentEntities") or []):
        if p.get("parentType") == "hachrazot":
            parent_to_children[p["parentEntityId"]][t].append(e)


def responsible_from_description(e):
    """Excavation/survey description is 'אחראי חובות חפירה: <name>' -> name, else None."""
    d = (e.get("description") or {}).get("hebrew")
    if not d:
        return None
    if ":" in d:
        return d.split(":", 1)[1].strip() or None
    return d.strip() or None


def year_from_title(e):
    t = (e.get("title") or {}).get("hebrew") or (e.get("title") or {}).get("english") or ""
    m = YEAR_BRACKET.search(t)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- build records
records = []

# ---- 1. declared sites (hachraza) -------------------------------------------
n_win = 0
for i, e in sorted(by_type.get("hachraza", {}).items()):
    gs = shapes_geom(e)
    if not in_window_itm(gs):
        continue
    n_win += 1
    hid = e["originEntityId"]
    det = details.get(hid)
    ag = agol.get(hid)

    lic_long = [l["longName"] for l in (e.get("licenses") or [])]
    parsed = [parse_licence(x) for x in lic_long]
    years = sorted({y for _, _, y in parsed if y})
    prefixes = sorted({p for p, _, _ in parsed if p})

    kids = parent_to_children.get(i, {})

    # ---- licence classification, evidence-based only -----------------------
    # A licence counts towards this site only when the licence entity itself
    # names this site in parentEntities (bidirectional edge). The licence's own
    # parentEntities then say whether it is an excavation or a survey licence.
    exc_lic_names, sur_lic_names, other_lic_names, unresolved_lic_names = [], [], [], []
    exc_eids, sur_eids, exp_eids = set(), set(), set()
    route_used = {"bidirectional": 0, "site_asserted": 0}
    exc_routes = set()
    for l in (e.get("licenses") or []):
        lid = l["licenseId"]
        name = l.get("longName")
        if lid in lic_entity:
            # route 1: the licence record itself names this site and its activities
            par = lic_parents[lid]
            if i not in par.get("hachrazot", set()):
                other_lic_names.append(name)           # licence known, does not name this site
                continue
            is_exc = bool(par.get("excavations"))
            is_sur = bool(par.get("surveys"))
            exc_eids |= par.get("excavations", set())
            sur_eids |= par.get("surveys", set())
            exp_eids |= par.get("expeditions", set())
            route_used["bidirectional"] += 1
            if is_exc:
                exc_routes.add("bidirectional")
        elif lid in lic_activity:
            # route 2: the licence record is unavailable, but querying activities
            # by this licence id returned an excavation / survey / expedition.
            act = lic_activity[lid]
            is_exc = bool(act.get("excavation"))
            is_sur = bool(act.get("survey"))
            exc_eids |= act.get("excavation", set())
            sur_eids |= act.get("survey", set())
            exp_eids |= act.get("expedition", set())
            route_used["site_asserted"] += 1
            if is_exc:
                exc_routes.add("site_asserted")
        else:
            unresolved_lic_names.append(name)          # neither route resolved it
            continue
        if is_exc:
            exc_lic_names.append(name)
        elif is_sur:
            sur_lic_names.append(name)
        else:
            other_lic_names.append(name)

    # entities behind those ids, when we hold them
    exc = [by_type["excavation"][x] for x in sorted(exc_eids) if x in by_type.get("excavation", {})]
    sur = [by_type["survey"][x] for x in sorted(sur_eids) if x in by_type.get("survey", {})]
    exp = [by_type["expedition"][x] for x in sorted(exp_eids) if x in by_type.get("expedition", {})]
    # publications and conservation reports attach to the site directly
    pub = list(kids.get("publication", []))
    con = list(kids.get("conservation_report", []))
    exc += [x for x in kids.get("excavation", []) if x["entityId"] not in exc_eids]
    sur += [x for x in kids.get("survey", []) if x["entityId"] not in sur_eids]
    exp += [x for x in kids.get("expedition", []) if x["entityId"] not in exp_eids]

    def brief(lst):
        seen, out = set(), []
        for x in lst:
            k = x["entityId"]
            if k in seen:
                continue
            seen.add(k)
            out.append({
                "entityId": x["entityId"],
                "originEntityId": x["originEntityId"],
                "title_hebrew": (x.get("title") or {}).get("hebrew"),
                "title_english": (x.get("title") or {}).get("english"),
                "responsible_hebrew": responsible_from_description(x),
                "year_from_title": year_from_title(x),
                "licenses": [l["longName"] for l in (x.get("licenses") or [])],
            })
        return out

    exc_b, sur_b = brief(exc), brief(sur)
    exp_b, pub_b, con_b = brief(exp), brief(pub), brief(con)
    exc_years = sorted({b["year_from_title"] for b in exc_b if b["year_from_title"]})
    sur_years = sorted({b["year_from_title"] for b in sur_b if b["year_from_title"]})

    periods = sorted({t["wordName"]["hebrew"] for t in (e.get("thesaurus") or [])
                      if t.get("categoryId") == 4 and t.get("wordName", {}).get("hebrew")})
    contexts = sorted({t["wordName"]["hebrew"] for t in (e.get("thesaurus") or [])
                       if t.get("categoryId") == 5 and t.get("wordName", {}).get("hebrew")})

    gazette = (det or {}).get("atarOfficialAnnouncementGazette") or []
    gaz_dates = sorted({g["announcementDate"][:10] for g in gazette if g.get("announcementDate")})

    rec = {
        "_record_type": "declared_site",
        "_source_id": "iaa_discover",
        "_source_dataset": "discover.iaa.org.il /api/query + /api/hachraza (entityType=hachraza)",
        "_retrieved": RETRIEVED,
        "_srcfile": e.get("_srcfile"),
        "_has_detail_record": det is not None,
        "_has_agol_record": ag is not None,

        # ---- original fields, POST /api/query entity ----
        "entityType": e["entityType"],
        "entityId": e["entityId"],
        "originEntityId": e["originEntityId"],
        "title": e.get("title"),
        "description": e.get("description"),
        "imageUrl": e.get("imageUrl"),
        "externalUrl": e.get("externalUrl"),
        "downloadUrl": e.get("downloadUrl"),
        "licenses": e.get("licenses"),
        "thesaurus": e.get("thesaurus"),
        "shapes": e.get("shapes"),
        "parentEntities": e.get("parentEntities"),
    }

    # ---- original fields, GET /api/hachraza/{entityId} ----
    for k in ("hachrazaId", "hachrazaEntityId", "atarTitle", "atarType", "atarStatus",
              "isPublicAtar", "atarOfficialName", "atarNames", "atarDescription",
              "atarOfficialAnnouncementGazette", "atarTabu", "atarSouthWest", "atarNorthEast",
              "atarMehozName", "atarMerchavName", "ataId", "ataTatId", "atarSeif",
              "atarMapInformation", "atarPeriodsAndElements"):
        rec[k] = (det or {}).get(k)

    # ---- original fields, AGOL HACRAZOT_PUBLIC/FeatureServer/0 ----
    for k in ("objectid", "ata_id", "ata_tat_id", "xoid", "meh_id", "sai_id", "pers_do",
              "peilut_seq", "sug_atar", "ata_sug", "ata_shem", "ata_status", "ata_date_status",
              "ata_chang_id", "ata_date_ishur", "ata_ishur_id", "ata_sug_pir", "ata_last_pir",
              "ata_pir_amud", "ata_public", "ata_date_owner", "ata_not_ok", "ata_create_date",
              "ata_create_user", "ata_update_date", "ata_update_user", "ata_law", "kabala_date",
              "odaa_number", "odaa_date", "base_details_seq", "atar_number", "globalid",
              "Shape__Area", "Shape__Length"):
        rec["agol_" + k] = (ag or {}).get(k)

    # ---- derived ----
    rec.update(geom_summary(gs))
    rec.update({
        "derived_name_he": ((det or {}).get("atarOfficialName") or {}).get("hebrew")
                            or (e.get("title") or {}).get("hebrew"),
        "derived_name_en": ((det or {}).get("atarOfficialName") or {}).get("english")
                            or (e.get("title") or {}).get("english"),
        "derived_site_number": hid,
        "derived_site_number_main": (det or {}).get("ataId"),
        "derived_site_number_sub": (det or {}).get("ataTatId"),
        "derived_is_sub_site": (None if det is None
                                else (det.get("ataTatId") not in (None, 0))),
        "derived_status_he": (det or {}).get("atarStatus"),
        "derived_is_declared": (None if det is None
                                else (det.get("atarStatus") == "מוכרז/תקין")),
        "derived_public_access_flag": (det or {}).get("isPublicAtar"),
        "derived_declaration_dates": gaz_dates or None,
        "derived_declaration_first_date": gaz_dates[0] if gaz_dates else None,
        "derived_declaration_last_date": gaz_dates[-1] if gaz_dates else None,
        "derived_periods_he": periods or None,
        "derived_periods_reaching_past_1700": sorted(set(periods) & POST_1700_PERIODS) or None,
        "derived_period_span_crosses_1700": bool(set(periods) & POST_1700_PERIODS),
        "derived_archaeological_contexts_he": contexts or None,
        "derived_licence_count": len(lic_long),
        "derived_licence_names": lic_long or None,
        "derived_licence_prefixes": prefixes or None,
        "derived_licence_years": years or None,
        "derived_licence_year_min": years[0] if years else None,
        "derived_licence_year_max": years[-1] if years else None,

        # -- excavation / survey evidence. See docs section 10 item 5.
        # "confirmed" = the IAA's own licence record names both this site and an
        # excavation (or a survey). Nothing here is inferred from proximity.
        "derived_excavation_licence_names_confirmed": exc_lic_names or None,
        "derived_survey_licence_names_confirmed": sur_lic_names or None,
        "derived_licence_names_unresolved": unresolved_lic_names or None,
        "derived_licence_names_other": other_lic_names or None,
        "derived_licence_unresolved_count": len(unresolved_lic_names),
        "derived_excavation_entity_ids": sorted(exc_eids) or None,
        "derived_survey_entity_ids": sorted(sur_eids) or None,
        "derived_licence_link_routes": route_used,
        "derived_excavation_link_strength": (
            "bidirectional" if "bidirectional" in exc_routes
            else ("site_asserted" if "site_asserted" in exc_routes else None)),
        "derived_was_excavated": (
            True if (exc_lic_names or exc_eids or kids.get("excavation"))
            else (False if not (e.get("licenses") or []) else None)),
        "derived_excavation_evidence": (
            "confirmed_excavation_licence" if (exc_lic_names or exc_eids or kids.get("excavation"))
            else ("no_licences_at_all" if not (e.get("licenses") or [])
                  else ("survey_licences_only" if (sur_lic_names and not unresolved_lic_names)
                        else "unresolved"))),
        "derived_excavation_count": len(exc_b),
        "derived_excavation_years": exc_years or None,
        "derived_excavations": exc_b or None,
        "derived_survey_count": len(sur_b),
        "derived_survey_years": sur_years or None,
        "derived_surveys": sur_b or None,
        "derived_expeditions": exp_b or None,
        "derived_publications": pub_b or None,
        "derived_conservation_reports": con_b or None,
        "derived_has_conservation_report": bool(con_b),
        "derived_tabu_gushim": sorted({t["tabuGush"] for t in ((det or {}).get("atarTabu") or [])
                                       if t.get("tabuGush")}) or None,
        "derived_tabu_yishuvim": sorted({t["tabuYishuvName"] for t in ((det or {}).get("atarTabu") or [])
                                         if t.get("tabuYishuvName")}) or None,
        "derived_survey_sheet_sai_id": (ag or {}).get("sai_id"),
        "derived_internal_note": (ag or {}).get("ata_not_ok"),
        "derived_permalink": f"https://discover.iaa.org.il/?entityId={e['entityId']}&entityType=hachraza",
    })
    records.append(rec)
print("declared_site records from the API:", n_win, flush=True)

# ---- 1b. declared sites present ONLY in the ArcGIS layer --------------------
# Completeness control: the ArcGIS envelope query is a pure spatial query over
# the authoritative national layer (24,714 records) with no administrative
# filter, so anything it returns inside the window that the region/settlement
# pull missed is a genuine gap. These records have no /api/hachraza detail
# because we never obtained their entityId, so every detail field stays null.
api_numbers = {r["derived_site_number"] for r in records if r["_record_type"] == "declared_site"}
n_agol_only = 0
for num, ag in sorted(agol.items()):
    if num in api_numbers:
        continue
    n_agol_only += 1
    g = agol_geom.get(num)
    rec = {
        "_record_type": "declared_site",
        "_source_id": "iaa_discover",
        "_source_dataset": "ArcGIS HACRAZOT_PUBLIC/FeatureServer/0 only (absent from the /api/query pull)",
        "_retrieved": RETRIEVED,
        "_srcfile": "12_agol_hacrazot_public_window_off*.geojson",
        "_has_detail_record": False,
        "_has_agol_record": True,
        "entityType": "hachraza", "entityId": None, "originEntityId": num,
        "title": None, "description": None, "imageUrl": None, "externalUrl": None,
        "downloadUrl": None, "licenses": None, "thesaurus": None, "shapes": None,
        "parentEntities": None,
    }
    for k in ("hachrazaId", "hachrazaEntityId", "atarTitle", "atarType", "atarStatus",
              "isPublicAtar", "atarOfficialName", "atarNames", "atarDescription",
              "atarOfficialAnnouncementGazette", "atarTabu", "atarSouthWest", "atarNorthEast",
              "atarMehozName", "atarMerchavName", "ataId", "ataTatId", "atarSeif",
              "atarMapInformation", "atarPeriodsAndElements"):
        rec[k] = None
    for k in ag:
        rec["agol_" + k] = ag[k]
    if g is not None:
        b = g.bounds
        cx = (b[0] + b[2]) / 2.0; cy = (b[1] + b[3]) / 2.0
        lat, lon = itm_to_wgs(cx, cy)
        rec.update(dict(derived_itm_x=round(cx, 2), derived_itm_y=round(cy, 2), lat=lat, lon=lon,
                        derived_itm_xmin=round(b[0], 2), derived_itm_ymin=round(b[1], 2),
                        derived_itm_xmax=round(b[2], 2), derived_itm_ymax=round(b[3], 2),
                        derived_bbox_width_m=round(b[2]-b[0], 1), derived_bbox_height_m=round(b[3]-b[1], 1),
                        derived_position_uncertainty_m=round(max(b[2]-b[0], b[3]-b[1]) / 2.0, 1),
                        derived_n_shapes=1, derived_shape_is_rectangle=None,
                        derived_shape_wkt_itm=g.wkt))
    rec.update({
        "derived_name_he": ag.get("ata_shem"), "derived_name_en": None,
        "derived_site_number": num,
        "derived_site_number_main": ag.get("ata_id"),
        "derived_site_number_sub": ag.get("ata_tat_id"),
        "derived_is_sub_site": (ag.get("ata_tat_id") not in (None, 0)),
        "derived_status_he": None, "derived_is_declared": None,
        "derived_public_access_flag": None,
        "derived_was_excavated": None,
        "derived_excavation_evidence": "no_api_record",
        "derived_survey_sheet_sai_id": ag.get("sai_id"),
        "derived_internal_note": ag.get("ata_not_ok"),
        "derived_permalink": None,
    })
    records.append(rec)
print("declared_site records present only in the ArcGIS layer:", n_agol_only, flush=True)

# ---- 2. excavations ---------------------------------------------------------
# licenceId -> declared-site entityIds (from the license entity's parentEntities)
lic_to_sites = collections.defaultdict(set)
for lid, le in lic_entity.items():
    for p in (le.get("parentEntities") or []):
        if p.get("parentType") == "hachrazot":
            lic_to_sites[lid].add(p["parentEntityId"])
hach_by_eid = by_type.get("hachraza", {})

n_exc = 0
for i, e in sorted(by_type.get("excavation", {}).items()):
    gs = shapes_geom(e)
    if not in_window_itm(gs):
        continue
    n_exc += 1
    lic_long = [l["longName"] for l in (e.get("licenses") or [])]
    parsed = [parse_licence(x) for x in lic_long]
    years = sorted({y for _, _, y in parsed if y})
    site_eids = set()
    for l in (e.get("licenses") or []):
        site_eids |= lic_to_sites.get(l["licenseId"], set())
    sites = []
    for se in sorted(site_eids):
        h = hach_by_eid.get(se)
        if not h:
            continue
        sites.append({"entityId": se, "site_number": h["originEntityId"],
                      "title_hebrew": (h.get("title") or {}).get("hebrew")})
    rec = {
        "_record_type": "excavation",
        "_source_id": "iaa_discover",
        "_source_dataset": "discover.iaa.org.il /api/query (entityType=excavation)",
        "_retrieved": RETRIEVED,
        "_srcfile": e.get("_srcfile"),
        "entityType": e["entityType"], "entityId": e["entityId"],
        "originEntityId": e["originEntityId"],
        "title": e.get("title"), "description": e.get("description"),
        "imageUrl": e.get("imageUrl"), "externalUrl": e.get("externalUrl"),
        "downloadUrl": e.get("downloadUrl"), "licenses": e.get("licenses"),
        "thesaurus": e.get("thesaurus"), "shapes": e.get("shapes"),
        "parentEntities": e.get("parentEntities"),
    }
    rec.update(geom_summary(gs))
    rec.update({
        "derived_name_he": (e.get("title") or {}).get("hebrew"),
        "derived_name_en": (e.get("title") or {}).get("english"),
        "derived_excavator_he": responsible_from_description(e),
        "derived_year_from_title": year_from_title(e),
        "derived_licence_names": lic_long or None,
        "derived_licence_years": years or None,
        "derived_attached_declared_sites": sites or None,
        "derived_attached_declared_site_numbers": [s["site_number"] for s in sites] or None,
        "derived_permalink": f"https://discover.iaa.org.il/?entityId={e['entityId']}&entityType=excavation",
    })
    records.append(rec)
print("excavation records:", n_exc, flush=True)

# ---- 3. Archaeological Survey of Israel sites -------------------------------
map_meta = {}
mm = json.load(open(os.path.join(RAW, "18_survey_GetMaps.json"), encoding='utf-8'))["d"]
if isinstance(mm, str):
    mm = json.loads(mm)
for m in mm:
    map_meta[str(m["id"])] = m

T4326_2039 = Transformer.from_crs("EPSG:4326", "EPSG:2039", always_xy=True)
n_sv = 0
for fn in sorted(glob.glob(os.path.join(RAW, "20_survey_GetPolygonsSites_map*.json"))):
    d = json.load(open(fn, encoding='utf-8'))["d"]
    if isinstance(d, str):
        d = json.loads(d)
    for f in d.get("features", []):
        props = {p["key"]: p["value"] for p in f["properties"]}
        g = f["geometry"]
        c = g["coordinates"]
        if g["type"] != "point" or not isinstance(c[0], (int, float)):
            lon = lat = None
        else:
            lon, lat = float(c[0]), float(c[1])
        if lat is None or not (WIN_LL[0] <= lat <= WIN_LL[1] and WIN_LL[2] <= lon <= WIN_LL[3]):
            continue
        n_sv += 1
        x, y = T4326_2039.transform(lon, lat)
        mid = props.get("gis_map_id")
        meta = map_meta.get(str(mid), {})
        records.append({
            "_record_type": "survey_site",
            "_source_id": "iaa_discover",
            "_source_dataset": "survey.iaa.org.il aspxService/Service.aspx (Archaeological Survey of Israel)",
            "_retrieved": RETRIEVED,
            "_srcfile": os.path.basename(fn),
            # original fields
            "id": props.get("id"),
            "site_num": props.get("site_num"),
            "gis_map_id": props.get("gis_map_id"),
            "name_heb": props.get("name_heb"),
            "description_heb": props.get("description_heb"),
            "finding_heb": props.get("finding_heb"),
            "bibliography_heb": props.get("bibliography_heb"),
            "icon": props.get("icon"),
            "geometry": g,
            # survey-sheet metadata (original field names from /GetMaps)
            "map_num": meta.get("map_num"),
            "map_name": meta.get("name"),
            "map_Author": meta.get("Author"),
            "map_isbn": meta.get("isbn"),
            # derived
            "lat": round(lat, 7), "lon": round(lon, 7),
            "derived_itm_x": round(x, 2), "derived_itm_y": round(y, 2),
            "derived_name_he": props.get("name_heb"),
            "derived_survey_sheet_number": meta.get("map_num"),
            "derived_survey_site_ref": (f'{meta.get("map_num")}/{props.get("site_num")}'
                                       if meta.get("map_num") else None),
            "derived_position_uncertainty_m": None,
            "derived_permalink": (f'https://survey.iaa.org.il/#/MapSurvey/{mid}' if mid else None),
        })
print("survey_site records:", n_sv, flush=True)

# ---------------------------------------------------------------- normalise keys
# Every record of a given _record_type gets every key seen in that type, so a
# consumer can rely on a stable column set. Filler is null, never a made-up value.
keys_by_type = collections.defaultdict(set)
for r in records:
    keys_by_type[r["_record_type"]] |= set(r.keys())
for r in records:
    for k in keys_by_type[r["_record_type"]]:
        r.setdefault(k, None)
print("\nstable key count per record type:",
      {k: len(v) for k, v in keys_by_type.items()}, flush=True)

# ---------------------------------------------------------------- write
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(records, fh, ensure_ascii=False, indent=1)
print("\nWROTE", OUT, len(records), "records", flush=True)
print("by _record_type:", collections.Counter(r["_record_type"] for r in records).most_common())
