/* ==========================================================================
   אתרי תרבות ומורשת בעמק יזרעאל
   המכון הישראלי למדיניות תרבות

   No build step and no framework: one payload, one file, plain DOM. The whole
   vocabulary (labels, status values, tones, period spans) arrives inside
   data/sites.json from src/schema.py, so nothing here restates it.
   ========================================================================== */
'use strict';

const DATA_URL = 'data/sites.json';
const CLAIMS_URL = 'data/claims.json';
const BOUNDARY_URL = 'data/boundary.geojson';

const BASEMAPS = {
  ihm: {
    label: 'שבילי ישראל',
    tiles: ['https://israelhiking.osm.org.il/Hebrew/Tiles/{z}/{x}/{y}.png'],
    maxzoom: 16,
    attrib: 'מפת בסיס: <a href="https://israelhiking.osm.org.il/" target="_blank" rel="noopener">מפת שבילי ישראל</a> · נתונים: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
  },
  osm: {
    label: 'OSM',
    tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
    maxzoom: 19,
    attrib: 'מפת בסיס: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
  },
  sat: {
    label: 'תצלום אוויר',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    maxzoom: 18,
    attrib: 'תצלום אוויר: Esri, Maxar, Earthstar Geographics',
  },
};

/* --------------------------------------------------------------- app state */
const S = {
  vocab: null,
  sites: [],
  view: 'map',
  base: 'ihm',
  selected: null,
  claims: null,
  boundary: null,
  filtered: [],
};

const F = {
  q: '',
  cats: new Set(),
  periods: new Set(),
  status: {},           // axis -> Set(values)
  types: new Set(),
  localities: new Set(),
  minConf: 0,
  showOutside: false,
  onlyReview: false,
};

/* ------------------------------------------------------------------- utils */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k === 'text') n.textContent = v;
    else if (k === 'style') n.setAttribute('style', v);
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) {
    n.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return n;
}

const num = n => (n === null || n === undefined || Number.isNaN(n) ? '—' : n.toLocaleString('he-IL'));
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);

function yearLabel(y) {
  if (y === null || y === undefined) return null;
  return y < 0 ? `${Math.abs(y).toLocaleString('he-IL')} לפנה"ס` : `${y.toLocaleString('he-IL')} לספירה`;
}

function catColor(cat) {
  const map = { archaeological: '--arch', historic: '--hist', culture: '--cult' };
  return getComputedStyle(document.documentElement).getPropertyValue(map[cat] || '--gap').trim();
}

/* glyph: shape carries identity alongside colour, so neither rests on the other */
function glyph(cat, size = 13) {
  const c = catColor(cat);
  const s = size;
  let inner;
  if (cat === 'archaeological') inner = `<path d="M1.5 ${s - 2} L${s - 1.5} ${s - 2} L${s * .74} ${s * .3} L${s * .26} ${s * .3} Z"/>`;
  else if (cat === 'historic') inner = `<rect x="${s * .17}" y="${s * .17}" width="${s * .66}" height="${s * .66}" rx="1"/>`;
  else inner = `<circle cx="${s / 2}" cy="${s / 2}" r="${s * .35}"/>`;
  return el('span', {
    class: 'glyph',
    style: `display:inline-block;width:${s}px;height:${s}px;color:${c}`,
    html: `<svg width="${s}" height="${s}" viewBox="0 0 ${s} ${s}" fill="currentColor" aria-hidden="true">${inner}</svg>`,
  });
}

/* tooltip shared by every chart mark */
const TIP = $('#tip');
function tipOn(node, text) {
  node.addEventListener('mouseenter', () => { TIP.textContent = text; TIP.hidden = false; });
  node.addEventListener('mousemove', e => {
    TIP.style.left = Math.min(e.clientX + 12, innerWidth - TIP.offsetWidth - 8) + 'px';
    TIP.style.top = (e.clientY + 16) + 'px';
  });
  node.addEventListener('mouseleave', () => { TIP.hidden = true; });
  node.setAttribute('aria-label', text);
}

const TONE_VAR = { good: '--ok', warn: '--warn', bad: '--bad', gap: '--gap', neutral: '--ink-3' };
const toneColor = t => getComputedStyle(document.documentElement).getPropertyValue(TONE_VAR[t] || '--gap').trim();

/* ------------------------------------------------------------------- boot */
async function boot() {
  const bars = $('#loading .bars');
  for (let i = 0; i < 18; i++) {
    bars.append(el('i', { style: `animation-delay:${i * 28}ms` }));
  }
  try {
    const payload = await (await fetch(DATA_URL)).json();
    S.vocab = payload.vocab;
    S.sites = payload.sites;
    S.generated = payload.generated;
    S.council = payload.council;
  } catch (e) {
    $('#loading').innerHTML = '<p>לא הצלחנו לטעון את הנתונים. רעננו את הדף או נסו שוב מאוחר יותר.</p>';
    return;
  }
  try { S.boundary = await (await fetch(BOUNDARY_URL)).json(); } catch (e) { S.boundary = null; }

  for (const axis of Object.keys(S.vocab.status_axes)) F.status[axis] = new Set();
  F.status.reg_summary = new Set();

  readHash();
  buildRail();
  initMap();
  wire();
  apply();
  renderAbout();
  $('#loading').remove();
}

/* --------------------------------------------------------------- filtering */
// Which settlement a site belongs to for grouping. A sourced locality always wins; where no
// source named one, the computed nearest settlement stands in, and the interface says so
// rather than presenting it as a fact from a source.
function placeOf(s) { return s.locality || s.nearest_settlement || '—'; }
function placeIsDerived(s) { return !s.locality && !!s.nearest_settlement; }

function textOf(s) {
  return [s.name, s.name_en, s.locality, S.vocab.site_types[s.type]?.he,
    ...(s.rest?.names_alt || []).map(a => a.name), s.rest?.address, s.rest?.operator]
    .filter(Boolean).join(' ').toLowerCase();
}

function passes(s, skip) {
  if (!F.showOutside && s.in_council === false) return false;
  if (F.onlyReview && !s.needs_review) return false;
  if (s.confidence < F.minConf) return false;
  if (skip !== 'q' && F.q) {
    if (!(s._txt ??= textOf(s)).includes(F.q)) return false;
  }
  if (skip !== 'cats' && F.cats.size) {
    if (!(s.categories || [s.category]).some(c => F.cats.has(c))) return false;
  }
  if (skip !== 'periods' && F.periods.size) {
    if (!(s.periods || []).some(p => F.periods.has(p))) return false;
  }
  if (skip !== 'types' && F.types.size && !F.types.has(s.type || 'unknown')) return false;
  if (skip !== 'localities' && F.localities.size && !F.localities.has(placeOf(s))) return false;
  for (const [axis, set] of Object.entries(F.status)) {
    if (!set.size || skip === axis) continue;
    if (!set.has(s[axis] || 'unknown')) return false;
  }
  return true;
}

function countFor(skip, get) {
  const c = new Map();
  for (const s of S.sites) {
    if (!passes(s, skip)) continue;
    for (const v of get(s)) c.set(v, (c.get(v) || 0) + 1);
  }
  return c;
}

function apply() {
  S.filtered = S.sites.filter(s => passes(s, null));
  // The header must not imply that every counted point is drawn: a site with no coordinate
  // is real and stays in the table and the counts, but it cannot be placed on the map.
  const mappable = S.filtered.filter(s => s.lat !== null && s.lat !== undefined).length;
  const gap = S.filtered.length - mappable;
  $('#countN').textContent = num(S.filtered.length);
  $('#countLabel').textContent = [
    S.filtered.length === S.sites.length ? 'נקודות' : `מתוך ${num(S.sites.length)}`,
    gap ? `· ${num(mappable)} על המפה, ${num(gap)} ללא קואורדינטה` : '',
  ].filter(Boolean).join(' ');
  refreshCounts();
  if (S.view === 'map') renderMap();
  if (S.view === 'table') renderTable();
  if (S.view === 'metrics') renderMetrics();
  writeHash();
  const active = F.q || F.cats.size || F.periods.size || F.types.size || F.localities.size
    || F.minConf > 0 || F.onlyReview || F.showOutside
    || Object.values(F.status).some(s => s.size);
  $('#resetBtn').disabled = !active;
}

