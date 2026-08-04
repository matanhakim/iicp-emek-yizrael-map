"""Where the pipeline's inputs live, with a frozen fallback.

Two states have to work:

  WORKING   data/raw/ holds 336 MB of byte-for-byte downloads and data/interim/ holds the
            83 MB of normalized payloads the adapters read. Neither is in git; both are
            reproducible only by re-running the extraction against the live sources.

  FROZEN    data/frozen/ holds the same inputs gzipped, about 8 MB, and IS committed. A fresh
            clone with no data/raw and no data/interim can still run the whole pipeline and
            rebuild the published map.

Every input is fetched through this module so the two states are interchangeable and no caller
has to know which one it is in. Before this existed the boundary polygon and the settlement
list, which the harmoniser cannot run without, sat in gitignored data/raw, so the repository
looked complete and was not.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
FROZEN = ROOT / "data" / "frozen"
OUT = ROOT / "data" / "out"
MANUAL = ROOT / "data" / "manual"

# The per-source payloads the adapters read. Order is documentation, not logic.
SOURCE_PAYLOADS = [
    "declared_antiquities.json",
    "declared_antiquities_known_survey_points.json",
    "iaa_discover.json",
    "iaa_cluster_table.json",
    "heritage_official.json",
    "blue_signs.json",
    "culture_institutions.json",
    "iicp_culture_table.json",
    "osm_wikidata.json",
]

# Inputs that are not per-source payloads but that the pipeline cannot run without.
ESSENTIAL_RAW = [
    "boundary_emek_yizrael.geojson",
    "settlements_emek_yizrael.json",
]


def _resolve(name: str, *dirs: Path) -> Path | None:
    """First existing candidate: a plain file, then its gzipped frozen twin."""
    for d in dirs:
        p = d / name
        if p.exists():
            return p
        gz = d / (name + ".gz")
        if gz.exists():
            return gz
    return None


def read_json(path: Path):
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(path.read_text(encoding="utf-8"))


def source_payload(name: str):
    """Load a per-source payload from the working copy, else from the frozen archive."""
    p = _resolve(name, INTERIM, FROZEN)
    return None if p is None else read_json(p)


def boundary_file() -> Path | None:
    """Path to the council boundary GeoJSON. May be a .gz, so read it via read_json."""
    return _resolve("boundary_emek_yizrael.geojson", RAW, FROZEN)


def settlements() -> list[dict]:
    """The council's 49 settlements with CBS codes and coordinates."""
    p = _resolve("settlements_emek_yizrael.json", RAW, FROZEN)
    if p is None:
        return []
    data = read_json(p)
    rows = data if isinstance(data, list) else (
        data.get("settlements") or data.get("records") or [])
    return [r for r in rows if isinstance(r, dict)]


def boundary_geojson():
    p = boundary_file()
    return None if p is None else read_json(p)


def state() -> dict:
    """Which inputs are present, and from where. Used by the freeze check and the audit."""
    def where(name: str, dirs: tuple[Path, ...]) -> str:
        p = _resolve(name, *dirs)
        if p is None:
            return "MISSING"
        return ("frozen" if p.parent == FROZEN else "working") + (".gz" if p.suffix == ".gz" else "")

    return {
        "sources": {n: where(n, (INTERIM, FROZEN)) for n in SOURCE_PAYLOADS},
        "essential": {n: where(n, (RAW, FROZEN)) for n in ESSENTIAL_RAW},
        "manual_additions": "present" if (MANUAL / "additions.json").exists() else "MISSING",
    }
