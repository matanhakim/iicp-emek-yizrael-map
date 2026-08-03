"""Source adapters: raw extraction output in, CLAIM RECORDS out.

Each adapter owns exactly one source and answers three questions about it: which of its
rows belong on this map at all, what each of its columns means in our vocabulary, and what
it is entitled to claim. An adapter never invents a value and never reaches into another
source's data.

Output: data/interim/<source_id>.claims.json, consumed by src/harmonize.py.
"""

from __future__ import annotations

import collections
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import geo  # noqa: E402
import hebrew as he  # noqa: E402
import schema as sc  # noqa: E402
import vocabmap as vm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INTERIM = ROOT / "data" / "interim"
RAW = ROOT / "data" / "raw"
TODAY = "2026-08-03"

COUNCIL_NAME = "עמק יזרעאל"


def load(name: str):
    p = INTERIM / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


_LOCALITIES: set[str] | None = None


def known_localities() -> set[str]:
    """Normalized names of the council's settlements.

    Used to sanitise the locality field. Wikidata's P131 returns the whole administrative
    chain, so an unfiltered read yields localities like ישראל and מחוז הצפון, which are true
    statements and useless ones. A locality that is not a settlement of this council is
    dropped rather than kept as noise.
    """
    global _LOCALITIES
    if _LOCALITIES is not None:
        return _LOCALITIES
    names: set[str] = set()
    p = RAW / "settlements_emek_yizrael.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else (
            data.get("settlements") or data.get("records") or [])
        for r in rows:
            if isinstance(r, str):
                names.add(r)
            elif isinstance(r, dict):
                for k in ("name_he", "name", "shem_yishuv", "שם יישוב", "settlement"):
                    if r.get(k):
                        names.add(str(r[k]))
                        break
    for r in load("iicp_culture_table.json") or []:
        if r.get("_is_emek_yizrael_council") and clean(r.get("שם יישוב")):
            names.add(clean(r["שם יישוב"]))
    _LOCALITIES = {he.key(n) for n in names if he.key(n)}
    return _LOCALITIES


def sane_locality(value) -> str | None:
    """Return the value only if it names a settlement of this council."""
    v = clean(value)
    if not v:
        return None
    for part in re.split(r"[;|,]", str(v)):
        part = part.strip()
        if part and he.key(part) in known_localities():
            return part
    return None


def clean(v):
    """Blank-ish source values become None. Israeli exports are full of ' ' and '-'."""
    if v is None:
        return None
    if isinstance(v, (dict, list, tuple, set)):
        # Some IAA fields are objects ({hebrew, english}) rather than strings. A caller that
        # wants one of those must reach into it explicitly, so refuse it here instead of
        # letting a dict leak into a name or a regex.
        return None
    if isinstance(v, str):
        s = v.strip().strip("‎‏")
        if s in ("", "-", "--", "לא ידוע", "אין מידע", "אין", "לא רלוונטי", "nan", "None"):
            return None
        return s
    return v


def claim(source_id, record_id, **kw) -> dict:
    """Build a CLAIM_RECORD with all the required keys present."""
    r = {
        "source_id": source_id, "record_id": record_id, "url": None, "retrieved": TODAY,
        "name": None, "names_alt": [], "name_en": None, "description": None,
        "lat": None, "lon": None, "itm_x": None, "itm_y": None,
        "location_precision": "unknown", "category_hint": None, "type": None,
        "periods": [], "year_from": None, "year_to": None, "date_text": None,
        "locality": None, "statuses": {}, "practical": {}, "ids": {}, "extra": {}, "raw": {},
    }
    r.update(kw)
    r["names_alt"] = [n for n in (r["names_alt"] or []) if n and he.key(n) != he.key(r["name"])]
    r["statuses"] = {k: v for k, v in (r["statuses"] or {}).items()
                     if v is not None and k in sc.STATUS_AXES}
    r["practical"] = {k: v for k, v in (r["practical"] or {}).items() if v is not None}
    r["ids"] = {k: v for k, v in (r["ids"] or {}).items() if v is not None}
    r["extra"] = {k: v for k, v in (r["extra"] or {}).items() if v not in (None, "", [], {})}
    return r


# --------------------------------------------------------------------------------------
# name conventions
# --------------------------------------------------------------------------------------
# Israeli antiquity catalogues invert the name: "פרוה, ח'" means "ח' פרוה". A different
# comma convention appends a sub-feature: "בית שערים, בית כנסת" is the synagogue AT Beit
# She'arim. The two look identical and mean opposite things, so both are handled and the
# untouched original is always kept as an alias.
_GENERIC_TAILS = {
    "ח'", "ח", "חר'", "חורבת", "חורבה", "תל", "ת'ל", "ע'", "עין", "באר", "ביר",
    "נבי", "שיח", "שייח", "דיר", "רוג'ם", "רג'ם", "כ'", "ג'", "כפר", "מערת", "אום",
}


def split_catalog_name(raw: str | None) -> tuple[str | None, str | None]:
    """Return (site name, sub-feature type key or None)."""
    s = clean(raw)
    if not s or "," not in s:
        return s, None
    head, _, tail = s.rpartition(",")
    head, tail = head.strip(), tail.strip()
    if not head or not tail:
        return s, None
    if tail in _GENERIC_TAILS or (len(tail) <= 3 and tail.endswith("'")):
        return f"{tail} {head}", None          # inverted catalogue form
    t = vm.site_type(tail)
    if t:
        return head, t                          # sub-feature qualifier
    return s, None


