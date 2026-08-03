"""Hebrew place-name normalization for cross-source matching.

Israeli heritage sources spell the same place many ways: חורבת / ח'ירבת / ח' / חר',
תל שמרון / תל שימרון, בית שערים / בית שאערים, כפר / כפר-. Matching on raw strings finds
almost nothing, so every comparison goes through a normalization ladder:

    display()    human-facing cleanup only (niqqud, whitespace, stray quotes)
    key()        strict matching key: canonical prefixes, final letters, no punctuation
    loose_key()  aggressive key for CANDIDATE GENERATION ONLY, never for an auto-merge

The loose key deliberately over-collapses (it folds ט/ת, כ/ק, ש/ס and drops א/ע/ה) because
it is always paired with a hard distance gate and a scored decision afterwards.
"""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

# Hebrew points, cantillation and the maqaf/geresh family.
_NIQQUD = re.compile(r"[֑-ׇֽֿׁׂׅׄ]")
_QUOTES = re.compile(r"[׳״'\"`‘’“”]")
_DASHES = re.compile(r"[־‐-―\-]")
_PARENS = re.compile(r"[()\[\]{}]")
_MULTISPACE = re.compile(r"\s+")

_FINALS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})

# Canonical prefixes. Order matters: longest spelling first, so ח'ירבת is caught before ח'.
_PREFIX_CANON: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^(חירבת|חרבת|כירבת|כרבת|חורבת|חורבה|חרבה|חר|ח)\b"), "חורבת"),
    (re.compile(r"^(תל|טל)\b"), "תל"),
    (re.compile(r"^(ח'?אן|כאן)\b"), "חאן"),
    (re.compile(r"^(עיון|עין|איין|עיין|ען)\b"), "עין"),
    (re.compile(r"^(ביר|באר|בר)\b"), "באר"),
    (re.compile(r"^(רוג'ום|רוגום|רג'ום)\b"), "רוגום"),
    (re.compile(r"^(שיח|שייח|שח)\b"), "שיח"),
    (re.compile(r"^(דיר|דייר)\b"), "דיר"),
    (re.compile(r"^(נבי|נביא)\b"), "נבי"),
]

# Arabic definite article as transliterated into Hebrew: אל- and the sun-letter
# assimilations א-, א‑ט-, א-ס-, א-ש- and friends. Must run BEFORE dashes are folded to
# spaces, otherwise the hyphen that identifies the article is already gone.
_ARABIC_ARTICLE = re.compile(r"(?:(?<=\s)|^)(?:אל|א[טסשדזרנתלצכ])[־‐-―\-](?=\S)")
_ARABIC_ARTICLE_SP = re.compile(r"(?:(?<=\s)|^)אל(?=\s)")

# Generic heads of Hebrew and Arabic toponyms. They say what KIND of place it is, not
# which one, so two names sharing only a head are not similar. Used by `distinctive()`.
# Written in post-`key()` form, i.e. with final letters already folded.
_GENERIC_HEADS = {
    "בית", "כפר", "תל", "חורבת", "חאנ", "עינ", "באר", "שיח", "דיר", "נבי", "רוגומ",
    "גבעת", "רמת", "נחל", "הר", "מצפה", "אבנ", "מגדל", "קרית", "קריית", "עמק",
    "חצר", "מעונ", "משמר", "עני", "אומ", "תחנת",
}

# Generic words that carry no identifying content. Removed from the KEY only, so that
# "מוזיאון בית הראשונים" and "בית הראשונים" can meet, while the words stay in the display
# name. Deliberately does NOT include מוזיאון/גלריה/ספרייה, because those distinguish a
# culture institution from the heritage site it sits in.
_STOPWORDS = {
    "אתר", "אתרי", "עתיקות", "שרידי", "של", "ה", "את",
    "מתקן", "מבנה", "מבני", "אזור", "גן", "לאומי", "שמורת", "טבע",
}
# 'שריד' is deliberately NOT a stopword: it is also the name of Kibbutz Sarid, and stripping it
# left he.key('שריד') empty, which silently made that site unmatchable against anything.