/* --------------------------------------------------------------- rail build */
function buildRail() {
  // categories
  const cats = $('#cats');
  for (const [key, meta] of Object.entries(S.vocab.categories)) {
    const b = el('button', {
      class: 'cat', 'data-cat': key, type: 'button', 'aria-pressed': 'false',
      onclick: () => { toggle(F.cats, key); syncCats(); apply(); },
    }, glyph(key, 14), el('span', { class: 'label', text: meta.he }), el('span', { class: 'n', 'data-n': key, text: '0' }));
    b.title = meta.note;
    cats.append(b);
  }

  // the stratigraphic section
  const box = $('#strata');
  const periods = S.vocab.periods;
  const cutoff = S.vocab.antiquity_cutoff;
  periods.forEach((p, i) => {
    if (i > 0 && periods[i - 1].to <= cutoff && p.from >= cutoff) {
      box.append(el('div', { class: 'antiquity-line', 'aria-hidden': 'true' },
        el('span', { class: 'yr', text: String(cutoff) }),
        el('span', { text: 'קו העתיקות' }),
        el('span', { class: 'hint', text: 'מכאן ומעלה: מורשת' })));
    }
    const b = el('button', {
      class: 'stratum', type: 'button', 'data-period': p.key, 'data-era': p.era,
      'aria-pressed': 'false',
      onclick: () => { toggle(F.periods, p.key); syncStrata(); apply(); },
    }, el('span', { class: 'fill', 'data-fill': p.key, style: 'width:0' }),
      el('span', { class: 'nm', text: p.he }),
      el('span', { class: 'n', 'data-pn': p.key, text: '0' }));
    b.title = `${p.he}: ${yearLabel(p.from)} עד ${yearLabel(p.to)}`;
    box.append(b);
  });
  $('#strataCaption').textContent =
    `החתך נקרא מלמטה למעלה, מהקדום לחדש. עובי הפס הוא מספר האתרים בתקופה. ` +
    `חוק העתיקות מגדיר עתיקות כשרידים מלפני ${cutoff}, ולכן הקו מסמן את הגבול שבין אחריות רשות העתיקות לאחריות המועצה לשימור אתרי מורשת. ` +
    `לתקופות אין תוקף למוסדות תרבות.`;

  // status facets. Order is editorial: what a visitor asks first comes first.
  const order = ['reg_summary', 'excavation', 'accessibility', 'activity', 'signage',
    'reg_antiquity', 'reg_conservation', 'reg_institution', 'protected_area',
    'condition', 'a11y_disabled', 'visitor_dev', 'ownership'];
  const openByDefault = new Set(['reg_summary', 'excavation', 'accessibility']);
  const host = $('#facets');

  for (const axis of order) {
    const isDerived = axis === 'reg_summary';
    const label = isDerived ? 'רישום והכרזה' : S.vocab.status_axes[axis].he;
    const values = isDerived
      ? Object.entries(S.vocab.reg_summary).map(([key, he]) => ({ key, he, tone: key === 'registered' ? 'good' : key === 'not_registered' ? 'bad' : 'gap' }))
      : S.vocab.status_axes[axis].values;
    host.append(facet(axis, label, values, openByDefault.has(axis),
      isDerived ? 'מחושב מארבעה צירי רישום: הכרזת עתיקות, סימון לשימור, רישום מוסדי ושטח מוגן.' : null));
  }

  // type and locality facets are built from the data itself
  host.append(facet('types', 'סוג האתר', null, false, null));
  host.append(facet('localities', 'יישוב', null, false,
    'רוב האתרים הארכאולוגיים נמצאים בשטח חקלאי פתוח ואף מקור אינו מציין יישוב עבורם. במקרים האלה מוצג היישוב הקרוב ביותר, בחישוב שלנו, כדי לאפשר התמצאות. שיוך שהגיע ממקור מסומן בכרטיס האתר.'));

  // data quality
  host.append(qualityFacet());
}

function facet(axis, label, values, open, note) {
  const opts = el('div', { class: 'opts' });
  const wrap = el('section', { class: 'facet', 'data-open': open ? 'true' : 'false', 'data-axis': axis },
    el('button', {
      class: 'fhead', type: 'button', 'aria-expanded': open ? 'true' : 'false',
      onclick: e => {
        const w = e.currentTarget.closest('.facet');
        const nowOpen = w.dataset.open !== 'true';
        w.dataset.open = nowOpen ? 'true' : 'false';
        e.currentTarget.setAttribute('aria-expanded', String(nowOpen));
      },
    }, el('span', { text: label }), el('span', { class: 'n', 'data-fn': axis }),
      el('span', {
        class: 'chev', html: '<svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M2.5 4l2.5 2.5L7.5 4"/></svg>',
      })),
    note ? el('p', { class: 'strata-caption', style: 'padding-top:0;margin:0 0 .4rem', text: note }) : null,
    opts);
  wrap._values = values;
  wrap._opts = opts;
  return wrap;
}

function qualityFacet() {
  const set = key => v => { F[key] = v; apply(); };
  const conf = el('input', {
    type: 'range', min: '0', max: '95', step: '5', value: '0', id: 'confRange',
    style: 'width:100%',
    oninput: e => { $('#confVal').textContent = e.target.value + '%'; set('minConf')(Number(e.target.value) / 100); },
  });
  return el('section', { class: 'facet', 'data-open': 'false', 'data-axis': 'quality' },
    el('button', {
      class: 'fhead', type: 'button', 'aria-expanded': 'false',
      onclick: e => {
        const w = e.currentTarget.closest('.facet');
        const o = w.dataset.open !== 'true';
        w.dataset.open = o ? 'true' : 'false';
        e.currentTarget.setAttribute('aria-expanded', String(o));
      },
    }, el('span', { text: 'איכות הנתון' }),
      el('span', { class: 'chev', html: '<svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M2.5 4l2.5 2.5L7.5 4"/></svg>' })),
    el('div', { class: 'opts' },
      el('label', { class: 'opt', style: 'cursor:default', for: 'confRange' },
        el('span', { class: 'nm', text: 'רמת ודאות מזערית' }),
        el('span', { class: 'n', id: 'confVal', text: '0%' })),
      conf,
      checkRow('הצגת נקודות שדורשות בדיקה בלבד', () => F.onlyReview, v => { F.onlyReview = v; apply(); }),
      checkRow('הצגת נקודות מחוץ לגבול השיפוט', () => F.showOutside, v => { F.showOutside = v; apply(); },
        'ברירת המחדל מסתירה אותן. הן נשמרות במאגר כדי שההחרגה תהיה בדיקה ולא מחיקה.')));
}

function checkRow(label, get, setv, note) {
  const b = el('button', {
    class: 'opt', type: 'button', 'aria-pressed': String(get()),
    onclick: e => { const v = e.currentTarget.getAttribute('aria-pressed') !== 'true'; e.currentTarget.setAttribute('aria-pressed', String(v)); setv(v); },
  }, el('span', {
    class: 'box', html: '<svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M2 5.2l2 2L8 3"/></svg>',
  }), el('span', { class: 'nm', text: label }));
  if (note) b.title = note;
  return b;
}

function toggle(set, v) { set.has(v) ? set.delete(v) : set.add(v); }

function syncCats() {
  $$('#cats .cat').forEach(b => b.setAttribute('aria-pressed',
    String(F.cats.size === 0 || F.cats.has(b.dataset.cat))));
  if (F.cats.size === 0) $$('#cats .cat').forEach(b => b.setAttribute('aria-pressed', 'false'));
}
function syncStrata() {
  $$('#strata .stratum').forEach(b => b.setAttribute('aria-pressed', String(F.periods.has(b.dataset.period))));
}

/* facet option lists are rebuilt on every apply so counts stay honest: the count
   beside a value is how many sites you would get if you added it to the current
   filter, not a static total. */