# --------------------------------------------------------------------------------------
# 1. IAA conservation survey table (Table A of the user-supplied files)
# --------------------------------------------------------------------------------------
def adapt_iaa_cluster_table() -> list[dict]:
    """רשות העתיקות conservation survey, Galilee and Valleys cluster.

    No coordinates anywhere in this source, so every row arrives geometry-free and depends
    on matching against a source that does have a position. In exchange it carries by far
    the richest status data of any source: excavation state, tourism development, physical
    condition, conservation works, statutory protection and the antiquity site number.

    Scope: rows whose own LOCAL_AUTHORITY column says עמק יזרעאל. The other 18 rows belong
    to neighbouring councils by the source's own attribution and are dropped, not guessed at.
    """
    rows = load("iaa_cluster_table.json") or []
    out = []
    for r in rows:
        if clean(r.get("LOCAL_AUTHORITY")) != COUNCIL_NAME:
            continue
        name, sub_type = split_catalog_name(r.get("SHEM_ATAR"))
        feature = clean(r.get("FEATURE_NAME"))
        if not name:
            name = feature
        if not name:
            continue

        st: dict = {}
        st["excavation"] = vm.EXC_STATUS.get(clean(r.get("EXC_STATUS")))
        turism = clean(r.get("INV_TURISM"))
        st["visitor_dev"] = vm.TURISM_DEV.get(turism)
        st["accessibility"] = vm.TURISM_ACCESS.get(turism)
        st["reg_conservation"] = vm.SHIMUR_STATUS.get(clean(r.get("SHIMUR_STATUS")))
        st["condition"] = (vm.ENGINEERING_CONDITION.get(clean(r.get("ENGINEERING_STATE")))
                           or vm.RISK_CONDITION.get(clean(r.get("GENERAL_RISK_LEVEL"))))
        st.update(vm.statutory_protection(r.get("STATUTORY_PROTECTION")))
        st.setdefault("protected_area", vm.current_use_protected(r.get("CURRENT_USE")))
        if clean(r.get("INV_KNOWN_INTRS")) and 'רט"ג' in str(r.get("INV_KNOWN_INTRS")):
            st.setdefault("ownership", "state")

        periods = vm.periods(r.get("INV_PERIODS"))
        site_no = r.get("_ata_site_number")
        sub_no = r.get("_ata_sub_number")

        out.append(claim(
            "iaa_cluster_table", r.get("_record_id") or f"A{r.get('_excel_row')}",
            name=name,
            names_alt=[clean(r.get("SHEM_ATAR")), feature],
            description=clean(r.get("ATAR_DESC")) or clean(r.get("DESCRIPTION")),
            category_hint="archaeological",
            type=sub_type or vm.site_type(r.get("INV_ELEMENT"), r.get("CATEGORY"),
                                          r.get("SPATIAL_DISTRIBUTION"), name),
            periods=periods,
            statuses=st,
            location_precision="unknown",
            # The MAIN antiquity site number is the identity; the sub-number identifies a
            # sub-feature (תת-אתר) of that same site. Keying on the full "2500/33" made two
            # records of Beit She'arim look like two different sites and blocked their merge.
            ids={"iaa_site_id": str(site_no) if site_no is not None else None},
            extra={
                "site_xoid": r.get("SITE_XOID"),
                "ata_num": clean(r.get("ATA_NUM")),
                "iaa_site_sub_id": f"{site_no}/{sub_no}" if site_no is not None else None,
                "feature_name": feature,
                "feature_type": clean(r.get("FEATURE_TYPE")),
                "iaa_category": clean(r.get("CATEGORY")),
                "survey": clean(r.get("SURVEY")),
                "iaa_district": clean(r.get("MAHOZ")),
                "current_use": clean(r.get("CURRENT_USE")),
                "access_route": clean(r.get("INV_ACCESS")),
                "access_remark": clean(r.get("ACCESS_REMARK")),
                "remains_height": clean(r.get("REMAINS_HEIGHT")),
                "engineering_state": clean(r.get("ENGINEERING_STATE")),
                "risk_level": clean(r.get("GENERAL_RISK_LEVEL")),
                "threats": clean(r.get("THREATS_DESC")),
                "weathering": clean(r.get("ACTIVE_WEATHERING")),
                "cultural_display": clean(r.get("CULTURAL_DISPLAY")),
                "wall_technique": clean(r.get("INV_TECHNIQUES")) or clean(r.get("WALL_TECHNIQUE")),
                "shimur_status": clean(r.get("SHIMUR_STATUS")),
                "shimur_project": clean(r.get("SHIMUR_PROJ_NUM")),
                "treatment_needed": clean(r.get("INV_TREATEMENT_NEEDED")),
                "periods_raw": clean(r.get("INV_PERIODS")),
                "excavation_years": [str(r["EXC_YEAR"])] if clean(r.get("EXC_YEAR")) else [],
            },
            raw={k: v for k, v in r.items() if not k.startswith("_")},
        ))
    return out


# --------------------------------------------------------------------------------------
# 2. IICP culture and heritage inventory (Table B)
# --------------------------------------------------------------------------------------
def adapt_iicp_culture_table() -> list[dict]:
    """The institute's own field inventory.

    Scope: rows the extraction step attributed to Emek Yizrael Regional Council and did not
    exclude. Rows whose סוג רשומה is אדם are individual people, out of scope by the brief,
    and were already flagged `_excluded`; they are not read here at all.

    Only 46 of its rows carry a coordinate. The rest are contributed for their names,
    statuses and contact details and are positioned by matching.
    """
    rows = load("iicp_culture_table.json") or []
    out = []
    for r in rows:
        if not r.get("_is_emek_yizrael_council") or r.get("_excluded"):
            continue
        name = clean(r.get("שם מוסד"))
        if not name:
            continue

        kind = clean(r.get("סוג רשומה"))
        arch_her = clean(r.get("ארכיאולוגי / מורשת"))
        if arch_her == "ארכיאולוגי":
            cat = "archaeological"
        elif arch_her == "מורשת":
            cat = "historic"
        elif kind == "מוסד":
            cat = "culture"
        else:
            cand = clean(r.get("_map_category_candidate"))
            cat = {"culture_institution": "culture", "historic": "historic",
                   "archaeological": "archaeological"}.get(cand)

        st: dict = {}
        for token, mapping in vm.IICP_STATE.items():
            if clean(r.get("פעיל / משומר / מוכר")) == token:
                st.update(mapping)
        if r.get("קיום שלט כחול") is True:
            st["signage"] = "blue_sign"
        elif r.get("קיום שלט כחול") is False and r.get("הנגשה - שילוט") is True:
            st["signage"] = "other_sign"
        elif r.get("קיום שלט כחול") is False and r.get("הנגשה - שילוט") is False:
            st["signage"] = "none"
        if r.get("הנגשה - גישה לנכים") is True:
            st["a11y_disabled"] = "accessible"
        elif r.get("הנגשה - גישה לנכים") is False:
            st["a11y_disabled"] = "not_accessible"
        st["ownership"] = vm.ownership(r.get("מגזר"))
        if cat == "culture" and "activity" not in st:
            # The institute recorded the place as operating, but did not state a date, so
            # this is an unverified activity claim and stays out. The verification wave
            # resolves it from first-party evidence.
            pass

        lat, lon = r.get("lat"), r.get("lon")
        desc = clean(r.get("תיאור (מה זה)"))
        locality = clean(r.get("שם יישוב"))

        # Contact details for a private-sector record can belong to a person rather than an
        # institution, so they are kept internally and redacted at publish time.
        sector = clean(r.get("מגזר"))
        out.append(claim(
            "iicp_culture_table", r.get("_record_id"),
            name=name,
            description=desc,
            category_hint=cat,
            type=vm.site_type(desc, name, r.get("תחום")),
            lat=lat, lon=lon,
            location_precision="approx_100m" if lat is not None else "unknown",
            locality=locality,
            statuses=st,
            practical={
                "address": clean(r.get("כתובת")),
                "phone": clean(r.get("מספר טלפון")),
                "email": clean(r.get("דואר אלקטרוני")),
                "website": clean(r.get("אתר אינטרנט")),
                "operator": None,
            },
            extra={
                "locality_code": r.get("סמל יישוב"),
                "domain": clean(r.get("תחום")),
                "record_kind": kind,
                "inside_or_outside_settlement": clean(r.get("בתוך ישוב / מחוץ")),
                "sector": sector,
                "web_presence_score": r.get("הנגשה - קיום ידע במרשתת"),
                "notes": clean(r.get("הערות")),
                "google_plus_code": clean(r.get("קוד כתובת (גוגל)")),
                "contact_is_private_sector": sector == "פרטי",
            },
            raw={k: v for k, v in r.items()
                 if not k.startswith("_") and k not in ("ממפה",)},  # mapper name is staff PII
        ))
    return out