def display(s: str | None) -> str:
    """Human-facing cleanup: strip niqqud, normalize whitespace, drop stray edge punctuation."""
    if not s:
        return ""
    s = unicodedata.normalize("NFC", str(s))
    s = _NIQQUD.sub("", s)
    s = s.replace("‎", "").replace("‏", "").replace(" ", " ")
    s = _MULTISPACE.sub(" ", s).strip()
    return s.strip(" ,.;:-־")


def _base(s: str) -> str:
    s = display(s)
    s = _QUOTES.sub("", s)
    s = _PARENS.sub(" ", s)
    s = _ARABIC_ARTICLE.sub(" ", s)
    s = _ARABIC_ARTICLE_SP.sub(" ", s)
    s = _DASHES.sub(" ", s)
    s = s.translate(_FINALS)
    return _MULTISPACE.sub(" ", s).strip()


def canon_prefix(s: str) -> str:
    """Fold the ruin/tell/spring prefix family onto one spelling."""
    s = s.strip()
    for pat, repl in _PREFIX_CANON:
        if pat.match(s):
            return pat.sub(repl, s, count=1)
    return s


def tokens(s: str) -> list[str]:
    return [t for t in _base(s).split() if t]


def key(s: str | None) -> str:
    """Strict matching key. Safe to use for an auto-merge decision when paired with distance.

    Removing the stopwords must never empty the key: a name made entirely of words that happen
    to be generic ('שריד', 'גן לאומי') is still that place's name, and an empty key makes the
    record invisible to every name comparison rather than merely hard to match.
    """
    if not s:
        return ""
    t = canon_prefix(_base(s))
    toks = [p for p in t.split() if p]
    parts = [p for p in toks if p not in _STOPWORDS]
    return " ".join(parts or toks)


_LOOSE_MAP = str.maketrans({"ט": "ת", "ק": "כ", "ש": "ס", "א": "", "ע": "", "ה": "", "ו": "ו"})


def loose_key(s: str | None) -> str:
    """Over-collapsing key for candidate generation only. Never decide a merge on this."""
    k = key(s)
    if not k:
        return ""
    k = k.translate(_LOOSE_MAP)
    k = re.sub(r"(.)\1+", r"\1", k)  # collapse doubled letters (יי, וו, שש)
    return _MULTISPACE.sub(" ", k).strip()


# LOCALITY_HEADS is filled at runtime from the council's official settlement list.
# Inside a single council a settlement name is a LOCATION QUALIFIER, not an identity:
# "בית העם נהלל" is the community hall OF Nahalal, and matching it against "נהלל" itself
# on the strength of the shared word is how a community centre gets fused with the moshav
# it stands in. So settlement names join the generic-head set and stop counting as
# distinctive. Two records that are BOTH just a settlement name still match, because
# distinctive() falls back to all tokens when everything is a head.
LOCALITY_HEADS: set[str] = set()


def add_locality_heads(names) -> int:
    """Register settlement names so they stop acting as distinguishing tokens."""
    before = len(LOCALITY_HEADS)
    for n in names or ():
        for tok in key(n).split():
            if len(tok) >= 3:
                LOCALITY_HEADS.add(tok)
    return len(LOCALITY_HEADS) - before


def distinctive(s: str | None) -> list[str]:
    """The identifying tokens of a name: everything that is not a generic toponym head.

    'תל שמרון' -> ['שמרונ'] and 'תל מגידו' -> ['מגידו'], so the two cannot be similar
    merely because both are a tel. Falls back to all tokens when a name is nothing but
    generic heads.
    """
    toks = [t for t in key(s).split() if t]
    core = [t for t in toks if t not in _GENERIC_HEADS and t not in LOCALITY_HEADS]
    return core or toks


_NO_SHARED_SPECIFIER_CAP = 0.45

