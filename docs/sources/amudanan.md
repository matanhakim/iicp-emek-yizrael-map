# Source: amudanan (עמוד ענן)

**source_id:** `amudanan`
**Site:** https://amudanan.co.il/
**Retrieval date:** 2026-08-03
**Status: STOPPED - the site's own legal page explicitly forbids machine downloading. ZERO records delivered.**

---

## 1. Bottom line

`data/interim/amudanan.json` is an **empty array**. No site records from עמוד ענן are
contributed to this project.

עמוד ענן does have exactly the machine-readable POI endpoint we were looking for, and it
covers our search window densely. We must not use it. Its "הבהרה משפטית" (legal
disclaimer) page forbids automated downloading in terms whose only carve-out is for a
**non-geographic** search-engine index, which is the precise opposite of what this project
is. See section 3 for the verbatim text.

**Do not re-attempt this source with another agent.** The only legitimate route is written
permission from the site owner (section 7).

---

## 2. What the source is

עמוד ענן ("Pillar of Cloud") is an Israeli hiking/topographic map platform, founded and
edited by **יואב רופא** (Yoav Rofe). Per its about page:

> מטרת האתר "עמוד ענן" היא הצגת מפות של ארץ ישראל, ויצירת אנציקלופדיה גיאוגרפית מקוונת,
> שתהייה נגישה לציבור הגולשים, ללא תשלום.

Architecture: a Google-Maps-based viewer (`min2ver25.js`) over a **MediaWiki** instance at
`/w/`, where each point of interest is a wiki page named `P<id>`. Points are crowd-sourced
by named contributors, ordinary users can add sites through the map UI
(`/w/index.php/מיוחד:FormEdit/Point/`), and the site's own sitemap
(`http://amudanan.co.il/services/sitemap.php`) enumerated **359,778** such `#!wiki=P<id>`
pages nationally.

### Upstream provenance - IMPORTANT for de-duplication

This was a specific question in the task brief. Answer: **the POI/sites layer is NOT
derived from OpenStreetMap.** The copyright notice compiled into the map layer config
attributes each layer separately:

| Layer | Attribution in the JS layer config |
|---|---|
| Topographic base maps (I50, I50N) | `© המרכז למיפוי ישראל` (Survey of Israel, mapi.gov.il) |
| Trail markings (סימוני שבילים) | `© OpenStreetMap contributors, CC-BY-SA` |
| Foreign/international maps | OpenTopoMap (CC-BY-SA) |
| PEF-1880 historical map | scanned from the דן ירדני collection |
| Satellite imagery | Google |
| **Sites layer (אתרים)** | **`אתרים: © עמוד ענן`** |

So OSM supplies only the *trail geometry* on the basemap. The heritage points themselves
are עמוד ענן's own crowd-sourced wiki content. **There is therefore no OSM double-count
risk from this source** - but equally, there is no open licence to fall back on. The
about page confirms trails came from GPS tracks donated by נעם עציוני, not from OSM.

A separate mechanism does pull Wikipedia points (`en.wikipedia.org/w/api.php` geosearch),
but the code guards it with `if (inIsrael(lat, lon)) return;` - it fires **only outside
Israel**. Emek Yizrael is inside Israel, so no Wikipedia-sourced points would ever appear
in our window. Not a contamination vector.

---

## 3. The prohibition - verbatim

From https://amudanan.co.il/w/index.php/עמוד_ענן:הבהרה_משפטית
(saved at `data/raw/amudanan/wiki_legal_disclaimer.html`, page last modified per MediaWiki
footer; retrieved 2026-08-03):

> השימוש בחומר המוצג באתר הינו במסגרת כללי השימוש ההוגן. אין להעתיק חומר ללא אישור מפורש
> של בעלי האתר. **הורדת חומר ע״י מכונה או הנדסה לאחור של האתר אסורים** פרט ליצירת אינדקס
> לא-גיאוגרפי ע״י מנועי החיפוש הגדולים כדוגמת גוגל.