# --------------------------------------------------------------------------------------
# 3. OpenStreetMap and Wikidata cross-check layer
# --------------------------------------------------------------------------------------
# A relevance gate is unavoidable here. The extraction ran over a box around the council
# and so returned hills, wadis, springs, kibbutzim and Highway 75, none of which is a
# heritage site or a culture institution. Two rules, both deliberately conservative:
#   - an OSM record needs a tag that identifies a heritage or culture PLACE;
#   - a Wikidata record needs a relevant class, or a heritage identifier that proves
#     somebody official has designated it.
# A functioning contemporary place of worship is NOT in scope: it is neither pre-1700
# archaeology, nor a designated post-1700 heritage site, nor a culture institution. It
# enters only with independent evidence of heritage status or a pre-1948 date.
_WD_RELEVANT_CLASS = {
    "אתר ארכאולוגי", "תל", "עיר עתיקה", "מערת קבורה", "מערה", "אמת מים", "מטחנה",
    "אנדרטה", "פסל", "כנסייה", "בית כנסת", "מסגד", "מנזר", "ארכיון", "ארכיון קיבוצי",
    "ארכיון יישובי", "מוזיאון", "ספרייה", "תיאטרון", "תחנת רכבת", "מבנה רומי עתיק",
    "תיאטרון רומי", "שמורת טבע", "שמורת יער", "פארק לאומי", "גן לאומי", "יער",
    "כפר פלסטיני עקור", "יישוב לשעבר", "קרב", "בית קברות", "אתר מורשת", "מבצר",
    "בית עלמין", "גשר היסטורי", "מבנה היסטורי", "אתר היסטורי", "מגדל מים",
}
_WD_HERITAGE_IDS = (
    "wd_P1435_heritage_designation", "wd_P3941_israel_antiquities_authority_id",
    "wd_P2186_wiki_loves_monuments_id", "wd_P10392_inpa_park_id",
)
_OSM_ALWAYS = ("historic", "heritage", "archaeological_site", "tomb", "memorial", "ruins")


def _osm_relevant(r: dict) -> tuple[bool, str | None]:
    for k in _OSM_ALWAYS:
        if clean(r.get(k)):
            return True, f"{k}={r.get(k)}"
    if clean(r.get("man_made")) in ("watermill", "water_well", "cistern", "water_tower"):
        return True, f"man_made={r.get('man_made')}"
    if clean(r.get("tourism")) in ("museum", "gallery", "artwork"):
        return True, f"tourism={r.get('tourism')}"
    if clean(r.get("amenity")) in ("library", "arts_centre", "theatre", "community_centre", "cinema"):
        return True, f"amenity={r.get('amenity')}"
    if clean(r.get("boundary")) == "protected_area" or clean(r.get("leisure")) == "nature_reserve":
        return True, "protected_area"
    if clean(r.get("amenity")) == "place_of_worship":
        # Needs independent evidence of heritage status or a pre-state date.
        sd = str(clean(r.get("start_date")) or "")
        m = re.search(r"\b(1[0-9]{3})\b", sd)
        if clean(r.get("heritage")) or clean(r.get("historic")) or (m and int(m.group(1)) < 1948):
            return True, "place_of_worship+heritage_evidence"
        return False, None
    if clean(r.get("tourism")) == "information" and clean(r.get("information")) == "board":
        return False, None
    return False, None


def _wd_relevant(r: dict) -> tuple[bool, str | None]:
    for p in _WD_HERITAGE_IDS:
        if clean(r.get(p)):
            return True, p
    groups = str(clean(r.get("wd_relevance_groups")) or "")
    if groups and groups != "None":
        return True, f"relevance={groups}"
    labels = {x.strip() for x in str(clean(r.get("wd_P31_instance_of_he")) or "").split("|")
              for x in x.split(";")}
    hit = labels & _WD_RELEVANT_CLASS
    if hit:
        return True, f"class={sorted(hit)[0]}"
    return False, None


def _year(v) -> int | None:
    if v in (None, ""):
        return None
    m = re.search(r"(-?\d{1,4})", str(v))
    if not m:
        return None
    y = int(m.group(1))
    return y if -4000 <= y <= 2100 else None


def adapt_osm_wikidata(jur: geo.Jurisdiction | None = None) -> list[dict]:
    rows = load("osm_wikidata.json") or []
    out = []
    for r in rows:
        lat, lon = r.get("lat"), r.get("lon")
        if lat is None or lon is None:
            continue
        # Keep everything inside the council plus a 600 m apron, so a site whose OSM node
        # sits just outside the line can still be matched and then adjudicated.
        if jur is not None:
            d = jur.signed_distance_m(lat, lon)
            if d < -600:
                continue
        elif not r.get("in_council_boundary"):
            continue

        is_osm = r.get("rec_source") in ("osm", "both")
        is_wd = r.get("rec_source") in ("wikidata", "both")
        why_osm = why_wd = None
        ok = False
        if is_osm:
            ok_o, why_osm = _osm_relevant(r)
            ok = ok or ok_o
        if is_wd:
            ok_w, why_wd = _wd_relevant(r)
            ok = ok or ok_w
        if not ok:
            continue

        name = (clean(r.get("name:he")) or clean(r.get("wd_label_he"))
                or clean(r.get("name")) or clean(r.get("wd_P1705_native_label")))
        if not name:
            continue
        alts = [clean(r.get(k)) for k in ("name", "alt_name", "alt_name:he", "loc_name:he",
                                          "old_name", "wd_P1448_official_name", "wd_label_he")]

        # type
        t = None
        if clean(r.get("archaeological_site")):
            t = vm.OSM_ARCH_SITE_TYPE.get(str(r["archaeological_site"]).lower())
        if not t:
            for tag in ("historic", "tourism", "amenity", "man_made", "railway"):
                v = clean(r.get(tag))
                if v:
                    t = vm.OSM_TYPE.get(f"{tag}={v}")
                    if t:
                        break
        if not t:
            qids = str(clean(r.get("wd_P31_instance_of_qids")) or "")
            for q in re.findall(r"Q\d+", qids):
                if q in vm.WD_TYPE and q not in vm.WD_TYPE_BLOCKLIST:
                    t = vm.WD_TYPE[q]
                    break
        if not t:
            t = vm.site_type(clean(r.get("wd_P31_instance_of_he")),
                             clean(r.get("wd_description_he")), name)

        # dates and periods
        periods = vm.periods(clean(r.get("wd_P2348_time_period_he")))
        if not periods:
            periods = vm.periods(clean(r.get("historic:civilization")))
        y_from = _year(clean(r.get("wd_P571_inception"))) or _year(clean(r.get("start_date")))
        y_to = _year(clean(r.get("wd_P576_dissolved_demolished_date")))

        st: dict = {}
        if clean(r.get("boundary")) == "protected_area" or clean(r.get("leisure")) == "nature_reserve":
            title = str(clean(r.get("protect_title")) or clean(r.get("protection_title")) or "")
            st["protected_area"] = ("national_park" if "לאומי" in title or "National" in title
                                    else "nature_reserve")
        if clean(r.get("wd_P10392_inpa_park_id")):
            st.setdefault("protected_area", "national_park")
        wc = clean(r.get("wheelchair"))
        if wc in ("yes", "designated"):
            st["a11y_disabled"] = "accessible"
        elif wc == "limited":
            st["a11y_disabled"] = "partial"
        elif wc == "no":
            st["a11y_disabled"] = "not_accessible"
        acc = clean(r.get("access"))
        if acc in ("yes", "public"):
            st["accessibility"] = "open_free"
        elif acc in ("private", "no"):
            st["accessibility"] = "not_accessible"
        elif acc == "permissive":
            st["accessibility"] = "open_free"
        if clean(r.get("historic")) == "ruins" or clean(r.get("ruins")):
            st.setdefault("condition", "poor")

        # category
        cat = None
        if t in sc.SITE_TYPES and sc.SITE_TYPES[t]["cat"]:
            cat = sc.SITE_TYPES[t]["cat"]
        era = sc.era_from_periods(periods)
        if era:
            cat = era
        elif y_from is not None:
            cat = "archaeological" if y_from < sc.ANTIQUITY_CUTOFF_YEAR else "historic"

        out.append(claim(
            "osm_wikidata", r.get("rec_id"),
            url=clean(r.get("osm_url")) or clean(r.get("wd_url")),
            name=name, names_alt=alts,
            name_en=clean(r.get("name:en")) or clean(r.get("wd_label_en")),
            description=clean(r.get("description:he")) or clean(r.get("wd_description_he")),
            category_hint=cat, type=t, periods=periods,
            year_from=y_from, year_to=y_to,
            date_text=clean(r.get("wd_P2348_time_period_he")),
            lat=lat, lon=lon,
            location_precision=("exact" if r.get("geom_method") == "osm_node_coordinates"
                                else "approx_100m"),
            locality=(sane_locality(r.get("addr:city"))
                      or sane_locality(r.get("wd_P131_located_in_admin_entity_he"))
                      or sane_locality(r.get("addr:city:he"))),
            statuses=st,
            practical={
                "address": " ".join(x for x in [clean(r.get("addr:street")), clean(r.get("addr:housenumber"))] if x) or clean(r.get("wd_P6375_street_address")),
                "phone": clean(r.get("phone")) or clean(r.get("wd_P1329_phone_number")),
                "email": clean(r.get("wd_P968_email")),
                "website": clean(r.get("website")) or clean(r.get("contact:website")) or clean(r.get("wd_P856_official_website")),
                "hours_text": clean(r.get("opening_hours")),
                "operator": clean(r.get("operator")),
                "founded_year": y_from if (y_from or 0) > 1700 else None,
            },
            ids={
                "wikidata_qid": clean(r.get("wd_qid")) or clean(r.get("wikidata")),
                "osm_id": f"{r.get('osm_type')}/{r.get('osm_id')}" if r.get("osm_id") else None,
                "iaa_site_id": clean(r.get("wd_P3941_israel_antiquities_authority_id")),
            },
            extra={
                "wikipedia_he": clean(r.get("wd_hewiki_url")),
                "image_url": clean(r.get("wd_P18_image")) or clean(r.get("image")),
                "image_credit": "Wikimedia Commons" if clean(r.get("wd_P18_image")) else None,
                "heritage_designation": clean(r.get("wd_P1435_heritage_designation_he")),
                "wlm_id": clean(r.get("wd_P2186_wiki_loves_monuments_id")),
                "inpa_park_id": clean(r.get("wd_P10392_inpa_park_id")),
                "wd_classes": clean(r.get("wd_P31_instance_of_he")),
                "relevance_reason": why_osm or why_wd,
                "rec_source": r.get("rec_source"),
                "osm_wd_coord_distance_m": r.get("osm_wd_coord_distance_m"),
                "architect": clean(r.get("wd_P84_architect_he")),
                "architectural_style": clean(r.get("wd_P149_architectural_style_he")),
                "inscription": clean(r.get("inscription")),
                "material": clean(r.get("material")),
            },
            raw={k: v for k, v in r.items() if k in (
                "rec_id", "osm_type", "osm_id", "wd_qid", "historic", "tourism", "amenity",
                "man_made", "heritage", "archaeological_site", "start_date",
                "wd_P31_instance_of_he", "wd_P571_inception", "wd_P2348_time_period_he")},
        ))
    return out


