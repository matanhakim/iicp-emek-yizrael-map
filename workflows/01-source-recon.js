export const meta = {
  name: 'emek-yizrael-source-recon',
  description: 'Recon + raw extraction of every heritage/culture data source for the Emek Yizrael map',
  phases: [{ title: 'Recon', detail: '9 parallel source-extraction agents' }],
}

const ROOT = 'C:/Users/matan/OneDrive/Documents/projects/iicp-emek-yizrael-map'
const BBOX = 'WGS84 lat 32.55-32.85, lon 35.05-35.50; ITM/EPSG:2039 roughly x 198000-245000, y 710000-750000'

const COMMON = `
CONTEXT
You are one of nine agents gathering source data for a public interactive map of culture and heritage sites inside the jurisdiction of מועצה אזורית עמק יזרעאל (Emek Yizrael / Jezreel Valley Regional Council), Israel.
Project root: ${ROOT}
Search window (council plus generous margin): ${BBOX}
The map will have exactly three site categories: (1) archaeological site = anything up to 1700 CE, remit of רשות העתיקות; (2) historic site = after 1700 CE, remit of המועצה לשימור אתרי מורשת בישראל; (3) active culture and arts institutions. Individual people are explicitly out of scope.

HARD RULES
1. NEVER invent, guess or interpolate. If a value is absent from the source, record null and say so. This applies above all to coordinates, dates, IDs and status values. An honest gap beats fabricated content. You will be adversarially audited later, so a fabricated value is the worst possible outcome.
2. Save every raw payload you obtain, byte-for-byte unmodified, under ${ROOT}/data/raw/ . ASCII file names only - Hebrew path segments break when passed between shells.
3. Hebrew text must be written and read as UTF-8 explicitly: Python encoding='utf-8'; PowerShell always -Encoding UTF8 and -LiteralPath. If you see mojibake with multiplication-sign characters, some layer decoded UTF-8 as a single-byte codepage; it is byte-preserving and reversible.
4. Document your work in ${ROOT}/docs/sources/<your-source-id>.md : exact endpoints and URLs, request parameters, the FULL schema of what came back (every field name, its meaning, units, CRS), record counts, licence or terms of use if stated, retrieval timestamp (today is 2026-08-03), and known limitations. Hebrew markdown files get wrapped in <div dir="rtl"> with a blank line after the opening tag and before the closing tag.
5. Be a polite client: at most about one request per second, never parallel hammering, descriptive User-Agent. If a site blocks you, stop and report it. Do not attempt to evade blocks.
6. Prefer machine-readable endpoints (REST/JSON/GeoJSON/ArcGIS FeatureServer/WFS/CSV) over HTML scraping. To find them: fetch the page HTML, extract the JS bundle URLs, fetch the bundle text and grep for /api, FeatureServer, MapServer, query?, graphql, .json.
7. Do NOT run any git command. Do NOT touch ${ROOT}/src or ${ROOT}/site . You own only data/raw, data/interim and docs/sources.
8. Coordinates: record the native CRS exactly as given. Israeli sources use ITM (EPSG:2039, x about 200k, y about 700k) or the older ICS (EPSG:28193, x about 190k, y about 230k) - the y magnitude distinguishes them. Never silently treat one as the other. If you convert to WGS84, keep the original columns as well.
9. Python 3.14 is available with pandas, geopandas, shapely, pyproj, openpyxl, requests, rapidfuzz. No fiona.
10. Output a machine-readable per-record file too: ${ROOT}/data/interim/<source-id>.json as a JSON array of flat objects, one per site, keeping ALL original fields under their original names plus, where you could derive them honestly, lat and lon in WGS84.
`

const SCHEMA = {
  type: 'object',
  required: ['status', 'source_id', 'summary', 'record_count', 'files_written', 'caveats'],
  properties: {
    status: { type: 'string', enum: ['ok', 'partial', 'failed'] },
    source_id: { type: 'string' },
    summary: { type: 'string', description: 'What you obtained, how, and how trustworthy it is. 3-10 sentences.' },
    record_count: { type: 'integer', description: 'Records saved that plausibly fall in the search window; -1 if not applicable' },
    files_written: { type: 'array', items: { type: 'string' } },
    endpoints: { type: 'array', items: { type: 'string' }, description: 'Exact URLs/endpoints that worked' },
    native_crs: { type: 'string' },
    field_names: { type: 'array', items: { type: 'string' }, description: 'Every field present in the extracted records' },
    status_fields_available: { type: 'array', items: { type: 'string' }, description: 'Fields usable as a per-site STATUS (declared/registered, excavated, accessible, condition, active, signed, protected by plan, etc.) - name them exactly' },
    join_keys_available: { type: 'array', items: { type: 'string' }, description: 'Fields usable to match this source against other sources (names, IAA site numbers, licence numbers, permit numbers, wikidata QIDs, coordinates)' },
    caveats: { type: 'array', items: { type: 'string' } },
    leads_for_others: { type: 'array', items: { type: 'string' }, description: 'Anything you found that another source agent or the harmonization step must know' },
  },
}