function refreshCounts() {
  const catC = countFor('cats', s => s.categories || [s.category]);
  $$('#cats .n').forEach(n => n.textContent = num(catC.get(n.dataset.n) || 0));
  syncCats();

  const perC = countFor('periods', s => s.periods || []);
  const maxP = Math.max(1, ...perC.values());
  $$('#strata .stratum').forEach(b => {
    const c = perC.get(b.dataset.period) || 0;
    b.querySelector('[data-pn]').textContent = c ? num(c) : '';
    b.querySelector('.fill').style.width = (c / maxP * 100).toFixed(1) + '%';
    b.dataset.empty = c === 0 && !F.periods.has(b.dataset.period) ? 'true' : 'false';
    b.disabled = c === 0 && !F.periods.has(b.dataset.period);
  });
  syncStrata();

  for (const wrap of $$('#facets .facet')) {
    const axis = wrap.dataset.axis;
    if (axis === 'quality') continue;
    let values = wrap._values;
    let getter;
    if (axis === 'types') {
      getter = s => [s.type || 'unknown'];
      const c = countFor('types', getter);
      values = [...c.keys()].sort((a, b) => c.get(b) - c.get(a))
        .map(k => ({ key: k, he: S.vocab.site_types[k]?.he || k, tone: 'neutral' }));
    } else if (axis === 'localities') {
      getter = s => [placeOf(s)];
      const c = countFor('localities', getter);
      values = [...c.keys()].sort((a, b) => (c.get(b) - c.get(a)) || a.localeCompare(b, 'he'))
        .map(k => ({ key: k, he: k === '—' ? 'ללא שיוך' : k, tone: 'neutral' }));
    } else {
      getter = s => [s[axis] || 'unknown'];
    }
    const counts = countFor(axis, getter);
    const max = Math.max(1, ...counts.values());
    const set = F.status[axis] || (F[axis] instanceof Set ? F[axis] : null);
    const target = axis === 'types' ? F.types : axis === 'localities' ? F.localities : F.status[axis];

    wrap._opts.replaceChildren(...values
      .filter(v => (counts.get(v.key) || 0) > 0 || target.has(v.key))
      .map(v => {
        const c = counts.get(v.key) || 0;
        const on = target.has(v.key);
        return el('button', {
          class: 'opt', type: 'button', 'aria-pressed': String(on),
          'data-unknown': String(v.key === 'unknown' || v.key === '—'),
          onclick: () => { toggle(target, v.key); apply(); },
        }, el('span', { class: 'bar', style: `width:${(c / max * 100).toFixed(1)}%` }),
          el('span', { class: 'box', html: '<svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M2 5.2l2 2L8 3"/></svg>' }),
          el('span', { class: 'nm', text: v.he }),
          el('span', { class: 'n', text: num(c) }));
      }));
    const sel = target.size;
    wrap.querySelector('[data-fn]').textContent = sel ? `${sel} נבחרו` : '';
  }
}

/* --------------------------------------------------------------------- map */
// Shape carries the category, fill carries how well we know WHERE the thing is. A solid mark
// is a position from a source; a hollow mark is a settlement centre standing in for an
// institution we could not pin down, and it must not look like a surveyed point.
function markerImage(cat, size = 34, approx = false) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  const x = c.getContext('2d');
  const col = catColor(cat);
  const ring = getComputedStyle(document.documentElement).getPropertyValue('--panel').trim() || '#fff';
  const s = size, m = s * 0.13;
  x.lineWidth = s * 0.13;
  x.strokeStyle = ring;
  x.shadowColor = 'rgba(20,26,22,.45)';
  x.shadowBlur = s * 0.09;
  x.fillStyle = col;
  const path = () => {
    x.beginPath();
    if (cat === 'archaeological') {
      x.moveTo(m, s - m); x.lineTo(s - m, s - m); x.lineTo(s * 0.72, m * 1.9); x.lineTo(s * 0.28, m * 1.9); x.closePath();
    } else if (cat === 'historic') {
      const a = m * 1.35, w = s - a * 2;
      x.roundRect ? x.roundRect(a, a, w, w, s * 0.06) : x.rect(a, a, w, w);
    } else {
      x.arc(s / 2, s / 2, s / 2 - m * 1.4, 0, Math.PI * 2);
    }
  };
  path(); x.stroke(); x.fill();
  if (approx) {
    // Punch the middle out so the mark reads as an outline.
    x.shadowColor = 'transparent';
    x.globalCompositeOperation = 'destination-out';
    x.save();
    x.translate(s / 2, s / 2); x.scale(0.5, 0.5); x.translate(-s / 2, -s / 2);
    path(); x.fill();
    x.restore();
    x.globalCompositeOperation = 'source-over';
  }
  return x.getImageData(0, 0, size, size);
}

const APPROX_PRECISION = new Set(['locality_centroid', 'approx_500m', 'unknown']);

function scrimFrom(boundary) {
  // Everything that is NOT the council, dimmed, so the jurisdiction reads as the subject.
  //
  // The council is a doughnut: it wraps around Afula, Nazareth, Migdal HaEmek, Yokneam Illit
  // and others, which appear as interior rings. Punching out only the OUTER rings leaves
  // those cities undimmed, so the map would show them as though they belonged to the
  // council. So the interior rings are added back as their own solid parts of the scrim.
  const outer = [];
  const holes = [];
  const eatPoly = coords => {
    if (!coords || !coords.length) return;
    outer.push(coords[0]);
    for (let i = 1; i < coords.length; i++) holes.push([coords[i]]);
  };
  const eat = g => {
    if (!g) return;
    if (g.type === 'Polygon') eatPoly(g.coordinates);
    else if (g.type === 'MultiPolygon') g.coordinates.forEach(eatPoly);
    else if (g.type === 'GeometryCollection') g.geometries.forEach(eat);
  };
  if (boundary.type === 'FeatureCollection') boundary.features.forEach(f => eat(f.geometry));
  else eat(boundary.geometry || boundary);
  if (!outer.length) return null;
  const world = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
  return {
    type: 'Feature', properties: {}, geometry: {
      type: 'MultiPolygon',
      coordinates: [[world, ...outer], ...holes],
    },
  };
}

function initMap() {
  const b = BASEMAPS[S.base];
  S.map = new maplibregl.Map({
    container: 'map',
    style: {
      version: 8,
      sources: { base: { type: 'raster', tiles: b.tiles, tileSize: 256, maxzoom: b.maxzoom, attribution: '' } },
      layers: [{ id: 'base', type: 'raster', source: 'base' }],
    },
    center: [35.25, 32.68], zoom: 10.2, minZoom: 8, maxZoom: 18,
    attributionControl: false, hash: false,
  });
  $('#attrib').innerHTML = b.attrib;

  S.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
  S.map.addControl(new maplibregl.ScaleControl({ maxWidth: 90, unit: 'metric' }), 'bottom-right');
  S.map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), 'top-left');

  S.map.on('load', () => {
    for (const cat of Object.keys(S.vocab.categories)) {
      S.map.addImage('m-' + cat, markerImage(cat, 34, false), { pixelRatio: 2 });
      S.map.addImage('m-' + cat + '-approx', markerImage(cat, 34, true), { pixelRatio: 2 });
    }

    if (S.boundary) {
      const scrim = scrimFrom(S.boundary);
      if (scrim) {
        S.map.addSource('scrim', { type: 'geojson', data: scrim });
        S.map.addLayer({
          id: 'scrim', type: 'fill', source: 'scrim',
          paint: { 'fill-color': '#0d130f', 'fill-opacity': 0.3 },
        });
      }
      S.map.addSource('bnd', { type: 'geojson', data: S.boundary });
      S.map.addLayer({
        id: 'bnd-line', type: 'line', source: 'bnd',
        paint: { 'line-color': '#1c231f', 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.1, 14, 2.4], 'line-opacity': 0.75 },
      });
      fitBoundary();
    }

    S.map.addSource('pts', { type: 'geojson', data: fc([]) });
    S.map.addLayer({
      id: 'sel', type: 'circle', source: 'pts',
      filter: ['==', ['get', 'id'], ''],
      paint: { 'circle-radius': 15, 'circle-color': 'transparent', 'circle-stroke-width': 2.5, 'circle-stroke-color': '#1c231f' },
    });
    S.map.addLayer({
      id: 'pts', type: 'symbol', source: 'pts',
      layout: {
        'icon-image': ['concat', 'm-', ['get', 'category'],
          ['case', ['get', 'approx'], '-approx', '']],
        // The Israel Hiking base map is dense with trails and contours, so the marks have to
        // hold their own against it: bigger than a default dot, with a thick surface ring.
        'icon-size': ['interpolate', ['linear'], ['zoom'], 9, 0.46, 11, 0.56, 13, 0.68, 16, 0.86],
        'icon-allow-overlap': true, 'icon-ignore-placement': true,
      },
    });

    let pop = null;
    S.map.on('mouseenter', 'pts', () => { S.map.getCanvas().style.cursor = 'pointer'; });
    S.map.on('mouseleave', 'pts', () => { S.map.getCanvas().style.cursor = ''; if (pop) { pop.remove(); pop = null; } });
    S.map.on('mousemove', 'pts', e => {
      const p = e.features[0].properties;
      if (pop) pop.remove();
      pop = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 14, className: 'hoverpop' })
        .setLngLat(e.features[0].geometry.coordinates)
        .setHTML(`<div class="pop-t">${escapeHtml(p.name)}</div><div class="pop-m">${escapeHtml(p.sub)}</div>`)
        .addTo(S.map);
    });
    S.map.on('click', 'pts', e => select(e.features[0].properties.id));
    renderMap();
  });
}