# --------------------------------------------------------------------------------------
# 4. IAA national archaeology database (discover.iaa.org.il)
# --------------------------------------------------------------------------------------
APRON_M = -600.0  # keep a record this far outside the line so it can still be matched


def _in_scope(jur, lat, lon) -> bool:
    if lat is None or lon is None:
        return False
    if jur is None:
        return True
    return jur.signed_distance_m(lat, lon) > APRON_M


def _coords(r: dict, jur) -> tuple[float | None, float | None]:
    lat, lon = r.get("lat"), r.get("lon")
    if lat is None and r.get("derived_itm_x") is not None:
        try:
            lat, lon = geo.to_wgs84(r["derived_itm_x"], r["derived_itm_y"], "itm", geo.PLAUSIBLE)
        except geo.CoordError:
            return None, None
    return lat, lon


_DECLARED_PREFIX = re.compile(r"^\s*(אתר מוכרז|אתר עתיקות מוכרז)\s*")
_TRAILING_NUM = re.compile(r"\s+\d{1,6}\s*$")


def _discover_name(r: dict) -> str | None:
    """Site name from an IAA record. Titles arrive as 'אתר מוכרז בית שערים, ח' 2500'."""
    for cand in (clean(r.get("atarOfficialName")),
                 clean((r.get("title") or {}).get("hebrew") if isinstance(r.get("title"), dict) else None),
                 clean(r.get("name_heb")), clean(r.get("agol_ata_shem"))):
        if not cand:
            continue
        s = _TRAILING_NUM.sub("", _DECLARED_PREFIX.sub("", cand)).strip()
        if s:
            name, _ = split_catalog_name(s)
            return name
    return None


