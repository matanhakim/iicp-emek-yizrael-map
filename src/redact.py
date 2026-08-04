"""One place that decides what contact detail may be published.

Matan's instruction was explicit: publish only what goes on the map, no individual-person rows,
and withhold the phone and email of private records. The first implementation applied that only
to the resolved fields of the site payload, which left two holes wide open:

  1. claims.json dumps every RAW claim, including the ones that lost, with no redaction at all.
     A contact withheld from the record was still sitting in its own claim log.
  2. data/out/sites.json is the pre-redaction internal store and was committed to a PUBLIC
     repository, so the store leaked what the payload withheld.

Twenty-four personal addresses reached the public repository that way. The lesson is that
redaction cannot be a step near the end; it has to be a gate that every published artifact
passes through, which is what this module is.

The rule: a contact detail is publishable only when it belongs to an INSTITUTION. A recognised
museum, a registered public library, a council or kibbutz or NGO operator - those publish their
own phone number and expect to be contacted. A private studio's mobile and a person's gmail are
personal data under חוק הגנת הפרטיות and stay in the working copy only.
"""

from __future__ import annotations

import re

CONTACT_FIELDS = ("phone", "email")

# Words that identify an operator as an organisation rather than a person.
_INSTITUTIONAL_OPERATOR = (
    "מועצה", "עמות", "מתנ\"ס", "מתנס", "קיבוץ", "מושב", "אגודה", "חברה", "מוסד",
    "משרד", "רשות", "רט\"ג", "קק\"ל", "ארכיון", "ספריי", "ספרי", "מוזיאון", "מוזאון",
    "בית ספר", "מכללה", "אוניברסיט", "ועד", "איגוד", "תאגיד", "ח.פ", "חפ ", "ע\"ר",
)

# Registrations and ownerships that are institutional by definition.
_INSTITUTIONAL_REG = {"recognized_museum", "public_library"}
_INSTITUTIONAL_OWNERSHIP = {"state", "council", "settlement", "ngo", "religious"}

_FREE_MAIL = ("gmail.", "walla.", "hotmail.", "outlook.", "yahoo.", "icloud.")


def is_institutional(site: dict) -> bool:
    """True when this record's contact details belong to a body rather than a person."""
    if site.get("reg_institution") in _INSTITUTIONAL_REG:
        return True
    if site.get("ownership") in _INSTITUTIONAL_OWNERSHIP:
        return True
    rest = site.get("rest") if isinstance(site.get("rest"), dict) else site
    operator = str(rest.get("operator") or site.get("operator") or "")
    if any(w in operator for w in _INSTITUTIONAL_OPERATOR):
        return True
    # An explicit private-sector marker from any source settles it the other way.
    for e in (site.get("extra") or {}).values():
        if isinstance(e, dict) and e.get("contact_is_private_sector"):
            return False
    return False


def scrub_deep(value):
    """Scrub email addresses out of every string anywhere in a structure.

    Needed because addresses also sit inside prose: one record's `operator` reads
    'לא צוין במקור; קשור למועצה לשימור אתרי מורשת בישראל (כתובת הדוא"ל ...)', and a description
    lists a museum's former names together with a mailbox. Field-level redaction never sees those.
    """
    if isinstance(value, str):
        return scrub_free_text(value)
    if isinstance(value, list):
        return [scrub_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub_deep(v) for k, v in value.items()}
    return value


def phone_publishable(site: dict) -> bool:
    """A phone number may be published only for a body that is unambiguously institutional."""
    return (site.get("reg_institution") in _INSTITUTIONAL_REG
            or site.get("ownership") in {"state", "council"})


def redact_site(site: dict) -> tuple[dict, list[str]]:
    """Return a copy safe to publish, plus the names of the fields withheld. Mutates nothing.

    EMAIL IS NEVER PUBLISHED. That is a deliberate retreat from a cleverer rule that tried to
    judge whether the body was institutional. It failed on the real data: the regional library
    runs its branches from named librarians' personal gmail accounts, so the institution is
    genuine and the mailbox is a person's, and no heuristic separates hayogev.lib@gmail.com from
    nellikrogius@gmail.com without judging whether a string is somebody's name. A map showing
    where heritage is does not need to be a contact directory, institutions publish a website,
    and the addresses remain in the working copy for the institute's own use.
    """
    removed: list[str] = []
    out = dict(site)
    rest = dict(out["rest"]) if isinstance(out.get("rest"), dict) else None

    for container, where in ((out, "site"), (rest, "rest")):
        if container is None:
            continue
        if container.get("email") not in (None, ""):
            container["email"] = None
            removed.append(f"{where}.email")
        if container.get("phone") not in (None, "") and not phone_publishable(site):
            container["phone"] = None
            removed.append(f"{where}.phone")

    if rest is not None:
        if removed:
            rest["contact_withheld"] = True
        out["rest"] = rest
    elif removed:
        out["contact_withheld"] = True

    if isinstance(out.get("claims"), list):
        out["claims"] = redact_claims(out["claims"])

    return scrub_deep(out), removed