function fitBoundary() {
  let minx = 180, miny = 90, maxx = -180, maxy = -90;
  const walk = c => {
    if (typeof c[0] === 'number') {
      minx = Math.min(minx, c[0]); maxx = Math.max(maxx, c[0]);
      miny = Math.min(miny, c[1]); maxy = Math.max(maxy, c[1]);
    } else c.forEach(walk);
  };
  const eat = g => g && walk(g.coordinates);
  if (S.boundary.type === 'FeatureCollection') S.boundary.features.forEach(f => eat(f.geometry));
  else eat(S.boundary.geometry || S.boundary);
  if (minx < maxx) S.map.fitBounds([[minx, miny], [maxx, maxy]], { padding: 36, duration: 0 });
}

function fc(sites) {
  return {
    type: 'FeatureCollection',
    features: sites.filter(s => s.lat !== null && s.lat !== undefined).map(s => ({
      type: 'Feature', id: undefined,
      properties: {
        id: s.id, name: s.name || 'ללא שם', category: s.category,
        approx: APPROX_PRECISION.has(s.location_precision),
        sub: [S.vocab.categories[s.category]?.he, placeOf(s) === '—' ? null : placeOf(s),
          S.vocab.site_types[s.type]?.he,
          APPROX_PRECISION.has(s.location_precision) ? 'מיקום מקורב' : null].filter(Boolean).join(' · '),
      },
      geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
    })),
  };
}

function renderMap() {
  if (!S.map || !S.map.getSource('pts')) return;
  S.map.getSource('pts').setData(fc(S.filtered));
  if (S.map.getLayer('sel')) S.map.setFilter('sel', ['==', ['get', 'id'], S.selected || '']);
}

function setBase(key) {
  S.base = key;
  const b = BASEMAPS[key];
  S.map.getSource('base').setTiles(b.tiles);
  $('#attrib').innerHTML = b.attrib;
  $$('.basemap-switch button').forEach(x => x.setAttribute('aria-pressed', String(x.dataset.base === key)));
  writeHash();
}

const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ---------------------------------------------------------- detail panel */
async function select(id) {
  const s = S.sites.find(x => x.id === id);
  if (!s) return;
  S.selected = id;
  renderMap();
  const d = $('#detail');
  $('#dName').textContent = s.name || 'ללא שם';
  $('#dGlyph').replaceWith(Object.assign(glyph(s.category, 15), { id: 'dGlyph' }));
  $('#dMeta').textContent = [S.vocab.categories[s.category]?.he, s.locality,
    S.vocab.site_types[s.type]?.he].filter(Boolean).join(' · ');
  $('#dBody').replaceChildren(...detailSections(s));
  d.dataset.open = 'true';
  d.focus();
  if (s.lat !== null && s.lat !== undefined && S.view === 'map') {
    S.map.easeTo({ center: [s.lon, s.lat], zoom: Math.max(S.map.getZoom(), 13.5), duration: 500 });
  }
  if (!S.claims) {
    try {
      const j = await (await fetch(CLAIMS_URL)).json();
      S.claims = j.claims || {};
      S.detail = j.detail || {};
    } catch (e) { S.claims = {}; S.detail = {}; }
    if (S.selected === id) $('#dBody').replaceChildren(...detailSections(s));
  }
}

function kv(pairs) {
  const dl = el('dl', { class: 'kv' });
  for (const [k, v, src] of pairs) {
    if (v === null || v === undefined || v === '') continue;
    dl.append(el('dt', { text: k }));
    const dd = el('dd', {}, v instanceof Node ? v : String(v));
    if (src) dd.append(el('span', { class: 'src', text: ` · ${src}` }));
    dl.append(dd);
  }
  return dl.children.length ? dl : null;
}

function gapDd(text) { return el('span', { class: 'gap', text }); }

function statusPill(axis, val) {
  const meta = S.vocab.status_axes[axis];
  const v = meta.values.find(x => x.key === (val || 'unknown')) || { he: val, tone: 'gap' };
  const cls = { good: 'on', bad: 'off', warn: 'mid', gap: 'gap', neutral: '' }[v.tone] || '';
  return el('span', { class: `pill ${cls}`, text: v.he });
}

