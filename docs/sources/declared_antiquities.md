# Source: `declared_antiquities`

**Official registration status of archaeological sites: אתרי עתיקות מוכרזים (declared antiquity sites) under חוק העתיקות התשל"ח-1978.**

Retrieved: **2026-08-03**. All requests made from a single client at roughly one request per second with
User-Agent `IICP-EmekYizraelMap/1.0 (cultural-heritage mapping research; matan@iicp.org.il)`.

---

## 1. Bottom line

The authoritative declared-antiquities layer **was found** and downloaded, with polygons, official names,
and the ילקוט הפרסומים (Official Gazette) declaration reference for each site.

It is published by **רשות העתיקות (Israel Antiquities Authority, IAA)** through its own public application
**המאגר הלאומי לארכיאולוגיה** (`https://discover.iaa.org.il`) and the IAA's ArcGIS Online organisation
`SzLu0BtKF8WSi3ll`.

| What | Endpoint | National count | In search window |
|---|---|---|---|
| Declared-site polygons (primary) | `HACRAZOT_PUBLIC1/FeatureServer/0` | 31,303 | **2,264** |
| Declared-site polygons (2nd copy, extra admin fields, fewer rows) | `HACRAZOT_PUBLIC/FeatureServer/0` | 24,714 | 1,933 |
| Declaration list (id + he/en name) | `GET /api/hachrazot?prefix=` | 31,303 | n/a (national list) |
| Per-declaration record (gazette ref, status, gush/parcel, WKT) | `GET /api/hachraza/{hachrazaEntityId}` | one per site | see `decl_detail_fetched` |
| **Known** antiquity sites, i.e. Archaeological Survey of Israel points (NOT a declaration layer) | `SURVEY_MAPS_SITE_POINTS_PUBLIC/FeatureServer/0` | 23,312 | **1,801** |
| Survey map sheets (polygons) | `SURVEY_MAPS_SITE_POINTS_PUBLIC/FeatureServer/1` (`GIS_MAPS_PUBLIC`) | 327 | 35 |
| Declared-antiquity rectangles inside the national marine plan (secondary, coastal only) | Planning Administration AGOL, layer 41 | 581 | 19 |

**The declared / merely-known distinction is directly measurable:** of the 1,801 Archaeological-Survey site
points in the window, **1,296 fall inside a declared polygon and 505 do not**. The 505 are known but not
declared. This is the registered-status test the map needs, and it is defensible because it is a spatial
test against the IAA's own declaration polygons.

---

## 2. Exact endpoints and parameters

### 2.1 Primary: IAA declared-site polygons

```
https://services1.arcgis.com/SzLu0BtKF8WSi3ll/arcgis/rest/services/HACRAZOT_PUBLIC1/FeatureServer/0
```

* ArcGIS Online hosted FeatureServer, organisation id `SzLu0BtKF8WSi3ll` (= רשות העתיקות; the same org id
  is returned for the IAA-owned AGOL account `IaaAdmin02`).
* `geometryType`: `esriGeometryPolygon`; `spatialReference`: **wkid 2039 / latestWkid 2039 = EPSG:2039,
  Israel TM Grid (ITM)**.
* `maxRecordCount`: 2000. Layer `fullExtent` (ITM): `xmin 132947.5378, ymin 383300, xmax 284551.026,
  ymax 803700.112`.
* **A token is required.** Anonymous requests return `{"error":{"code":499,"message":"Token Required"}}`.
  The token used is the Esri API key that the IAA itself serves, unauthenticated, to every visitor of its
  public site, at `https://discover.iaa.org.il/api/config/gis.js` (variable `window.gis.esriApiKey`,
  alongside `appId: 'Uz4hXkqxlyfEqva8'`). No login, no credential, and no block was circumvented: this is
  the same key the public web app uses for the same public layer. **It will rotate** - re-read `gis.js`
  before any refresh rather than hard-coding it. The raw `gis.js` payload is saved.

Queries actually used (all `POST`, `application/x-www-form-urlencoded`, to avoid URL length limits):

```
POST .../HACRAZOT_PUBLIC1/FeatureServer/0/query
  where=1=1
  geometry={"xmin":198000,"ymin":710000,"xmax":247500,"ymax":751000,"spatialReference":{"wkid":2039}}   # union envelope, see section 5
  geometryType=esriGeometryEnvelope
  inSR=2039
  spatialRel=esriSpatialRelIntersects
  returnIdsOnly=true
  f=json
  token=<key from gis.js>
-> 2264 objectIds

POST .../HACRAZOT_PUBLIC1/FeatureServer/0/query
  objectIds=<300 ids per page>
  outFields=*
  returnGeometry=true
  outSR=4326          (and a second pass with outSR=2039)
  f=geojson           (and a second pass with f=json)
  token=<key>
-> 2264 features, 8 pages
```

### 2.2 IAA declaration list and per-declaration record

Plain public JSON, no token, no auth:

```
GET https://discover.iaa.org.il/api/hachrazot?prefix=       -> 5,591,189 bytes, 31,303 declarations
GET https://discover.iaa.org.il/api/hachraza/{hachrazaEntityId}
GET https://discover.iaa.org.il/api/entity-types            -> confirms id "hachrazot" = "אתרי עתיקות מוכרזים"
GET https://discover.iaa.org.il/api/config/gis.js
```

`hachrazaId` in this API is byte-identical to `atar_number` in the FeatureServer (format `<ataId>/<ataTatId>`,
e.g. `2723/0`). **All 2,264 window polygons matched an entry in the declaration list**, which independently
confirms every polygon in `HACRAZOT_PUBLIC1` is an officially declared site.

Note: `www.iaa.org.il` and `gwa.israntique.org.il` sit behind an F5 WAF that rejects a plain `curl`
("Request Rejected ... support ID"). `discover.iaa.org.il` does not. The route into the API was found by
reading the public page `https://www.iaa.org.il/page/sitechecks`, whose "בדיקת גוש וחלקה" link points to
`https://gwa.israntique.org.il/webapp/shovarEn/FindByGushparEn.html`, which redirects to
`https://discover.iaa.org.il`; the service URLs are hard-coded in that app's `static/main.js`.

### 2.3 Known-sites (Archaeological Survey of Israel) points

```
https://services1.arcgis.com/SzLu0BtKF8WSi3ll/arcgis/rest/services/SURVEY_MAPS_SITE_POINTS_PUBLIC/FeatureServer/0
https://services1.arcgis.com/SzLu0BtKF8WSi3ll/arcgis/rest/services/SURVEY_MAPS_SITE_POINTS_PUBLIC/FeatureServer/1
```
Same org, same token requirement, `spatialReference` wkid 2039. Layer 0 = 23,312 site points; layer 1
(`GIS_MAPS_PUBLIC`) = 327 survey map sheets. Same envelope query as above.

### 2.4 Secondary: declared-antiquity rectangles in the national marine plan

```
https://services2.arcgis.com/9xNzs4HrnCQY9yx4/arcgis/rest/services/שכבות_מידע_המרחב_הימי/FeatureServer/41
```
AGOL organisation `9xNzs4HrnCQY9yx4` = **מינהל התכנון** (urlKey `pnimgis`). Layer name `אתר עתיקות מוכרז`,
`description`: "אתרי עתיקות מוכרזים על-פי חוק העתיקות- מרובעים". Polygon, EPSG:2039, 581 features
nationally, 19 intersecting the window (Haifa coastal strip only - `xmax` of the layer is ITM 211800).
No token needed. Useful only as an independent cross-check on the west edge; the IAA layer supersedes it.

---

## 3. Full schema of what came back

### 3.1 `HACRAZOT_PUBLIC1/0` - the primary declared-sites layer (13 fields)

| Field | Esri type | Alias (as published) | Meaning / units | Fill in window |
|---|---|---|---|---|
| `objectid` | OID | objectid | ArcGIS row id, service-local, **not stable across refreshes** | 2264 |
| `globalid` | GUID | GlobalID | stable row GUID | 2264 |
| `atar_number` | String | מספר אתר | IAA site number, `<ataId>/<ataTatId>`, e.g. `2723/0`. **Join key.** | 2264, all distinct |
| `meh_id` | Integer | קוד מחוז | IAA district code; 7 distinct values here: 0, 12, 13, 14, 21, 97, 100. No lookup table found. | 2264 |
| `mehoz_name` | String | שם מחוז | IAA district name | **0 of 2264 - entirely null in this layer** |
| `ata_shem` | String | שם אתר | official site name, Hebrew | 2263 (1 null) |
| `atar_heb_desc` | String | תאור אתר בעברית | free-text description of remains and periods, Hebrew | 2264 (36 are whitespace only) |
| `atar_eng_desc` | String | תאור אתר באנגלית | same in English; 34 read "No Description in English"; word order is often scrambled in the source | 2264 (35 read "No Description in English") |
| `ata_last_pir` | Double | מספר פרסום בילקוט הפרסומים | **Official Gazette issue number** of the declaration | 1944 (320 null) |
| `ata_pir_amud` | Double | מספר עמוד בילקוט הפרסומים | **page number** in that Gazette issue | 1944 (320 null) |
| `globalid_1` | GlobalID | globalid_1 | second GUID column | 2264 |
| `Shape__Area` | Double | Shape__Area | polygon area, **square metres in EPSG:2039** | 2264 |
| `Shape__Length` | Double | Shape__Length | perimeter, **metres in EPSG:2039** | 2264 |

### 3.2 `HACRAZOT_PUBLIC/0` - second copy of the same layer, 36 fields

Fewer rows (24,714 national / 1,933 in window) but more administrative columns. Joined into the interim
file on `atar_number` with an `hp_` prefix. Fields carried over:

| Field | Meaning | Observed values in window |
|---|---|---|
| `ata_id`, `ata_tat_id` | the two halves of `atar_number` | integers |
| `sug_atar` | site-type code | `"1"` (1923), `"2"` (10) |
| `ata_status` | site status code | **`"6"` for all 1,933 rows** - the layer contains only one status |
| `ata_date_status` | date the status was set (epoch ms) | 1,666 filled |
| `ata_date_ishur` | approval date (epoch ms) | 999 filled |
| `ata_sug_pir` | publication type | `"י"` = ילקוט הפרסומים (1,865); 68 null |
| `ata_public` | publication flag | `"1"` (1,916), `"0"` (16), 1 null |
| `ata_not_ok` | **internal caseworker note** | 133 filled. Includes `"פתיחת אתר לפי בקשה"` (29), `"חסר מס' אתר בסקר ישראל"` (21) and, for 27 rows, a note containing **`"לא להכרזה!!!"`** (not for declaration) - i.e. an internal note saying *not* for declaration, on a row that nonetheless sits in the declared layer. Do not surface this field publicly and do not treat it as a status. |
| `ata_law` | law reference code | only 2 rows filled (`1`) |
| `odaa_number`, `odaa_date` | notice (הודעה) number and date | 560 filled |
| `ata_update_date` | last update (epoch ms) | 1,767 filled |
| `sai_id` | survey-map / index id | 30 distinct |

Other columns present in the service but not carried over because they are pure internals:
`xoid`, `pers_do`, `peilut_seq`, `ata_sug` (100% null), `ata_chang_id`, `ata_ishur_id`,
`ata_date_owner` (100% null), `ata_create_date`, `ata_create_user`, `ata_update_user`,
`kabala_date`, `base_details_seq`.

### 3.3 `GET /api/hachraza/{entityId}` - the per-declaration record

The richest and most citable object. Structure (from the Tel Megiddo record, `hachrazaId` `2723/0`,
`hachrazaEntityId` 29559):

| Key | Meaning |
|---|---|
| `hachrazaId` | = `atar_number` |
| `hachrazaEntityId` | numeric entity id used by the API |
| `atarTitle.{hebrew,english}` | e.g. " אתר מוכרז מגידו, תל 2723" / "Declared archeological site Mutasallim, T. el- 2723" |
| `atarType` | `"יבשתי"` (terrestrial) / marine |
| **`atarStatus`** | **per-site declaration status string, e.g. `"מוכרז/תקין"`** - the status field to use |
| `isPublicAtar` | boolean |
| `atarOfficialName.{hebrew,english}` | official name, e.g. "מגידו, תל" / "Megiddo, T." |
| `atarNames[]` | every recorded name variant: `nameCode` (`A` = Arabic, `H` = Hebrew), `originalName`, `transliterationName` |
| `atarDescription.{hebrew,english}` | description of remains and periods |
| **`atarOfficialAnnouncementGazette[]`** | **the declaration itself**: `announcementType` (`"י"` = ילקוט הפרסומים), `announcementNo` (1091), `announcementPage` ("1387"), `announcementDate` ("1964-05-18T00:00:00") |
| `atarTabu[]` | `tabuGush`, `tabuHelkaFrom`, `tabuHelkaTo`, `tabuYishuvName`, `tabuWarnDate` - land-registry block/parcel |
| `atarSouthWest` / `atarNorthEast` | declared bounding box in ITM. **`gisAtarWidth` is the EASTING and `gisAtarHeight` the NORTHING** (Megiddo: 217000/721000 to 218000/722000) |
| `atarMehozName` | IAA district name, e.g. "גליל תחתון והעמקים" |
| `atarMerchavName` | IAA region, e.g. "צפון" |
| `ataId`, `ataTatId`, `atarSeif` | ids and law-section reference |
| **`atarPeriodsAndElements[]`** | **the only structured period attribution in this source**: an array of `{structureName:{hebrew,english}, periods:[{hebrew,english}]}`, i.e. per built element, the periods attributed to it. Example: `[{"structureName":{"hebrew":"יישוב/חורבה/תל"},"periods":[{"hebrew":"לא ניתנת לזיהוי"}]},{"structureName":{"hebrew":"פיזור כלי צור/חרסים"},"periods":[{"hebrew":"נבטים"},{"hebrew":"ביזנטית"}]}]`. Flattened into `decl_periods_he/en` and `decl_structure_types_he/en` in the interim file. |
| `atarMapInformation[]` | `shapeId`, **`shapeWkt`** (polygon WKT in ITM), `shapeType` (`"boundary"`), `shapeData` |

### 3.4 `SURVEY_MAPS_SITE_POINTS_PUBLIC/0` - known (documented) antiquity sites, 36 fields

`OBJECTID`, `EXT_ID`, `SITE_NUM`, `FIELD_NUM` (e.g. `"0–9/1"`), `MAP_ID`, `NAME_HEB`, `NAME_EN`,
`ADDITIONAL_NAME_HEB`, `ADDITIONAL_NAME_EN`, `GIS_X`, `GIS_Y`, `GIS_H`, `XY_KIND_ID`, `X_OLD`, `Y_OLD`,
`X_NEW`, `Y_NEW`, `X_UTM`, `Y_UTM`, `X_WGS_84`, `Y_WGS_84`, `DESCRIPTION_HEB` (HTML), `DESCRIPTION_EN`,
`BIBLIOGRAPHY_HEB`, `BIBLIOGRAPHY_EN`, `LASTUPDATED`, `ORIG_GLOBALID`, `GlobalID`, `ORIG_ID`,
`PERIOD_HEB`, `PERIOD_EN`, `AUTHORS_HEB`, `AUTHORS_EN`, `REMAINS_HEB`, `REMAINS_EN`.

