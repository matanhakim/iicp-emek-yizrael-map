# Source: `heritage_official`

Official heritage-side layers for the Emek Yizrael map: the post-1700 register of the
Council for Conservation of Heritage Sites, the statutory conservation layer of the
Planning Administration, the national-park / nature-reserve designations, KKL-JNF, the
national heritage programme, and Valley Railway heritage.

- **Agent:** `heritage_official`
- **Retrieval date:** 2026-08-03 (all timestamps in this document refer to that day)
- **Search window:** WGS84 lat 32.55-32.85, lon 35.05-35.50; ITM (EPSG:2039) envelope
  `198000,710000,245000,750000`
- **User-Agent used for every request:**
  `IICP-EmekYizraelMap/1.0 (cultural heritage mapping research; matan@iicp.org.il)`
- **Rate:** one request at a time, ~1.1 s between requests, no parallel fetching.
- **Raw payloads:** `data/raw/heritage_official/` (~110 MB; see the inventory at the end)
- **Per-record output:** `data/interim/heritage_official.json` - 3,207 flat objects, 153 distinct field names

> A note on TLS: `curl` had to be run with `--ssl-no-revoke` because Windows schannel
> could not reach the CRL responders (`CRYPT_E_NO_REVOCATION_CHECK`). Python's OpenSSL
> cannot complete a TLS handshake with `ags.iplan.gov.il` at all
> (`UNEXPECTED_EOF_WHILE_READING`), so every Planning Administration request was issued
> through `curl`. Neither is a certificate-validation bypass of the peer identity.

---

## 1. Council for Conservation of Heritage Sites in Israel (`shimur.org`)

The Council is the body whose remit is post-1700 built heritage. Its own site description
states the reason it was founded in 1984: the Antiquities Law then applied only to things
built before 1700.

### 1.1 How the data was found

`https://shimur.org/wp-json/` is open (WordPress REST API, 2.5 MB route index). It exposes
**no** custom post type for sites - `wp/v2/types` returns only `post`, `page`, `attachment`,
`product`, `mailpoet_email` and the block/template types. The sites are therefore not
reachable through `wp-json`.

The site's own map is rendered server-side. `https://shimur.org/wp-content/themes/shimur/js/cfmap.js`
reads `.marker` elements out of the page HTML and their `data-lat` / `data-lng` attributes,
so **the whole national dataset is embedded in the HTML of `https://shimur.org/sites/`**
(2.1 MB, 879 markers). No `admin-ajax` action serves the sites; the eight `admin-ajax`
references on the page all belong to WooCommerce.

`https://shimur.org/robots.txt` disallows only WooCommerce and `wp-admin` paths and
contains an explicit `User-agent: * / Disallow:` (allow-all) Yoast block.

### 1.2 Endpoints used

| URL | What it is | Raw file |
|---|---|---|
| `https://shimur.org/wp-json/` | REST route index (used to rule out an API) | `shimur_wpjson_root.json` |
| `https://shimur.org/wp-json/wp/v2/types` | registered post types | `shimur_types.json` |
| `https://shimur.org/sites/` | **the dataset** - 879 map markers | `shimur_sites_page.html` |
| `https://shimur.org/wp-content/themes/shimur/js/cfmap.js` | proves markers carry the coordinates | `shimur_cfmap.js` |
| `https://shimur.org/sitemap_index.xml` | post-type inventory | `shimur_sitemap_index.xml` |
| `https://shimur.org/page-sitemap.xml` | page inventory (found the Kfar Yehoshua audio-tour pages) | `shimur_page_sitemap.xml` |
| `https://shimur.org/hbuildings/` | archive of "מבנים לשימור" | `shimur_archive_hbuildings.html` |
| `https://shimur.org/sitesgefen/` , `https://shimur.org/adopt/` | other post types, checked and rejected | `shimur_archive_*.html` |
| `https://shimur.org/{sites,signs}/<slug>/` | 51 detail pages for the in-window markers + `/sites/rakevet-haemek/` | `shimur_detail/*.html` (52 files) |

### 1.3 Marker schema (from `/sites/` HTML)

Each marker is `<div class="marker" data-id data-type data-lat data-lng data-icon>` wrapping
an info box.

| field | meaning | units / CRS |
|---|---|---|
| `data-id` | WordPress post ID | integer |
| `data-type` | `sites` (אתרי מורשת, blue pin) or `signs` (שלטים, red pin) | enum |
| `data-lat`, `data-lng` | marker position | **WGS84 decimal degrees (EPSG:4326)** |
| `<h3>` | site name | Hebrew text |
| info-box `<li>` label/value pairs | `מיקום`, `טלפון`, `דוא“ל`, `שפות הדרכה` | Hebrew text |
| `<a href>` | canonical site/sign URL | URL |

**Counts:** 879 markers total - `signs` 709, `sites` 170. Zero markers of the third UI
option `hbuildings` (מבנים לשימור): the `<select>` on the page offers it, but
`https://shimur.org/hbuildings/` is an empty post-type archive and there is no
`hbuildings-sitemap.xml`. **The Council publishes no "buildings for conservation" list
through this site.**

**In the search window: 51 markers (27 `signs`, 24 `sites`).** One further site
(`/sites/rakevet-haemek/`, "אתר רכבת העמק כפר יהושע") is linked from the main navigation but
carries no map marker, so it is *not* in the 170; it was fetched separately, giving 52
records. One of the 24 in-window `sites` URLs 404s (post id 342, "בית גרושקביץ" in
קריית מוצקין) - recorded with `site_is_404: true`.

Two markers elsewhere in the country have malformed coordinates (`31.671870N,34.594396E`
and `33, 1' 17.330400,35, 34' 40.866500`); both are outside the window. The parser keeps
`lat_raw`/`lng_raw` verbatim and takes the leading numeric run for `lat`/`lon`.

