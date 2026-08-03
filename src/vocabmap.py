"""Translate the Hebrew vocabularies of the source systems into the controlled vocabulary.

Every mapping here is a judgement that could be wrong, so each one is written down with
its reasoning rather than buried in an adapter. Three rules govern the whole file:

1. An unmapped value returns None, never a guess. The adapter then emits nothing for that
   field and the site keeps `unknown`.
2. Where a source term genuinely straddles the 1700 line, it maps to BOTH periods rather
   than to whichever one we would prefer. `עות'מנית` unqualified is the important case:
   the Ottoman era ran 1516 to 1918, so an unqualified Ottoman attribution really does span
   the line, and saying so is more honest than picking a side.
3. Longest match first. `ביזנטית קדומה` must be tested before `ביזנטית`, or every
   qualified period collapses onto its base term.
"""

from __future__ import annotations

import re

# --------------------------------------------------------------------------------------
# periods
# --------------------------------------------------------------------------------------
# Ordered longest-first within each group. Values are lists because one source term can
# legitimately cover several of our periods.
PERIOD_MAP: list[tuple[str, list[str]]] = [
    # prehistory
    ("פרהיסטור", ["paleolithic"]),
    ("פליאולית", ["paleolithic"]),
    ("אפיפליאולית", ["paleolithic"]),
    ("נאולית", ["neolithic"]),
    ("ניאולית", ["neolithic"]),
    ("כלקולית", ["chalcolithic"]),
    # bronze. 'ברונזה ביניימית' is the Intermediate Bronze Age, about 2200 to 2000 BCE,
    # which sits inside our bronze_early span.
    ("ברונזה ביניימית", ["bronze_early"]),
    ("ברונזה קדומה", ["bronze_early"]),
    ("ברונזה תיכונה", ["bronze_middle"]),
    ("ברונזה מאוחרת", ["bronze_late"]),
    ("ברונזה", ["bronze_early", "bronze_middle", "bronze_late"]),
    # IAA abbreviations: ב"ק early, ב"ת middle, ב"מ late Bronze.
    ("ב\"ק", ["bronze_early"]),
    ("ב\"ת", ["bronze_middle"]),
    ("ב\"מ", ["bronze_late"]),
    # iron
    ("ברזל", ["iron"]),
    ("ישראלית", ["iron"]),
    # classical
    ("פרסית", ["persian"]),
    ("הלניסט", ["hellenistic"]),
    ("רומית", ["roman"]),
    ("רומאית", ["roman"]),
    ("ביזנט", ["byzantine"]),
    # islamic and medieval
    ("אסלאמית קדומה", ["early_islamic"]),
    ("אסלמית קדומה", ["early_islamic"]),
    # IAA's 'אסלאמית מאוחרת' covers roughly 1099 to 1516, which is our crusader plus mamluk.
    ("אסלאמית מאוחרת", ["crusader", "mamluk"]),
    ("אסלמית מאוחרת", ["crusader", "mamluk"]),
    ("אסלאמית", ["early_islamic"]),
    ("צלבנ", ["crusader"]),
    ("איובית", ["crusader"]),
    ("ממלוכ", ["mamluk"]),
    # ottoman: qualified forms resolve, the bare form spans the 1700 line
    ("עות'מנית קדומה", ["ottoman_early"]),
    ("עותמנית קדומה", ["ottoman_early"]),
    ("עות'מנית מאוחרת", ["ottoman_late"]),
    ("עותמנית מאוחרת", ["ottoman_late"]),
    ("עות'מנ", ["ottoman_early", "ottoman_late"]),
    ("עותמנ", ["ottoman_early", "ottoman_late"]),
    ("טורקית", ["ottoman_early", "ottoman_late"]),
    # modern
    ("מנדט", ["mandate"]),
    ("מנדטור", ["mandate"]),
    ("בריטית", ["mandate"]),
    ("מדינת ישראל", ["state"]),
    ("מודרנ", ["state"]),
]
PERIOD_MAP.sort(key=lambda kv: -len(kv[0]))


def _dedupe(seq):
    seen, out = set(), []
    for k in seq:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def periods(text: str | None) -> list[str]:
    """Parse a comma-separated Hebrew period attribution, one period per chunk."""
    if not text:
        return []
    out: list[str] = []
    for chunk in re.split(r"[,;/|]| - |–", str(text)):
        chunk = chunk.strip()
        if not chunk:
            continue
        for term, keys in PERIOD_MAP:
            if term in chunk:
                out.extend(keys)
                break
    return _dedupe(out)