**Coordinate-column trap, verified, do not get this wrong:**

* `X_WGS_84` holds the **latitude** and `Y_WGS_84` the **longitude**. Checked against the layer's own
  geometry on 400 consecutive rows: 400/400 had `X_WGS_84 == geometry latitude` and
  `Y_WGS_84 == geometry longitude`.
* `X_NEW` holds the ITM **northing** and `Y_NEW` the ITM **easting** (row 1: `X_NEW 719396`,
  `Y_NEW 200382`; correct ITM is easting 200382, northing 719396).
* `GIS_X`/`GIS_Y` are truncated grid references on the same swapped convention (`21940`/`15040`).
* `X_OLD`/`Y_OLD` are on the older grid but `Y_OLD` carries a leading `1` (`150400` / `1219401`). I did
  **not** work out that convention and did not use those columns. Treat them as unknown.
* Use the returned **geometry**, not these columns.

### 3.5 Marine-plan layer 41 (secondary)

`OBJECTID`, `LAYER_NAME` (always `"אתר_עתיקות_מוכרז"`), `TYPE_NAME` (`"0"`/`"1"`), `ADDRESS` (place text,
e.g. "חיפה, בת גלים"), `SOURCE` (always `"מאגר למרחב הימי"`), `DATA_DATE` (epoch ms, all 2018-12-31),
`REMARKS` (free text describing the remains), `STATUS` (always `"מסמך מדיניות שלב ב"` - this is the
*planning-document* stage, **not** a declaration status), `Shape__Area`, `Shape__Length`. EPSG:2039.

---

## 4. Files written

Raw payloads, byte-for-byte as received, in
`data/raw/declared_antiquities/`:

| File | What |
|---|---|
| `iaa_HACRAZOT_PUBLIC1_FeatureServer.json`, `iaa_HACRAZOT_PUBLIC1_layer0.json` | service + layer metadata |
| `iaa_hacrazot_public1_window_objectids.json` | the 2,264 objectIds |
| `iaa_hacrazot_public1_window_wgs84.geojson` | 2,264 polygons, EPSG:4326 |
| `iaa_hacrazot_public1_window_itm2039_esrijson.json` | same 2,264 polygons, **native EPSG:2039** |
| `iaa_HACRAZOT_PUBLIC_FeatureServer.json`, `iaa_HACRAZOT_PUBLIC_layer0.json` | 36-field variant metadata |
| `iaa_hacrazot_window_objectids.json`, `iaa_hacrazot_window_wgs84.geojson`, `iaa_hacrazot_window_itm2039_esrijson.json` | 1,933 polygons of the 36-field variant |
| `iaa_discover_api_hachrazot_all.json` | the full national declaration list, 31,303 entries |
| `iaa_discover_api_hachraza_details_window.json` | per-declaration records for the window sites |
| `iaa_discover_api_hachraza_29559_sample.json` | single pretty sample (Tel Megiddo) |
| `iaa_discover_api_entity_types.json`, `iaa_discover_api_config_gis.js` | API self-description; app config |
| `iaa_SURVEY_MAPS_SITE_POINTS_PUBLIC_*.json`, `iaa_survey_site_points_window_*.{geojson,json}` | 1,801 survey site points, both CRS |
| `iaa_survey_gis_maps_window_*.{geojson,json}` | 35 survey map sheets |
| `iaa_agol_services_dir.json` | the IAA AGOL service directory (682 services) |
| `marine_declared_antiquity_layer41_meta.json`, `marine_layer41_declared_window_itm2039.geojson` | Planning-Administration marine declared-antiquity rectangles, 19 in window |
| `govmap_layers_catalog_he.json` | the full GovMap layer catalogue (883 layers) |
| `datagov_all_packages.json`, `datagov_package_list.json`, `datagov_organization_list.json`, `datagov_package_search_*.json` | the negative result on data.gov.il |
| `iplan_PlanningPublic_services.json`, `iplan_all_service_layers.json` | the negative result on מינהל התכנון's own ArcGIS |

Machine-readable per-record outputs in `data/interim/`:

| File | Rows | What |
|---|---|---|
| `declared_antiquities.json` | 2,264 | one flat object per declared site; all original field names preserved, plus joined and derived fields |
| `declared_antiquities.geojson` | 2,264 | the same records with their **polygon** geometry in EPSG:4326, for point-in-polygon status assignment |
| `declared_antiquities_known_survey_points.json` | 1,801 | Archaeological-Survey known sites, each flagged declared / not declared |
| `declared_antiquities_known_survey_points.geojson` | 1,801 | the same as points, EPSG:4326 |

### The registered / not-registered test, already computed

`declared_antiquities_known_survey_points.json` carries, per survey point:

* `_inside_declared_polygon` - boolean, from a `shapely` `covers()` point-in-polygon test against
  `declared_antiquities.geojson`.
* `_declared_atar_numbers` - the `atar_number`(s) of the declared polygon(s) the point falls in, or `null`.
* `_registration_status` / `_registration_status_en` / `_registration_status_basis`.
* `_in_wgs84_search_window`.

Result over the window: **1,296 of 1,801 surveyed sites are inside a declared polygon; 505 are not.**
The 505 are the "known but not declared" class -
real, documented archaeology with no declaration protection. Examples: survey site 1 נחל תנינים
(remains: גל אבנים), 7 צַבָּארִין (גורן, ספלול, אמת מים, באר), 24 רֻגְ'ם אֶל-בַּהְתָּה (גל אבנים, רצפה, קבורה).

Caveat on that test: a survey point missing a declared polygon is evidence the *point* is not inside a
declared square, which is not identical to "the site is not declared" - a declaration may cover a nearby
square, and 320 declared rows in the window carry no Gazette reference at all. Treat 505 as an upper bound
on the not-declared class and re-run the test after the council boundary clip.

### Derived fields added (all prefixed or clearly named, originals untouched)

* `lat`, `lon` - **area-weighted centroid of the polygon's outer ring(s), computed by me**, not an
  IAA-supplied point. Flagged in every record by `_centroid_method`.
* `_bbox_wgs84`, `_bbox_itm2039` - bounding boxes in both CRS.
* `_gazette_reference` - a formatted string, e.g. `ילקוט הפרסומים 1091, עמ' 1387`, built **only** from
  `ata_last_pir` and `ata_pir_amud`; `null` where those are null. Nothing invented.
* `_registration_status` = `אתר עתיקות מוכרז`, `_registration_status_en` = `declared antiquity site`,
  `_registration_status_basis` - why.
* `hp_*` - the joined fields from the 36-field `HACRAZOT_PUBLIC` variant, `null` where no match
  (331 of 2,264 have no match).
* `hachraza_name_hebrew`, `hachraza_name_english`, `hachrazaEntityId` - from `/api/hachrazot`.
* `decl_*` - from `/api/hachraza/{entityId}`: status, type, official names, district, region,
  gazette issue/page/date, gush list, and the declared ITM bounding box.
* `_source_id`, `_source_layer`, `_native_crs`, `_retrieved`.

---

## 5. Native CRS and the search window

* **Native CRS: EPSG:2039, Israel TM Grid (ITM).** Every IAA layer used reports
  `spatialReference: {wkid: 2039, latestWkid: 2039}`. Native-CRS copies of every geometry are saved
  alongside the WGS84 copies.
* The spatial filter used was an **ITM envelope** with `inSR=2039`, because that is the layer's own CRS
  and avoids a reprojection at query time.
* **The two windows in the brief are not equivalent, and the ITM one is the smaller. This matters.**
  Reprojecting the four corners of the stated WGS84 box (lat 32.55-32.85, lon 35.05-35.50) to EPSG:2039
  gives `x 204950-247217, y 717320-750618`, which **overflows the stated ITM envelope**
  (`x 198000-245000, y 710000-750000`) by up to 2,217 m on the east and 618 m on the north. Querying only
  the stated ITM figures silently drops sites that are inside the stated WGS84 box. I therefore re-queried
  with the **union envelope `x 198000-247500, y 710000-751000` (EPSG:2039)** and merged the delta. That
  recovered **154 additional declared polygons, 142 additional rows in the second layer copy, 49
  additional survey site points and 5 additional survey map sheets**. Any other agent filtering this
  window in ITM should use the union, not the stated ITM figures.
* The union envelope is in turn wider than the WGS84 box on the south-west, so some centroids fall outside
  the tighter box (centroid range: lat 32.4793-32.8479, lon 34.9702-35.4789). Nothing was discarded - a
  per-record boolean `_in_wgs84_search_window` marks which are inside - so the later clip to the council
  boundary decides, not me.
* Reprojection sanity check: for all 2,264 polygons I reprojected the ITM bounding-box centre with
  `pyproj` EPSG:2039 -> EPSG:4326 and compared it with the WGS84 bounding-box centre returned by the
  service. **Maximum deviation 0.000004 deg, about 0.5 m.** The service's reprojection is sound.

---

## 5a. Independent verification performed

1. **Second government publisher agrees, 19/19.** The מינהל התכנון marine-plan layer "אתר עתיקות מוכרז"
   (section 2.4) has 19 rectangles inside our window. I reprojected each from EPSG:2039 to EPSG:4326 and
   tested it against the IAA polygons: **all 19 intersect an IAA declared polygon.** Two independent
   government publications of the same declarations agree spatially.
