export const meta = {
  name: 'emek-yizrael-verification',
  description: 'Adversarially verify the harmonized Emek Yizrael heritage dataset to a 95% confidence target',
  phases: [
    { title: 'Verify', detail: '10 verification agents, each with a distinct lens' },
    { title: 'Refute', detail: 'skeptics try to break every proposed correction' },
  ],
}

const ROOT = 'C:/Users/matan/OneDrive/Documents/projects/iicp-emek-yizrael-map'

const COMMON = `
CONTEXT
A public interactive map of culture and heritage sites inside מועצה אזורית עמק יזרעאל has been
built by harmonizing eight sources. Your job is to find where it is WRONG. The stated goal is
that the published data is correct at 95% confidence or better, so a finding you confirm is
worth more than a finding you assume.

Project root: ${ROOT}
The dataset: ${ROOT}/data/out/sites.json - a JSON array of 1044 site records.
Also available: ${ROOT}/data/out/review_queue.json , ${ROOT}/data/out/harmonize_stats.json ,
the raw source payloads under ${ROOT}/data/raw/ , the per-source documentation in
${ROOT}/docs/sources/*.md , and the official council boundary at
${ROOT}/data/raw/boundary_emek_yizrael.geojson .

Record shape, the fields that matter:
  id, name, name_en, names_alt[], category (archaeological|historic|culture), categories[],
  type, periods[], year_from, year_to, era_basis, lat, lon, itm_x, itm_y,
  location_precision (exact|approx_100m|approx_500m|locality_centroid|unknown),
  locality (SOURCED) and nearest_settlement (COMPUTED by us, not a source claim),
  in_council, dist_to_boundary_m (positive inside, negative outside), near_boundary,
  12 status axes: reg_antiquity reg_conservation reg_institution protected_area excavation
  accessibility a11y_disabled condition activity signage visitor_dev ownership,
  confidence, confidence_components{existence,location,category}, source_count,
  sources[], provenance{field: [source_id]}, claims[] (every raw claim incl. rejected),
  conflicts[], needs_review, review_reasons[], overlay_notes[].

The three categories are legal, not stylistic: archaeological is up to 1700 CE and is the remit
of רשות העתיקות under חוק העתיקות התשל"ח-1978; historic is after 1700 and the remit of המועצה
לשימור אתרי מורשת; culture is an institution operating today. A place can be several at once.

HOW TO WORK
1. Load the data with Python, do not read the 3 MB file into your context. Filter first.
2. Verify against INDEPENDENT evidence: Hebrew Wikipedia, Wikidata, the IAA's own site,
   shimur.org, the council's website, INPA, OSM. State the source and the URL for every
   finding. A finding with no citable evidence is not a finding.
3. NEVER invent a value. If you cannot establish the truth, say so and mark the item
   unresolved. "I could not determine this" is a valid and useful answer.
4. Be a polite client: about one request per second, no hammering. If a site refuses
   automated access, stop and report it rather than working around it.
5. Do NOT modify ${ROOT}/data/out/sites.json or anything under ${ROOT}/src or ${ROOT}/site .
   Corrections are applied centrally. Write your findings to
   ${ROOT}/data/verify/<your-agent-id>.json and nothing else.
6. Hebrew files are UTF-8: Python encoding='utf-8'; PowerShell -Encoding UTF8 -LiteralPath.
   Never use an em-dash in any output you write.
7. Today is 2026-08-03.

YOUR OUTPUT FILE must be a JSON object:
{ "agent_id": "...", "checked": <int>, "method": "...",
  "findings": [ { "site_id": "...", "site_name": "...", "field": "...",
                  "current": <any>, "proposed": <any>,
                  "verdict": "wrong" | "right" | "unresolved",
                  "severity": "high" | "medium" | "low",
                  "evidence": "what you found, with the URL",
                  "confidence": 0.0-1.0 } ],
  "unresolved": [...], "notes": "..." }
`

