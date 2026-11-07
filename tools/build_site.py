"""Assemble the static site in site/ from the package and the scored results.

    python tools/build_site.py

Copies slop_index/*.py into site/py/ (loaded into Pyodide at runtime), writes
site/py/manifest.json, site/data/weights.json (defaults) and
site/data/comparison.json (one row per scored author in results/).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from slop_index.cli import LABELS  # noqa: E402
from slop_index.web import default_weights  # noqa: E402

SITE = ROOT / "site"
(SITE / "py").mkdir(parents=True, exist_ok=True)
(SITE / "data").mkdir(parents=True, exist_ok=True)

files = []
for p in sorted((ROOT / "slop_index").glob("*.py")):
    if p.name == "cli.py" or p.name == "fetch.py":
        continue  # not needed in the browser
    (SITE / "py" / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    files.append(p.name)
(SITE / "py" / "manifest.json").write_text(json.dumps({"files": files}), encoding="utf-8")

(SITE / "data" / "weights.json").write_text(json.dumps(default_weights(), indent=1), encoding="utf-8")

rows = []
for f in sorted((ROOT / "results").glob("*/summary.json")):
    s = json.loads(f.read_text(encoding="utf-8"))
    a, l = s["all_authorships"], s["lead_authorships"]
    rows.append({
        "slug": s["slug"], "label": LABELS.get(s["slug"], s["slug"]),
        "papers": a["papers"], "no_abstract": a["papers_no_abstract"],
        "tiers": a["tiers"], "h": a["h_index"], "h_empirical": a["h_empirical"],
        "slop_index": a["slop_index"], "penalized_share": a["penalized_topic_share"],
        "rescued_full": a["rescued_full"], "rescued_partial": a["rescued_partial"],
        "positive_share": a["share_positive_value"], "median_value": a["median_paper_value"],
        "tsi": a["total_slop_index"], "tsi_cw": a["total_slop_index_citation_weighted"],
        "lead_tsi": l["total_slop_index"], "lead_n": l["papers"],
        "designs": a["designs"],
    })
rows.sort(key=lambda r: (r["tsi"] is None, r["tsi"] or 0))
(SITE / "data" / "comparison.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
print(f"site: {len(files)} python files, {len(rows)} comparison rows")