def periods_in_text(text: str | None) -> list[str]:
    """Find EVERY period named anywhere in a Hebrew prose description.

    IAA site descriptions bury the dating in a sentence: "חרסים מן התקופות הרומית
    והביזנטית והעות'מנית" names three periods joined by vav, which the comma-splitting
    parser above would read as one chunk and resolve to only the first. Here each term is
    searched independently, longest first, and a term already covered by a longer match that
    contains it is skipped so that 'ביזנטית קדומה' does not also register bare 'ביזנט'.
    """
    if not text:
        return []
    s = str(text)
    out: list[str] = []
    consumed: list[str] = []
    for term, keys in PERIOD_MAP:          # already sorted longest-first
        if term in s and not any(term in longer for longer in consumed):
            consumed.append(term)
            out.extend(keys)
    return _dedupe(out)


# --------------------------------------------------------------------------------------
# site types
# --------------------------------------------------------------------------------------
TYPE_MAP: list[tuple[str, str]] = [
    # archaeological
    ("בית כנסת", "synagogue_ancient"),
    ("כנסי", "church_ancient"),
    ("מנזר", "church_ancient"),
    ("פסיפס", "mosaic"),
    ("מצודה", "fortification"),
    ("מבצר", "fortification"),
    ("ביצור", "fortification"),
    ("מחנה צבא", "fortification"),
    ("קבורה", "burial"),
    ("קבר", "burial"),
    ("נקרופול", "necropolis"),
    ("מערת קבורה", "burial"),
    ("טחנת קמח", "mill"),
    ("טחנת", "mill"),
    ("מעין", "water_installation"),
    ("מעיין", "water_installation"),
    ("בור מים", "water_installation"),
    ("באר", "water_heritage"),
    ("אמת מים", "water_installation"),
    ("מתקן מים", "water_installation"),
    ("גת", "agricultural_installation"),
    ("בית בד", "agricultural_installation"),
    ("מלאכה וחקלאות", "agricultural_installation"),
    ("מחצבה", "quarry"),
    ("אבן מיל", "road_milestone"),
    ("מערה", "cave"),
    ("ח'אן", "khan"),
    ("חאן", "khan"),
    ("יישוב/חורבה/תל", "settlement_remains"),
    ("חורבה", "khirbe"),
    ("תל", "tel"),
    ("ישוב", "settlement_remains"),
    ("מכלול", "settlement_remains"),
    # historic
    ("טמפלר", "templer"),
    ("מגדל מים", "industrial_heritage"),
    ("בניין שימור", "settlement_heritage"),
    ("מבנה שימור", "settlement_heritage"),
    ("בית ראשונים", "founders_building"),
    ("תחנת רכבת", "railway"),
    ("רכבת", "railway"),
    ("קטר", "railway"),
    ("אנדרט", "memorial"),
    ("הנצחה", "memorial"),
    ("פסל", "memorial"),
    ("בית קברות", "cemetery"),
    ("מסגד", "place_of_worship"),
    ("מורשת ביטחונ", "defense_heritage"),
    ("חומה ומגדל", "defense_heritage"),
    ("מורשת התיישבות", "settlement_heritage"),
    # culture
    ("מרכז מבקרים", "visitor_center"),
    ("מוזיאון", "museum"),
    ("מוזאון", "museum"),
    ("ארכיון", "archive"),
    ("ספרי", "library"),
    ("מרכז מורשת", "heritage_center"),
    ("קונסרבטור", "conservatory"),
    ("בית ספר לאומנ", "art_school"),
    ("אולפן הקלטות", "studio_collective"),
    ("סטודיו", "studio_collective"),
    ("נגרי", "studio_collective"),
    ("קרמיק", "studio_collective"),
    ("גלרי", "gallery"),
    ("גלריי", "gallery"),
    ("אמפי", "amphitheater"),
    ("היכל התרבות", "hall"),
    ("אולם", "hall"),
    ("קולנוע", "cinema"),
    ("מרכז תרבות", "community_culture_center"),
    ("מתנ\"ס", "community_culture_center"),
    ("מרכז קהילת", "community_culture_center"),
    ("בית תרבות", "community_culture_center"),
    ("פסטיבל", "festival_venue"),
]
TYPE_MAP.sort(key=lambda kv: -len(kv[0]))


def site_type(*texts: str | None) -> str | None:
    """First matching type across the given texts, tried in the order supplied."""
    for t in texts:
        if not t:
            continue
        s = str(t)
        for term, key in TYPE_MAP:
            if term in s:
                return key
    return None


# --------------------------------------------------------------------------------------
# statuses, per source system
# --------------------------------------------------------------------------------------

# רשות העתיקות conservation survey (Table A)
EXC_STATUS = {
    "חפור במלואו": "excavated",
    "חפור בחלקו": "excavated",
    "בחפירה": "excavated",
    "לא חפור": "not_excavated",
    "נסקר": "surveyed_only",
}