phase('Recon')

const tasks = [

  // 1 - official boundary
  () => agent(`${COMMON}
YOUR TASK - source_id: boundary
Deliver the authoritative official boundary of מועצה אזורית עמק יזרעאל as a GeoJSON polygon/multipolygon in WGS84 at ${ROOT}/data/raw/boundary_emek_yizrael.geojson , alongside the untouched original download.

The user specifically asked for the boundary as published by the Israeli Central Bureau of Statistics (הלמ"ס). Try in this order and report what worked:
- CBS GIS layers: municipal boundaries / statistical areas (אזורים סטטיסטיים 2022) shapefile or GeoJSON on cbs.gov.il.
- data.gov.il CKAN API: https://data.gov.il/api/3/action/package_search?q=<url-encoded Hebrew for boundaries or local authorities>, then package_show, then the resource download or datastore_search.
- Israeli government ArcGIS REST services (govmap, מרכז למיפוי ישראל, משרד הפנים): find a municipal-boundaries FeatureServer/MapServer and query it with f=geojson&outSR=4326&where=...
- OpenStreetMap via Overpass is a CROSS-CHECK ONLY, never the primary: the admin relation named מועצה אזורית עמק יזרעאל, converted to a polygon. Save it separately as boundary_osm_crosscheck.geojson and report the area difference and maximum boundary deviation versus the official one.

CRITICAL CORRECTNESS REQUIREMENT. This council is a doughnut-shaped multipolygon: it wraps around municipalities that are NOT part of it, including Migdal HaEmek, Nof HaGalil, Nazareth, Afula, Yokneam Illit, Ramat Yishai, Kiryat Tiv'on, Iksal, Kfar Kanna, Zarzir, Basmat Tab'un, Bir el-Maksur. Neighbouring REGIONAL councils such as מועצה אזורית מגידו, מועצה אזורית הגלבוע, מועצה אזורית הגליל התחתון and מועצה אזורית זבולון are likewise separate and must be excluded. If your polygon lacks those holes and exclusions, every later point-in-polygon test is worthless.
VALIDATE IT, do not assume:
(a) Load it with shapely. Confirm that the centre of Afula, Nazareth, Migdal HaEmek and Yokneam Illit each falls OUTSIDE. Get those centres from an independent source, not from memory.
(b) Find the OFFICIAL list of settlements that constitute the council, with a citable source (the council's own website, the Ministry of Interior order - צו המועצות המקומיות, or CBS). For each settlement obtain a coordinate from an independent source (CBS yishuv coordinates, Wikidata, or OSM) and test it against the polygon. Report how many fall inside; expect essentially all of them. List every failure with its distance to the boundary and diagnose whether the polygon or the coordinate is at fault.
(c) Report: CBS authority code (סמל רשות) for the council, computed area in km2 versus the officially published area (cite it), number of polygon parts, number of holes.
Also write ${ROOT}/data/raw/settlements_emek_yizrael.json - the settlement list with Hebrew name, English name if available, CBS yishuv code if available, coordinate, and the source of each. Later agents depend on this list, so make it complete and accurate.
In your summary, state plainly whether the delivered polygon passed every check, and if not, exactly which check failed.`,
    { label: 'boundary:CBS official', phase: 'Recon', schema: SCHEMA }),

  // 2 - IAA national archaeology database
  () => agent(`${COMMON}
YOUR TASK - source_id: iaa_discover
Extract archaeological sites in the search window from the Israel Antiquities Authority national archaeology database at https://discover.iaa.org.il/?entity_index=0&tabId=2 (המאגר הלאומי לארכאולוגיה).

This is a single-page app, so find its backing API rather than scraping rendered HTML. Steps: fetch the page, list the JS/JSON assets it loads, fetch those bundles and grep them for endpoint patterns (/api/, FeatureServer, MapServer, elastic, search, graphql, /rest/). Also probe the obvious hosts: api.iaa.org.il, discover.iaa.org.il/api, www.antiquities.org.il, survey.antiquities.org.il (the Archaeological Survey of Israel), and any ArcGIS service you find. Try a spatial or bounding-box query parameter, and if none exists, a paged full listing filtered afterwards by coordinates.
The database distinguishes several entity types (the URL parameter entity_index and tabId hint at tabs): sites, excavations/permits, surveys, finds, publications. Map out which entity types exist and what each offers. For our map the priorities are: site identity and name, coordinates, periods, declaration/registration status, whether it was excavated versus only surveyed, excavation licence numbers and years, excavator, and any accessibility or condition note. Excavation records are especially valuable because they establish the excavated status and give a date - capture them and the site they attach to.
Save the raw JSON responses, then produce ${ROOT}/data/interim/iaa_discover.json .
If and only if pure HTTP genuinely fails, say so explicitly in your caveats and describe precisely which endpoint returned what - a later step may drive a real browser. Do not use browser automation yourself.
Report the full field schema and, critically, which fields can serve as join keys against a spreadsheet of IAA sites (site number, סמל אתר, IAA ID, name).`,
    { label: 'iaa:national database API', phase: 'Recon', schema: SCHEMA }),

  // 3 - amud anan
  () => agent(`${COMMON}
YOUR TASK - source_id: amudanan
Extract relevant points of interest in the search window from עמוד ענן, https://amudanan.co.il/ - an Israeli hiking/topographic map platform with layered points of interest.

Find its data API rather than scraping tiles: fetch the page, enumerate its JS bundles and config files, grep for /api, .json, layers, markers, poi, points, geoserver, FeatureServer, and for tile/vector-tile URLs that reveal a data host. Check for an accompanying mobile-app API and for any documented developer endpoint. Also check whether its points originate from a known upstream (Israel Hiking Map, OSM, INPA, KKL, the Survey of Israel) - if they do, note it loudly, because we must not double-count OSM data that another agent already pulls.
We want only points that are plausibly a heritage or culture site: archaeological remains, ruins (חורבה, ח'ירבת, תל), springs with built structures, ancient tombs, forts, khans, mills, wells, mosques/churches/synagogues, historic buildings, memorials and monuments, museums, visitor centres. Exclude pure nature points (viewpoints, picnic tables, trees, bicycle trails, parking, water taps) unless they are the marker for a heritage site.
Record every attribute the source gives, including its own category/layer name, any description text, and any accessibility hint (access road, trail, whether it is inside a closed military zone or a nature reserve).
Save raw payloads and produce ${ROOT}/data/interim/amudanan.json .
Respect the site: low request rate, no bulk tile downloading. If it requires a login or clearly forbids automated access in its terms, stop, report exactly what it says, and deliver whatever you could obtain legitimately.`,
    { label: 'amudanan:POI layers', phase: 'Recon', schema: SCHEMA }),

  // 4 - blue signs
  () => agent(`${COMMON}
YOUR TASK - source_id: blue_signs
Extract the שלטים כחולים (blue signs) of המועצה לשימור אתרי מורשת בישראל that fall in the search window.

Primary source: the Hebrew Wikipedia portal page https://he.wikipedia.org/wiki/פורטל:אתרי_מורשת_בישראל/שלטים_כחולים (URL-encode it). Use the MediaWiki API rather than parsing rendered HTML: action=parse or action=query with prop=revisions&rvslots=main to get the wikitext of the list, plus the pages it links to.
For each blue-sign entry get: the sign name/title, the sign number if listed, the settlement, the region, the linked Wikipedia article, and the sign text if available. Then obtain coordinates properly: for every linked article call the MediaWiki API with prop=coordinates (and pageprops to get the wikibase_item), and query Wikidata for coordinate location (P625), heritage designation (P1435), inception (P571) and image (P18). Coordinates that come from Wikidata or Wikipedia geo-tags are acceptable; NEVER invent a coordinate for an entry that has none - mark it null and list it as needing manual geolocation.
Also check the Council for Conservation's own site (a shimur.org domain) for a searchable sites list or map with an API, and note whether it gives a richer status (surveyed, listed for conservation, conservation plan, restored, endangered, מסומן לשימור).
Filter to the council area by coordinate against the bounding window, and ALSO keep entries whose settlement name matches a settlement of Emek Yizrael Regional Council even when they lack coordinates - the settlement list will be at ${ROOT}/data/raw/settlements_emek_yizrael.json once another agent writes it (poll for it a few times while you work; if it never appears, use your own sourced list and say so).
These sites are overwhelmingly post-1700, so they map to the historic-site category. Flag any that are actually pre-1700 antiquities.
Save raw payloads and produce ${ROOT}/data/interim/blue_signs.json .`,
    { label: 'blue signs:council + wikidata', phase: 'Recon', schema: SCHEMA }),

  // 5 - OSM + wikidata sweep
  () => agent(`${COMMON}
YOUR TASK - source_id: osm_wikidata
Build an INDEPENDENT cross-check layer of heritage and culture features in the search window from OpenStreetMap and Wikidata. Its main job is verification: later steps will use it to confirm that sites reported by other sources really exist at the stated place under the stated name.

OpenStreetMap via Overpass API (https://overpass-api.de/api/interpreter, one careful query at a time, and set a sane timeout). Collect nodes, ways and relations in the window with any of: historic=* (archaeological_site, ruins, monument, memorial, castle, tomb, church, city_gate, aqueduct, milestone, building, wayside_shrine), tourism=museum, tourism=artwork, tourism=attraction, tourism=information where information=board or heritage, amenity=library, amenity=arts_centre, amenity=theatre, amenity=community_centre, amenity=place_of_worship, heritage=*, ref:IL:heritage=*, man_made=watermill, man_made=water_well, archaeological_site=*, site_type=*, and boundary=protected_area or leisure=nature_reserve where it wraps a heritage site. Keep every tag, the OSM type and id, and for ways/relations compute a representative point plus the raw geometry.
Wikidata via SPARQL (https://query.wikidata.org/sparql, format=json, descriptive User-Agent). Query items with coordinate location P625 inside a box around the council, and separately items whose located-in-administrative-entity P131 chain reaches the Emek Yizrael Regional Council item (find its QID yourself). For each item capture: label he and en, description, instance of P31, inception P571, heritage designation P1435, IAA or heritage identifiers, Commons image P18, Hebrew Wikipedia sitelink, and coordinates.
Note that OSM tag name:he is our Hebrew label source; record name, name:he, name:en, alt_name, old_name and wikidata/wikipedia tags whenever present.
Save raw payloads and produce ${ROOT}/data/interim/osm_wikidata.json , with a field marking each record as coming from osm or wikidata (or both, if they are linked by a wikidata tag).
Report how many records carry a period/date, how many carry a wikidata QID, and how many carry a Hebrew name - those drive the matching later.`,
    { label: 'osm+wikidata:crosscheck layer', phase: 'Recon', schema: SCHEMA }),

  // 6 - declared antiquity sites
  () => agent(`${COMMON}
YOUR TASK - source_id: declared_antiquities
Obtain the OFFICIAL registration status layer for antiquities: the list and, if possible, the polygons of אתרי עתיקות מוכרזים (declared antiquity sites) under חוק העתיקות התשל"ח-1978, for the search window. This is the authoritative answer to the map's registered / not-registered status for archaeological sites, so accuracy matters more than volume.

Where to look:
- data.gov.il: search the CKAN API for antiquities datasets (עתיקות, אתרי עתיקות, רשות העתיקות) - both package_search and the datastore.
- Israeli government geospatial services: govmap layers for antiquities, and any ArcGIS FeatureServer/MapServer belonging to רשות העתיקות or מרכז למיפוי ישראל that exposes declared-antiquity polygons. Query with f=geojson&outSR=4326 and a spatial envelope.
- The IAA's own site (antiquities.org.il) for the published declaration lists (they were published in רשומות / ילקוט הפרסומים) and for any downloadable table.
- The national planning system: תמ"א and local outline plans mark antiquity sites; the מנהל התכנון / xplan ArcGIS services expose a declared-antiquities layer. Look for it.
Deliverable priorities: for each declared site - the official name, the declaration identifier or gazette reference, the polygon or at least a point, the geographic CRS, and any period attribution.
Also, separately, look for a layer or list of אתרי עתיקות (known antiquity sites that are NOT formally declared) so we can distinguish declared from merely known - that distinction IS the registered status field.
Save raw payloads including any polygon GeoJSON at ${ROOT}/data/raw/ and produce ${ROOT}/data/interim/declared_antiquities.json . If polygons are available, also save them as declared_antiquities.geojson so a later step can test which of our points fall inside a declared area - that is how we will assign the status defensibly.
If you cannot find an authoritative declared-sites layer, say so unambiguously rather than substituting a weaker source, and describe exactly what you tried.`,
    { label: 'IAA:declared antiquity sites', phase: 'Recon', schema: SCHEMA }),

  // 7 - active culture institutions
  () => agent(`${COMMON}
YOUR TASK - source_id: culture_institutions
Compile the ACTIVE culture and arts institutions physically located inside Emek Yizrael Regional Council. Category 3 of the map. Institutions and venues only - never individual artists or people, and never a person's home studio listed under their name.

In scope: museums, visitor centres, heritage centres and archives, libraries, community/culture centres (מתנ"ס, בית תרבות, מרכז קהילתי) where culture programming actually happens, theatres and halls (היכל התרבות, אולם, אמפי), galleries and exhibition spaces, conservatories and music/dance/art schools, artist collectives with a venue, cinemas, cultural festivals with a fixed venue, and rural/agricultural or pioneering heritage museums.
Sources to work through:
- The council's own website (מועצה אזורית עמק יזרעאל) - its culture department, education, community and tourism pages, and any institution directory.
- The Ministry of Culture and Sport recognised-museums list (מוזיאונים מוכרים, under חוק המוזיאונים התשמ"ג-1983) - a museum's presence there is a genuine registration status, so capture it.
- The libraries layer: the Ministry of Culture public-libraries list and the council library network.
- ICOM Israel / the Israeli museums association listing.
- Individual settlement websites and Hebrew Wikipedia articles for the council's settlements (use the settlement list another agent writes to ${ROOT}/data/raw/settlements_emek_yizrael.json ; poll for it, and if absent build your own sourced list).
- Google Maps or OSM only as a lead generator - anything you take from them must be corroborated by a first-party page.
For each institution record: official Hebrew name, English name if any, type, the settlement, street address if any, coordinates (from a first-party source or a geocode you can defend - state which), phone/email/website, opening hours if published, whether it charges admission, whether it is currently ACTIVE (and the evidence: a page updated recently, a current programme, a 2025-2026 event), accessibility for people with disabilities if stated, whether it is a recognised museum or a registered public library, the operating body, and the year founded.
Currently-active status is the single most important field here and the easiest to get wrong. For every institution state your evidence for activity and a confidence level. Anything you cannot corroborate as active goes in with active=unknown and a note; anything you find evidence has CLOSED must be recorded as inactive with the evidence, not dropped silently.
Save raw evidence (fetched pages as text) under ${ROOT}/data/raw/culture_institutions/ and produce ${ROOT}/data/interim/culture_institutions.json . Include a source URL per institution per claim where you can.`,
    { label: 'culture:active institutions', phase: 'Recon', schema: SCHEMA }),

  // 8 - conservation council + parks + protected heritage
  () => agent(`${COMMON}
YOUR TASK - source_id: heritage_official
Compile the official HERITAGE-side layers for the search window - the post-1700 side of the map and its protection statuses.

Work through:
- המועצה לשימור אתרי מורשת בישראל (Council for Conservation of Heritage Sites in Israel): its site list/map for the Jezreel Valley and Lower Galilee area. Look for a searchable database or map with an API. Capture per site: name, settlement, period/year built, site type, conservation status (surveyed, listed, conservation plan approved, restored, in restoration, endangered), whether it holds a blue sign, whether it is open to visitors, and ownership.
- רשות הטבע והגנים (INPA): declared national parks and nature reserves in the window, especially the ones that are heritage/archaeology parks. Find INPA's site list and, if available, the declared-parks GIS layer (an ArcGIS service or data.gov.il resource). Capture: park name, whether it is open to the public, entrance fee, opening hours, accessibility, and the archaeological site it protects.
- קק"ל / JNF heritage and memorial sites in the area, if they have a listing.
- Sites protected through statutory planning: local outline plans marking מבנים לשימור. Check the מנהל התכנון (Planning Administration) open GIS services for a conservation/heritage layer, and note whether one exists for this council.
- The Israeli national heritage programme (מורשת - תוכנית מורשת לאומית) list of funded/marked sites, if a list is published.
- Railway heritage specifically: the Jezreel Valley railway (רכבת העמק) line and its historic stations run through this council. Their stations and structures are prime post-1700 heritage. Identify each station/structure in the window from a citable source.
Candidate leads you must independently verify or drop - do not treat any of these as established: the Beit She'arim necropolis national park, the Zippori national park, Tel Shimron, Tel Yizre'el, the Kfar Yehoshua railway station museum, Sheikh Abreik / the Alexander Zaid monument, Bethlehem of Galilee's German Templer buildings, Nahalal's founding-era layout and buildings. For each, establish whether it exists, its coordinates from a citable source, its period, and CRUCIALLY which local authority's jurisdiction it sits in - several of these are near the border with Kiryat Tiv'on, Migdal HaEmek or Megiddo Regional Council and may not belong to Emek Yizrael at all. Flag jurisdiction uncertainty rather than resolving it by assumption.
Save raw payloads under ${ROOT}/data/raw/ and produce ${ROOT}/data/interim/heritage_official.json .`,
    { label: 'heritage:conservation council + INPA', phase: 'Recon', schema: SCHEMA }),

  // 9 - the two user-supplied tables
  () => agent(`${COMMON}
YOUR TASK - source_id: user_tables
Ingest and profile the two tables the user supplied. These are first-class sources and their column semantics drive the whole harmonization, so profile them exhaustively.

TABLE A - IAA archaeological sites for the Galilee and Valleys cluster, already copied for you to ${ROOT}/data/raw/iaa_galil_amakim_cluster.xlsx (original name: אתרים ארכיאולוגים אשכול גליל ועמקים (1).xlsx). Read it with pandas/openpyxl. Enumerate EVERY sheet, every column, dtype, null count, cardinality, and 5 sample values per column. Work out and document what each column means, including any Hebrew abbreviations and coded values - list the full value set of every categorical column. Identify: the site name column, the site identifier, the coordinate columns and their CRS (check the magnitude: ITM EPSG:2039 has x about 200k and y about 700k; the older ICS EPSG:28193 has y about 230k - getting this wrong shifts everything by hundreds of kilometres, so verify by converting a few rows and checking the resulting lat/lon lands in the Jezreel Valley), the period column, and any status-like column (declaration, survey, excavation, condition, ownership, planning restriction). Convert to WGS84 with pyproj, keeping the originals, and report how many rows fall in the search window.

TABLE B - the IICP culture mapping and points-of-interest table, Google Sheet id 1EuZyJ_gGwtS3SP2Ec5YorsUd51LIDwQwfJ1KxekMA5A . Read it with the gws CLI, which is installed and authenticated (run 'gws --help' and 'gws sheets --help' to find the right subcommand; the user's account is matan@iicp.org.il). Enumerate every tab, not just the first. Profile every column the same way. Determine which rows are culture institutions versus heritage/archaeology points versus something else, which rows refer to individual PEOPLE (those are out of scope and must be marked excluded, not deleted), and which rows are inside or near Emek Yizrael Regional Council. Extract coordinates however they are stored - separate lat/lon columns, a combined string, a Google Maps URL, a plus code, or only an address. Where only an address exists, do NOT geocode by guessing; mark it as needing geocoding.

Deliverables: ${ROOT}/data/interim/iaa_cluster_table.json and ${ROOT}/data/interim/iicp_culture_table.json , plus a single profiling report at ${ROOT}/docs/sources/user_tables.md with a column-by-column data dictionary for both tables in Hebrew (wrapped in an RTL div) and an explicit statement of the CRS evidence for Table A.
In your structured answer, put the union of both tables' field names in field_names, and be precise in status_fields_available and join_keys_available - the harmonization step depends on that.`,
    { label: 'user tables:xlsx + gsheet', phase: 'Recon', schema: SCHEMA }),
]

const results = (await parallel(tasks)).filter(Boolean)

log(`Recon complete: ${results.length}/9 agents returned`)
for (const r of results) {
  log(`${r.source_id}: ${r.status}, ${r.record_count} records`)
}

return {
  agents_returned: results.length,
  by_source: results.map(r => ({
    source_id: r.source_id,
    status: r.status,
    record_count: r.record_count,
    native_crs: r.native_crs,
    endpoints: r.endpoints,
    field_names: r.field_names,
    status_fields_available: r.status_fields_available,
    join_keys_available: r.join_keys_available,
    files_written: r.files_written,
    caveats: r.caveats,
    leads_for_others: r.leads_for_others,
    summary: r.summary,
  })),
}