# Institution names that recur once per settlement. Every moshav in the valley has a בית העם;
# most have a ספרייה and a מגדל מים. A name built only from these plus generic heads identifies
# a KIND of building, not a particular one, so two such names matching tells us nothing about
# whether they are the same place.
_GENERIC_INSTITUTION_WORDS = {
    "העמ", "עמ", "ספריה", "ספרייה", "מוזיאונ", "ארכיונ", "מרכז", "תרבות", "קהילתי",
    "מגדל", "מימ", "בארות", "מקווה", "צרכניה", "מכולת", "מרפאה", "גנ", "ילדימ",
    "קברות", "עלמינ", "כנסת", "מסגד", "כנסיה", "אנדרטה", "אנדרטת", "מצפור",
    "אולמ", "מופעימ", "היכל", "גלריה", "סטודיו", "בריכה", "מתנס", "ישנ", "ישנה",
    "הראשונימ", "ראשונימ", "מבקרימ", "אמנות", "אומנות",
}


def is_generic_name(s: str | None) -> bool:
    """True when a name identifies a kind of place rather than a particular one.

    'בית העם' and 'ספרייה' are generic; 'בית העם אלוני אבא' and 'מוזיאון חנקין' are not.
    Callers must refuse to merge two generic names on the strength of the name alone.
    """
    toks = [t for t in key(s).split() if t]
    if not toks:
        return True

    def is_generic_token(t: str) -> bool:
        # The definite article rides on the word in Hebrew, so 'המימ' and 'הישנ' have to be
        # tested with it stripped or 'מגדל המים' looks like a specific name.
        for form in {t, t[1:]} if t.startswith("ה") and len(t) > 2 else {t}:
            if form in _GENERIC_HEADS or form in LOCALITY_HEADS \
                    or form in _GENERIC_INSTITUTION_WORDS:
                return True
        return False

    return not [t for t in toks if not is_generic_token(t)]


def similarity(a: str | None, b: str | None) -> float:
    """0..1 name similarity, gated so a shared generic head cannot carry a match on its own."""
    ka, kb = key(a), key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0

    strict = max(fuzz.token_set_ratio(ka, kb), fuzz.token_sort_ratio(ka, kb)) / 100.0
    la, lb = loose_key(a), loose_key(b)
    loose = max(fuzz.token_set_ratio(la, lb), fuzz.token_sort_ratio(la, lb)) / 100.0 if la and lb else 0.0
    # The loose fold can pull a score up part of the way, never dominate it.
    whole = max(strict, 0.65 * loose + 0.35 * strict)

    # The specifier carries the identity, so it carries the score. A differing generic head
    # ('תל שמרון' against 'חורבת שמרון') is a weak signal, not a disqualification, because
    # sources disagree about what to call the same mound.
    da, db = distinctive(a), distinctive(b)
    sa = " ".join(loose_key(t) or t for t in da)
    sb = " ".join(loose_key(t) or t for t in db)
    spec = max(fuzz.token_set_ratio(sa, sb), fuzz.token_sort_ratio(sa, sb)) / 100.0 if sa and sb else 0.0
    score = 0.80 * spec + 0.20 * whole

    # Gate: at least one distinctive token has to actually correspond, so that two names
    # sharing only a head cannot reach the merge threshold on the strength of the head.
    best = 0.0
    for ta in da:
        fa = loose_key(ta) or ta
        for tb in db:
            fb = loose_key(tb) or tb
            best = max(best, fuzz.ratio(fa, fb) / 100.0)
            if best >= 0.75:
                break
        if best >= 0.75:
            break
    if best < 0.75:
        return round(min(score, whole, _NO_SHARED_SPECIFIER_CAP), 4)
    return round(min(score, 1.0), 4)


def slug(s: str | None) -> str:
    """Stable ASCII-safe id fragment from a Hebrew name."""
    import hashlib

    k = key(s) or "unnamed"
    h = hashlib.sha1(k.encode("utf-8")).hexdigest()[:6]
    return h