def adapt_iaa_discover(jur=None) -> list[dict]:
    """המאגר הלאומי לארכאולוגיה, רשות העתיקות.

    Three record types arrive in one file and only two of them are places:

      declared_site  a declaration record (הכרזה). Authoritative for reg_antiquity.
      survey_site    a site documented by the Archaeological Survey of Israel. Known to the
                     state but not necessarily declared, which is exactly the distinction
                     between reg_antiquity 'declared' and 'known'.
      excavation     an EVENT, not a place. Excavations are aggregated onto the site they
                     belong to rather than emitted as points of their own, because this map
                     shows sites: a salvage dig in a road cutting is evidence that a site was
                     excavated, not a heritage site a visitor can go and see. Excavations
                     that name no site are counted and reported, not silently dropped.
    """
    rows = load("iaa_discover.json") or []
    by_type = collections.defaultdict(list)
    for r in rows:
        by_type[r.get("_record_type")].append(r)

    # Aggregate excavation events by the declared-site numbers they attach to.
    exc_by_site: dict[str, dict] = {}
    unattached = 0
    for r in by_type.get("excavation", []):
        nums = r.get("derived_attached_declared_site_numbers") or []
        if isinstance(nums, str):
            nums = [x.strip() for x in re.split(r"[;,|]", nums) if x.strip()]
        keys = {str(n).split("/")[0] for n in nums if str(n).strip()}
        if not keys:
            unattached += 1
            continue
        years = r.get("derived_excavation_years") or []
        if isinstance(years, str):
            years = [y for y in re.findall(r"\d{4}", years)]
        lic = r.get("derived_licence_names") or []
        if isinstance(lic, str):
            lic = [x.strip() for x in re.split(r"[;,|]", lic) if x.strip()]
        who = clean(r.get("derived_excavator_he"))
        for k in keys:
            agg = exc_by_site.setdefault(k, {"years": set(), "licences": set(),
                                             "excavators": set(), "count": 0})
            agg["count"] += 1
            agg["years"].update(str(y) for y in years)
            agg["licences"].update(str(x) for x in lic)
            if who:
                agg["excavators"].add(who)

    out = []
    for kind in ("declared_site", "survey_site"):
        for r in by_type.get(kind, []):
            lat, lon = _coords(r, jur)
            if not _in_scope(jur, lat, lon):
                continue
            name = _discover_name(r)
            if not name:
                continue

            # Only a DECLARATION record carries an antiquity site number (ATA). A survey
            # record's site_num belongs to the Archaeological Survey's own per-map numbering,
            # where site 1 exists on every sheet in the country. Treating the two as one
            # identifier space manufactured hundreds of false id conflicts and would have
            # merged unrelated sites, so a survey record contributes no strong id at all and
            # is matched on name and distance like any other source.
            main = None
            if kind == "declared_site":
                main = clean(r.get("derived_site_number_main"))
                if not main and clean(r.get("originEntityId")):
                    main = str(r["originEntityId"]).split("/")[0]
            survey_num = clean(r.get("site_num")) or clean(r.get("derived_survey_site_ref"))

            desc = None
            if isinstance(r.get("description"), dict):
                desc = clean(r["description"].get("hebrew"))
            desc = desc or clean(r.get("description_heb")) or clean(r.get("atarDescription"))

            per = vm.periods(clean(r.get("atarPeriodsAndElements"))) or []
            if not per:
                per = vm.periods_in_text(desc)

            st: dict = {}
            if kind == "declared_site":
                if r.get("derived_is_declared") is True or clean(r.get("atarStatus")) == "מוכרז/תקין":
                    st["reg_antiquity"] = "declared"
                elif r.get("derived_is_declared") is False or clean(r.get("atarStatus")) == "לא להכרזה":
                    st["reg_antiquity"] = "known"
            else:
                # Presence in the Archaeological Survey proves the state knows the site.
                # It does NOT prove a declaration, so this may never say 'declared'.
                st["reg_antiquity"] = "known"

            agg = exc_by_site.get(main or "")
            excavated = bool(r.get("derived_was_excavated")) or bool(agg and agg["count"])
            if excavated:
                st["excavation"] = "excavated"
            elif r.get("derived_survey_count") or kind == "survey_site":
                st["excavation"] = "surveyed_only"
            if r.get("derived_public_access_flag") is True:
                st["accessibility"] = "open_free"

            unc = r.get("derived_position_uncertainty_m")
            prec = ("exact" if isinstance(unc, (int, float)) and unc <= 60
                    else "approx_100m" if isinstance(unc, (int, float)) and unc <= 150
                    else "approx_500m" if isinstance(unc, (int, float)) and unc <= 600
                    else "approx_100m")

            names_alt = []
            an = r.get("atarNames")
            if isinstance(an, str):
                names_alt += [x.strip() for x in re.split(r"[;|,]", an) if x.strip()]
            elif isinstance(an, list):
                names_alt += [clean(x if isinstance(x, str) else (x or {}).get("hebrew")) for x in an]

            out.append(claim(
                "iaa_discover", f"{kind}:{r.get('entityId') or r.get('id') or r.get('site_num')}",
                url=clean(r.get("derived_permalink")) or clean(r.get("externalUrl")),
                name=name, names_alt=names_alt, description=desc,
                category_hint="archaeological",
                type=vm.site_type(clean(r.get("atarPeriodsAndElements")), desc, name),
                periods=per,
                lat=lat, lon=lon,
                itm_x=r.get("derived_itm_x"), itm_y=r.get("derived_itm_y"),
                location_precision=prec,
                locality=sane_locality(r.get("derived_tabu_yishuvim")),
                statuses=st,
                ids={"iaa_site_id": main},
                extra={
                    "record_type": kind,
                    "survey_site_num": survey_num,
                    "iaa_site_sub_id": clean(r.get("derived_site_number")) or clean(r.get("originEntityId")),
                    "iaa_status_he": clean(r.get("derived_status_he")) or clean(r.get("atarStatus")),
                    "gazette": clean(r.get("atarOfficialAnnouncementGazette")),
                    "declaration_first_date": clean(r.get("derived_declaration_first_date")),
                    "periods_raw": clean(r.get("atarPeriodsAndElements")),
                    "excavation_years": sorted(agg["years"]) if agg else
                                        [str(y) for y in (r.get("derived_excavation_years") or [])],
                    "excavation_licenses": sorted(agg["licences"])[:40] if agg else [],
                    "excavators": sorted(agg["excavators"])[:20] if agg else
                                  ([clean(r.get("derived_excavator_he"))] if clean(r.get("derived_excavator_he")) else []),
                    "excavation_count": (agg or {}).get("count"),
                    "survey_count": r.get("derived_survey_count"),
                    "survey_sheet": clean(r.get("derived_survey_sheet_number")) or clean(r.get("map_name")),
                    "publications": r.get("derived_publications") if isinstance(r.get("derived_publications"), list) else None,
                    "bibliography": clean(r.get("bibliography_heb")),
                    "remains": clean(r.get("finding_heb")),
                    "map_information": clean(r.get("atarMapInformation")),
                    "iaa_district": clean(r.get("atarMehozName")),
                    "position_uncertainty_m": unc,
                    "is_sub_site": r.get("derived_is_sub_site"),
                },
                raw={k: v for k, v in r.items() if k in (
                    "entityId", "entityType", "originEntityId", "atarStatus", "atarType",
                    "derived_is_declared", "derived_site_number", "derived_was_excavated")},
            ))
    if unattached:
        print(f"  iaa_discover: {unattached} excavation records name no site and were not "
              f"turned into points (they are events, not places)")
    return out


# --------------------------------------------------------------------------------------
# 5. Declared antiquity polygons + Archaeological Survey points (IAA ArcGIS)
# --------------------------------------------------------------------------------------
def adapt_declared_antiquities(jur=None) -> list[dict]:
    """Two IAA ArcGIS layers, which together carry the whole registration axis.

    The polygon layer is the register of DECLARED antiquity sites under חוק העתיקות, with a
    gazette reference for each. The survey-points layer is sites documented in the
    Archaeological Survey of Israel, which the source itself labels as not necessarily
    declared, so it may only ever claim 'known'.

    A trap worth recording: in the survey layer the column named X_WGS_84 holds the LATITUDE
    and Y_WGS_84 the longitude. The extraction step caught it and wrote corrected `lat`/`lon`,
    which is what is read here. The raw X_/Y_WGS_84 columns are deliberately not touched.
    """
    out = []

    for r in load("declared_antiquities.json") or []:
        lat, lon = r.get("lat"), r.get("lon")
        if not _in_scope(jur, lat, lon):
            continue
        name, sub_type = split_catalog_name(r.get("ata_shem"))
        if not name:
            continue
        desc = clean(r.get("atar_heb_desc"))
        num = clean(r.get("atar_number"))
        main = str(num).split("/")[0] if num else (str(r["hp_ata_id"]) if r.get("hp_ata_id") else None)
        area = r.get("Shape__Area")
        out.append(claim(
            "declared_antiquities", f"poly:{r.get('objectid')}",
            name=name, names_alt=[clean(r.get("ata_shem")), clean(r.get("hachraza_name_hebrew"))],
            name_en=clean(r.get("hachraza_name_english")),
            description=desc,
            category_hint="archaeological",
            type=sub_type or vm.site_type(desc, name),
            periods=vm.periods_in_text(desc),
            lat=lat, lon=lon,
            # A polygon centroid is not a surveyed point, and a large site's centroid can sit
            # a long way from anything visible, so precision follows the polygon's size.
            location_precision=("exact" if isinstance(area, (int, float)) and area <= 20_000
                                else "approx_100m" if isinstance(area, (int, float)) and area <= 120_000
                                else "approx_500m"),
            statuses={"reg_antiquity": "declared"},
            ids={"iaa_site_id": main},
            extra={
                "atar_number": num,
                "gazette": clean(r.get("_gazette_reference")),
                "declaration_status_he": clean(r.get("_registration_status")),
                "polygon_area_m2": round(area) if isinstance(area, (int, float)) else None,
                "polygon_perimeter_m": round(r["Shape__Length"]) if isinstance(r.get("Shape__Length"), (int, float)) else None,
                "bbox_wgs84": r.get("_bbox_wgs84"),
                "centroid_method": clean(r.get("_centroid_method")),
                "description_en": clean(r.get("atar_eng_desc")),
                "iaa_district": clean(r.get("mehoz_name")),
            },
            raw={k: r.get(k) for k in ("objectid", "atar_number", "ata_shem", "hp_ata_status")},
        ))

    for r in load("declared_antiquities_known_survey_points.json") or []:
        lat, lon = r.get("lat"), r.get("lon")
        if not _in_scope(jur, lat, lon):
            continue
        name, sub_type = split_catalog_name(r.get("NAME_HEB"))
        if not name:
            continue
        desc = re.sub(r"<[^>]+>", " ", str(r.get("DESCRIPTION_HEB") or "")).strip() or None
        per = vm.periods(clean(r.get("PERIOD_HEB"))) or vm.periods_in_text(desc)
        out.append(claim(
            "declared_antiquities", f"survey:{r.get('GlobalID') or r.get('OBJECTID')}",
            name=name,
            names_alt=[clean(r.get("ADDITIONAL_NAME_HEB")), clean(r.get("NAME_HEB"))],
            name_en=clean(r.get("NAME_EN")),
            description=desc,
            category_hint="archaeological",
            type=sub_type or vm.site_type(clean(r.get("REMAINS_HEB")), desc, name),
            periods=per,
            lat=lat, lon=lon,
            itm_x=r.get("_itm2039_x"), itm_y=r.get("_itm2039_y"),
            location_precision="exact",
            statuses={"reg_antiquity": "known"},
            # SITE_NUM is a survey-map number, not an antiquity site number: see the note in
            # adapt_iaa_discover. It stays out of the identifier space.
            ids={},
            extra={
                "survey_site_num": r.get("SITE_NUM"),
                "survey_field_num": clean(r.get("FIELD_NUM")),
                "survey_map_id": r.get("MAP_ID"),
                "remains": clean(r.get("REMAINS_HEB")),
                "periods_raw": clean(r.get("PERIOD_HEB")),
                "bibliography": clean(r.get("BIBLIOGRAPHY_HEB")),
                "authors": clean(r.get("AUTHORS_HEB")),
                "registration_status_he": clean(r.get("_registration_status")),
            },
            raw={k: r.get(k) for k in ("OBJECTID", "SITE_NUM", "NAME_HEB", "PERIOD_HEB")},
        ))
    return out