const FINDING_SCHEMA = {
  type: 'object',
  required: ['agent_id', 'checked', 'confirmed_wrong', 'confirmed_right', 'unresolved', 'summary'],
  properties: {
    agent_id: { type: 'string' },
    checked: { type: 'integer', description: 'How many records you actually verified' },
    confirmed_wrong: { type: 'integer' },
    confirmed_right: { type: 'integer' },
    unresolved: { type: 'integer' },
    high_severity: { type: 'integer' },
    file_written: { type: 'string' },
    top_findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['site_name', 'field', 'problem', 'evidence'],
        properties: {
          site_id: { type: 'string' }, site_name: { type: 'string' },
          field: { type: 'string' }, problem: { type: 'string' },
          proposed: { type: 'string' }, evidence: { type: 'string' },
          severity: { type: 'string' },
        },
      },
      description: 'The findings that most change the map. At most 12.',
    },
    systemic_issues: {
      type: 'array', items: { type: 'string' },
      description: 'Patterns rather than single records: a whole source mis-mapped, a rule that is wrong. These matter most.',
    },
    summary: { type: 'string' },
  },
}

phase('Verify')

const AGENTS = [
  {
    id: 'jurisdiction_edge',
    label: 'verify:jurisdiction edges',
    task: `Verify the jurisdiction decision for every site where it could plausibly be wrong.

Select: all sites with in_council === false, plus all with near_boundary === true and
abs(dist_to_boundary_m) <= 150, plus all with in_council === null (no coordinate).
That is a few hundred records, so work in order of risk: smallest abs(dist_to_boundary_m) first,
and stop when you have verified at least 60 of them properly. Report how many you covered.

For each: establish from an INDEPENDENT source which local authority the place actually belongs
to. Hebrew Wikipedia articles usually state the council; Wikidata P131 gives the administrative
entity; the settlement it sits in is decisive because a site on Kibbutz Gvat's land is in Emek
Yizrael and a site in Kfar Kanna is not. Neighbouring authorities to watch for: עפולה, נצרת,
נוף הגליל, מגדל העמק, יקנעם עילית, רמת ישי, קרית טבעון, אכסאל, כפר כנא, זרזיר, בסמת טבעון,
כפר כמא, and the neighbouring regional councils מגידו, הגלבוע, הגליל התחתון, זבולון, עמק המעיינות.
Flag any case where our answer disagrees with the evidence, in EITHER direction: a site we
excluded that actually belongs to the council is as much an error as one we wrongly included.
Also sanity-check the boundary itself: if you find several adjacent sites all misclassified the
same way, that points at the polygon rather than the points, and you should say so loudly.`,
  },
  {
    id: 'coordinate_accuracy',
    label: 'verify:coordinates',
    task: `Verify that sites are actually where we say they are.

Draw a STRATIFIED sample of at least 45 sites: at least 8 from each of the three categories,
at least 5 per contributing source (declared_antiquities, iaa_discover, iaa_cluster_table,
blue_signs, heritage_official, culture_institutions, iicp_culture_table, osm_wikidata), and
deliberately include the sites whose location_precision is approx_500m or locality_centroid and
those whose review_reasons mention sources_disagree_on_location.

For each, find an independent position: the Hebrew Wikipedia article's coordinates, Wikidata
P625, an OSM element, or the IAA's own record. Compute the distance between our coordinate and
theirs and report it. Judge: under 100 m is fine for an area site; over 500 m needs explaining;
over 2 km is almost certainly an error and is high severity. Watch specifically for a
latitude/longitude swap, an ITM grid read as the older ICS grid, and a polygon centroid that
lands outside its own site. Report the median and the worst error you found, and give the
distribution, because that is what tells us the overall positional quality of the map.`,
  },
  {
    id: 'era_1700',
    label: 'verify:the 1700 line',
    task: `Verify the archaeological / historic split, which is the map's central classification.

Select the riskiest cases: every site whose era_basis is 'unknown' or 'site_type', every site
whose review_reasons contain a 'stated_year_..._contradicts_periods' entry, every site whose
categories array has both 'archaeological' and 'historic', and a sample of 20 where era_basis is
'source_authority'. Verify at least 50 records.

For each, establish the period or construction date from an independent source and judge whether
our category is right under the legal rule: any remains from before 1700 make it an antiquities
site under חוק העתיקות, even if later layers exist; only a place whose whole story begins after
1700 is purely post-1700 heritage. Pay attention to the genuinely hard cases: an Ottoman-period
site can fall on either side of 1700 and needs a real date, not a guess; a modern settlement
monument standing on an ancient tell is BOTH and should carry both categories; a British Mandate
police fort is unambiguously post-1700. Report any site where we put a demonstrably pre-1700
site in 'historic' or a demonstrably post-1700 building in 'archaeological', and say whether the
error looks like a one-off or a rule that is wrong.`,
  },
  {
    id: 'merge_audit',
    label: 'verify:merges',
    task: `Audit whether merged records really are one place. Try to REFUTE each merge.

Select the 35 riskiest merges: every site whose review_reasons contain
'merged_on_name_without_geometry', every one with 'sources_disagree_on_location', those with the
largest source_count, and any where the names_alt list contains names that look like different
places rather than spellings of one.

For each, read the site's claims[] array to see exactly what each source contributed, then decide
from independent evidence whether these are one place or several. The specific failure to hunt
for: a settlement fused with a site inside it (the moshav Beit She'arim versus Khirbat Beit
She'arim), a modern institution fused with the heritage building it occupies, two neighbouring
ruins with a shared generic name, and a sub-feature of a large site treated as the whole site.
Default to "this merge is wrong" if you cannot positively establish that it is right, and say
which claim records should be split out. Also report the reverse error where you notice it: two
separate records in the output that are plainly the same place.`,
  },
  {
    id: 'duplicate_hunt',
    label: 'verify:missed duplicates',
    task: `Find sites that appear MORE THAN ONCE in the output because a merge was missed.

This is the false-negative side of matching. Work programmatically first: for every pair of
sites within 500 m of each other, compute a name similarity and list the suspicious pairs; also
group by nearest_settlement and eyeball the names within each settlement; also look for pairs
where one name is a superset of the other, or where one is a Hebrew transliteration variant of
the other (ח'ירבת/חורבת, שמרון/שימרון, צפורי/ציפורי, ס/ש, ט/ת, כ/ק).

Then verify the promising pairs against independent evidence and report each confirmed duplicate
with both site ids. Note that the pipeline deliberately blocks a merge when two records carry
DIFFERENT antiquity site numbers, which is usually right but will be wrong when the IAA itself
holds two numbers for one place, so check ${ROOT}/data/out/review_queue.json under
blocked_by_conflicting_id for exactly that case. Report how many genuine duplicates you found out
of how many candidate pairs you examined, since that ratio is our precision estimate.`,
  },
  {
    id: 'culture_activity',
    label: 'verify:institution activity',
    task: `Verify the culture institutions, which are the only category that makes a present-tense claim.

Select every site whose categories include 'culture'. For each, establish from FIRST-PARTY
evidence whether it is operating today: its own website or social page with something dated in
2025 or 2026, the council's culture or tourism pages, a ticketing portal with future dates, a
current programme. Check the Ministry of Culture recognised-museums list and the public-libraries
register for the ones we mark as registered, and confirm or deny that registration.

Judge each as active, seasonal, inactive or genuinely unknown, and give the evidence and its
date. An institution we call active with no current evidence is a real error, and one we have as
unknown that is plainly operating is a missed opportunity. Also flag anything that should not be
on the map at all under the brief: an individual artist's home studio listed under a person's
name is out of scope, whereas a business with its own name that the council publishes as a visitor
destination is in scope. Finally check the practical details we publish, opening hours and
admission, and report any that are stale or contradicted by the institution itself.`,
  },
  {
    id: 'status_provenance',
    label: 'verify:status provenance',
    task: `Audit the status axes for values that are not entitled to be there.

Work programmatically over all 1044 records. For each non-unknown value on each of the 12 status
axes, check the record's provenance and claims to confirm that the value came from a source
permitted to make that claim. The rules the pipeline is supposed to enforce:
reg_antiquity may come ONLY from declared_antiquities, iaa_discover or iaa_cluster_table;
reg_institution only from culture_institutions; signage only from blue_signs, heritage_official
or iicp_culture_table. Report every violation.

Then check the 390 reg_conservation and 118 protected_area values that were assigned SPATIALLY
from the Planning Administration overlay rather than by name. Read the overlay_notes on those
records. Sample 25 of them and judge whether the spatial inference is sound: is the site really
inside that conservation designation, or did a large polygon radius sweep in a site that has
nothing to do with the plan? This is the newest and least verified inference in the whole
pipeline, so scrutinise it hardest, and say plainly whether it should be kept, narrowed or
dropped. Also verify the reg_antiquity 'declared' versus 'known' distinction on a sample of 20:
'declared' must mean a formal declaration under חוק העתיקות with a gazette reference.`,
  },
  {
    id: 'flagship_sites',
    label: 'verify:flagship sites',
    task: `Verify, in full and in depth, the 25 sites a visitor is most likely to open.

Choose them by prominence rather than by our confidence score: the national parks, the UNESCO
listing, the sites with Wikipedia articles, the largest declared antiquity sites, the recognised
museum, the well-known tells, the Jezreel Valley railway heritage, and the famous monuments.
Beit She'arim, Zippori, Tel Shimron, Tel Yizre'el, the Kfar Yehoshua railway station, the
Alexander Zaid monument at Sheikh Abreik, Nahalal, Bethlehem of Galilee and Beit Hankin are
obvious candidates, but establish the list from the data rather than from this sentence, and
verify for each of them that it exists, is where we say, is in the council's jurisdiction, has
the right category and periods, and carries correct statuses and a correct name.

These records carry the map's credibility, so check EVERY field on each one and report anything
off, including a clumsy or wrong Hebrew name, a missing famous alternative name, a wrong period,
and a status that contradicts what the site's own official page says. Where a site is genuinely
famous and we have it under an obscure name, that is a high-severity finding even though the
data is not strictly false.`,
  },
  {
    id: 'completeness',
    label: 'verify:what is missing',
    task: `Find heritage and culture places inside the council that are ABSENT from the map entirely.

Everything else in this workflow checks what we have. You check what we lack, which no other
agent will catch. Work from independent enumerations rather than from our own data: the Hebrew
Wikipedia category tree for the council and for each of its 49 settlements, the council's own
tourism and culture pages, the INPA list of parks and reserves in the area, the Council for
Conservation's site list, the Jezreel Valley railway stations, the settlement histories that name
a founders' house or a water tower or a first school, museums and archives at the kibbutzim (many
kibbutzim run an archive, and kibbutz archives ARE culture institutions in scope), and lists of
memorials.

The council's settlement list with coordinates is at
${ROOT}/data/raw/settlements_emek_yizrael.json . For each candidate you find, check whether it is
already in our data by name and by position before reporting it as missing, and give its
coordinates and category so it can actually be added. Report gaps by TYPE as well as by instance:
if kibbutz archives or memorials or libraries are systematically under-represented, that is the
most valuable thing you can tell us.`,
  },
  {
    id: 'name_quality',
    label: 'verify:names and labels',
    task: `Audit the names the map displays, since the name is what a visitor reads first.

Check all 1044 display names programmatically for mechanical problems, then verify the worst by
hand. Look for: a name that is still in the inverted catalogue form ("פרוה, ח'" instead of
"ח' פרוה"); a name that is a designation rather than a name ("מבנה לשימור", "אתר מוכרז", "בלוק
מבנה לשימור"); a name carrying a leftover site number; a name that is only a settlement name
where the site is something inside that settlement; mojibake or reversed Hebrew (the source layer
tmm_park_or_reserve has a NAMEL column containing deliberately reversed text such as
"מור תבריח - ירופיצ", so check that none of that leaked in); an English name sitting in the
Hebrew name field; and duplicated words.

Also check that where a site has a well-known Hebrew name, that is the one we display and the
catalogue variant is in names_alt rather than the other way round. Then verify a sample of 25
names against Hebrew Wikipedia or the IAA record and report any that are simply wrong. Give the
count of each problem class, because the class matters more than the instance here.`,
  },
]