function detailSections(s) {
  const r = s.rest || {};
  const V = S.vocab;
  const out = [];

  if (s.in_council === false) {
    out.push(el('div', { class: 'dsec' }, el('div', {
      class: 'warnbox',
      text: `הנקודה נמצאת מחוץ לגבול השיפוט של המועצה, במרחק ${num(Math.abs(Math.round(s.dist_to_boundary_m || 0)))} מטר ממנו. היא נשמרת במאגר כתיעוד ההחרגה ואינה נכללת בספירות.`,
    })));
  } else if (s.near_boundary) {
    out.push(el('div', { class: 'dsec' }, el('div', {
      class: 'warnbox',
      text: `הנקודה סמוכה לגבול השיפוט, ${num(Math.round(s.dist_to_boundary_m || 0))} מטר בתוכו. השיוך למועצה אומת נקודתית.`,
    })));
  }

  // classification
  const periods = (s.periods || []).map(p => V.periods.find(x => x.key === p)?.he).filter(Boolean);
  out.push(el('div', { class: 'dsec' }, el('h3', { text: 'סיווג ותיארוך' }),
    kv([
      ['קטגוריה', (V.categories[s.category] || {}).he],
      ['קטגוריות נוספות', (s.categories || []).length > 1
        ? s.categories.filter(c => c !== s.category).map(c => V.categories[c]?.he).join(', ') : null],
      ['סוג', V.site_types[s.type]?.he || gapDd('לא סווג')],
      ['תקופות', periods.length ? periods.join(' · ') : gapDd('לא מתוארך')],
      ['תיארוך', s.date_text || (s.year_from !== null && s.year_from !== undefined
        ? [yearLabel(s.year_from), yearLabel(s.year_to)].filter(Boolean).join(' עד ') : null)],
      ['בסיס השיוך התקופתי', V.era_basis[s.era_basis]],
    ])));

  // statuses that apply to this category
  const axes = Object.entries(V.status_axes).filter(([, m]) => m.applies_to.includes(s.category));
  const grid = el('dl', { class: 'kv' });
  for (const [axis, meta] of axes) {
    grid.append(el('dt', { text: meta.he }));
    const dd = el('dd', {}, statusPill(axis, s[axis]));
    const srcs = (r.provenance || {})[axis];
    if (srcs && srcs.length) dd.append(el('span', { class: 'src', text: ` · ${srcs.map(x => V.sources[x] || x).join(', ')}` }));
    grid.append(dd);
  }
  const ovNotes = (r.overlay_notes || []).map(o => el('p', {
    class: 'strata-caption', style: 'padding-top:.4rem',
    text: `${V.status_axes[o.axis]?.he || o.axis}: נקבע לפי מיקום בתוך ייעוד סטטוטורי `
      + `"${o.designation}"${o.plan ? `, ${o.plan}` : ''}${o.plan_number ? ` (${o.plan_number})` : ''}`
      + `, ${num(Math.round(o.distance_m))} מטר ממרכז הייעוד. זהו שיוך מרחבי שלנו ולא הצהרה של הגוף המוסמך.`,
  }));
  out.push(el('div', { class: 'dsec' }, el('h3', { text: 'סטטוס' }), grid, ...ovNotes,
    (r.excavation_years || []).length
      ? el('p', { class: 'strata-caption', style: 'padding-top:.5rem', text: `שנות חפירה: ${r.excavation_years.join(', ')}` })
      : null,
    (r.excavators || []).length
      ? el('p', { class: 'strata-caption', style: 'padding-top:.1rem', text: `חופרים: ${r.excavators.join('; ')}` })
      : null));

  // practical
  const site = r.website ? el('a', { href: r.website, target: '_blank', rel: 'noopener', text: r.website.replace(/^https?:\/\//, '').slice(0, 42) }) : null;
  const prac = kv([
    ['כתובת', r.address], ['טלפון', r.phone],
    ['דואר אלקטרוני', r.email ? el('a', { href: 'mailto:' + r.email, text: r.email }) : null],
    ['אתר', site], ['שעות', r.hours_text], ['כניסה', r.admission],
    ['מפעיל', r.operator], ['שנת ייסוד', r.founded_year],
  ]);
  if (prac) out.push(el('div', { class: 'dsec' }, el('h3', { text: 'פרטים מעשיים' }), prac));

  // location
  out.push(el('div', { class: 'dsec' }, el('h3', { text: 'מיקום' }),
    kv([
      ['יישוב', s.locality
        || (s.nearest_settlement
          ? el('span', {}, s.nearest_settlement,
            el('span', { class: 'src', text: ` · היישוב הקרוב, ${s.nearest_settlement_km} ק"מ, בחישוב שלנו ולא לפי מקור` }))
          : gapDd('לא זוהה'))],
      ['קו רוחב, קו אורך', s.lat !== null && s.lat !== undefined
        ? el('span', { style: 'font-variant-numeric:tabular-nums', text: `${s.lat.toFixed(5)}, ${s.lon.toFixed(5)}` })
        : gapDd('אין קואורדינטה')],
      ['רשת ישראל החדשה', r.itm_x ? el('span', { style: 'font-variant-numeric:tabular-nums', text: `${Math.round(r.itm_x)}, ${Math.round(r.itm_y)}` }) : null],
      ['דיוק המיקום', APPROX_PRECISION.has(s.location_precision)
        ? el('span', { class: 'pill mid', text: V.location_precision[s.location_precision] || 'מקורב' })
        : (V.location_precision[s.location_precision] || null)],
      ['בתחום השיפוט', s.in_council === null ? gapDd('לא נבדק')
        : el('span', { class: `pill ${s.in_council ? 'on' : 'off'}`, text: s.in_council ? 'כן' : 'לא' })],
      ['מרחק מהגבול', s.dist_to_boundary_m !== null && s.dist_to_boundary_m !== undefined
        ? `${num(Math.abs(Math.round(s.dist_to_boundary_m)))} מטר ${s.dist_to_boundary_m > 0 ? 'בתוך התחום' : 'מחוצה לו'}` : null],
      ['פיזור בין המקורות', r.location_spread_m ? `${num(Math.round(r.location_spread_m))} מטר` : null],
    ]),
    s.lat !== null && s.lat !== undefined ? el('p', { style: 'margin:.5rem 0 0;font-size:.78rem' },
      el('a', {
        href: `https://www.google.com/maps/search/?api=1&query=${s.lat},${s.lon}`,
        target: '_blank', rel: 'noopener', text: 'פתיחת המיקום בניווט',
      })) : null));

  // confidence
  const c = r.confidence_components || {};
  out.push(el('div', { class: 'dsec' }, el('h3', { text: 'רמת ודאות' }),
    el('div', { class: 'conf-meter' },
      el('div', { class: 'conf-track' }, el('div', { class: 'conf-fill', style: `width:${(s.confidence * 100).toFixed(0)}%` })),
      el('span', { class: 'conf-val', text: `${Math.round(s.confidence * 100)}%` })),
    kv([
      ['קיום האתר', c.existence !== undefined ? `${Math.round(c.existence * 100)}%` : null],
      ['מיקום', c.location !== undefined ? `${Math.round(c.location * 100)}%` : null],
      ['סיווג תקופתי', c.category !== undefined ? `${Math.round(c.category * 100)}%` : null],
      ['סטטוסים', c.status !== undefined ? `${Math.round(c.status * 100)}%` : null],
      ['מספר מקורות', s.source_count],
      ['אימות', (r.verification || {}).status === 'verified'
        ? el('span', { class: 'pill on', text: 'אומת' })
        : (r.verification || {}).status === 'flagged'
          ? el('span', { class: 'pill off', text: 'סומן לבדיקה' })
          : gapDd('לא אומת נקודתית')],
    ]),
    (r.review_reasons || []).length
      ? el('p', { class: 'strata-caption', style: 'padding-top:.5rem', text: 'סימוני בדיקה: ' + r.review_reasons.join(', ') })
      : null));

  // sources and the claim log
  const sl = el('div', { class: 'srclist' });
  for (const src of s.rest?.sources || []) {
    sl.append(el('div', {},
      src.url ? el('a', { href: src.url, target: '_blank', rel: 'noopener', text: src.source_he || src.source_id })
        : el('span', { text: src.source_he || src.source_id }),
      src.retrieved ? el('span', { class: 'src', text: ` · נשלף ${src.retrieved}` }) : null));
  }
  const claims = (S.claims || {})[s.id];
  const claimBox = claims && claims.length
    ? el('details', { class: 'claims' }, el('summary', { text: `מה כל מקור אמר (${claims.length} טענות)` }),
      ...claims.map(cl => el('div', { class: 'claim-row', 'data-used': String(!!cl.used) },
        el('span', { class: 'f', text: cl.field }),
        el('span', { class: 'v', text: Array.isArray(cl.value) ? cl.value.join(', ') : String(cl.value) }),
        el('span', { class: 's', text: V.sources[cl.source_id] || cl.source_id }))))
    : (S.claims ? null : el('p', { class: 'strata-caption', text: 'טוענים את יומן הטענות' }));

  const conf = (r.conflicts || []).length
    ? el('details', { class: 'claims' }, el('summary', { text: `סתירות שהוכרעו (${r.conflicts.length})` }),
      ...r.conflicts.map(cf => el('div', { class: 'claim-row' },
        el('span', { class: 'f', text: cf.field }),
        el('span', { class: 'v' }, el('span', { text: `נבחר: ${cf.chosen}. נדחו: ${cf.rejected.map(x => `${x.value} (${V.sources[x.source_id] || x.source_id})`).join('; ')}` })),
        el('span', { class: 's', text: (cf.chosen_by || []).map(x => V.sources[x] || x).join(', ') }))))
    : null;

  if ((r.related_ids || []).length) {
    out.push(el('div', { class: 'dsec' }, el('h3', { text: 'רשומות נוספות באותו מקום' }),
      el('p', { class: 'strata-caption', style: 'padding-top:0', text: 'רשומות שלא אוחדו, כדי לא למחוק הבחנה שהגוף המוסמך עושה.' }),
      ...r.related_ids.map(x => el('p', { style: 'margin:.25rem 0;font-size:.8rem' },
        el('button', {
          class: 'btn', style: 'padding:.15rem .5rem',
          onclick: () => select(x.id), text: x.name || x.id,
        }),
        el('span', { class: 'src', text: ` · ${num(Math.round(x.distance_m))} מטר · ${x.reason}` })))));
  }

  if (s.name && !/[֐-׿]/.test(s.name)) {
    out.push(el('div', { class: 'dsec' }, el('div', {
      class: 'warnbox',
      text: 'לאתר הזה יש שם באנגלית בלבד במקורות שנבדקו, ולכן זה השם שמוצג. לא הומצא לו שם עברי.',
    })));
  }

  out.push(el('div', { class: 'dsec' }, el('h3', { text: 'מקורות וראיות' }), sl, conf, claimBox,
    (r.names_alt || []).length
      ? el('p', { class: 'strata-caption', style: 'padding-top:.5rem', text: 'שמות נוספים: ' + r.names_alt.map(a => a.name).join(' · ') })
      : null,
    el('p', { style: 'margin:.6rem 0 0;font-size:.78rem;display:flex;gap:.8rem;flex-wrap:wrap' },
      r.wikipedia_he ? el('a', { href: r.wikipedia_he, target: '_blank', rel: 'noopener', text: 'ויקיפדיה' }) : null,
      r.wikidata_qid ? el('a', { href: 'https://www.wikidata.org/wiki/' + r.wikidata_qid, target: '_blank', rel: 'noopener', text: 'Wikidata' }) : null,
      r.iaa_site_id ? el('span', { class: 'src', text: `מספר אתר רשות העתיקות: ${r.iaa_site_id}` }) : null,
      r.blue_sign_number ? el('span', { class: 'src', text: `שלט כחול ${r.blue_sign_number}` }) : null)));

  return out;
}

/* ------------------------------------------------------------- table view */
const TABLE_COLS = [
  ['name', 'שם', s => s.name || '—'],
  ['category', 'קטגוריה', s => S.vocab.categories[s.category]?.he || ''],
  ['type', 'סוג', s => S.vocab.site_types[s.type]?.he || ''],
  ['locality', 'יישוב', s => placeOf(s) === '—' ? '' : placeOf(s) + (placeIsDerived(s) ? ' (הקרוב)' : '')],
  ['periods', 'תקופות', s => (s.periods || []).map(p => S.vocab.periods.find(x => x.key === p)?.he).filter(Boolean).join(', ')],
  ['reg_summary', 'רישום', s => S.vocab.reg_summary[s.reg_summary] || ''],
  ['excavation', 'חפירה', s => lab('excavation', s.excavation)],
  ['accessibility', 'נגישות', s => lab('accessibility', s.accessibility)],
  ['condition', 'מצב', s => lab('condition', s.condition)],
  ['activity', 'פעילות', s => lab('activity', s.activity)],
  ['signage', 'שילוט', s => lab('signage', s.signage)],
  ['lat', 'קו רוחב', s => (s.lat ?? '')],
  ['lon', 'קו אורך', s => (s.lon ?? '')],
  ['source_count', 'מקורות', s => s.source_count],
  ['confidence', 'ודאות', s => Math.round(s.confidence * 100) + '%'],
];

function lab(axis, v) {
  const m = S.vocab.status_axes[axis];
  return m ? (m.values.find(x => x.key === (v || 'unknown'))?.he || '') : '';
}

let sortCol = 'name', sortDir = 1;

function renderTable() {
  const rows = [...S.filtered].sort((a, b) => {
    const A = TABLE_COLS.find(c => c[0] === sortCol)[2](a);
    const B = TABLE_COLS.find(c => c[0] === sortCol)[2](b);
    if (typeof A === 'number' && typeof B === 'number') return (A - B) * sortDir;
    return String(A).localeCompare(String(B), 'he') * sortDir;
  });
  const t = el('table', { class: 'data' },
    el('caption', { text: `${num(rows.length)} נקודות. אותם הנתונים שעל המפה, בתצוגה נגישה למקלדת ולקורא מסך. לחיצה על שורה פותחת את כל שדות הנקודה.` }),
    el('thead', {}, el('tr', {}, ...TABLE_COLS.map(([k, label]) => el('th', {
      scope: 'col', 'aria-sort': sortCol === k ? (sortDir === 1 ? 'ascending' : 'descending') : 'none',
    }, el('button', {
      type: 'button',
      onclick: () => { if (sortCol === k) sortDir = -sortDir; else { sortCol = k; sortDir = 1; } renderTable(); },
    }, label, sortCol === k ? (sortDir === 1 ? ' ▲' : ' ▼') : ''))))),
    el('tbody', {}, ...rows.map(s => el('tr', {
      tabindex: '0', 'aria-selected': String(S.selected === s.id),
      onclick: () => select(s.id),
      onkeydown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(s.id); } },
    }, ...TABLE_COLS.map(([k, , get]) => {
      const v = get(s);
      const isNum = ['lat', 'lon', 'source_count', 'confidence'].includes(k);
      const cell = el('td', { class: isNum ? 'num' : null, title: String(v) });
      if (k === 'name') { cell.append(glyph(s.category, 11), ' ', String(v)); }
      else cell.textContent = typeof v === 'number' ? (k === 'lat' || k === 'lon' ? v.toFixed(5) : num(v)) : String(v);
      return cell;
    })))));
  $('#tablewrap').replaceChildren(rows.length ? t : el('div', { class: 'empty' },
    el('h3', { text: 'אין נקודות שעונות על המסננים' }),
    el('p', { text: 'הסירו מסנן או נקו הכל כדי לראות שוב את כל הנקודות.' })));
}

/* ----------------------------------------------------------- metrics view */
function tile(label, fig, note, cat) {
  return el('div', { class: 'tile', 'data-cat': cat || null },
    el('div', { class: 'lab' }, cat ? glyph(cat, 11) : null, label),
    el('div', { class: 'fig' }, fig),
    note ? el('div', { class: 'note', text: note }) : null);
}

function stackedRow(label, counts, order, total) {
  const track = el('div', { class: 'sbar-track' });
  for (const v of order) {
    const n = counts.get(v.key) || 0;
    if (!n) continue;
    const w = (n / total * 100);
    const seg = el('div', {
      class: 'sbar-seg', 'data-tone': v.tone,
      style: `flex:0 0 ${w.toFixed(2)}%;background:${toneColor(v.tone)}`,
    }, w > 7 ? el('span', { text: num(n) }) : null);
    tipOn(seg, `${v.he}: ${num(n)} (${pct(n, total)}%)`);
    track.append(seg);
  }
  return el('div', { class: 'sbar-row' }, el('div', { class: 'lab', text: label }), track);
}

function renderMetrics() {
  const V = S.vocab;
  const all = S.filtered;
  const n = all.length;
  const host = $('#metricsInner');
  if (!n) {
    host.replaceChildren(el('div', { class: 'empty' }, el('h3', { text: 'אין נתונים להצגה' }),
      el('p', { text: 'המסננים הנוכחיים לא מחזירים נקודות.' })));
    return;
  }

  const byCat = {};
  for (const c of Object.keys(V.categories)) byCat[c] = all.filter(s => s.category === c).length;
  const withCoord = all.filter(s => s.lat !== null && s.lat !== undefined).length;
  const inside = all.filter(s => s.in_council === true).length;
  const merged = all.filter(s => s.source_count > 1).length;
  const hiConf = all.filter(s => s.confidence >= 0.95).length;
  const meanConf = all.reduce((a, s) => a + s.confidence, 0) / n;
  const dated = all.filter(s => (s.periods || []).length).length;

  const out = [];
  out.push(el('h2', { text: 'נתוני סיכום' }));
  out.push(el('p', {
    class: 'lede',
    text: `הנתונים מתייחסים ל-${num(n)} הנקודות שעונות על המסננים הנוכחיים. כל אחוז מחושב על הבסיס הזה, וקטגוריית "לא ידוע" מוצגת בכל מקום שבו היא קיימת, כי היקף הפערים הוא חלק מהתמונה ולא רעש שצריך להסתיר.`,
  }));

  out.push(el('div', { class: 'tiles' },
    tile('סך הנקודות', num(n), `${num(inside)} אומתו בתוך גבול השיפוט`),
    tile('אתרים ארכאולוגיים', num(byCat.archaeological || 0), 'עד 1700, רשות העתיקות', 'archaeological'),
    tile('אתרים היסטוריים', num(byCat.historic || 0), 'אחרי 1700, המועצה לשימור', 'historic'),
    tile('מוסדות תרבות', num(byCat.culture || 0), 'פעילים או שנבדקה פעילותם', 'culture'),
    tile('ודאות ממוצעת', `${Math.round(meanConf * 100)}%`, `${num(hiConf)} נקודות מעל 95%`),
    tile('הצטלבות מקורות', num(merged), `${pct(merged, n)}% מהנקודות אושרו ביותר ממקור אחד`)));

  // status distribution, one stacked bar per axis
  const axesToShow = ['reg_antiquity', 'reg_conservation', 'excavation', 'signage',
    'accessibility', 'a11y_disabled', 'condition', 'visitor_dev', 'activity', 'protected_area', 'ownership'];
  const bars = el('div', { class: 'sbar' });
  const tonesUsed = new Set();
  for (const axis of axesToShow) {
    const meta = V.status_axes[axis];
    const pool = all.filter(s => meta.applies_to.includes(s.category));
    if (!pool.length) continue;
    const counts = new Map();
    for (const s of pool) {
      const k = s[axis] || 'unknown';
      counts.set(k, (counts.get(k) || 0) + 1);
    }
    for (const v of meta.values) if (counts.get(v.key)) tonesUsed.add(v.tone);
    bars.append(stackedRow(meta.he, counts, meta.values, pool.length));
  }
  const toneLabel = { good: 'מצב חיובי או קיים', warn: 'חלקי או בתהליך', bad: 'שלילי או לא קיים', gap: 'לא ידוע', neutral: 'ניטרלי' };
  out.push(el('section', { class: 'chartblock' },
    el('h3', { text: 'התפלגות הסטטוסים' }),
    el('p', { class: 'sub', text: 'כל פס הוא 100% מהנקודות שהציר חל עליהן. ריחוף מציג את הערך המדויק.' }),
    bars,
    el('div', { class: 'legend' }, ...['good', 'warn', 'bad', 'gap'].filter(t => tonesUsed.has(t)).map(t =>
      el('span', { class: 'item' }, el('span', { class: 'sw', style: `background:${toneColor(t)}` }), toneLabel[t])))));

  // period histogram
  const perCounts = new Map();
  for (const s of all) for (const p of s.periods || []) perCounts.set(p, (perCounts.get(p) || 0) + 1);
  const maxPer = Math.max(1, ...perCounts.values());
  const hb = el('div', { class: 'hbar' });
  for (const p of [...V.periods].reverse()) {
    const c = perCounts.get(p.key) || 0;
    if (!c) continue;
    const fill = el('div', { class: 'fill', style: `width:${(c / maxPer * 100).toFixed(1)}%;background:${p.era === 'archaeological' ? catColor('archaeological') : catColor('historic')}` });
    const row = el('div', { class: 'hbar-row' },
      el('div', { class: 'lab', text: p.he }),
      el('div', { class: 'track' }, fill),
      el('div', { class: 'n', text: num(c) }));
    tipOn(row, `${p.he} (${yearLabel(p.from)} עד ${yearLabel(p.to)}): ${num(c)} אתרים`);
    hb.append(row);
  }
  out.push(el('section', { class: 'chartblock' },
    el('h3', { text: 'אתרים לפי תקופה' }),
    el('p', { class: 'sub', text: `אתר יכול להופיע בכמה תקופות. ${num(n - dated)} מהנקודות אינן מתוארכות.` }),
    hb,
    el('div', { class: 'legend' },
      el('span', { class: 'item' }, el('span', { class: 'sw', style: `background:${catColor('archaeological')}` }), 'לפני 1700, תחום העתיקות'),
      el('span', { class: 'item' }, el('span', { class: 'sw', style: `background:${catColor('historic')}` }), 'אחרי 1700, תחום המורשת'))));

  // coverage meters
  const meters = [
    ['נקודות עם קואורדינטה', withCoord, n, 'בלי קואורדינטה אין הצגה על המפה'],
    ['נקודות בתוך גבול השיפוט', inside, n, 'נבדק נקודתית מול הגבול הרשמי'],
    ['נקודות מתוארכות', dated, n, 'יש להן לפחות תקופה אחת'],
    ['ודאות מעל 95%', hiConf, n, 'היעד שהוגדר למפה'],
  ];
  for (const axis of ['reg_antiquity', 'excavation', 'accessibility', 'condition', 'activity']) {
    const meta = V.status_axes[axis];
    const pool = all.filter(s => meta.applies_to.includes(s.category));
    if (!pool.length) continue;
    const known = pool.filter(s => (s[axis] || 'unknown') !== 'unknown').length;
    meters.push([`ידוע: ${meta.he}`, known, pool.length, `מתוך ${num(pool.length)} שהציר חל עליהן`]);
  }
  out.push(el('section', { class: 'chartblock' },
    el('h3', { text: 'שלמות הנתונים' }),
    el('p', { class: 'sub', text: 'מה אנחנו יודעים ומה עדיין חסר. פער מוצהר עדיף על ניחוש, ולכן הוא נמדד.' }),
    el('div', { class: 'meters' }, ...meters.map(([label, a, b, note]) => {
      const p = pct(a, b);
      const tone = p >= 80 ? null : p >= 50 ? 'warn' : 'bad';
      return el('div', { class: 'meter' },
        el('div', { class: 'top' }, el('span', { text: label }), el('span', { class: 'n', text: `${p}%` })),
        el('div', { class: 'track' }, el('div', { class: 'fill', 'data-tone': tone, style: `width:${p}%` })),
        el('div', { class: 'note', text: `${num(a)} מתוך ${num(b)}. ${note}` }));
    }))));

  // top localities
  const locC = new Map();
  for (const s of all) locC.set(placeOf(s), (locC.get(placeOf(s)) || 0) + 1);
  const top = [...locC.entries()].sort((a, b) => b[1] - a[1]).slice(0, 14);
  const maxL = Math.max(1, ...top.map(t => t[1]));
  const derivedN = all.filter(placeIsDerived).length;
  out.push(el('section', { class: 'chartblock' },
    el('h3', { text: 'ריכוז לפי יישוב' }),
    el('p', {
      class: 'sub',
      text: `${num(locC.size)} יישובים. מוצגים ארבעה-עשר הגדולים. ב-${num(derivedN)} מהנקודות אף מקור אינו מציין יישוב, ולכן הן משויכות ליישוב הקרוב ביותר בחישוב שלנו.`,
    }),
    el('div', { class: 'hbar' }, ...top.map(([loc, c]) => {
      const row = el('div', { class: 'hbar-row' },
        el('div', { class: 'lab', text: loc === '—' ? 'ללא שיוך' : loc }),
        el('div', { class: 'track' }, el('div', { class: 'fill', style: `width:${(c / maxL * 100).toFixed(1)}%;background:${getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()}` })),
        el('div', { class: 'n', text: num(c) }));
      tipOn(row, `${loc}: ${num(c)} נקודות`);
      return row;
    }))));

  host.replaceChildren(...out);
}

/* -------------------------------------------------------------- about view */
function renderAbout() {
  const V = S.vocab;
  $('#aboutInner').replaceChildren(
    el('h2', { text: 'על המפה' }),
    el('div', { class: 'prose' },
      el('p', { text: `המפה מרכזת אתרים ארכאולוגיים, אתרים היסטוריים ומוסדות תרבות פעילים בתחום השיפוט של מועצה אזורית עמק יזרעאל, ומאחדת אותם למאגר אחד שבו לכל נקודה מקורות מזוהים, סטטוסים ורמת ודאות מוצהרת. היא נבנתה על ידי המכון הישראלי למדיניות תרבות.` }),

      el('h3', { text: 'שלוש הקטגוריות' }),
      el('p', { text: `חוק העתיקות התשל"ח-1978 מגדיר עתיקות כשרידים שנוצרו לפני שנת ${V.antiquity_cutoff}, ולכן ${V.antiquity_cutoff} היא הקו שמפריד בין אתר ארכאולוגי, שבאחריות רשות העתיקות, לאתר היסטורי, שבתחום הטיפול של המועצה לשימור אתרי מורשת בישראל. הקטגוריה השלישית היא מוסדות תרבות ואומנות פעילים כיום. אתר יכול להיות בכמה קטגוריות, למשל מוזיאון שיושב בתוך אתר ארכאולוגי, ובמקרה כזה הוא מופיע בסינון של כל אחת מהן. אנשים בודדים אינם נכללים במפה.` }),

      el('h3', { text: 'גבול השיפוט' }),
      el('p', { text: `הגבול הוא רב-מצולע עם חורים: המועצה עוטפת רשויות שאינן בתחומה, ובהן עפולה, נצרת, מגדל העמק, יקנעם עילית, רמת ישי וקרית טבעון. כל נקודה נבדקה נקודתית מול הגבול הרשמי, ולא מול מלבן חוסם, ולכן אתר בנצרת או בעפולה אינו נכלל גם אם הוא באמצע האזור. נקודות שנמצאו מחוץ לגבול נשמרות במאגר ומסומנות כמוחרגות, כדי שההחרגה תהיה בדיקה שניתן לבחון ולא מחיקה שקטה. אפשר להציג אותן דרך המסנן "איכות הנתון".` }),

      el('h3', { text: 'איך התמודדנו עם הצלבת מקורות' }),
      el('p', { text: `אותו אתר מופיע במקורות שונים בשמות שונים, ולכן ההתאמה בין מקורות אינה מסתמכת על השם בלבד. שני רשומות מזוהות כאותו מקום לפי שילוב של מרחק גאוגרפי, בסף שמשתנה לפי סוג האתר, ושל דמיון שם שמנוטרל מראשי שם גנריים. שני שמות שחולקים רק את הראש הגנרי, כמו תל שמרון ותל מגידו, לא ייחשבו דומים בגלל המילה תל. מזהה חזק משותף, כמו מספר אתר של רשות העתיקות או מזהה Wikidata, מאחד רשומות בכל מקרה, ושני מזהים חזקים שונים חוסמים איחוד בכל מקרה.` }),
      el('p', { text: `כשמקורות חולקים על ערך, ההכרעה נעשית לפי סמכות שהוגדרה מראש לכל שדה בנפרד, ולא לפי דירוג כללי של מקורות, כי הסמכות משתנה: טבלת רשות העתיקות קובעת קואורדינטה של אתר ארכאולוגי, המועצה לשימור קובעת סטטוס שימור, והאתר של המוסד עצמו קובע אם הוא פתוח. בשדות של סטטוס משפטי, ערך שמגיע ממקור שאינו הסמכות נזרק ואינו נכנס למאגר. סטטוס משפטי שגוי גרוע מפער מוצהר.` }),

      el('h3', { text: 'מה המפה לא יודעת' }),
      el('p', { text: `לכל ציר סטטוס יש ערך "לא ידוע" מפורש, והוא מוצג. לא הושלמו קואורדינטות, תקופות או סטטוסים שלא נמצאו במקור. בלוח נתוני הסיכום יש מדדי שלמות שמראים בכמה מהנקודות כל ציר ידוע בפועל, וכל נקודה נושאת רמת ודאות מחושבת משלה עם פירוט לארבעה מרכיבים. לחיצה על נקודה חושפת את יומן הטענות: מה כל מקור אמר, כולל הערכים שנדחו.` }),

      el('h3', { text: 'נגישות' }),
      el('p', { text: `המפה נבנתה לפי ת"י 5568 המאמץ את WCAG 2.0 ברמת AA. תצוגת הטבלה היא חלופה נגישה מלאה למפה עם אותם הנתונים, ניתנת לניווט במקלדת ולקריאה בקורא מסך. כל הפקדים נגישים במקלדת עם סימון מיקוד גלוי, הצבעים נבדקו בכלי אימות אוטומטי גם לעיוורון צבעים, וזיהוי הקטגוריה נשען גם על צורת הסמן ולא על הצבע בלבד. אנימציות מכובות למי שביקש הפחתת תנועה במערכת ההפעלה. נתקלתם בבעיית נגישות: כתבו ל-matan@iicp.org.il.` }),

      el('h3', { text: 'מקורות הנתונים' }),
      el('ul', {}, ...Object.entries(V.sources).map(([k, he]) => el('li', { text: he }))),

      el('h3', { text: 'שימוש חוזר' }),
      el('p', {}, 'כל הנתונים ניתנים להורדה כקובץ CSV מלוח המסננים. מפת הבסיס מ-OpenStreetMap ומ',
        el('a', { href: 'https://israelhiking.osm.org.il/', target: '_blank', rel: 'noopener', text: 'מפת שבילי ישראל' }),
        ', בכפוף לרישיון ODbL. הנתונים על האתרים מקורם בגופים הרשמיים המפורטים למעלה, וייחוס נשמר לכל נקודה בנפרד.')));
}

/* ------------------------------------------------------------------- views */
function setView(v) {
  S.view = v;
  for (const t of $$('.tabs button')) {
    const on = t.dataset.view === v;
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
  }
  for (const p of ['map', 'table', 'metrics', 'about']) $('#view-' + p).hidden = p !== v;
  if (v === 'table') renderTable();
  if (v === 'metrics') renderMetrics();
  if (v === 'map' && S.map) S.map.resize();
  writeHash();
}

/* ---------------------------------------------------------------- csv out */
function csv() {
  const cols = [
    ['id', s => s.id], ...TABLE_COLS.map(([k, l, g]) => [l, g]),
    ['בתחום השיפוט', s => s.in_council === null ? '' : s.in_council ? 'כן' : 'לא'],
    ['מרחק מהגבול במטרים', s => s.dist_to_boundary_m ?? ''],
    ['דורש בדיקה', s => s.needs_review ? 'כן' : 'לא'],
    ['מקורות', s => (s.rest?.sources || []).map(x => x.source_he || x.source_id).join(' | ')],
  ];
  const esc = v => {
    const t = String(v ?? '');
    return /[",\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
  };
  const lines = [cols.map(c => esc(c[0])).join(',')];
  for (const s of S.filtered) lines.push(cols.map(c => esc(c[1](s))).join(','));
  // BOM so Excel on Windows reads the Hebrew as UTF-8 rather than as the ANSI codepage
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = el('a', { href: URL.createObjectURL(blob), download: 'emek-yizrael-heritage-sites.csv' });
  document.body.append(a); a.click(); a.remove();
}

/* --------------------------------------------------------------- url state */
function writeHash() {
  const p = new URLSearchParams();
  if (S.view !== 'map') p.set('v', S.view);
  if (S.base !== 'ihm') p.set('b', S.base);
  if (F.q) p.set('q', F.q);
  if (F.cats.size) p.set('c', [...F.cats].join(','));
  if (F.periods.size) p.set('p', [...F.periods].join(','));
  if (F.types.size) p.set('t', [...F.types].join(','));
  if (F.minConf) p.set('mc', String(Math.round(F.minConf * 100)));
  if (F.onlyReview) p.set('rv', '1');
  if (F.showOutside) p.set('out', '1');
  for (const [axis, set] of Object.entries(F.status)) if (set.size) p.set('s.' + axis, [...set].join(','));
  if (S.selected) p.set('id', S.selected);
  const h = p.toString();
  history.replaceState(null, '', h ? '#' + h : location.pathname);
}

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  if (p.get('v')) S.view = p.get('v');
  if (p.get('b') && BASEMAPS[p.get('b')]) S.base = p.get('b');
  F.q = (p.get('q') || '').toLowerCase();
  const fill = (set, v) => { if (v) v.split(',').forEach(x => set.add(x)); };
  fill(F.cats, p.get('c')); fill(F.periods, p.get('p')); fill(F.types, p.get('t'));
  F.minConf = Number(p.get('mc') || 0) / 100;
  F.onlyReview = p.get('rv') === '1';
  F.showOutside = p.get('out') === '1';
  for (const [k, v] of p.entries()) {
    if (k.startsWith('s.')) { F.status[k.slice(2)] ||= new Set(); fill(F.status[k.slice(2)], v); }
  }
  S._wantSelect = p.get('id');
}

/* ------------------------------------------------------------------- wiring */
function wire() {
  $$('.tabs button').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
  $$('.tabs button').forEach(b => b.addEventListener('keydown', e => {
    const tabs = $$('.tabs button');
    const i = tabs.indexOf(e.currentTarget);
    let j = null;
    if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;      // rtl: right is next
    if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
    if (j !== null) { e.preventDefault(); tabs[j].focus(); setView(tabs[j].dataset.view); }
  }));

  let t;
  $('#q').addEventListener('input', e => {
    clearTimeout(t);
    $('#qClear').hidden = !e.target.value;
    t = setTimeout(() => { F.q = e.target.value.trim().toLowerCase(); apply(); }, 140);
  });
  $('#qClear').addEventListener('click', () => {
    $('#q').value = ''; $('#qClear').hidden = true; F.q = ''; apply(); $('#q').focus();
  });
  if (F.q) { $('#q').value = F.q; $('#qClear').hidden = false; }

  $('#resetBtn').addEventListener('click', () => {
    F.q = ''; $('#q').value = ''; $('#qClear').hidden = true;
    F.cats.clear(); F.periods.clear(); F.types.clear(); F.localities.clear();
    for (const s of Object.values(F.status)) s.clear();
    F.minConf = 0; F.onlyReview = false; F.showOutside = false;
    const cr = $('#confRange'); if (cr) { cr.value = 0; $('#confVal').textContent = '0%'; }
    $$('#facets .opt[aria-pressed="true"]').forEach(b => b.setAttribute('aria-pressed', 'false'));
    apply();
  });
  $('#csvBtn').addEventListener('click', csv);

  $$('.basemap-switch button').forEach(b => b.addEventListener('click', () => setBase(b.dataset.base)));
  $$('.basemap-switch button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.base === S.base)));

  $('#dClose').addEventListener('click', closeDetail);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if ($('#detail').dataset.open === 'true') closeDetail();
      else if ($('#rail').dataset.open === 'true') toggleRail(false);
    }
  });

  $('#railToggle').addEventListener('click', () => toggleRail($('#rail').dataset.open !== 'true'));

  const th = $('#themeToggle');
  const stored = localStorage.getItem('eyz-theme');
  if (stored) document.documentElement.dataset.theme = stored;
  th.addEventListener('click', () => {
    const cur = document.documentElement.dataset.theme
      || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('eyz-theme', next);
    if (S.map && S.map.isStyleLoaded()) {
      for (const cat of Object.keys(S.vocab.categories)) {
        for (const [id, approx] of [['m-' + cat, false], ['m-' + cat + '-approx', true]]) {
          if (S.map.hasImage(id)) S.map.removeImage(id);
          S.map.addImage(id, markerImage(cat, 34, approx), { pixelRatio: 2 });
        }
      }
      S.map.triggerRepaint();
    }
    if (S.view === 'metrics') renderMetrics();
  });

  setView(S.view);
  if (S._wantSelect) setTimeout(() => select(S._wantSelect), 60);
}

function closeDetail() {
  $('#detail').dataset.open = 'false';
  S.selected = null;
  renderMap();
  if (S.view === 'table') renderTable();
  writeHash();
}

function toggleRail(open) {
  $('#rail').dataset.open = open ? 'true' : 'false';
  $('#railToggle').setAttribute('aria-expanded', String(open));
  $('#railToggle').setAttribute('aria-label', open ? 'סגרו את המסננים' : 'פתחו את המסננים');
}

boot();