### 1.4 Blue-sign detail schema - the most useful part

A `signs` detail page carries an icon-labelled list. Parsed by icon id, with the first item
by position:

| output field | source | example |
|---|---|---|
| `sign_place` | first list item (map-pin icon) | `אתר כפר יהושע` |
| `sign_local_authority` | list item with `<g id="home">` | **`מועצה אזורית עמק יזרעאל`** |
| `sign_year_erected` | list item matching `^\d{4}$` | `2008` |
| `sign_address` | remaining unmatched list item | `יבנאל, בית גן, יבנאל, 1522500` |
| `sign_languages` | icon `clarity:language-line` | `עברית` |
| `sign_type` | icon `teenyicons:sign-outline` | `שלט על רגל` / `שלט תלוי` |
| `shimur_text` | the sign's narrative text | Hebrew prose |

`sign_local_authority` is the single most valuable field in this source: **the Council
states the local authority for every blue sign**, which resolves the jurisdiction question
from the source itself rather than by inference. Of the 27 in-window signs, **11 carry
`מועצה אזורית עמק יזרעאל`**; the rest are attributed to מועצה אזורית זבולון,
מועצה אזורית הגליל התחתון, מועצה אזורית הגלבוע, עיריית יקנעם, מועצה מקומית יבנאל and
מועצה מקומית כפר כמא.

`sign_year_erected` is missing (null) on 5 of the 27 - the field is genuinely absent on
those pages, not dropped by the parser.

### 1.5 Heritage-site detail schema

| output field | source label on page |
|---|---|
| `site_opening_hours__א‘ - ה‘`, `__ו‘ וערבי חג`, `__שבתות וחגים`, `__הערות` | the opening-hours block |
| `site_languages` | `שפות הדרכה` |
| `site_suitable_kids_3_10` | `מתאים לילדים בגיל 10-3` |
| `site_phone`, `site_email` | `טלפון`, `דוא''ל` |
| `site_notes` | `הערות` |
| `site_official_url` | the `לאתר הרשמי` link |
| `site_entry_fee_raw` | text following `דמי הכניסה` (verbatim, un-normalised) |
| `site_accessibility_mentioned` | boolean: does the narrative mention הנגשה / נגישות |
| `shimur_info_block__*` | every label/value pair found, unfiltered |

**What this source does NOT carry.** There is no structured field anywhere on
`shimur.org` for: period or year built, conservation status (surveyed / listed /
conservation plan approved / restored / in restoration / endangered), or ownership.
Those items of the task specification **cannot be filled from this source**; they appear
only as free prose inside `shimur_text`, if at all. Entry fees exist for exactly one
in-window site (the Kfar Yehoshua railway site).

---

## 2. Statutory planning - Planning Administration conservation layer

**This layer exists and covers this council.** It is the answer to "local outline plans
marking מבנים לשימור".

- Service root: `https://ags.iplan.gov.il/arcgisiplan/rest/services?f=json`
  (note the path is `/arcgisiplan/`, **not** `/arcgis/`, which returns a gov.il error page)
- Folder: `PlanningPublic` (47 services)
- Service: **`PlanningPublic/Shimour/MapServer`** - `currentVersion` 10.81, spatial
  reference `wkid 2039` (ITM), `maxRecordCount` 1000, no copyright text, no service
  description.

| layer | name | geometry |
|---|---|---|
| 0 | `שימור` | Group Layer |
| 1 | `ישויות נקודתיות` | `esriGeometryPoint` |
| 2 | `ישויות פוליגונליות` | `esriGeometryPolygon` |

### 2.1 Field schema (identical on both layers except geometry-derived fields)

| field | alias | type | meaning |
|---|---|---|---|
| `objectid` | ESRI Object ID | OID | |
| `group_id` | מזהה קבוצת שכבות | int | layer-group id |
| `layer_id` | מזהה שכבה | int | layer id |
| `mavat_code` | קוד מבא"ת | int | code of the standard planning entity |
| `mavat_name` | שם מבא"ת | string(50) | **the designation**, e.g. `בלוק מבנה לשימור`, `מבנה לשימור`, `אתר/מתחם לשימור`, `אתר ארכיאולוגי לשימור`, `שטח עתיקות/הסטורי לשימור`, `שימור נופי`, `בלוק אנדרטה` |
| `mp_id` | מזהה תכנית ראשי | double | master plan id |
| `pl_id` | מספר מהדורה | double | plan edition id |
| `pl_name` | שם התכנית | string(78) | plan name - **the only name any feature has** |
| `pl_number` | מספר תכנית | string(78) | plan number, e.g. `204-0256354` |
| `pl_order_print_version`, `pl_tasrit_prn_version` | גירסת הוראות / תשריט | double | |
| `station` | קוד סטטוס | double | status code, e.g. 3010 |
| `station_desc` | סטטוס | string(26) | **the statutory status**: `אישור`, `הפקדה להתנגדויות/השגות`, `במילוי תנאים להפקדה`, `בהליך אישור`, `בבדיקה תכנונית`, `הכרעה בהתנגדויות / אישור`, `רשת חלוקה`, `תסקיר סביבתי` |
| `last_update_date` | תאריך עדכון אחרון | date | epoch milliseconds |
| `rotation` | זווית ציור | double | layer 1 only |
| `shape_area`, `shape_length` | שטח / אורך מחושב | double | layer 2 only, m² and m |

### 2.2 Query used

```
GET https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Shimour/MapServer/{1,2}/query
    where=1=1
    geometry=198000,710000,245000,750000
    geometryType=esriGeometryEnvelope
    inSR=2039
    spatialRel=esriSpatialRelIntersects
    outFields=*
    returnGeometry=true
    outSR=2039
    f=json
    resultOffset=<0,1000,2000>
    resultRecordCount=1000
```