# INV_TURISM speaks about development for visitors AND about being open, so it feeds two axes.
TURISM_DEV = {
    "מוסדר ופתוח לקהל": "developed",
    "פתוח לקהל ללא שירותים": "partial",
    "סגור למבקרים": "undeveloped",
}
TURISM_ACCESS = {
    "מוסדר ופתוח לקהל": "open_free",
    "פתוח לקהל ללא שירותים": "open_free",
    "סגור למבקרים": "not_accessible",
}

# ENGINEERING_STATE is the structural reading; GENERAL_RISK_LEVEL is the threat reading.
# Physical condition takes the structural one, because a stable site under high threat is
# still in good condition today.
ENGINEERING_CONDITION = {
    "יציב": "good",
    "מעורער": "fair",
    "מסוכן": "poor",
    "הרוס": "destroyed",
}
RISK_CONDITION = {"גבוהה": "endangered"}

SHIMUR_STATUS = {
    "בוצע שימור מלא": "restored",
    "בוצע שימור חלקי": "restored",
    "שימור מלווה חפירה": "restored",
    "כיסוי קבוע מלא": "plan_approved",
    "פסיפסים הוצאו": "plan_approved",
    "לא בוצע שימור": "surveyed",
    "לא רלוונטי – אתר לא חפור": None,
    "לא רלוונטי - אתר לא חפור": None,
}


def statutory_protection(text: str | None) -> dict:
    """Read STATUTORY_PROTECTION, which mixes declaration and planning-protection facts.

    'מוכרז', 'מוכרז 33619' and 'הכרזה תקינה' are declaration statements and are the only
    thing allowed to set reg_antiquity=declared from this source. 'גן לאומי' and
    'שמורת טבע' are protected-area statements. תמ"א 8 is a national outline plan for parks
    and reserves, so it is protection but not a declaration.
    """
    out: dict = {}
    if not text:
        return out
    s = str(text)
    if "מוכרז" in s or "הכרזה" in s:
        out["reg_antiquity"] = "declared"
    if "גן לאומי" in s or 'ג"ל' in s:
        out["protected_area"] = "national_park"
    elif "שמורת טבע" in s or 'ש"ט' in s or 'רט"ג' in s:
        out["protected_area"] = "nature_reserve"
    return out


def current_use_protected(text: str | None) -> str | None:
    if not text:
        return None
    s = str(text)
    if "גן לאומי" in s or 'ג"ל' in s:
        return "national_park"
    if "שמורת טבע" in s:
        return "nature_reserve"
    if "יער" in s:
        return "forest"
    return None


def ownership(text: str | None) -> str | None:
    if not text:
        return None
    s = str(text)
    if "פרטי" in s:
        return "private"
    if "ציבורי" in s:
        return "state"
    if "שלישי" in s or "עמות" in s:
        return "ngo"
    if "מועצה" in s:
        return "council"
    if "דת" in s or "וקף" in s or "כנסי" in s:
        return "religious"
    return None


# IICP table (Table B): 'פעיל / משומר / מוכר'
IICP_STATE = {
    "פעיל": {"activity": "active"},
    "משומר": {"reg_conservation": "restored"},
    "מוכר": {"reg_conservation": "listed"},
}

# IICP 'תחום' (cultural domain) is a sector, not a building type, but it does tell us the
# record is a culture institution rather than a heritage point.
IICP_DOMAIN_IS_CULTURE = {
    "הופעות וחגיגות", "אומנויות חזותיות ומלאכה", "עיצוב ושירותים יצירתיים",
    "מדיה אור-קולית ואינטראקטיבית", "ספרים ודפוס", "מוזיקה", "מורשת תרבותית וטבעית",
}

# OSM tags to our types. Only tags that identify a heritage or culture place.
OSM_TYPE = {
    "historic=archaeological_site": "settlement_remains",
    "historic=ruins": "khirbe",
    "historic=tomb": "burial",
    "historic=monument": "memorial",
    "historic=memorial": "memorial",
    "historic=castle": "fortification",
    "historic=fort": "fortification",
    "historic=city_gate": "fortification",
    "historic=aqueduct": "water_installation",
    "historic=milestone": "road_milestone",
    "historic=battlefield": "defense_heritage",
    "historic=building": "settlement_heritage",
    "historic=church": "church_ancient",
    "historic=wayside_shrine": "place_of_worship",
    "man_made=watermill": "mill",
    "man_made=water_well": "water_heritage",
    "man_made=water_tower": "industrial_heritage",
    "tourism=museum": "museum",
    "tourism=gallery": "gallery",
    "tourism=artwork": "memorial",
    "amenity=library": "library",
    "amenity=arts_centre": "gallery",
    "amenity=theatre": "hall",
    "amenity=community_centre": "community_culture_center",
    "amenity=place_of_worship": "place_of_worship",
    "amenity=cinema": "cinema",
    "historic=locomotive": "railway",
    "railway=station": "railway",
}