const found = await parallel(AGENTS.map(a => () => agent(
  `${COMMON}\nYOUR AGENT ID: ${a.id}\nWrite your findings to ${ROOT}/data/verify/${a.id}.json\n\nYOUR TASK\n${a.task}`,
  { label: a.label, phase: 'Verify', schema: FINDING_SCHEMA },
)))

const ok = found.filter(Boolean)
log(`Verification: ${ok.length}/${AGENTS.length} agents returned`)
let wrong = 0, high = 0
for (const r of ok) {
  wrong += r.confirmed_wrong || 0
  high += r.high_severity || 0
  log(`${r.agent_id}: checked ${r.checked}, wrong ${r.confirmed_wrong}, unresolved ${r.unresolved}`)
}

// Adversarial pass: the systemic claims are the ones that would change the pipeline, so they get
// challenged before they are acted on. A wrong "fix" to a rule damages every record at once.
phase('Refute')
const systemic = ok.flatMap(r => (r.systemic_issues || []).map(s => ({ agent: r.agent_id, claim: s })))
log(`${systemic.length} systemic claims to challenge`)

const REFUTE_SCHEMA = {
  type: 'object',
  required: ['claim', 'holds_up', 'reasoning'],
  properties: {
    claim: { type: 'string' },
    holds_up: { type: 'boolean', description: 'true only if you FAILED to refute it' },
    reasoning: { type: 'string' },
    counter_evidence: { type: 'string' },
    recommended_action: { type: 'string' },
  },
}