# --------------------------------------------------------------------------------------
# 6. Blue signs (Council for Conservation of Heritage Sites, via Hebrew Wikipedia + shimur.org)
# --------------------------------------------------------------------------------------
def adapt_blue_signs(jur=None) -> list[dict]:
    """שלטים כחולים של המועצה לשימור אתרי מורשת בישראל.

    A blue sign is a physical fact about a place, so this source is an authority for the
    signage axis and for nothing else about legal status. Its coordinates come from the
    Wikipedia coord template and were cross-checked against the linked article's own geotag.

    Category: blue signs are overwhelmingly post-1700 heritage, which is the whole point of
    the Council's remit, but a few mark genuine antiquities. The extraction step flagged
    those, and the flag is honoured rather than the assumption.
    """
    rows = load("blue_signs.json") or []
    out = []
    for r in rows:
        lat, lon = r.get("lat"), r.get("lon")
        in_ey = r.get("in_emek_yizrael_council_boundary")
        matched = r.get("emek_yizrael_settlement_matched") or r.get("settlement_matches_emek_yizrael_list")
        if lat is not None and lon is not None:
            if not _in_scope(jur, lat, lon):
                continue
        elif not (in_ey or matched):
            continue          # no coordinate and no settlement tie to this council

        name = clean(r.get("site_name")) or clean(r.get("shimur_sign_name"))
        if not name:
            continue

        pre1700 = r.get("pre1700_keyword_flags") or r.get("possible_archaeological_site")
        cat = clean(r.get("site_category"))
        if cat not in ("archaeological", "historic", "culture"):
            cat = "archaeological" if pre1700 else "historic"

        sign_text = clean(r.get("sign_text"))
        # A year is only taken from an explicit founding or construction phrase in the sign's
        # own text. The page-level year fields are NOT usable as a site date: shimur.org's
        # year is the sign or page year, and reading one of those as a founding date put 2017
        # on Khirbat Tira, a DECLARED ANTIQUITY SITE, which then outranked its Byzantine and
        # Mamluk periods and reclassified it as post-1700 heritage. They stay in `extra`.
        year = None
        for pat in (r"\bנבנ(?:ת[הו]?|ה|ו)\s+ב(?:שנת\s+)?(\d{3,4})",
                    r"\b(?:נוסד|הוקם|הוקמה|נוסדה|נחנך|נחנכה)\s+ב(?:שנת\s+)?(\d{3,4})",
                    r"\bבשנת\s+(\d{3,4})\s+(?:נבנ|הוק|נוסד|התיישב|עלו|הגיע)"):
            m = re.search(pat, str(sign_text or ""))
            if m:
                y = int(m.group(1))
                if 300 <= y <= 2025:
                    year = y
                    break

        out.append(claim(
            "blue_signs", r.get("record_id"),
            url=clean(r.get("site_wiki_article_url")) or clean(r.get("shimur_url"))
                or clean(r.get("wikipedia_source_page_url")),
            name=name,
            names_alt=[clean(r.get("shimur_sign_name")), clean(r.get("wikidata_label_he"))],
            name_en=clean(r.get("wikidata_label_en")),
            description=sign_text,
            category_hint=cat,
            type=vm.site_type(name, sign_text, clean(r.get("shimur_sign_type"))),
            periods=vm.periods_in_text(sign_text),
            year_from=year,
            lat=lat, lon=lon,
            location_precision=("exact" if r.get("coord_source") in
                                ("hewiki_bluesign_table_coord_template", "hewiki_article_geotag")
                                else "approx_500m" if lat is not None else "unknown"),
            locality=sane_locality(r.get("settlement")) or clean(r.get("settlement")),
            statuses={"signage": "blue_sign"},
            practical={"address": clean(r.get("address")) or clean(r.get("shimur_address"))},
            ids={"wikidata_qid": clean(r.get("wikidata_qid")),
                 "blue_sign_number": clean(r.get("sign_number"))},
            extra={
                "sign_text": sign_text,
                "wikipedia_he": clean(r.get("site_wiki_article_url")),
                "image_url": (f"https://commons.wikimedia.org/wiki/Special:FilePath/"
                              f"{(r.get('image_files') or [None])[0]}"
                              if (r.get("image_files") or [None])[0] else None),
                "image_credit": "Wikimedia Commons" if (r.get("image_files") or [None])[0] else None,
                "coord_source": clean(r.get("coord_source")),
                "coord_cross_source_distance_m": r.get("coord_cross_source_distance_m"),
                "shimur_url": clean(r.get("shimur_url")),
                "shimur_sign_type": clean(r.get("shimur_sign_type")),
                "shimur_local_authority": clean(r.get("shimur_local_authority")),
                "shimur_matched": r.get("shimur_matched"),
                "needs_manual_geolocation": r.get("needs_manual_geolocation"),
                "possible_archaeological_site": r.get("possible_archaeological_site"),
                "category_basis": clean(r.get("site_category_basis")),
                "heritage_designation": clean(r.get("P1435_heritage_designation_labels")),
                "sign_page_year_not_a_site_date": clean(r.get("shimur_year_on_sign_page")),
                "wikidata_inception": clean(r.get("P571_inception")),
            },
            raw={k: r.get(k) for k in ("record_id", "site_name", "settlement", "sign_number",
                                       "coord_source", "in_emek_yizrael_council_boundary")},
        ))
    return out