**Counts in the window: layer 1 = 751 points, layer 2 = 2,224 polygons** (layer 2 needed
three pages). Composition (`mavat_name` × `station_desc`) is in
`iplan_Shimour_L1_stats.json` / `iplan_Shimour_L2_stats.json`; the largest groups are
`בלוק מבנה לשימור`/`אישור` (396 points) and `אתר עתיקות/אתר הסטורי`/`אישור` (897 polygons).

### 2.3 The critical limitation of this layer

**No feature has a site name.** The only textual identity is the plan it belongs to, and
one plan generates dozens of identical blocks (e.g. 31 `בלוק מבנה לשימור` points around
בית לחם הגלילית all belong to plan `ג/23860`). This layer is therefore **a status overlay,
not a list of sites**: use it to answer "is this location marked for conservation, in
which plan, at what statutory stage", and never as a source of names or counts of
distinct sites. Records are typed `iplan_conservation_point` / `iplan_conservation_polygon`
with `site_name: null` and a `site_name_note` saying exactly this.

---

## 3. National parks and nature reserves

### 3.1 INPA's own site is blocked - reported, not evaded

`https://www.parks.org.il/...` returns **HTTP 403 from CloudFront** ("Request blocked")
for both `curl` with a descriptive User-Agent and for `WebFetch`. Two URLs were tried
(`/article/npa/` = אתרים מוכרזים, and the reserves-and-parks list page); both blocked.
Raw bodies kept as `inpa_reserves_list.html`, `inpa_govmap2.html`. **No attempt was made
to rotate User-Agents or otherwise get around the block.** Consequence: **visitor
information for INPA parks - open to the public, entrance fee, opening hours,
accessibility, and which archaeological site each park protects - is NOT in this dataset.**
Those fields are `null` throughout and must be obtained another way (a human visiting
parks.org.il, or a formal data request to INPA).

### 3.2 GovMap's own API needs a key

`https://www.govmap.gov.il/` is a Vite SPA; its bundle
(`/assets/index-df773dd4.js`, 10 MB, kept as `govmap_bundle.js`) names
`https://api.govmap.gov.il` with an auth path `/layers-catalog/api/auth` and docs at
`https://api.govmap.gov.il/docs/intro`. Unauthenticated calls to
`api.govmap.gov.il/layers-catalog/api/{layers,catalog}` return
`403 AccessDenied`. The INPA layers referenced in public GovMap links
(`lay=150` אתרי רשות הטבע והגנים, `lay=442` אתרי המורשת הלאומית, `RES_PARKS_MEFORAT`)
are therefore **not retrievable without a GovMap API key**. Getting one is a human action.

### 3.3 `data.gov.il` has nothing

CKAN `package_search` for `גנים לאומיים`, `שמורות`, `טבע`, `parks`, `גן` returns only
unrelated municipal datasets (`nature-reservesmaaleadumim`, `urban-nature-br7`,
`park_n_ride`, ...). **No national parks / nature reserves dataset is published on
data.gov.il.** Raw: `datagov_search_parks.json`, `agol_search_parks.json`.

### 3.4 A third-party ArcGIS Online copy exists but is unusable

`https://services6.arcgis.com/fYVNvQPRN8L3SXKg/arcgis/rest/services/Respark_meforat_24jul23/FeatureServer/0`
- titled "Israel national parks and nature reserves", `serviceDescription`
"Israel National Nature and Park Reserves", owner `moshe.tom` in the Israel
Oceanographic and Limnological Research (IsraMarBio) ArcGIS Online organisation. Fields
`PARK_ENG_N`, `PLAN_NUMBE`, `PARK_TYPE_`, `STATUS_DES`, `Area`; SR 2039.
**Rejected:** total feature count is 88 for the entire country and the layer extent stops
at `xmax 210853`; an envelope query over the window returns **0 features**. It is a
partial snapshot dated 24 Jul 2023, republished by a third party. Raw kept
(`agol_respark_*.json`) for the record.

### 3.5 What WAS obtained: the Planning Administration TMM compilations

This is the best official, machine-readable, **named** source for parks and reserves
available without a key.

**North district** -
`PlanningPublic/compilation_tmm_tzafonn/MapServer/8` (`ייעודי קרקע`, polygons, SR 2039).

Fields: `OBJECTID`, `ET_ID`, `FID_שכב`, `NAME`, `NAMEL`, `REGISHUT`, `SET_CODE`,
`SOURCE`, `UPDATE_`, `AREA`, `X_Center`, `Y_Center`, `TYPE_CODE`, `TYPE_NAME`,
`PL_CHANGE`, `REMARKS`, `AREA_SQM`, `DUNAM`, `Shape_Leng`, `Shape_Le_1`,
`Shape_Length`, `Shape_Area`.