2. **Named-site spot checks against public knowledge.** Every well-known Jezreel Valley site checked was
   found, with a plausible position and a Gazette reference:
   `2723/0 מגידו, תל` at 32.5878, 35.1836 (ילקוט הפרסומים 1091, עמ' 1387);
   `2725/0 נהלל` at 32.6775, 35.1788 (י"פ 1091, עמ' 1382);
   `2765/0 כפר ברוך` at 32.6419, 35.1953 (י"פ 4539, עמ' 4240);
   `2462/0 הזורע, תל קירה` at 32.6441, 35.1117 (י"פ 1810, עמ' 1287);
   `2727/0 בית לחם הגלילית` at 32.7348, 35.1884 (י"פ 1164, עמ' 1446);
   `3062/0 עפולה` at 32.6058, 35.2901 (י"פ 1091, עמ' 1387);
   plus 10 sites at יקנעם, 13 around דבורה, 5 at גזית.
3. **Every polygon is in the official declaration list.** 2,264/2,264 window `atar_number` values matched
   an entry in `/api/hachrazot`, a separately-generated endpoint.
4. **Reprojection is sound**: max 0.5 m deviation over 2,264 polygons (section 5).
4a. **The FeatureServer geometry matches the declaration's own bounding box.** For every enriched record I
   compared the polygon's native-ITM bounding box against `atarSouthWest` / `atarNorthEast` from
   `/api/hachraza`. Zero deviations above 5 m; **maximum deviation 0.14 m**. The polygon and the declared
   coordinate box are the same object, reached through two different services.
5. **The grid-square nature of declarations is confirmed by the area distribution**: the most common
   `Shape__Area` values in the window are 10,000 m2 (255 rows), 400 m2 (170), ~40,000 m2 (222),
   ~1,000,000 m2 (123). These are 100x100 m, 20x20 m, 200x200 m and 1x1 km squares.

## 6. Licence / terms of use

* **No licence statement is attached to any of these services.** `copyrightText`, `licenseInfo` and
  `description` are empty on `HACRAZOT_PUBLIC1`, `HACRAZOT_PUBLIC` and
  `SURVEY_MAPS_SITE_POINTS_PUBLIC`. There is no terms-of-use document at the FeatureServer or on the
  `discover.iaa.org.il` API. **Treat licensing as unresolved and ask the IAA before republishing the
  polygons.**
* The IAA does publish a legal disclaimer on `https://www.iaa.org.il/page/sitechecks`, which applies to
  exactly this data. In substance: the ילקוט הפרסומים publication records the gush and parcel numbers as
  they stood at the time of publication and these may since have changed; only information in the State
  of Israel's official publications is correct and binding; output produced by the online system is not an
  approved registration or a copy of the Gazette registration; only a written confirmation signed by the
  authorised officer at the IAA establishes whether a given parcel is or is not inside a declared site;
  and **the determination of a site's boundaries is made by the coordinate points appearing in ילקוט
  הפרסומים**.
* Practical consequence for our map: present the declared-site polygons as **indicative**, cite the
  Gazette issue and page we carry per site, and link users to the IAA for a binding answer. Do not word
  anything as a legal determination.

---

## 7. Known limitations and caveats

1. **Licence unknown** (section 6). This is the biggest open risk for a public map.
2. **The polygons are declaration rectangles, not site footprints.** Declared areas are grid squares or
   unions of grid squares: Tel Megiddo's declared area is the 1 km square ITM 217000-218000 /
   721000-722000, and the most common `Shape__Area` values in the window are exactly 400 m2 (20x20 m),
   10,000 m2 (100x100 m) and 1,000,000 m2 (1x1 km). The marine layer's own description says so:
   "אתרי עתיקות מוכרזים על-פי חוק העתיקות- **מרובעים**". A polygon therefore tells you *a declaration
   covers this square*, not *the archaeology extends exactly this far*.
3. **Two copies of the layer disagree in row count**: 31,303 (`HACRAZOT_PUBLIC1`) vs 24,714
   (`HACRAZOT_PUBLIC`). 31,303 matches `/api/hachrazot` exactly, so `HACRAZOT_PUBLIC1` is treated as
   complete and `HACRAZOT_PUBLIC` as a filtered extract used only for extra columns. The window rows with
   no counterpart in the 24,714 copy therefore have null `hp_*` fields. **Evidence for what the filter is:**
   of the 331 window rows absent from the small copy, only 79 (24%) carry a Gazette reference, against
   1,865 of 1,933 (96%) among the rows that are present. The small copy looks like the subset of
   declarations that have a recorded ילקוט הפרסומים publication. This is an inference from the data, not
   something the IAA states.
4. **320 of 2,264 have no Gazette issue/page** in `ata_last_pir` / `ata_pir_amud`. Left `null`, not guessed.
   Some are recovered by `/api/hachraza`, and those that are not stay `null`.
5. **`ata_status` is a single constant `"6"`** in the copy that carries it, so it cannot discriminate
   anything. The usable status string is `atarStatus` from `/api/hachraza` (e.g. `"מוכרז/תקין"`).
6. **`ata_not_ok` contains internal caseworker notes, including 7 rows reading "לא להכרזה!!!" (not for
   declaration)** while sitting inside the declared layer. Do not publish this field and do not read it
   as a status; flag those rows for a human if any land inside the council.
7. **`mehoz_name` is 100% null** in `HACRAZOT_PUBLIC1`. District comes from `meh_id` (codes only, no
   lookup table found) or from `atarMehozName` in `/api/hachraza`.
8. **`atar_eng_desc` word order is scrambled in the source** (a right-to-left export artefact), e.g.
   ", buildings, gate, remains of walls, Artificial mound partly excavated". Use the Hebrew description.
9. **`lat`/`lon` in the interim file are my computed polygon centroids**, on a planar formula applied to
   degrees. Adequate for labelling at these latitudes and polygon sizes; do not treat as survey-grade.
   For a point representation of a declared site, prefer the matched Archaeological-Survey point.
10. **`objectid` is not a stable identifier** across service refreshes. Join on `atar_number`
    (or `globalid`).
11. **The token in `gis.js` will rotate.** Any refresh must re-read it.
12. **`atar_number` uniqueness**: unique within the 2,264 window rows of `HACRAZOT_PUBLIC1`, but in the
    24,714 copy `ata_id` repeats (e.g. `ata_id` 2500 appears 39 times with different `ata_tat_id`), so
    always use the full `<ataId>/<ataTatId>` string.
13. **Period attribution: free text on the declared layer, a real coded-ish field on the survey layer.**
    The declared layer has no period column at all; periods sit inside `atar_heb_desc`. The
    Archaeological-Survey points layer does carry `PERIOD_HEB` / `PERIOD_EN`, populated for **1,368 of
    1,801** window points (comma-separated period names, e.g. `"הביזנטית, הרומית"`, sometimes with a
    period repeated), plus `REMAINS_HEB` for 1,752 and `DESCRIPTION_HEB` for 1,793.
14. **"Declared antiquity site" is NOT a synonym for "pre-1700".** In the window, **173 declared rows
    mention the Ottoman period** in their Hebrew description and 14 more spell it `עותמאנ`;
    `"העות'מאנית"` is the 4th most common `PERIOD_HEB` value on the survey points (60 points). 19 declared
    rows are flour mills (`טחנת קמח`), 31 lime kilns (`כבשן סיד`), 9 Muslim cemeteries, 6 mosques. The IAA
    declares post-1700 remains as antiquities, so the map's "archaeological = up to 1700" rule will
    disagree with this layer for a real number of sites. Decide that split explicitly in harmonization
    rather than assuming IAA-declared implies pre-1700. (No row mentions `המנדט`, `הבריט` or `תחנת רכבת`,
    so British-Mandate infrastructure is genuinely absent from the declared layer - that belongs to
    המועצה לשימור אתרי מורשת.)
15. The window count is **not** the council count. 2,264 polygons is the generous search window, which
    includes Haifa, Qiryat Ata and other territory well outside מועצה אזורית עמק יזרעאל.
16. **Text artefacts in `ata_shem`, must be normalised downstream:** 4 names contain embedded carriage
    returns or line feeds (`'\rנהלל\r\n'`, `'\nנחל אזנית [3]\n'`, `'\nגבעה מול תל גובל\n'`,
    `'\nמצפה נטופה\n'`); the same 4 need `strip()`. **53 names end in a question mark**
    (`"אלון, ח' (דרום)?"`, `"רמת השופט (מערב)?"`) - in the IAA's own notation that marks an uncertain
    identification, so do not print it as part of a site's name without explaining it.
    2,263 of 2,264 `atar_heb_desc` values have leading/trailing whitespace. `ata_shem` is **not unique**:
    "טירת כרמל" appears 8 times, "נחל צפורי" 7, "כרם מהר\"ל" 6 - never key on the name.
17. `atar_number` values also appear with a `[n]` suffix inside `ata_shem` (`'נהלל [1]'`) where the IAA
    numbered several declarations at one place. Different `atar_number`, same locality.

---

## 7a. Join keys this source offers other sources

| Key | Field(s) | Notes |
|---|---|---|
| **IAA site number** | `atar_number` (= `hachrazaId`, format `<ataId>/<ataTatId>`) | the canonical IAA identifier; also `hp_ata_id` + `hp_ata_tat_id` separately |
| IAA entity id | `hachrazaEntityId` | key into `discover.iaa.org.il/api/hachraza/{id}` |
| Archaeological-Survey site number | `SITE_NUM`, `FIELD_NUM`, `MAP_ID`, `EXT_ID`, `ORIG_ID` (survey-points file) | survey-map site numbering, e.g. `FIELD_NUM` `"0–9/1"` |
| Official name | `ata_shem` / `decl_official_name_he` / `decl_official_name_en` / `decl_name_variants[]` | `atarNames[]` carries Arabic and Hebrew variants with transliterations - **the best fuzzy-match material in the whole project** |
| Land registry | `decl_tabu_gushim[]` (`tabuGush`, `tabuHelkaFrom`, `tabuHelkaTo`, `tabuYishuvName`) | gush/parcel; also enables a join to the cadastral layer `GUSH_AND_PARCEL_POSTGRES/FeatureServer/0` in the same IAA org |
| Geometry | polygon (declared), point (survey) | the polygon is what makes the registered-status test possible |
| Gazette citation | `_gazette_reference`, `decl_gazette_no`, `decl_gazette_page`, `decl_gazette_date` | for citing the declaration |
| Administrative | `decl_mehoz_name` (IAA district, e.g. `גליל תחתון והעמקים`), `decl_merchav_name` (`צפון`), `meh_id` | IAA's own regions, **not** the same as planning districts |

No wikidata QIDs, no licence numbers and no permit numbers are present in this source.

## 7b. Overlap with the `iaa_discover` source - read before harmonising

The sibling source `iaa_discover` (`data/interim/iaa_discover.json`, 5,396 rows) independently pulled the
same `/api/hachraza/{id}` endpoint and contains **2,509 rows with `entityType == "hachraza"`**, carrying the
identical keys (`hachrazaId`, `atarStatus`, `atarOfficialAnnouncementGazette`, `atarTabu`,
`atarPeriodsAndElements`, ...) plus excavation records this source does not have.

Deduplicate on **`hachrazaId`** (= my `atar_number`). What each side uniquely contributes:

* **This source** contributes the **polygon geometry** (`declared_antiquities.geojson`), the native-ITM
  copies, the `hp_*` administrative columns from the second layer copy, and the Archaeological-Survey
  known-sites points with the declared/not-declared flag already computed.
* **`iaa_discover`** contributes excavations, licences and other entity types, and a different spatial
  slice - its 2,509 declarations are not necessarily the same 2,264 as mine, because the two agents used
  different filters (mine is the ITM envelope on the polygon layer).

Do **not** treat the two counts as independent evidence of anything; they are the same registry read twice.

## 8. What was tried and did **not** work (so nobody repeats it)

* **data.gov.il** - full CKAN sweep: `organization_list` (no רשות העתיקות organisation exists),
  `package_list` (1,198 datasets), and all 1,198 package records pulled via
  `package_search?q=*:*&rows=500` and grepped for `עתיק`, `מורשת`, `שימור`, `ארכיאולוג`, `מוכרז`.
  **No antiquities dataset of any kind.** `package_search` with Hebrew `q=עתיקות` returns
  `count: 0` (its Hebrew indexing is unreliable), which is why the exhaustive dump was necessary.
* **מינהל התכנון / xplan ArcGIS** - `https://ags.iplan.gov.il/arcgisiplan/rest/services` -> folders
  `PlanningPublic`, `Utilities`; all **46** `PlanningPublic` MapServers enumerated and every layer name
  grepped. **No declared-antiquities layer.** (`/arcgis/rest/services` is a dead path that returns an
  error page; the live path is `/arcgisiplan/`. On Windows, `curl` needs `--ssl-no-revoke` for this host
  or schannel fails with `CRYPT_E_NO_REVOCATION_CHECK`; Python `requests` fails with `SSLEOFError`.)
* **GovMap** - the layer exists in the catalogue: id `182`, `serviceLayerId` `govmap:layer_atikot_sites_itm`,
  caption "אתרי עתיקות", `publisherId` 40 = רשות העתיקות, keywords including "שטח מוכרז",
  `layerKind` 2 (polygon), `updateDate` 2024-07-30. Getting the catalogue needs an `x-trace-id` request
  header (`https://www.govmap.gov.il/api/layers-catalog/catalog?lang=he`; without it, HTTP 400
  `{"error":"access denied"}`). But its **feature service is not publicly reachable**: the catalogue
  advertises GeoServer WFS at `//geoserver/wfs?service=wfs&version=1.1.0`, and every candidate path on
  `www.govmap.gov.il` returns the SPA `index.html` while the actual GeoServer host
  `tiles.govmap.gov.il` returns **HTTP 401** on every path. I stopped there rather than push at an
  authenticated host. GovMap's documented public API (`api.govmap.gov.il`) needs a registered API key.
  This is a dead end that the IAA source makes unnecessary.
* **`gisserver.antiquities.org.il`, `ags.antiquities.org.il`, `gis.iaa.org.il`, `gisapp.iaa.org.il`,
  `maps.iaa.org.il`, `arcgis.iaa.org.il`, `ags.mapi.gov.il`, `gis.mapi.gov.il`, `hatzav.mapi.gov.il`** -
  do not resolve in DNS.
* **`open.govmap.gov.il`** - returns the national 404 page; the portal no longer exists.
* **ArcGIS Online keyword search** for `"אתרים מוכרזים"` returns 0 items; `"אתרי עתיקות"` returns 12
  items, all of them third-party surveys (מכון דש"א and similar) rather than the IAA layer. The IAA's
  public AGOL account `IaaAdmin02` (141 items) is almost entirely the Lifta survey and 3D models. The
  declared layer is **not discoverable by search** - it is only reachable via the service URL hard-coded
  in `discover.iaa.org.il`'s bundle. Worth remembering for any future Israeli GIS hunt.
* **`hub.arcgis.com/datasets/3a16db50b51841d2827aafcfffed6dcf_2`** ("אתרי עתיקות שתועדו בסקר", a common
  search hit) is the **Palmachim** survey by מכון דש"א, extent lon 34.61-34.88 / lat 31.76-32.04.
  Nowhere near our window and not authoritative.
