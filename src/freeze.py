"""Build the frozen input archive, so a fresh clone can rebuild the map.

data/raw/ is 336 MB of original downloads and data/interim/ is 83 MB of normalized payloads.
Neither belongs in git, but without them the repository cannot regenerate its own output, which
for a frozen project means the work is only as durable as one laptop's disk. This writes the
inputs the pipeline actually reads into data/frozen/ as gzip, roughly 8 MB, and that directory
IS committed.

Run:  python src/freeze.py            build or refresh the archive
      python src/freeze.py --check    report what is present, change nothing
"""

from __future__ import annotations

import gzip
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import paths  # noqa: E402
import redact  # noqa: E402


def gz_copy(src: Path, dst: Path) -> tuple[int, int]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as f_in, gzip.open(dst, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out, length=1024 * 1024)
    return src.stat().st_size, dst.stat().st_size


def gz_redacted(src: Path, dst: Path, redactor) -> tuple[int, int, dict]:
    """Redact a payload before archiving it, because data/frozen/ is committed PUBLICLY.

    This archive is committed, so it is a published artifact and has to pass the same gate as
    the map. Archiving the raw institute table would have put its 81 individual-person rows and
    their contact details in a public repository, which is exactly what Matan asked to avoid.
    """
    rows = paths.read_json(src)
    if not isinstance(rows, list):
        return (*gz_copy(src, dst), {"note": "not a row list; copied unchanged"})
    cleaned, report = redactor(rows)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(dst, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(cleaned, f, ensure_ascii=False)
    return src.stat().st_size, dst.stat().st_size, report


def build() -> dict:
    paths.FROZEN.mkdir(parents=True, exist_ok=True)
    report: dict = {"written": [], "skipped": [], "raw_mb": 0.0, "frozen_mb": 0.0}

    wanted = [(paths.INTERIM / n, n) for n in paths.SOURCE_PAYLOADS]
    wanted += [(paths.RAW / n, n) for n in paths.ESSENTIAL_RAW]

    for src, name in wanted:
        dst = paths.FROZEN / (name + ".gz")
        if not src.exists():
            if dst.exists():
                report["skipped"].append(f"{name}: no working copy, archive already present")
            else:
                report["skipped"].append(f"{name}: MISSING from both working copy and archive")
            continue
        if name.endswith(".geojson"):
            raw, frozen = gz_copy(src, dst)          # geometry only, no personal data
            note = ""
        else:
            raw, frozen, det = gz_redacted(src, dst, lambda rows, n=name: redact.redact_payload(n, rows))
            det = {k: v for k, v in det.items() if v}
            note = ("  redacted: " + ", ".join(f"{k}={v}" for k, v in det.items())) if det else ""
        report["raw_mb"] += raw / 1e6
        report["frozen_mb"] += frozen / 1e6
        report["written"].append(
            f"{name}: {raw/1e6:.1f} MB -> {frozen/1e6:.2f} MB ({raw/max(frozen,1):.1f}x){note}")

    report["raw_mb"] = round(report["raw_mb"], 1)
    report["frozen_mb"] = round(report["frozen_mb"], 2)

    readme = paths.FROZEN / "README.md"
    readme.write_text(
        "<div dir=\"rtl\">\n\n"
        "# ארכיון קלט קפוא\n\n"
        "הקבצים כאן הם הקלט שהצינור קורא, דחוסים ב-gzip ונשמרים בגיט. "
        "המקורות הגולמיים המקוריים, כ-336 מ\"ב, אינם בגיט; מה שמתועד עליהם נמצא ב-`docs/sources/`, "
        "כולל נקודות הקצה המדויקות לשליפה חוזרת.\n\n"
        "הקוד קורא את הקבצים האלה אוטומטית דרך `src/paths.py` כאשר `data/interim/` "
        "ו-`data/raw/` אינם קיימים, ולכן שכפול טרי של הריפו יכול לבנות את המפה מחדש:\n\n"
        "```\npython src/adapters.py && python src/harmonize.py && python src/build_site.py\n```\n\n"
        "לרענון הארכיון מתוך עותק עבודה: `python src/freeze.py`.\n\n"
        "</div>\n",
        encoding="utf-8")
    return report


def check() -> dict:
    return paths.state()


if __name__ == "__main__":
    import json

    if "--check" in sys.argv:
        print(json.dumps(check(), ensure_ascii=False, indent=1))
    else:
        rep = build()
        for line in rep["written"]:
            print("  " + line)
        for line in rep["skipped"]:
            print("  ! " + line)
        print(f"\n{len(rep['written'])} files: {rep['raw_mb']} MB -> {rep['frozen_mb']} MB")
        print(json.dumps(check(), ensure_ascii=False, indent=1))
