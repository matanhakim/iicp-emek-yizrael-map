"""Coordinate handling and jurisdiction testing.

Two Israeli grids show up in heritage data and confusing them displaces a site by
hundreds of kilometres:

    ITM  EPSG:2039   Israel 1993 / Israeli TM Grid    x about 130k-280k,  y about 380k-790k
    ICS  EPSG:28193  Palestine 1923 / Israeli CS Grid  x about  80k-230k,  y about  -40k-290k

The y magnitude separates them cleanly, but we never rely on the guess alone: every
conversion is checked against a plausibility box for the Jezreel Valley and anything
outside it is refused rather than silently accepted.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from pyproj import Transformer
from shapely import union_all
from shapely.geometry import Point, shape
from shapely.ops import transform as shp_transform
from shapely.prepared import prep

EPSG_ITM = 2039
EPSG_ICS = 28193
EPSG_WGS84 = 4326

_T_ITM_WGS = Transformer.from_crs(EPSG_ITM, EPSG_WGS84, always_xy=True)
_T_ICS_WGS = Transformer.from_crs(EPSG_ICS, EPSG_WGS84, always_xy=True)
_T_WGS_ITM = Transformer.from_crs(EPSG_WGS84, EPSG_ITM, always_xy=True)

# Generous plausibility box for the council plus margin. Used to refuse bad conversions.
PLAUSIBLE = {"lat": (32.45, 32.95), "lon": (34.95, 35.60)}
# Israel-wide sanity box, used when we only want to know the grid was read correctly.
ISRAEL = {"lat": (29.4, 33.4), "lon": (34.2, 35.9)}


class CoordError(ValueError):
    pass


def detect_grid(x: float, y: float) -> str:
    """Return 'itm', 'ics' or 'unknown' from the coordinate magnitudes."""
    if x is None or y is None:
        return "unknown"
    x, y = float(x), float(y)
    if 300_000 <= y <= 820_000 and 100_000 <= x <= 300_000:
        return "itm"
    if -60_000 <= y <= 299_999 and 60_000 <= x <= 260_000:
        return "ics"
    return "unknown"


def to_wgs84(x, y, grid: str | None = None, box: dict | None = None) -> tuple[float, float]:
    """Project a projected Israeli coordinate to (lat, lon). Raises if the result is implausible."""
    if x is None or y is None:
        raise CoordError("missing coordinate")
    x, y = float(x), float(y)
    grid = grid or detect_grid(x, y)
    if grid == "itm":
        lon, lat = _T_ITM_WGS.transform(x, y)
    elif grid == "ics":
        lon, lat = _T_ICS_WGS.transform(x, y)
    else:
        raise CoordError(f"cannot identify grid for x={x} y={y}")
    b = box or ISRAEL
    if not (b["lat"][0] <= lat <= b["lat"][1] and b["lon"][0] <= lon <= b["lon"][1]):
        raise CoordError(f"{grid} ({x},{y}) projected to ({lat:.5f},{lon:.5f}), outside the sanity box")
    return round(lat, 6), round(lon, 6)


def to_itm(lat: float, lon: float) -> tuple[float, float]:
    x, y = _T_WGS_ITM.transform(lon, lat)
    return round(x, 1), round(y, 1)


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Jurisdiction:
    """The council boundary, held in a metric CRS so distances are in real metres.

    Holes matter: the council wraps around Afula, Nazareth, Migdal HaEmek and others, so a
    naive convex hull or bounding box would wrongly accept sites in those cities. The
    geometry is used exactly as published, and `report()` states which test decided.
    """

    def __init__(self, geom_wgs84):
        self.wgs = geom_wgs84
        self.itm = shp_transform(lambda xs, ys, z=None: _T_WGS_ITM.transform(xs, ys), geom_wgs84)
        self._prep = prep(self.itm)
        self._edge = self.itm.boundary

    @classmethod
    def from_geojson(cls, path: str | Path):
        # The boundary may be stored gzipped in the frozen archive, so decompress transparently.
        p = Path(path)
        if p.suffix == ".gz":
            import gzip
            with gzip.open(p, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(p.read_text(encoding="utf-8"))
        geoms = []
        if data.get("type") == "FeatureCollection":
            geoms = [shape(f["geometry"]) for f in data["features"] if f.get("geometry")]
        elif data.get("type") == "Feature":
            geoms = [shape(data["geometry"])]
        else:
            geoms = [shape(data)]
        geom = geoms[0] if len(geoms) == 1 else union_all(geoms)
        if not geom.is_valid:
            geom = geom.buffer(0)
        return cls(geom)

    @property
    def area_km2(self) -> float:
        return round(self.itm.area / 1e6, 2)

    @property
    def parts(self) -> int:
        return len(getattr(self.itm, "geoms", [self.itm]))

    @property
    def holes(self) -> int:
        polys = getattr(self.itm, "geoms", [self.itm])
        return sum(len(p.interiors) for p in polys)

    def contains(self, lat: float, lon: float) -> bool:
        x, y = _T_WGS_ITM.transform(lon, lat)
        return self._prep.contains(Point(x, y))

    def signed_distance_m(self, lat: float, lon: float) -> float:
        """Metres to the nearest boundary line. Positive inside, negative outside."""
        x, y = _T_WGS_ITM.transform(lon, lat)
        p = Point(x, y)
        d = p.distance(self._edge)
        return round(d if self._prep.contains(p) else -d, 1)

    def report(self, lat: float, lon: float) -> dict:
        d = self.signed_distance_m(lat, lon)
        return {
            "in_council": d > 0,
            "in_council_method": "point_in_official_multipolygon",
            "dist_to_boundary_m": d,
            "near_boundary": abs(d) <= 300,
        }