`TYPE_CODE` values queried (from the layer's own renderer legend):
`852 = גן לאומי`, `853 = שמורת טבע`, `851 = שמורת נוף`, `730 = פארק טבע ותיירות`.
`SOURCE` names the plan that created the designation (`תמ''מ 2/9`, `תמ"א 8`,
`תממ/ 2/ 9/ 29`, ...). `X_Center` / `Y_Center` are **centroids supplied by the source**,
in ITM.

Result: **71 features**, of which 69 are named and 2 are empty artefacts with
`NAME=''` and `X_Center=Y_Center=0` (kept, coordinates fell back to the ring centroid).
Named parks and reserves in the window include גן לאומי בית שערים (1,242 dunam),
גן לאומי ציפורי (ריש לקיש) (13,588), ציפורי - תל חנתון, ציפורי - חירבת רומ,
גן לאומי שימרון (2,641) + שמורת טבע שימרון (285), גן לאומי תל מגידו (292),
גן לאומי מעין חרוד (1,794), גן לאומי הר תבור (3,676), גן לאומי נחל ציפורי,
גן לאומי + שמורת טבע גוש אלונים, יפתחאל, שמורת טבע בלפוריה, שמורת טבע הגלבוע (37,018).

**Haifa district** - `PlanningPublic/compilation_tmm_haifa/MapServer/7` (`יעודי קרקע`).
Different schema: `OBJECTID`, `TYPE_CODE`, `area_m2`, `YK`, `label`, `name`,
`plan_name`, `Shape_Length`, `Shape_Area`; **no centroid fields**, so centroids here are
derived by this agent. `TYPE_CODE` legend: `12 = גן לאומי`, `13 = גן לאומי שנוסף בתכנית זו`,
`32 = שמורה שנוספה בתכנית זו`, `33 = שמורת טבע`, `34 = שמורת נוף`,
`27 = פארק מטרופוליני`, `28 = פארק תיירות`. Result: **89 features**.
Note: layer numbering differs between the two services (8 vs 7) - querying layer 8 on the
Haifa service returns `{"code":400,"message":"Invalid or missing input parameters."}`.

**Status semantics - read this before using the word "declared".**
`tmm_park_or_reserve` records carry
`statutory_status = "land-use designation in the district/national outline-plan
compilation; NOT a declaration under the National Parks and Nature Reserves Law"`.
A TMM land-use designation and a formal הכרזה are different legal acts. This dataset
**cannot** tell you whether a park is *declared*. Do not label these "declared national
parks" on the map.

---

## 4. Jurisdiction - resolved from the official boundary layer, not by inference

`https://open.govmap.gov.il/geoserver/opendata/wfs` is an open OGC WFS 2.0 with **7**
feature types: `Nikuz` (אגני ניקוז), `SUB_GUSH_ALL` / `SUB_GUSH_ALL_ITM` (גושים),
`PARCEL_ALL` / `Parcels_ITM` (חלקות), `nechalim1` (נחלים), and **`muni_il`
(רשויות מוניציפאליות)**. The wider `/geoserver/wfs` (all workspaces) 404s - only the
`opendata` workspace is exposed.

```
GET https://open.govmap.gov.il/geoserver/opendata/wfs
    service=wfs&version=2.0.0&request=GetFeature
    typeNames=opendata:muni_il
    outputFormat=application/json
    srsName=EPSG:4326
    CQL_FILTER=BBOX(the_geom,35.05,32.55,35.50,32.85,'EPSG:4326')
```

`numberMatched = numberReturned = 99` (no truncation). `muni_il` attributes:
`Muni_Heb`, `Muni_Eng`, `Sug_Muni` (עירייה / מועצה מקומית / מועצה אזורית / ללא שיפוט),
`CR_PNIM`, `CR_LAMAS`, `Machoz`, `Hearot`, `Eshkol_MPn`, `Sign_Date`, `Tikun1`-`Tikun15`,
`Precision`, `FIRST_Nafa`, `LAST_Nafa2`, `Shape_Leng`, `Shape_Area`. Geometry is
`MultiSurface`, returned as 3-ordinate GeoJSON (`x,y,0`); the Z is dropped.
**`עמק יזרעאל` appears as three separate MultiPolygon features** - the council's
jurisdiction is fragmented, so a single-polygon assumption would be wrong.

Every record with a coordinate was tested point-in-polygon against this layer and given:

| field | meaning |
|---|---|
| `jurisdiction_muni_heb`, `jurisdiction_sug_muni`, `jurisdiction_machoz` | the containing authority |
| `jurisdiction_distance_to_boundary_m` | metres from the point to the containing polygon's boundary, measured in ITM |
| `jurisdiction_uncertain` | `true` when that distance is < 250 m, or no polygon contains the point, or there is no coordinate |
| `jurisdiction_note` | why it is uncertain |
| `jurisdiction_nearest_muni_heb`, `jurisdiction_nearest_distance_m` | context only, for points inside no polygon - **not** asserted as the jurisdiction |
| `jurisdiction_source` | `govmap open data WFS opendata:muni_il ..., retrieved 2026-08-03` |

**Independent validation of the method.** The 27 in-window blue signs are the one case
where the source states the authority itself (`sign_local_authority`) *and* a coordinate
exists, so the two can be compared. They agree on **26 of 27**, and both methods
independently return **exactly 11 signs in מועצה אזורית עמק יזרעאל**. The single
disagreement is `נתיב המעפילים` at יגור: the Council attributes it to
מועצה אזורית זבולון while its (address-geocoded) marker lands inside the unincorporated
`ללא שיפוט - אזור הר הכרמל` polygon, 732 m from the nearest boundary - a marker-placement
error, not a boundary-layer error.

**Result: 429 of 3,207 records fall inside `עמק יזרעאל`** (279 conservation polygons,
103 conservation points, 21 parks/reserves, 11 blue signs, 7 heritage sites,
7 candidate-lead checks, 1 KKL site). 937 records are flagged
`jurisdiction_uncertain`; 231 of those fall inside no polygon at all - **all 231 are
polygon centroids that lie outside the search window** (see §7).

---

## 5. KKL-JNF

`https://www.kkl.org.il/robots.txt` allows all crawlers except three AI-training agents
(Applebot-Extended, Bytespider) and disallows only search/account paths. Sitemap index:
`https://www.kkl.org.il/sitemap-he.xml` - **27 sub-sitemaps, and none of them is a
heritage- or memorial-sites sitemap.** The relevant ones are
`sitemap-travel-parks-and-forests.xml` (113 URLs), `sitemap-travel-scenic-lookouts.xml`
(105) and `sitemap-recreation-areas.xml` (2).

**Finding: KKL-JNF publishes no heritage-sites or memorial-sites register.** What it
publishes is forests, parks, scenic lookouts and picnic areas. Many lookouts are
memorials named after individuals, which the map excludes by definition.

164 leaf pages were fetched (blog, article, campaign and newsletter URLs excluded). Each
page carries four `application/ld+json` blocks; the fourth has a `@graph` containing a
`["TouristAttraction","Park"]` node with:

| JSON-LD field | output field |
|---|---|
| `name` | `jsonld_name` / `site_name` |
| `geo.latitude`, `geo.longitude` | `lat`, `lon` (WGS84) |
| `publicAccess` | `open_to_public` |
| `isAccessibleForFree` | `free_entry` |
| `address.addressRegion` | `addressRegion` |
| `additionalProperty[]` | `additionalProperty_שטח`, `_אזור גיאוגרפי`, `_עונה מומלצת`, `_כלבים מותרים` |

**6 pages fall in the window:** `beit_keshet_forest` (יער בית קשת), `kkl_nahasho`
(פארק נחל השופט), `kkl_ramatmena` (פארק רמת מנשה), `turaan_road` (דרך נוף הר תורען),
`zipori_forests` (טחנת הנזירים ויערות ציפורי), `scenic_lookout_tavor` (מצפור הר תבור).
Only one, `zipori_forests`, lands in עמק יזרעאל.

Two data quirks recorded verbatim: many KKL `name` values carry a stray leading `י`
(`ייער בית קשת`, `יטחנת הנזירים...`), and `kkl_nahasho` and `kkl_ramatmena` publish the
**identical** coordinate `32.59798323622 / 35.122259638619`, so at least one of the two is
wrong at source.

**Deviation from the raw-payload rule, declared:** each KKL page is ~650 KB, so full HTML
was kept only for the 8 pages fetched into the window (`data/raw/heritage_official/kkl/`).
For all 164 pages, `kkl_travel_index.json` records the URL, HTTP status, byte length,
**SHA-256 of the exact body**, `<title>`, the extracted JSON-LD fields, and - for
in-window pages - the JSON-LD blocks verbatim. Keeping all 164 bodies would have added
~140 MB to the repository.

---

## 6. The national heritage programme (מורשת / תמ"ר / ציוני דרך)

Source: Knesset Research and Information Center, **"אתרי מורשת לאומיים"**, 2023, 46 pp.
(`knesset_mmm_national_heritage_sites.pdf`, retrieved from
`https://fs.knesset.gov.il/globaldocs/MMM/cc425b38-d9a6-ed11-8152-005056aac6c3/2_cc425b38-d9a6-ed11-8152-005056aac6c3_11_20113.pdf`).

**There is no published list of funded מורשת sites.** The Knesset paper says so
explicitly (p. 16, PDF p. 18): the Ministry of Heritage "מפרסם מעת לעת באתר ציוני דרך
מידע על מיזמים בביצוע או מיזמים בולטים, אולם זו אינה רשימה מלאה של מיזמי המורשת שבהם
המשרד משקיע. לא ברור מדוע רשימה מלאה מעין זו אינה מתפרסמת באופן סדיר ופומבי."
The same paper (p. 2, PDF p. 4) records that Israel has **no heritage-sites inventory at
all** ("אין רשימת מצאי (אינוונטר) של אתרי מורשת"). Scale, for context: מורשת א' funded
>100 projects, מורשת ב' ~120, מורשת ג' has a ~600 M NIS envelope. **This item of the task
cannot be completed from public sources; it is a genuine gap, not a search failure.**

Two things the paper *does* give, and that are used here:

1. **Table 1, p. 7 (PDF p. 9) - all 18 אתרים לאומיים מוכרזים** (declared national sites
   under the law), with location, declaration year and manager. **None of the 18 is inside
   the search window** - the nearest are חוות כנרת (1984) and מחנה המעפילים עתלית (1985).
   Every `candidate_lead_check` record therefore carries
   `declared_national_site_under_law: false`. Footnote 16 of the paper cites a
   Survey of Israel (מרכז למיפוי ישראל) GIS layer "אתרים לאומיים" - **a lead worth chasing**,
   not retrieved here.
2. **p. 12 (PDF p. 14)** - the visitor sites the Council itself operates. Two are in this
   window: **מרכז מבקרים תחנת רכבת העמק כפר יהושע** and **משטרת נהלל ההיסטורית**.
3. **p. 44 (PDF p. 46)** - Israel's UNESCO World Heritage sites, including
   **אתרי הקבורה בבית שערים** and התלים המקראיים (מגידו, חצור, באר שבע).

The statutory hook for local conservation lists is also stated there (p. 2): the Fourth
Schedule to the Planning and Building Law obliges every local authority to set up a
conservation committee and keep a register of buildings for conservation - but the State
Comptroller found those registers too easily amended to be an effective instrument. **No
Emek Yizrael conservation-committee register was found published anywhere.**

Hebrew Wikipedia's `אתר מורשת לאומית (ישראל)` (`wikipedia_national_heritage_site_he.json`)
lists **רכבת העמק** among the 62 "מורשת ההתיישבות הבנויה" sites of the תמ"ר outline - a
secondary source, recorded as such.

---

## 7. Valley Railway (רכבת העמק)

Sources used: `shimur.org` (Council), the Knesset paper above, and Hebrew Wikipedia
`רכבת העמק` + per-station articles (`wikipedia_rakevet_haemek_he.json`,
`wikipedia_coords_candidates*.json`).

**Kfar Yehoshua / Tel a-Shammam station is the anchor.** The Council runs it as a visitor
centre and it is the one place in the window with a full, citable heritage picture:

- 6 Council blue signs, every one recording `רשות מקומית = מועצה אזורית עמק יזרעאל`:
  `מסילת הברזל ההיסטורית של רכבת העמק תחנת הרכבת תל-שמאם כפר יהושע` (2008, שלט על רגל),
  `הבניין המרכזי` (2008), `בית הטלפונאי` (2008), `בית הבומבאג'י` (2008),
  `הבניין לסגן מנהל התחנה` (year absent), `בניין עובדי המסילה` (year absent).
- Opening hours א'-ה' 09:00-15:00, ו' וערבי חג 10:00-13:00; entry 21 / 16 / 16 NIS
  (adult / child / senior); guiding in Hebrew, English, Arabic; accessibility provisions
  described; guided tours by prior arrangement - all from `/sites/rakevet-haemek/`.
- `shimur.org/page-sitemap.xml` reveals a full trilingual audio-tour page set for the
  compound (`/kfar-yehoshua-station-tel-a-shamam/`, `/the-water-tower-building/`,
  `/eastern-part-bombadge-house/`, `/the-line-house/`, plus Hebrew `-heb` and Arabic
  variants), i.e. the Council documents the individual structures.
- The 2008 sign credits the restoration to the Council with
  משרד המדע התרבות והספורט, קרן קיימת לישראל, הנהלת רכבת ישראל,
  מועצה אזורית עמק יזרעאל and הנהלת כפר יהושע.

**Coordinate conflict, unresolved on purpose.** he.wikipedia `תחנת הרכבת כפר יהושע`
(Q6372216) gives 32.671861 / 35.1528. All six shimur markers give
32.6821545 / 35.1612176, which is effectively the coordinate of the village כפר יהושע
itself (32.68216244 / 35.15241026, Q2889616) - the shimur marker is address-geocoded.
The two are ~1 km apart. Both are recorded; neither is presented as surveyed.

**Other stations in the window**, with what is and is not known:

| station | status | coordinate | note |
|---|---|---|---|
| תל א-שמאם / כפר יהושע | visitor centre, conserved | 32.671861 / 35.1528 (Wikipedia) | **עמק יזרעאל**, 1,195 m inside, by point-in-polygon |
| אלרואי | shimur heritage site `רכבת העמק אלרואי`; rolling stock on display | 32.71361207 / 35.10221045 (Wikipedia, Q123550952) | **קרית טבעון**, 267 m inside - **not Emek Yizrael**; the shimur address text agrees ("ברק בן אבינועם, קרית טבעון") |
| קריית חרושת | brick building survives inside "פארק הקטר" (Wikipedia) | **only the settlement centroid 32.6925 / 35.1095 is known** | **קרית טבעון**, 167 m - flagged uncertain. No citable coordinate for the building; do not present the settlement point as the station |
| כפר ברוך | **nothing remains** - "כיום לא נשאר ממנה דבר" (Wikipedia) | none | `exists: false`. Do not place a marker |
| עפולה (הישנה) | historic station | 32.6106 / 35.2903 (Wikipedia, Q6971074) | **עפולה** city, 1,253 m inside - outside Emek Yizrael RC |

**A CRS trap in the Wikipedia article, deliberately not resolved.** The article gives
`נ.צ.` for stations 1-16 and states the grid is `רשת ישראל הישנה` (ICS). The strings are
of the form `150887-1246325`: the easting matches ICS for Haifa East station exactly
(150887), but the northing is 7 digits beginning with `1` where ICS would be ~246325.
The pattern is consistent across all 16. **These values were NOT converted and are NOT in
the output** - the northing's leading digit has no verified interpretation, and guessing
it would be fabrication. Stations 17-48 (the ones in this window) carry no `נ.צ.` at all.

---

## 8. Candidate leads - verdicts

14 `candidate_lead_check` records. Every jurisdiction below comes from point-in-polygon
against `muni_il`, not from a name.

| lead | exists | period | category | jurisdiction (muni_il), distance to boundary |
|---|---|---|---|---|
| Beit She'arim necropolis NP | yes | Roman-Byzantine | **archaeological (pre-1700)** | **AMBIGUOUS - see note below** |
| Zippori NP | yes | Roman-Byzantine | **archaeological** | **עמק יזרעאל** (from the TMM park centroid; the lead record itself has no coordinate) |
| Tel Shimron | yes | Bronze-Roman tell | **archaeological** | **עמק יזרעאל**, 1,221 m inside |
| Tel Yizre'el | yes | Iron Age tell | **archaeological** | **הגלבוע** (Gilboa RC), 2,105 m inside - **NOT Emek Yizrael** |
| Kfar Yehoshua station museum | yes | 1904-05 / 2008 | historic + active institution | **עמק יזרעאל**, 1,195 m inside |
| Sheikh Abreik | yes | ancient hill (= Beit She'arim) | archaeological | **עמק יזרעאל**, 255 m inside - marginal |
| Alexander Zaid monument | yes | 20th c. | **historic (post-1700)** | **עמק יזרעאל**, but only **26 m** from the boundary - flagged uncertain |
| Bethlehem of Galilee Templer buildings | yes | colony founded 1906 | **historic** | **עמק יזרעאל**, 2,701 m inside |
| Nahalal founding-era layout | yes | founded 1921 | **historic** | **עמק יזרעאל**, 1,762 m inside |
| (added) משטרת נהלל ההיסטורית | yes | Mandate | historic + visitor site | **עמק יזרעאל**, 2,884 m inside |
| (added) תחנת הרכבת אלרואי | yes | Mandate | historic | **קרית טבעון** (local council), 267 m inside - **NOT Emek Yizrael** |
| (added) תחנת קריית חרושת | yes | Mandate | historic | **קרית טבעון**, 167 m - flagged uncertain; and the coordinate is the settlement, not the building |
| (added) תחנת כפר ברוך | **no** | 1926 | - | no coordinate, no marker possible |
| (added) תחנת עפולה ההיסטורית | yes | 1905 | historic | **עפולה** (city), 1,253 m inside - **NOT Emek Yizrael** |

Corrections worth flagging to the harmonizer:

- **Beit She'arim sits ON the Emek Yizrael / Kiryat Tiv'on line and its jurisdiction is
  genuinely ambiguous.** The two available coordinates disagree: the he.wikipedia point
  `32.70333 / 35.12917` falls inside **קרית טבעון**, **8.4 m** from the boundary; the
  Planning Administration `גן לאומי בית שערים` centroid (`212301.72 / 733824.50` ITM)
  falls inside **עמק יזרעאל**. The site also appears in *both* the North and the Haifa
  district TMM compilations - the Haifa-sheet copy's centroid likewise falls in
  **קרית טבעון**. **Do not assign this site to either authority on the strength of one
  point.** The same caution applies to שייח' אבריק (255 m) and to the Alexander Zaid
  monument (26 m), which are on the same hill.
- **Statutory conservation status differs sharply between the two Templer/pioneer villages.**
  בית לחם הגלילית has 31+ `בלוק מבנה לשימור` points from **approved** plan `ג/23860`
  (`station_desc = אישור`); נהלל has 12 from plan `ג/28808`, which is only
  `בבדיקה תכנונית` - not yet approved. Do not describe Nahalal's buildings as protected by
  an approved plan.
- **The Kfar Yehoshua station compound has NO feature in the statutory conservation layer
  within 800 m**, despite being the Council's flagship site here. Conservation by the
  Council and conservation by a plan are independent facts; the map should not conflate them.

---

## 9. Status fields available, by record type

| record type | status fields |
|---|---|
| `shimur_blue_sign` | `holds_blue_sign` (always true), `sign_year_erected`, `sign_type`, `sign_local_authority` |
| `shimur_heritage_site` | `site_opening_hours__*`, `site_entry_fee_raw`, `site_languages`, `site_suitable_kids_3_10`, `site_accessibility_mentioned`, `site_official_url`, `site_is_404` |
| `iplan_conservation_point` / `_polygon` | **`statutory_status` (= `station_desc`)**, `statutory_designation` (= `mavat_name`), `pl_number`, `pl_name`, `last_update_date` |
| `tmm_park_or_reserve` | `designation_type`, `statutory_status` (fixed disclaimer string), `statutory_plan_source`, `DUNAM` / `area_m2` |
| `kkl_travel_site` | `open_to_public`, `free_entry`, `additionalProperty_*` |
| `candidate_lead_check` | `exists`, `declared_national_site_under_law`, `unesco_world_heritage`, `open_to_visitors`, `opening_hours`, `entrance_fee`, `accessibility`, `council_blue_sign` |
| all | `jurisdiction_*`, `point_in_search_window`, `geometry_intersects_search_window` |

**Statuses that are NOT available anywhere in this source** and must not be invented:
surveyed / listed / conservation-plan-approved / restored / in-restoration / endangered as
a per-site Council status; ownership; period or year built as a structured field; INPA
visitor information of any kind.

## 10. Coordinates and CRS - what is native and what is derived

| record type | native CRS | how `lat`/`lon` were produced |
|---|---|---|
| `shimur_*` | WGS84 (EPSG:4326) | taken as given; `lat_raw`/`lng_raw` kept verbatim. **Address-geocoded by shimur.org, not surveyed.** |
| `iplan_conservation_point` | ITM (EPSG:2039) | `itm_x`/`itm_y` as served, converted with pyproj 3.7.2 |
| `iplan_conservation_polygon` | ITM (EPSG:2039) | **derived**: centroid of the largest ring, then converted |
| `tmm_park_or_reserve` (North) | ITM (EPSG:2039) | source-supplied `X_Center`/`Y_Center`, converted; **derived** ring centroid only for the 2 features whose `X_Center` was 0 |
| `tmm_park_or_reserve` (Haifa) | ITM (EPSG:2039) | **derived**: centroid of the largest ring |
| `kkl_travel_site` | WGS84 (EPSG:4326) | schema.org `geo` block as given |
| `candidate_lead_check` | WGS84 (EPSG:4326) | he.wikipedia `coordinates` property, secondary |

Original ITM values are always retained in `itm_x` / `itm_y`; `coord_crs_native` and
`coord_source` record the provenance on every record. Conversion check: the Beit She'arim
TMM centroid `212301.72 / 733824.50` (ITM) transforms to `32.69890 / 35.12814`, ~500 m from
Wikipedia's `32.70333 / 35.12917` for the same site - consistent, and the residual is the
polygon-centroid-vs-point difference, not a projection error.

**2,453 of 3,207 records have `point_in_search_window: true`.** The other 754 are features
whose *geometry intersects* the window (that is what an ArcGIS envelope query returns) but
whose centroid sits outside it. Filter on `point_in_search_window` before treating a
record as "in the area".

---

## 11. Licence and terms of use

| source | stated terms |
|---|---|
| `shimur.org` | no licence statement. `robots.txt` allows crawling; a תנאי שימוש page exists at `https://shimur.org/תנאי-שימוש/` and was **not** retrieved or reviewed. **Treat reuse as needing the Council's permission.** |
| `ags.iplan.gov.il` (Planning Administration) | the MapServer metadata carries an empty `copyrightText` and no `serviceDescription`. No licence was found on the service. Israeli government open-GIS practice is attribution, but **no licence text was located** - recorded as unverified. |
| `open.govmap.gov.il/geoserver/opendata` | published under the "opendata" workspace; no licence document was retrieved. |
| `kkl.org.il` | no licence statement; `robots.txt` explicitly blocks Applebot-Extended and Bytespider from AI training, which signals a restrictive stance on bulk reuse. |
| Knesset MMM PDF | Knesset Research and Information Center publication; cite by title, author body and date. |
| he.wikipedia.org | CC BY-SA 4.0 (Wikipedia default). Attribution required. |
| `services6.arcgis.com/.../Respark_meforat_24jul23` | no licence; third-party republication. Not used. |

**No licence was confirmed for any of the four primary sources.** The map must carry
attribution, and a human should confirm reuse terms with the Council for Conservation and
with the Planning Administration before publication.

---

## 12. Known limitations

1. **INPA is a hole.** parks.org.il is CloudFront-blocked and GovMap's API needs a key, so
   there is no open-to-public flag, entrance fee, opening hours, accessibility, or
   "which archaeological site does this park protect" for any national park or reserve.
2. **"Declared" is unavailable.** Neither declared national parks/reserves nor declared
   national sites (beyond the 18-row Knesset table, none of which is here) could be
   retrieved as GIS. Everything park-related in this dataset is a *planning designation*.
3. **The conservation layer has no names.** 2,975 of the 3,207 records identify only a
   plan, not a site. Counting them as sites would inflate the map by an order of magnitude.
4. **No period or year built** anywhere except free prose and the candidate-lead records.
   The pre-1700 / post-1700 split therefore cannot be made from this source alone for the
   conservation-layer records - `אתר ארכיאולוגי לשימור` and `אתר עתיקות/אתר הסטורי`
   conflate antiquities with historic sites in one designation.
5. **No ownership field** exists in any layer retrieved.
6. **shimur.org coordinates are address-geocoded**, sometimes to the village rather than
   the site (six distinct station buildings share one coordinate). Any use at building
   scale needs better geometry.
7. **מבנים לשימור on shimur.org is an empty post type** - the UI offers the filter, the
   archive has no entries.
8. **KKL raw HTML is complete only for in-window pages** (declared in §5, with SHA-256 for
   all 164).
9. **No Emek Yizrael local conservation-committee register** (Fourth Schedule) was found
   published. Whether one exists is unknown.
10. **Duplicate coverage with another agent.** `data/interim/blue_signs.json` and
    `blue_signs_shimur_org_signs_ey.json` already exist from a different source agent and
    also come from shimur.org signs. The harmonizer must de-duplicate on
    shimur post `id` (present here as `id`) rather than on name.
11. **Raw payload volume** is ~110 MB, ~75 MB of which is the 27 shimur sign detail pages
    (each ~2.7 MB of WordPress boilerplate). Consider git-ignoring `data/raw/`.

---

## 13. Raw file inventory

`data/raw/heritage_official/`

**shimur.org:** `shimur_wpjson_root.json`, `shimur_types.json`, `shimur_sites_page.html`,
`shimur_cfmap.js`, `shimur_robots.txt`, `shimur_sitemap_index.xml`,
`shimur_page_sitemap.xml`, `shimur_archive_hbuildings.html`,
`shimur_archive_sitesgefen.html`, `shimur_archive_adopt.html`, `shimur_detail/` (52 HTML),
plus two parser outputs kept beside the raw for traceability:
`shimur_markers_parsed_all.json` (all 879 markers), `shimur_window_parsed.json` (the 52).

**Planning Administration:** `iplan_services_root.json`,
`iplan_PlanningPublic_services.json`, `iplan_Shimour_meta.json`,
`iplan_Shimour_layer1.json`, `iplan_Shimour_layer2.json`, `iplan_Shimour_L1_stats.json`,
`iplan_Shimour_L2_stats.json`, `iplan_Shimour_L1_window_itm.json`,
`iplan_Shimour_L2_window_itm.json`, `iplan_Shimour_L1_window_itm_full.json`,
`iplan_Shimour_L2_window_itm_full.json`, `iplan_tmm_tzafon_meta.json`,
`iplan_tmm_tzafon_L8.json`, `iplan_compilation_tmm_tzafonn_L8_parks_itm.json`,
`iplan_tmm_haifa_meta.json`, `iplan_tmm_haifa_L7.json`,
`iplan_compilation_tmm_haifa_L7_parks_itm.json`.

**GovMap / boundaries:** `govmap_wfs_capabilities.xml`,
`govmap_wfs_all_capabilities.xml` (404 body), `govmap_wfs_muni_schema.xml`,
`govmap_muni_window_wgs84.json` (8.5 MB), `govmap_index.html`, `govmap_bundle.js` (10 MB).

**INPA / rejected sources:** `inpa_reserves_list.html`, `inpa_govmap2.html` (both 403
bodies), `datagov_search_parks.json`, `agol_search_parks.json`, `agol_search_npa.json`,
`agol_search_owner.json`, `agol_org_services.json`, `agol_respark_meta.json`,
`agol_respark_L0.json`, `agol_respark_count.json`, `agol_respark_window_itm.json`.

**KKL:** `kkl_robots.txt`, `kkl_sitemap_he.xml`,
`kkl_sitemap_travel-parks-and-forests.xml`, `kkl_sitemap_travel-scenic-lookouts.xml`,
`kkl_sitemap_recreation-areas.xml`, `kkl_travel_index.json`, `kkl/` (8 HTML).

**Documents:** `knesset_mmm_national_heritage_sites.pdf`,
`wikipedia_national_heritage_site_he.json`, `wikipedia_rakevet_haemek_he.json`,
`wikipedia_coords_candidates.json`, `wikipedia_coords_candidates2.json`,
`wikipedia_coords_candidates3.json`.

The three Wikipedia coordinate calls must be **merged**: MediaWiki returned the
`coordinates` property for a different subset of the requested titles in each call, so no
single file has them all.
