"""Single source of truth for the harmonized site schema and its controlled vocabularies.

Design principle borrowed from the IICP data lake: the store holds CLAIMS, not facts.
Every resolved field value carries the source ids that produced it, and every raw claim
(including the ones that lost) stays in the record so the map can show its own evidence.

Nothing in this module knows about a specific source. Source adapters live in
src/adapters/ and are required to emit records that validate against RECORD_FIELDS.
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------
# Categories. Exactly the three the brief asks for, plus the honest fact that a single
# place can belong to more than one (a museum inside an archaeological park). `category`
# is the primary one used for the marker; `categories` is the filterable multi-value.
# --------------------------------------------------------------------------------------

CATEGORIES = {
    "archaeological": {
        "he": "אתר ארכאולוגי",
        "note": "עד 1700, באחריות רשות העתיקות לפי חוק העתיקות התשל\"ח-1978",
        "color": "#8a5a2b",
    },
    "historic": {
        "he": "אתר היסטורי",
        "note": "אחרי 1700, בתחום המועצה לשימור אתרי מורשת בישראל",
        "color": "#1f6f8b",
    },
    "culture": {
        "he": "מוסד תרבות ואומנות",
        "note": "מוסד או מרחב תרבות פעיל כיום",
        "color": "#a2325c",
    },
}

# The 1700 CE line is the legal one: חוק העתיקות defines עתיקות as remains from before 1700.
ANTIQUITY_CUTOFF_YEAR = 1700

ERA_BASIS = {
    "authority_and_periods": "רישום רשות העתיקות ושיוך תקופתי שמאשר אותו",
    "explicit_year": "שנת בנייה או שנת ייסוד מפורשת במקור",
    "period_vocab": "שיוך תקופה ארכאולוגית מוכרת",
    "source_authority": "רישום או סיווג של הגוף המוסמך",
    "site_type": "טיפוס האתר מכריע את התקופה",
    "unknown": "לא נקבע",
}

# --------------------------------------------------------------------------------------
# Site types, per category. Kept flat so the UI can offer one type facet.
# --------------------------------------------------------------------------------------

SITE_TYPES = {
    # archaeological
    "tel": {"he": "תל", "cat": "archaeological"},
    "khirbe": {"he": "חורבה", "cat": "archaeological"},
    "settlement_remains": {"he": "שרידי יישוב", "cat": "archaeological"},
    "burial": {"he": "קברים ומערות קבורה", "cat": "archaeological"},
    "necropolis": {"he": "נקרופוליס", "cat": "archaeological"},
    "water_installation": {"he": "מתקן מים", "cat": "archaeological"},
    "agricultural_installation": {"he": "מתקן חקלאי", "cat": "archaeological"},
    "quarry": {"he": "מחצבה", "cat": "archaeological"},
    "road_milestone": {"he": "דרך ואבן מיל", "cat": "archaeological"},
    "fortification": {"he": "ביצורים ומבצר", "cat": "archaeological"},
    "cult_ancient": {"he": "מבנה פולחן קדום", "cat": "archaeological"},
    "synagogue_ancient": {"he": "בית כנסת קדום", "cat": "archaeological"},
    "church_ancient": {"he": "כנסייה קדומה", "cat": "archaeological"},
    "mosaic": {"he": "רצפת פסיפס", "cat": "archaeological"},
    "cave": {"he": "מערה", "cat": "archaeological"},
    "prehistoric": {"he": "אתר פרהיסטורי", "cat": "archaeological"},
    # historic
    "ottoman_building": {"he": "מבנה עות'מאני", "cat": "historic"},
    "khan": {"he": "ח'אן", "cat": "historic"},
    "mill": {"he": "טחנת קמח", "cat": "historic"},
    "railway": {"he": "מורשת רכבת", "cat": "historic"},
    "templer": {"he": "מבנה טמפלרי", "cat": "historic"},
    "founders_building": {"he": "מבנה ראשונים", "cat": "historic"},
    "settlement_heritage": {"he": "מורשת התיישבותית", "cat": "historic"},
    "defense_heritage": {"he": "מורשת ביטחונית", "cat": "historic"},
    "memorial": {"he": "אנדרטה ואתר הנצחה", "cat": "historic"},
    "place_of_worship": {"he": "מבנה דת היסטורי", "cat": "historic"},
    "cemetery": {"he": "בית קברות היסטורי", "cat": "historic"},
    "industrial_heritage": {"he": "מורשת תעשייתית", "cat": "historic"},
    "water_heritage": {"he": "מורשת מים ובאר", "cat": "historic"},
    # culture
    "museum": {"he": "מוזיאון", "cat": "culture"},
    "visitor_center": {"he": "מרכז מבקרים", "cat": "culture"},
    "heritage_center": {"he": "מרכז מורשת", "cat": "culture"},
    "archive": {"he": "ארכיון", "cat": "culture"},
    "library": {"he": "ספרייה", "cat": "culture"},
    "community_culture_center": {"he": "מרכז קהילתי ותרבות", "cat": "culture"},
    "hall": {"he": "אולם והיכל תרבות", "cat": "culture"},
    "amphitheater": {"he": "אמפיתיאטרון", "cat": "culture"},
    "gallery": {"he": "גלריה ומרחב תערוכה", "cat": "culture"},
    "art_school": {"he": "בית ספר לאומנויות", "cat": "culture"},
    "conservatory": {"he": "קונסרבטוריון", "cat": "culture"},
    "studio_collective": {"he": "מרחב יוצרים", "cat": "culture"},
    "cinema": {"he": "בית קולנוע", "cat": "culture"},
    "festival_venue": {"he": "מוקד פסטיבל קבוע", "cat": "culture"},
    "other_culture": {"he": "מוסד תרבות אחר", "cat": "culture"},
    "unknown": {"he": "לא מסווג", "cat": None},
}

# --------------------------------------------------------------------------------------
# Archaeological periods, ordered oldest to newest, with the year span used to decide the
# pre/post 1700 split. Spans are conventional Levantine archaeology, kept deliberately
# coarse; `year_from`/`year_to` on a record always win over the period span when present.
# --------------------------------------------------------------------------------------

PERIODS = [
    ("paleolithic", "פרהיסטוריה", -1_000_000, -10000),
    ("neolithic", "נאוליתית", -10000, -4500),
    ("chalcolithic", "כלקוליתית", -4500, -3600),
    ("bronze_early", "ברונזה קדומה", -3600, -2000),
    ("bronze_middle", "ברונזה תיכונה", -2000, -1550),
    ("bronze_late", "ברונזה מאוחרת", -1550, -1200),
    ("iron", "ברזל", -1200, -586),
    ("persian", "פרסית", -586, -332),
    ("hellenistic", "הלניסטית", -332, -37),
    ("roman", "רומית", -37, 324),
    ("byzantine", "ביזנטית", 324, 638),
    ("early_islamic", "אסלאמית קדומה", 638, 1099),
    ("crusader", "צלבנית", 1099, 1291),
    ("mamluk", "ממלוכית", 1291, 1516),
    ("ottoman_early", "עות'מאנית קדומה", 1516, 1700),
    ("ottoman_late", "עות'מאנית מאוחרת", 1700, 1918),
    ("mandate", "המנדט הבריטי", 1918, 1948),
    ("state", "מדינת ישראל", 1948, 2100),
]

PERIOD_HE = {k: he for k, he, _, _ in PERIODS}
PERIOD_SPAN = {k: (a, b) for k, _, a, b in PERIODS}
PERIOD_ORDER = {k: i for i, (k, _, _, _) in enumerate(PERIODS)}

# --------------------------------------------------------------------------------------
# Status axes. Every axis carries an explicit "unknown" so the map never has to pretend.
# The UI exposes each axis as a facet; `reg_summary` is the derived registered/not filter
# the brief asked for.
# --------------------------------------------------------------------------------------

STATUS_AXES = {
    "reg_antiquity": {
        "he": "הכרזה כאתר עתיקות",
        "applies_to": ["archaeological", "historic"],
        "values": {
            "declared": "אתר עתיקות מוכרז",
            "known": "אתר עתיקות ידוע, לא מוכרז",
            "none": "אינו אתר עתיקות",
            "unknown": "לא ידוע",
        },
        "authority": "declared_antiquities",
    },
    "reg_conservation": {
        "he": "סטטוס שימור",
        # Also culture: an operating institution frequently occupies a listed building.
        "applies_to": ["historic", "archaeological", "culture"],
        "values": {
            "listed": "מסומן לשימור",
            "plan_approved": "תוכנית שימור מאושרת",
            "restored": "שומר ושוחזר",
            "surveyed": "נסקר בלבד",
            "none": "אינו מסומן לשימור",
            "unknown": "לא ידוע",
        },
        "authority": "heritage_official",
    },
    "reg_institution": {
        "he": "רישום מוסדי",
        "applies_to": ["culture"],
        "values": {
            "recognized_museum": "מוזיאון מוכר",
            "public_library": "ספרייה ציבורית רשומה",
            "none": "אינו רשום",
            "unknown": "לא ידוע",
        },
        "authority": "culture_institutions",
    },
    "protected_area": {
        "he": "שטח מוגן",
        "applies_to": ["archaeological", "historic", "culture"],
        "values": {
            "national_park": "גן לאומי",
            "nature_reserve": "שמורת טבע",
            "forest": "יער קק\"ל",
            "none": "אינו בשטח מוגן",
            "unknown": "לא ידוע",
        },
        "authority": "heritage_official",
    },
    "excavation": {
        "he": "חפירה",
        "applies_to": ["archaeological", "historic"],
        "values": {
            "excavated": "נחפר",
            "surveyed_only": "נסקר, לא נחפר",
            "not_excavated": "לא נחפר",
            "unknown": "לא ידוע",
        },
        "authority": "iaa_discover",
    },
    "accessibility": {
        "he": "נגישות לציבור",
        "applies_to": ["archaeological", "historic", "culture"],
        "values": {
            "open_free": "פתוח וחופשי",
            "open_paid": "פתוח בתשלום",
            "by_appointment": "בתיאום מראש",
            "restricted": "גישה מוגבלת",
            "not_accessible": "לא נגיש לציבור",
            "unknown": "לא ידוע",
        },
        "authority": None,
    },
    "a11y_disabled": {
        "he": "נגישות לאנשים עם מוגבלות",
        "applies_to": ["archaeological", "historic", "culture"],
        "values": {
            "accessible": "נגיש",
            "partial": "נגיש חלקית",
            "not_accessible": "אינו נגיש",
            "unknown": "לא ידוע",
        },
        "authority": None,
    },
    "condition": {
        "he": "מצב פיזי",
        "applies_to": ["archaeological", "historic"],
        "values": {
            "good": "טוב",
            "fair": "בינוני",
            "poor": "ירוד",
            "endangered": "בסיכון",
            "destroyed": "נהרס",
            "unknown": "לא ידוע",
        },
        "authority": None,
    },
    "activity": {
        "he": "פעילות",
        # A heritage site can also be operating or abandoned, which is worth stating.
        "applies_to": ["culture", "historic", "archaeological"],
        "values": {
            "active": "פעיל",
            "seasonal": "פעיל עונתית",
            "inactive": "אינו פעיל",
            "unknown": "לא ידוע",
        },
        "authority": "culture_institutions",
    },
    "signage": {
        "he": "שילוט",
        # Also culture: museums and heritage centres carry blue signs too.
        "applies_to": ["archaeological", "historic", "culture"],
        "values": {
            "blue_sign": "שלט כחול",
            "other_sign": "שילוט אחר",
            "none": "אין שילוט",
            "unknown": "לא ידוע",
        },
        "authority": "blue_signs",
    },
    "visitor_dev": {
        "he": "פיתוח לקהל",
        "applies_to": ["archaeological", "historic"],
        "values": {
            "developed": "מפותח לקהל",
            "partial": "מפותח חלקית",
            "undeveloped": "לא מפותח",
            "unknown": "לא ידוע",
        },
        "authority": None,
    },
    "ownership": {
        "he": "בעלות או הפעלה",
        "applies_to": ["archaeological", "historic", "culture"],
        "values": {
            "state": "המדינה",
            "council": "המועצה האזורית",
            "settlement": "היישוב או האגודה",
            "ngo": "עמותה או תאגיד ללא כוונת רווח",
            "private": "פרטי",
            "religious": "גוף דתי",
            "unknown": "לא ידוע",
        },
        "authority": None,
    },
}

# Which values count as "registered" for the derived binary facet.
REGISTERED_POSITIVE = {
    "reg_antiquity": {"declared"},
    "reg_conservation": {"listed", "plan_approved", "restored"},
    "reg_institution": {"recognized_museum", "public_library"},
    "protected_area": {"national_park", "nature_reserve"},
}

# Tone per status value, for the metrics panel. These are STATUS colours in the charting
# sense (good / warning / serious / gap), reserved and never reused as a category hue, and
# always shipped with a text label. `gap` is its own tone because "not known" is a finding
# in its own right on a map like this, not a fourth shade of bad.
TONES: dict[str, str] = {
    "reg_antiquity.declared": "good", "reg_antiquity.known": "warn", "reg_antiquity.none": "bad",
    "reg_conservation.listed": "good", "reg_conservation.plan_approved": "good",
    "reg_conservation.restored": "good", "reg_conservation.surveyed": "warn",
    "reg_conservation.none": "bad",
    "reg_institution.recognized_museum": "good", "reg_institution.public_library": "good",
    "reg_institution.none": "bad",
    "protected_area.national_park": "good", "protected_area.nature_reserve": "good",
    "protected_area.forest": "warn", "protected_area.none": "bad",
    "excavation.excavated": "good", "excavation.surveyed_only": "warn",
    "excavation.not_excavated": "bad",
    "accessibility.open_free": "good", "accessibility.open_paid": "good",
    "accessibility.by_appointment": "warn", "accessibility.restricted": "warn",
    "accessibility.not_accessible": "bad",
    "a11y_disabled.accessible": "good", "a11y_disabled.partial": "warn",
    "a11y_disabled.not_accessible": "bad",
    "condition.good": "good", "condition.fair": "warn", "condition.poor": "bad",
    "condition.endangered": "bad", "condition.destroyed": "bad",
    "activity.active": "good", "activity.seasonal": "warn", "activity.inactive": "bad",
    "signage.blue_sign": "good", "signage.other_sign": "warn", "signage.none": "bad",
    "visitor_dev.developed": "good", "visitor_dev.partial": "warn", "visitor_dev.undeveloped": "bad",
    "ownership.state": "neutral", "ownership.council": "neutral", "ownership.settlement": "neutral",
    "ownership.ngo": "neutral", "ownership.private": "neutral", "ownership.religious": "neutral",
}


def tone(axis: str, value: str) -> str:
    if value in (None, "unknown"):
        return "gap"
    return TONES.get(f"{axis}.{value}", "neutral")


LOCATION_PRECISION = {
    "exact": "מדידה או נקודה מקורית",
    "approx_100m": "עד 100 מטר",
    "approx_500m": "עד 500 מטר",
    "locality_centroid": "מרכז היישוב בלבד",
    "unknown": "לא ידוע",
}

# --------------------------------------------------------------------------------------
# Source registry. `rank` is the default tie-break when two sources claim the same field
# and no field-specific rule in PRECEDENCE applies. Lower is stronger.
# --------------------------------------------------------------------------------------

SOURCES = {
    "declared_antiquities": {"he": "הכרזות אתרי עתיקות, רשות העתיקות", "rank": 1},
    "iaa_cluster_table": {"he": "טבלת אתרי ארכאולוגיה, אשכול גליל ועמקים", "rank": 2},
    "iaa_discover": {"he": "המאגר הלאומי לארכאולוגיה, רשות העתיקות", "rank": 2},
    "heritage_official": {"he": "המועצה לשימור אתרי מורשת ורשות הטבע והגנים", "rank": 3},
    "blue_signs": {"he": "שלטים כחולים, המועצה לשימור אתרי מורשת", "rank": 3},
    "culture_institutions": {"he": "מוסדות תרבות, מקורות ראשוניים", "rank": 3},
    "iicp_culture_table": {"he": "מיפוי מוסדות תרבות, המכון הישראלי למדיניות תרבות", "rank": 4},
    # Curated by hand from material Matan supplied, kept in data/manual/additions.json. Ranked
    # above the open crowd-sourced layers because a person checked each entry, and below the
    # official registers because it is not one.
    "manual_curated": {"he": "תוספות ידניות של צוות המכון", "rank": 4},
    "osm_wikidata": {"he": "OpenStreetMap ו-Wikidata", "rank": 5},
    "amudanan": {"he": "עמוד ענן", "rank": 6},
    "boundary": {"he": "גבולות שיפוט, הלמ\"ס", "rank": 1},
}

# Per-field source precedence. First match wins; a field absent here falls back to
# SOURCES[...]["rank"]. Documented in docs/02-harmonization.md and deliberately explicit,
# because "one source of truth per field" is only meaningful if it is written down.
PRECEDENCE = {
    "geometry.archaeological": [
        "iaa_cluster_table", "declared_antiquities", "iaa_discover",
        "heritage_official", "osm_wikidata", "amudanan", "iicp_culture_table",
    ],
    "geometry.historic": [
        "heritage_official", "blue_signs", "osm_wikidata",
        "iaa_cluster_table", "amudanan", "iicp_culture_table",
    ],
    "geometry.culture": [
        "culture_institutions", "iicp_culture_table", "osm_wikidata", "heritage_official",
    ],
    "name.archaeological": ["iaa_cluster_table", "declared_antiquities", "iaa_discover", "osm_wikidata"],
    "name.historic": ["blue_signs", "heritage_official", "osm_wikidata"],
    "name.culture": ["culture_institutions", "iicp_culture_table", "osm_wikidata"],
    "periods": ["iaa_cluster_table", "iaa_discover", "osm_wikidata", "heritage_official", "amudanan"],
    "reg_antiquity": ["declared_antiquities", "iaa_cluster_table", "iaa_discover"],
    "reg_conservation": ["heritage_official", "blue_signs"],
    "reg_institution": ["culture_institutions"],
    "protected_area": ["heritage_official", "osm_wikidata"],
    "excavation": ["iaa_discover", "iaa_cluster_table"],
    "signage": ["blue_signs", "heritage_official"],
    "activity": ["culture_institutions", "iicp_culture_table"],
    "accessibility": ["heritage_official", "culture_institutions", "amudanan", "osm_wikidata"],
}

# Fields where a value may ONLY come from the naming authority. Anything else is dropped
# to `unknown` rather than inferred, because a wrong legal status is worse than a gap.
AUTHORITY_ONLY = {
    "reg_antiquity": {"declared_antiquities", "iaa_cluster_table", "iaa_discover"},
    "reg_institution": {"culture_institutions"},
    # The blue-sign registry is definitive, but the institute's own field survey physically
    # recorded whether a sign stands at each point, which is direct observation of the same
    # fact rather than a weaker restatement of it.
    "signage": {"blue_signs", "heritage_official", "iicp_culture_table"},
}

RECORD_FIELDS = [
    # identity
    "id", "name", "name_en", "names_alt", "description",
    # classification
    "category", "categories", "type", "periods", "year_from", "year_to", "date_text", "era_basis",
    # location
    "lat", "lon", "itm_x", "itm_y", "location_precision",
    "locality", "locality_code", "in_council", "in_council_method", "dist_to_boundary_m",
    # statuses
    *STATUS_AXES.keys(), "reg_summary",
    # excavation detail
    "excavation_years", "excavation_licenses", "excavators",
    # practical
    "address", "phone", "email", "website", "hours_text", "admission", "operator", "founded_year",
    # links and ids
    "wikidata_qid", "wikipedia_he", "image_url", "image_credit",
    "iaa_site_id", "blue_sign_number", "osm_id", "external_links",
    # provenance and quality
    "sources", "provenance", "claims", "conflicts",
    "confidence", "confidence_components", "verification", "needs_review", "review_reasons",
]


def registered_summary(rec: dict) -> str:
    """Derive the registered / not-registered / unknown facet from the four registry axes."""
    any_unknown = False
    for axis, positive in REGISTERED_POSITIVE.items():
        val = rec.get(axis)
        if val in positive:
            return "registered"
        if val in (None, "unknown"):
            any_unknown = True
    return "unknown" if any_unknown else "not_registered"


def era_from_periods(periods: list[str]) -> str | None:
    """archaeological / historic from the period vocabulary, or None when undecidable."""
    if not periods:
        return None
    known = [p for p in periods if p in PERIOD_SPAN]
    if not known:
        return None
    # A site with any pre-1700 period is antiquities territory even if it was reused later.
    if any(PERIOD_SPAN[p][0] < ANTIQUITY_CUTOFF_YEAR for p in known):
        return "archaeological"
    return "historic"