Translation: "Use of the material presented on the site is within the rules of fair use.
Material may not be copied without the explicit permission of the site owners. **Downloading
material by machine, or reverse engineering of the site, are forbidden**, except for the
creation of a non-geographic index by the large search engines such as Google."

Three separate barriers in one paragraph:

1. **Machine downloading is forbidden outright.** Our tile fetching is machine downloading.
2. **Reverse engineering the site is forbidden.** Reading the JS bundle to locate the JSON
   endpoint is exactly that.
3. **The sole exception does not fit us.** It is limited to a *non-geographic* index by
   major search engines. This project is a geographic index, and IICP is not a search
   engine. The exception cannot be stretched to cover us; if anything its wording shows
   the owner thought about geographic harvesting specifically and excluded it.

From https://amudanan.co.il/w/index.php/עמוד_ענן:זכויות_יוצרים
(`data/raw/amudanan/wiki_copyright.html`):

> כל הזכויות באתר ובתוכן שמורות לעמוד ענן. כל הזכויות על המפות שמורות לגופי המיפוי, ראו
> פירוט ב״אודות האתר״.

"All rights in the site and in the content are reserved to עמוד ענן." The content is
**all-rights-reserved**, with no open licence of any kind. `עמוד ענן:תנאי שימוש`
(terms-of-use) returns 404 - the disclaimer page above is the operative document.

### robots.txt conflicts with this, and loses

`https://amudanan.co.il/robots.txt` (saved) is fully permissive:

```
User-agent: *
Disallow:
Sitemap: http://amudanan.co.il/services/sitemap.php
```

A permissive robots.txt does not override an explicit, specific, human-readable
prohibition on machine downloading. Where the two conflict the narrower express term
governs. Anyone re-reading this file should not take the open robots.txt as a green light.

---

## 4. What was retrieved before the prohibition was found, and what happened to it

Full disclosure of the sequence, because it matters for the audit:

1. Fetched `robots.txt`, the homepage, and the 63 MB sitemap.
2. Fetched the two JS bundles (`/cache/min/min1ver1.js`, `/min2ver25.js`) and grepped them
   for endpoints - this located the JSON POI endpoint.
3. Fetched one test tile to confirm the schema.
4. In the same scripted run that fetched the legal-disclaimer page, fetched the **30 JSON
   POI tiles** covering the search window (all HTTP 200, ~52,786 point rows in total
   before de-duplication and before any heritage filtering). Rate limited to one request
   per ~1.3 s, descriptive User-Agent, no parallelism, no raster tile downloading.
5. Read the disclaimer, recognised the prohibition, and **stopped**. No further requests
   were made to the host.
6. **Deleted** the harvested content payloads: all 30 tile JSONs, the test tile, the 63 MB
   sitemap, and the two JS bundles.

### Known tension with the project's hard rules - flagged deliberately