# OSM archaeological_site subtypes are more specific than the parent tag.
OSM_ARCH_SITE_TYPE = {
    "tell": "tel", "settlement": "settlement_remains", "necropolis": "necropolis",
    "tumulus": "burial", "megalith": "prehistoric", "fortification": "fortification",
    "villa": "settlement_remains", "roman_villa": "settlement_remains",
    "city": "settlement_remains", "cave": "cave", "petroglyph": "prehistoric",
}

# Wikidata P31 classes worth typing on. Kept short on purpose: Wikidata classes are noisy
# and a wrong type is worse than `unknown`.
WD_TYPE = {
    "Q839954": "settlement_remains",   # archaeological site
    "Q207694": "museum",               # art museum
    "Q33506": "museum",                # museum
    "Q7075": "library",                # library
    "Q24354": "hall",                  # theater building
    "Q2087181": "heritage_center",     # historic site
    "Q1081138": "memorial",            # historic marker
    "Q5003624": "memorial",            # memorial
    "Q271669": "tel",                  # landform? kept out below
    "Q160742": "archive",              # archive
    "Q22698": "other_culture",         # park
    "Q46169": "necropolis",            # necropolis
    "Q39614": "cemetery",              # cemetery
    "Q16970": "church_ancient",        # church building
    "Q32815": "place_of_worship",      # mosque
    "Q34627": "synagogue_ancient",     # synagogue
    "Q44613": "church_ancient",        # monastery
    "Q23413": "fortification",         # castle
    "Q57821": "fortification",         # fortification
    "Q2143825": "visitor_center",      # walking path? excluded below
    "Q1364900": "gallery",             # art gallery
    "Q17715832": "national_park",      # not a site type, handled as protected_area
}
# Classes above that must NOT set a site type.
WD_TYPE_BLOCKLIST = {"Q271669", "Q2143825", "Q22698", "Q17715832"}

# culture_institutions uses its own English type keys
CI_TYPE = {
    "museum": "museum", "heritage_museum": "museum",
    "public_library": "library", "public_library_branch": "library",
    "gallery": "gallery", "studio_gallery": "studio_collective",
    "permanent_exhibition": "gallery", "artist_collective": "studio_collective",
    "performance_hall": "hall", "culture_hall": "hall", "culture_venue": "other_culture",
    "amphitheatre": "amphitheater",
    "heritage_visitor_centre": "visitor_center", "heritage_visitor_site": "visitor_center",
    "heritage_experience_centre": "visitor_center",
    "culture_and_heritage_centre": "heritage_center",
    "young_adult_community_centre": "community_culture_center",
    "community_centre": "community_culture_center",
    "arts_school": "art_school", "arts_school_branch": "art_school",
    "conservatory": "conservatory", "archive": "archive", "cinema": "cinema",
    "registered_culture_nonprofit": "other_culture",
}

# Planning Administration conservation designations (mavat_name / statutory_designation).
# `station_desc` carries the plan's stage, which is what separates an approved conservation
# plan from one still being examined.
IPLAN_CONSERVATION = {
    "מבנה לשימור": "listed",
    "בלוק מבנה לשימור": "listed",
    "אתר/מתחם לשימור": "listed",
    "בלוק אתר לשימור ומספרו": "listed",
    "אתר עתיקות/אתר הסטורי": "listed",
    "שטח עתיקות/הסטורי לשימור": "listed",
    "שימור נופי": "listed",
    "שיקום/התחדשות": None,          # urban renewal, not heritage conservation
    "רשת חלוקה": None,              # a drafting grid, not a designation
}
IPLAN_APPROVED_STAGES = {"אישור", "הכרעה בהתנגדויות / אישור"}

TMM_PROTECTED = {
    "גן לאומי": "national_park",
    "גן לאומי שנוסף בתכנית זו": "national_park",
    "שמורת טבע": "nature_reserve",
    "שמורה שנוספה בתכנית זו": "nature_reserve",
    "שמורת נוף": "nature_reserve",
    "שמורת יער": "forest",
}

WD_PROTECTED = {
    "Q46169": None,
    "Q17715832": "national_park",  # national park of Israel
    "Q46169x": None,
    "Q179049": "nature_reserve",   # nature reserve
    "Q473972": "nature_reserve",   # protected area
}