# --------------------------------------------------------------------------------------
# 7. Culture institutions (first-party evidence)
# --------------------------------------------------------------------------------------
def adapt_culture_institutions(jur=None) -> list[dict]:
    """Active culture and arts institutions, compiled from first-party evidence.

    This is the authority for the activity axis, and it is the only source that carries
    EVIDENCE for activity rather than an assertion: a current programme, a ticketing portal
    with dated events, a valid business licence. Records it judged out of scope are skipped
    with their stated reason, not silently dropped.

    Position: only 15 of these have a real coordinate. For the rest the extraction found the
    settlement centre and explicitly warned that it is not the institution's location. That
    warning is honoured by tagging the position `locality_centroid`, which the map draws as a
    hollow marker and the detail panel labels as approximate, rather than by presenting a
    village centre as a building.
    """
    rows = load("culture_institutions.json") or []
    out = []
    for r in rows:
        if not r.get("in_scope_for_map"):
            continue
        name = clean(r.get("name_he"))
        if not name:
            continue

        lat, lon, prec = r.get("lat"), r.get("lon"), "approx_100m"
        if lat is None and r.get("fallback_settlement_lat") is not None:
            lat, lon, prec = r["fallback_settlement_lat"], r["fallback_settlement_lon"], "locality_centroid"
        elif lat is not None:
            prec = "exact" if clean(r.get("coord_confidence")) == "high" else "approx_100m"
        if lat is not None and jur is not None and jur.signed_distance_m(lat, lon) <= APRON_M:
            continue

        st: dict = {}
        act = clean(r.get("active"))
        if act == "yes":
            st["activity"] = "active"
        elif act == "no":
            st["activity"] = "inactive"
        elif act == "seasonal":
            st["activity"] = "seasonal"
        if r.get("recognised_museum") is True:
            st["reg_institution"] = "recognized_museum"
        elif r.get("registered_public_library") is True:
            st["reg_institution"] = "public_library"
        acc = clean(r.get("accessibility"))
        if acc:
            # A described set of accommodations is evidence of accessibility; a stated absence
            # is evidence of the opposite. Anything vaguer stays unknown.
            low = acc
            if any(w in low for w in ("נגיש", "מעלון", "מעלית", "כסא", "כיסא", "שירותי נכים")):
                st["a11y_disabled"] = "partial" if "חלקית" in low else "accessible"
            elif "אינו נגיש" in low or "לא נגיש" in low:
                st["a11y_disabled"] = "not_accessible"
        adm = clean(r.get("admission"))
        if adm:
            st["accessibility"] = "open_paid" if adm.startswith("כן") or 'ש"ח' in adm else "open_free"
        body = clean(r.get("operating_body")) or ""
        if "מועצה אזורית" in body:
            st["ownership"] = "council"
        elif "עמות" in body or clean(r.get("amuta")):
            st["ownership"] = "ngo"

        out.append(claim(
            "culture_institutions", r.get("inst_id"),
            url=clean(r.get("website")),
            name=name, name_en=clean(r.get("name_en")),
            description=clean(r.get("notes")),
            category_hint="culture",
            type=vm.CI_TYPE.get(clean(r.get("type"))) or vm.site_type(name, clean(r.get("notes"))),
            lat=lat, lon=lon, location_precision=prec,
            locality=clean(r.get("settlement")),
            statuses=st,
            practical={
                "address": clean(r.get("address")),
                "phone": clean(r.get("phone")),
                "email": clean(r.get("email")),
                "website": clean(r.get("website")),
                "hours_text": clean(r.get("opening_hours")),
                "admission": adm,
                "operator": clean(r.get("operating_body")),
                "founded_year": r.get("year_founded"),
            },
            extra={
                "activity_evidence": clean(r.get("active_evidence")),
                "activity_confidence": clean(r.get("active_confidence")),
                "accessibility_detail": acc,
                "recognised_museum_evidence": clean(r.get("recognised_museum_evidence")),
                "library_register_evidence": clean(r.get("registered_public_library_evidence")),
                "institution_type_raw": clean(r.get("type")),
                "position_is_settlement_centre": prec == "locality_centroid",
                "position_note": clean(r.get("fallback_settlement_source")) if prec == "locality_centroid" else clean(r.get("coord_source")),
                "evidence_sources": r.get("sources") if isinstance(r.get("sources"), list) else None,
                # A business licence names a licence-holder and a manager, which is personal
                # data about identifiable people. Only the fact and its expiry travel.
                "business_licence_valid_until": (r.get("business_licence") or {}).get("valid_until")
                if isinstance(r.get("business_licence"), dict) else None,
                "contact_is_private_sector": not ("מועצה" in body or "עמות" in body) and not clean(r.get("amuta")),
            },
            raw={k: r.get(k) for k in ("inst_id", "name_he", "type", "settlement", "active",
                                       "active_confidence", "in_scope_reason")},
        ))
    return out


# --------------------------------------------------------------------------------------
# 8. Conservation Council, INPA, KKL, and the statutory conservation overlay
# --------------------------------------------------------------------------------------
NAMED_HERITAGE_TYPES = {"shimur_blue_sign", "shimur_heritage_site", "candidate_lead_check",
                        "kkl_travel_site"}