def redact_claims(claims: list[dict]) -> list[dict]:
    """Drop contact claims outright, then scrub what remains.

    Every record's claim log is redacted, institutional or not: a rejected claim can carry a
    different person's number than the one that won, and nothing downstream reads it.
    """
    kept = [c for c in claims or [] if c.get("field") not in CONTACT_FIELDS]
    return [scrub_deep(c) for c in kept]


def scrub_free_text(value):
    """Remove an email address embedded in prose, such as a shimur.org visiting note."""
    if not isinstance(value, str):
        return value
    return re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[הוסר]", value)


# --------------------------------------------------------------------------------------
# input-side redaction, for the frozen archive that is committed publicly
# --------------------------------------------------------------------------------------
PERSON_ROW_MARKERS = ("אדם",)
INSTITUTE_TABLE_CONTACT_COLUMNS = ("מספר טלפון", "דואר אלקטרוני")


def redact_institute_table(rows: list[dict]) -> tuple[list[dict], dict]:
    """Make the institute's inventory publishable.

    Drops the individual-person rows outright, since the brief puts people out of scope and they
    contribute nothing to the map, and clears the contact columns. The pipeline already ignores
    the person rows, so removing them changes no output.
    """
    kept, dropped, cleared = [], 0, 0
    for r in rows or []:
        if str(r.get("סוג רשומה") or "").strip() in PERSON_ROW_MARKERS or r.get("_excluded"):
            dropped += 1
            continue
        r = dict(r)
        for c in INSTITUTE_TABLE_CONTACT_COLUMNS:
            if r.get(c) not in (None, ""):
                r[c] = None
                cleared += 1
        kept.append(r)
    return kept, {"rows_dropped": dropped, "contact_values_cleared": cleared}


def redact_culture_institutions(rows: list[dict]) -> tuple[list[dict], dict]:
    """Clear contacts and the licence block, which names a licence holder and a manager."""
    cleared, licences = 0, 0
    out = []
    for r in rows or []:
        r = dict(r)
        for c in ("phone", "email"):
            if r.get(c) not in (None, ""):
                r[c] = None
                cleared += 1
        if r.get("business_licence"):
            bl = r["business_licence"]
            if isinstance(bl, dict):
                r["business_licence"] = {"licence_type": bl.get("licence_type"),
                                         "valid_until": bl.get("valid_until")}
                licences += 1
        for k in ("accessibility", "notes", "active_evidence"):
            r[k] = scrub_free_text(r.get(k))
        out.append(r)
    return out, {"contact_values_cleared": cleared, "licence_blocks_reduced": licences}


def redact_heritage_official(rows: list[dict]) -> tuple[list[dict], dict]:
    """shimur.org publishes a private mailbox and mobile for some visitable sites."""
    cleared = 0
    out = []
    for r in rows or []:
        r = dict(r)
        for c in ("site_email", "site_phone", "shimur_info_block__טלפון",
                  "shimur_info_block__דוא''ל", "marker_kv_דוא“ל", "marker_kv_טלפון"):
            if r.get(c) not in (None, ""):
                r[c] = None
                cleared += 1
        for k in ("shimur_text", "site_notes", "site_opening_hours__הערות",
                  "shimur_info_block__הערות"):
            r[k] = scrub_free_text(r.get(k))
        out.append(r)
    return out, {"contact_values_cleared": cleared}


PAYLOAD_REDACTORS = {
    "iicp_culture_table.json": redact_institute_table,
    "culture_institutions.json": redact_culture_institutions,
    "heritage_official.json": redact_heritage_official,
}

# Column names that hold a contact address in one source or another. Cleared everywhere.
_CONTACT_COLUMNS = (
    "email", "site_email", "contact:email", "operator:email", "wd_P968_email",
    "דואר אלקטרוני", "phone", "site_phone", "contact:phone", "operator:phone",
    "wd_P1329_phone_number", "מספר טלפון",
)


def redact_payload(name: str, rows: list) -> tuple[list, dict]:
    """The single gate every frozen payload passes.

    A per-source redactor runs first where one exists, then ONE invariant is enforced over
    everything: no email address survives anywhere in the committed archive, in a column or
    inside prose. The per-source rules kept missing addresses in fields nobody thought to list,
    and the archive is committed to a public repository, so the blanket rule is the one that
    actually holds. OSM's institutional archive addresses are openly licensed and would be
    defensible to keep; they go too, because one invariant that always holds beats a rule with
    justified exceptions that has already failed once.
    """
    report: dict = {}
    redactor = PAYLOAD_REDACTORS.get(name)
    if redactor and isinstance(rows, list):
        rows, report = redactor(rows)

    cleared = 0
    if isinstance(rows, list):
        out = []
        for r in rows:
            if isinstance(r, dict):
                r = dict(r)
                for c in _CONTACT_COLUMNS:
                    if r.get(c) not in (None, ""):
                        r[c] = None
                        cleared += 1
                osm = r.get("osm_tags")
                if isinstance(osm, dict):
                    r["osm_tags"] = {k: v for k, v in osm.items()
                                     if "email" not in k and "phone" not in k}
            out.append(r)
        rows = out
    report["contact_columns_cleared"] = cleared
    return scrub_deep(rows), report