Hard rule 2 of the task brief says every raw payload must be saved byte-for-byte in
`data/raw/`. I deliberately broke that rule for this source, judging that the task's
source-specific instruction ("If it ... clearly forbids automated access in its terms,
stop, report exactly what it says, and deliver whatever you could obtain legitimately")
plus the reality that this repo is destined for **public publication** outweighed it.
Keeping ~40 MB of all-rights-reserved crowd-sourced content inside a repo that will be
published, from a source that expressly forbids copying without permission, seemed a worse
outcome for IICP than losing the bytes. **This is a judgment call I made without being
asked, and whoever reviews this should know it was mine, not a given.** The data is
re-obtainable at any time - but only with the owner's permission, which is the correct
route regardless.

### What remains in `data/raw/amudanan/`

Only documentary evidence, no site content:

| File | What it is |
|---|---|
| `robots.txt` | 77 b, the permissive robots policy quoted above |
| `homepage.html` | 22 kB, one ordinary page fetch; contains the layer checkboxes |
| `wiki_about.html` | about page - attribution table, editor's name, contact address |
| `wiki_copyright.html` | the all-rights-reserved statement |
| `wiki_legal_disclaimer.html` | **the operative prohibition** |
| `wiki_terms.html` | 404 placeholder for `תנאי שימוש` |
| `tiles_manifest.json` | per-tile URL, HTTP status, byte size, point count, timestamp. Aggregate metadata only - contains no POI records |

---

## 5. The endpoint, documented so nobody rediscovers and re-scrapes it

Recorded for the sole purpose of letting a future reader recognise this endpoint as
off-limits, and to let IICP describe precisely what it would be asking permission for.

**JSON POI tiles** (Web Mercator XYZ, **zoom 12 only**):

```
https://amudanan.co.il/cache/tiles/z_x1_{z}_x2_y_x1_{y}_x2_x_x1_{x}_x2_layers_x1_points.json
```

Uncached sibling, same payload: `services/ajax.php?actions=gettile&rand={r}&z={z}&y={y}&x={x}&type=json&showprivatepoints={bool}`

The client calls it from `downloadJsonForTile(z, y, x, useCache)`, always with `z = 12`
(`0xc` in the obfuscated source), driven by `requestPointsInBounds()` on map idle. Tile
indices are standard slippy-map: `x = floor((lon+180)/360 * 2^z)`,
`y = floor((1 - ln(tan φ + sec φ)/π)/2 * 2^z)`.

For our window (lat 32.55-32.85, lon 35.05-35.50) that is x 2446-2451, y 1651-1655 = 30 tiles.

Response shape: `{"points": [ ... ], "aaa": ...}`. Per-point fields observed:

| Field | Meaning | Notes |
|---|---|---|
| `id` | numeric POI id as string | client prefixes `P` -> wiki page `/w/index.php/P<id>` |
| `title` | site name (Hebrew) | falls back to `name` |
| `pointtype` | **the source's own category** | Hebrew free-ish vocabulary, e.g. `חקלאות עתיקה`, `מבנים ומקומות - אחר` |
| `description` | free-text description (Hebrew) | the substantive copyrighted content |
| `lat`, `lon` | **WGS84 decimal degrees, as strings** | native CRS is WGS84 here; the UI converts to ITM/ICS only for display |
| `alt` | elevation, metres | client maps it to `height`; served by `elev1.amudanan.co.il/api/v1/lookup` |
| `accessibility` | accessibility hint | present on a subset of records only |
| `images` | comma-separated image filenames | resolve via `/services/thumb.php?file=../w/images/<name>&size=<px>` |
| `contributors` | comma-separated usernames | crowd-sourcing provenance |
| `lastupdate` | Unix epoch seconds | as string |
| `public` | `"1"` public, `"0"` private | private points belong to the logged-in user |

**Native CRS: WGS84 (EPSG:4326)**, degrees, in the `lat`/`lon` fields directly - no
ITM/ICS conversion would have been needed. Worth knowing: the client *does* carry ITM
(EPSG:2039) and ICS (EPSG:28193) converters and distinguishes them by y magnitude
(`y > 0xcf850` = 850,000 -> ICS), which matches this project's own rule 8.

Other endpoints seen in the bundle, all equally covered by the prohibition:
`/services/ajax.php?actions=getpoint&pointid=`, `getroute`, `suggestlocation`;
`/services/findLocation.php?q=`; `/services/parseStream.php?url=|polylineid=`;
`/services/gettile.php`; `/services/thumb.php`; `/forms/my.php`; `/forms/savepath.php`;
`kalanit/viewgrid.php`. No documented public developer API and no separate mobile-app API
were found; the Android app is mentioned on the about page but no endpoint for it surfaced.

---

## 6. Scale it would have contributed, if licensed

Aggregate facts only (counts are not protectable expression), so IICP can judge whether
seeking permission is worth the effort:

- 30 tiles covering the window, all HTTP 200.
- **~52,786 raw point rows** total, before de-duplication across tile edges and before any
  heritage/culture filtering. Density is very uneven: 11 rows in the emptiest tile
  (z12/y1651/x2446, mostly sea/Haifa bay edge) up to 11,640 in the densest
  (z12/y1655/x2448).
- Most of that volume is *not* in scope - it is trail waypoints, viewpoints, water points
  and similar nature/navigation points that the task brief tells us to exclude.
- `pointtype` values genuinely relevant to us were present, e.g. `חקלאות עתיקה` (ancient
  agriculture - wine presses, oil presses) on records that named `גת` and `בית בד`. This
  is a real heritage layer with field-verified detail and photographs, and it is the kind
  of granular, locally-known material that רשות העתיקות and שימור אתרים lists do not have.

Honest assessment: this is the richest crowd-sourced heritage POI set for the area that I
found, and losing it is a real loss to coverage. It is not, however, a loss of
*authoritative* status data - the source is explicitly unverified (section 3's disclaimer
disclaims correctness) and its per-site "status" fields are `accessibility` free text and
nothing more. No declaration numbers, no licence numbers, no IAA site numbers, no
statutory status. It would have been a coverage and description enrichment, not a
status backbone.

---

## 7. If IICP wants this source: the permission route

The disclaimer bars copying "ללא אישור מפורש של בעלי האתר" - without the owners' explicit
permission. So permission cures it. Contact details from the about page:

- Founder and chief editor: **יואב רופא**
- Postal address given on the about page: רימון 349, ת.ד. 84, צור הדסה 99875
- Contact e-mail addresses on the about page are obfuscated by Cloudflare
  (`[email protected]`) and were **not** recovered - do not guess them; open the about
  page in a browser to read them.
- The about page actively invites partnership: *"שיתופי פעולה מכל סוג יתקבלו בברכה!"*
  ("collaborations of any kind are welcome!"), and lists an existing partnership with the
  ״לטייל בבטיחות״ safety project. A public-interest heritage map by a registered non-profit
  is a plausible thing for them to say yes to.

If permission is obtained, get it in writing, and get it to cover specifically: bulk
retrieval of the `points.json` tiles, storage, and **public re-publication** of the fields
IICP intends to show (name, category, coordinates, and whether description text may be
reproduced or must be paraphrased/linked). Attribution `© עמוד ענן` with a link back to
`https://amudanan.co.il/#!wiki=P<id>` should be offered regardless.

---

## 8. Politeness record

- Rate: one request per ~1.3 s, strictly sequential, single connection, no parallelism.
- User-Agent: `IICP-EmekYizraelMap/1.0 (heritage sites research for Emek Yizrael Regional Council; matan@iicp.org.il)` - identifying, with a real contact address.
- Total requests to the host across the whole session: ~40.
- No raster/basemap tiles were downloaded at any point.
- No login was attempted; no authentication wall was encountered (the prohibition is
  contractual, not technical).
- No block, CAPTCHA, rate-limit or 4xx/5xx throttling response was ever received. The site
  is fronted by Cloudflare but never challenged us. **We stopped because of the stated
  terms, not because we were stopped.**

---

## 9. Limitations of this source (moot, but recorded)

- Crowd-sourced and explicitly disclaimed as unverified: *"אין בעלי האתר, העורכים, ו/או
  הגולשים אחראים לנכונותו ולעדכניותו"*.
- No authoritative identifiers, so it could only ever have been joined to other sources
  fuzzily, by name and coordinate proximity.
- `pointtype` is an uncontrolled vocabulary with catch-all values (`מבנים ומקומות - אחר`),
  so mapping it onto the project's three categories would have needed manual review.
- JSON POI data exists at zoom 12 only; there is no bbox or attribute query, so any
  extraction is necessarily whole-tile.
- `accessibility` is sparse free text. The disclaimer warns users to check independently
  whether an area is a closed military zone or live-fire zone (*"שטח סגור או ... שטח אש"*);
  the data does not carry that as a field.