def adapt_heritage_official(jur=None) -> list[dict]:
    """המועצה לשימור אתרי מורשת, רשות הטבע והגנים, קק"ל, ומינהל התכנון.

    Only the NAMED records become points. The 609 in-scope records from the Planning
    Administration conservation layers are statutory designations rather than sites: their
    name field holds a designation type ('בלוק מבנה לשימור') and a plan name ('קיבוץ גבת'),
    so mapping them would put hundreds of identically-labelled markers on the map. They are
    written to a separate overlay instead and applied spatially in harmonize, which is what
    they actually are: a statement that a location falls inside a conservation designation.
    """
    rows = load("heritage_official.json") or []
    out = []
    for r in rows:
        if r.get("record_type") not in NAMED_HERITAGE_TYPES:
            continue
        lat, lon = r.get("lat"), r.get("lon")
        if not _in_scope(jur, lat, lon):
            continue
        name = clean(r.get("site_name")) or clean(r.get("shimur_title")) or clean(r.get("title"))
        if not name:
            continue

        rt = r.get("record_type")
        st: dict = {}
        if r.get("holds_blue_sign") is True:
            st["signage"] = "blue_sign"
        if rt in ("shimur_blue_sign", "shimur_heritage_site"):
            # A site the Council for Conservation publishes as its own is a listed site; where
            # the page records restoration work, that is a stronger statement.
            hist = clean(r.get("conservation_history")) or ""
            st["reg_conservation"] = "restored" if ("שוחזר" in hist or "שוקם" in hist
                                                    or "שוחזר" in str(clean(r.get("shimur_text")) or "")) else "listed"
        if clean(r.get("designation_type")):
            st["protected_area"] = vm.TMM_PROTECTED.get(clean(r["designation_type"]))
        if r.get("open_to_public") is True or r.get("publicAccess") is True:
            fee = clean(r.get("entrance_fee"))
            free = r.get("free_entry") is True or r.get("isAccessibleForFree") is True
            st["accessibility"] = "open_free" if free and not fee else ("open_paid" if fee else "open_free")
        hours = clean(r.get("site_opening_hours__הערות")) or clean(r.get("opening_hours"))
        if hours and "תיאום" in hours and "accessibility" not in st:
            st["accessibility"] = "by_appointment"

        period_note = clean(r.get("period")) or ""
        cat = "historic"
        if rt == "candidate_lead_check":
            exp = clean(r.get("map_category_expected")) or ""
            if "archaeological" in exp or "pre-1700" in exp:
                cat = "archaeological"
        if "pre-1700" in period_note and "post-1700" not in period_note:
            cat = "archaeological"
        if rt == "kkl_travel_site":
            cat = "historic"

        out.append(claim(
            "heritage_official", f"{rt}:{r.get('id') or r.get('slug') or r.get('OBJECTID')}",
            url=clean(r.get("source_url")) or clean(r.get("url")) or clean(r.get("site_official_url")),
            name=name,
            names_alt=[clean(r.get("shimur_title")), clean(r.get("jsonld_name"))],
            description=clean(r.get("shimur_text")) or clean(r.get("site_notes")),
            category_hint=cat,
            type=vm.site_type(name, clean(r.get("shimur_text")), clean(r.get("sign_type"))),
            periods=vm.periods_in_text(period_note) or vm.periods_in_text(clean(r.get("shimur_text"))),
            date_text=period_note or None,
            lat=lat, lon=lon,
            location_precision="approx_100m",
            locality=sane_locality(r.get("sign_place")) or sane_locality(r.get("jurisdiction_muni_heb")),
            statuses=st,
            practical={
                "address": clean(r.get("sign_address")),
                "phone": clean(r.get("site_phone")),
                # A personal mailbox published on a heritage page is still personal data, so it
                # is not carried at all; the phone is the visiting contact the Council itself
                # publishes for booking.
                "email": None,
                "website": clean(r.get("site_official_url")),
                "hours_text": hours,
                "admission": clean(r.get("entrance_fee")),
            },
            ids={"wikidata_qid": clean(r.get("wikidata_qid"))},
            extra={
                "record_type": rt,
                "shimur_url": clean(r.get("url")),
                "sign_year_erected": clean(r.get("sign_year_erected")),
                "sign_languages": clean(r.get("sign_languages")) or clean(r.get("site_languages")),
                "sign_type": clean(r.get("sign_type")),
                "sign_local_authority": clean(r.get("sign_local_authority")),
                "conservation_history": clean(r.get("conservation_history")),
                "unesco_world_heritage": clean(r.get("unesco_world_heritage")),
                "designation_type": clean(r.get("designation_type")),
                "statutory_status": clean(r.get("statutory_status")),
                "declared_national_site_under_law": r.get("declared_national_site_under_law"),
                "official_designation_evidence": clean(r.get("official_designation_evidence")),
                "period_note": period_note or None,
                "suitable_for_children": clean(r.get("site_suitable_kids_3_10")),
                "jurisdiction_muni": clean(r.get("jurisdiction_muni_heb")),
                "jurisdiction_distance_m": r.get("jurisdiction_distance_to_boundary_m"),
                "jurisdiction_uncertain": r.get("jurisdiction_uncertain"),
                "lead_as_given": clean(r.get("lead_as_given")),
                "email_withheld": bool(clean(r.get("site_email"))),
                "contact_is_private_sector": rt == "shimur_heritage_site" and not clean(r.get("sign_local_authority")),
            },
            raw={k: r.get(k) for k in ("id", "record_type", "title", "site_name", "period",
                                       "jurisdiction_muni_heb", "holds_blue_sign")},
        ))
    return out


def build_conservation_overlay(jur=None) -> dict:
    """Write the statutory conservation and protected-area overlay used by harmonize.

    Each entry is a location plus a status it confers on whatever site sits inside it, with a
    radius. Polygon rings were not retained by the extraction, so an equivalent-area radius
    stands in, capped so a very large park designation cannot claim half the valley.
    """
    rows = load("heritage_official.json") or []
    cons, prot = [], []
    for r in rows:
        rt = r.get("record_type")
        lat, lon = r.get("lat"), r.get("lon")
        if lat is None or not _in_scope(jur, lat, lon):
            continue
        if rt in ("iplan_conservation_polygon", "iplan_conservation_point"):
            desig = clean(r.get("mavat_name")) or clean(r.get("statutory_designation"))
            status = vm.IPLAN_CONSERVATION.get(desig)
            if not status:
                continue
            approved = clean(r.get("station_desc")) in vm.IPLAN_APPROVED_STAGES
            area = r.get("shape_area") or r.get("Shape_Area")
            radius = 40.0
            if isinstance(area, (int, float)) and area > 0:
                radius = min(400.0, max(40.0, (area / math.pi) ** 0.5))
            cons.append({
                "lat": lat, "lon": lon, "radius_m": round(radius, 1),
                "value": "plan_approved" if approved else status,
                "designation": desig, "plan_name": clean(r.get("pl_name")),
                "plan_number": clean(r.get("pl_number")), "stage": clean(r.get("station_desc")),
                "record_type": rt, "url": clean(r.get("source_url")),
            })
        elif rt == "tmm_park_or_reserve":
            value = vm.TMM_PROTECTED.get(clean(r.get("designation_type")) or clean(r.get("TYPE_NAME")))
            if not value:
                continue
            area = r.get("AREA_SQM") or r.get("AREA")
            radius = 300.0
            if isinstance(area, (int, float)) and area > 0:
                radius = min(1500.0, max(80.0, (area / math.pi) ** 0.5))
            prot.append({
                "lat": lat, "lon": lon, "radius_m": round(radius, 1), "value": value,
                "designation": clean(r.get("designation_type")) or clean(r.get("TYPE_NAME")),
                "name": clean(r.get("site_name")) or clean(r.get("NAME")),
                "plan": clean(r.get("SOURCE")), "record_type": rt,
                "note": clean(r.get("statutory_status")), "url": clean(r.get("source_url")),
            })
    overlay = {"reg_conservation": cons, "protected_area": prot,
               "source_id": "heritage_official", "retrieved": TODAY}
    (INTERIM / "_overlay_statutory.json").write_text(
        json.dumps(overlay, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"reg_conservation": len(cons), "protected_area": len(prot)}


# --------------------------------------------------------------------------------------
# registry and entry point
# --------------------------------------------------------------------------------------
ADAPTERS = {
    "declared_antiquities": adapt_declared_antiquities,
    "iaa_discover": adapt_iaa_discover,
    "iaa_cluster_table": adapt_iaa_cluster_table,
    "heritage_official": adapt_heritage_official,
    "blue_signs": adapt_blue_signs,
    "culture_institutions": adapt_culture_institutions,
    "iicp_culture_table": adapt_iicp_culture_table,
    "osm_wikidata": adapt_osm_wikidata,
}
NEEDS_JUR = {"declared_antiquities", "iaa_discover", "blue_signs", "osm_wikidata",
             "heritage_official", "culture_institutions"}


def run_all(only: list[str] | None = None) -> dict:
    bnd = RAW / "boundary_emek_yizrael.geojson"
    jur = geo.Jurisdiction.from_geojson(bnd) if bnd.exists() else None
    stats = {}
    for sid, fn in ADAPTERS.items():
        if only and sid not in only:
            continue
        try:
            rows = fn(jur) if sid in NEEDS_JUR else fn()
        except FileNotFoundError:
            stats[sid] = "no input"
            continue
        if not rows:
            stats[sid] = "no records (input missing or nothing in scope)"
            continue
        (INTERIM / f"{sid}.claims.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        stats[sid] = {
            "claims": len(rows),
            "with_coords": sum(1 for r in rows if r["lat"] is not None),
            "with_periods": sum(1 for r in rows if r["periods"]),
            "with_type": sum(1 for r in rows if r["type"]),
            "by_category": {c: sum(1 for r in rows if r["category_hint"] == c)
                            for c in list(sc.CATEGORIES) + [None]},
            "status_values": sum(len(r["statuses"]) for r in rows),
        }
    if not only or "heritage_official" in only:
        stats["_overlay_statutory"] = build_conservation_overlay(jur)
    return stats


if __name__ == "__main__":
    print(json.dumps(run_all(), ensure_ascii=False, indent=1))