const challenged = await parallel(systemic.slice(0, 14).map((s, i) => () => agent(
  `${COMMON}

YOU ARE A SKEPTIC. Another agent examined the dataset and made this SYSTEMIC claim about it,
meaning a claim about a whole source, rule or pattern rather than a single record:

  raised by: ${s.agent}
  claim: ${s.claim}

Try to REFUTE it. Check the actual data and the actual sources yourself. A systemic claim, if
acted on, changes hundreds of records at once, so the cost of accepting a wrong one is high and
you should default to refuted when the evidence is thin. Set holds_up true ONLY if you genuinely
could not refute it and you found positive evidence that it is correct. If it holds up, say
concretely what should change: which field, which records, which rule in the pipeline.
Do not write any files.`,
  { label: `refute:${i + 1}`, phase: 'Refute', schema: REFUTE_SCHEMA, effort: 'high' },
)))

const surviving = challenged.filter(Boolean).filter(c => c.holds_up)

return {
  agents_returned: ok.length,
  total_confirmed_wrong: wrong,
  total_high_severity: high,
  per_agent: ok.map(r => ({
    agent_id: r.agent_id, checked: r.checked, wrong: r.confirmed_wrong,
    right: r.confirmed_right, unresolved: r.unresolved, high: r.high_severity,
    file: r.file_written, summary: r.summary,
    top_findings: r.top_findings, systemic: r.systemic_issues,
  })),
  systemic_claims_raised: systemic.length,
  systemic_claims_surviving_refutation: surviving.map(c => ({
    claim: c.claim, reasoning: c.reasoning, action: c.recommended_action,
  })),
  systemic_claims_refuted: challenged.filter(Boolean).filter(c => !c.holds_up)
    .map(c => ({ claim: c.claim, why_refuted: c.reasoning })),
}
