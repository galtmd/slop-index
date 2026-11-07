"""Command line entry point.

    python -m slop_index run --author "El-Sayed, Abdulrahman M" --slug el-sayed-am
    python -m slop_index run --slug el-sayed-am            # reuse cached data in data/<slug>/
    python -m slop_index run --pmids 33502685 19643005 ...  # explicit list

Data for a slug lives in data/<slug>/:
    pubmed_raw.json        cached PubMed records (fetched if absent)
    icite_citations.csv    cached citation counts (fetched if absent)
    exclude.csv            optional: pmid,reason   (name collisions etc.)
    overrides.csv          optional: pmid,tier,subtype,note (manual corrections)

Results go to results/<slug>/: papers.csv, summary.json, report.md
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from . import fetch
from .classify import classify, author_role
from .score import summarise
from . import substance

ROOT = Path(__file__).resolve().parent.parent


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _surname_from_author(author: str) -> str:
    return author.split(",")[0].strip()


def run(args: argparse.Namespace) -> int:
    slug = args.slug or (args.author.split(",")[0].strip().lower().replace(" ", "-") if args.author else None)
    if not slug:
        print("Provide --slug or --author", file=sys.stderr)
        return 2
    ddir = ROOT / "data" / slug
    rdir = ROOT / "results" / slug
    ddir.mkdir(parents=True, exist_ok=True)
    rdir.mkdir(parents=True, exist_ok=True)

    raw_path = ddir / "pubmed_raw.json"
    cit_path = ddir / "icite_citations.csv"

    # ---- records
    if raw_path.exists() and not args.refresh:
        articles = json.loads(raw_path.read_text(encoding="utf-8"))
        print(f"[cache] {len(articles)} PubMed records from {raw_path}")
    else:
        if args.pmids:
            pmids = args.pmids
        elif args.query:
            pmids = fetch.esearch(args.query)
        elif args.author:
            # Full Author Name search avoids most initials collisions. Add variants
            # (e.g. "Smith, John A" and "Smith, John") with --author-variant.
            names = [args.author] + (args.author_variant or [])
            term = " OR ".join(f'"{n}"[Full Author Name]' for n in names)
            pmids = fetch.esearch(term)
        else:
            print("Nothing cached and no --author/--query/--pmids given", file=sys.stderr)
            return 2
        print(f"[pubmed] {len(pmids)} PMIDs; fetching records...")
        articles = fetch.efetch(pmids)
        raw_path.write_text(json.dumps(articles, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"[pubmed] saved {raw_path}")

    pmids = [a["identifiers"]["pmid"] for a in articles]

    # ---- citations
    cit = {r["pmid"]: r for r in _load_csv(cit_path)}
    missing = [p for p in pmids if p not in cit]
    if missing:
        print(f"[icite] fetching citations for {len(missing)} PMIDs...")
        got = fetch.icite_citations(missing)
        for p, v in got.items():
            cit[p] = {"pmid": p, "citation_count": v["citation_count"],
                      "relative_citation_ratio": v["relative_citation_ratio"] or "", "year": v["year"] or ""}
        with cit_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["pmid", "citation_count", "relative_citation_ratio", "year"])
            w.writeheader()
            for p in pmids:
                if p in cit:
                    w.writerow({k: cit[p].get(k, "") for k in w.fieldnames})

    excl = {r["pmid"]: r.get("reason", "") for r in _load_csv(ddir / "exclude.csv")}
    over = {r["pmid"]: r for r in _load_csv(ddir / "overrides.csv")}
    surname = args.surname or (_surname_from_author(args.author) if args.author else slug.split("-")[0])

    # ---- classify
    kept = [a for a in articles if a["identifiers"]["pmid"] not in excl]
    self_sim = substance.self_similarity(kept)
    rows = []
    for a in articles:
        p = a["identifiers"]["pmid"]
        c = classify(a)
        if p in over:
            o = over[p]
            c.tier = o.get("tier") or c.tier
            c.subtype = o.get("subtype") or c.subtype
            c.confidence = "override"
            c.needs_review = False
            c.evidence.append(f"manual override: {o.get('note','')}")
        year = a.get("publication_date", {}).get("year") or cit.get(p, {}).get("year", "")
        rcr_raw = cit.get(p, {}).get("relative_citation_ratio", "")
        rcr = float(rcr_raw) if rcr_raw not in ("", None) else None
        sub = substance.score(a, c.tier, c.subtype, c.topics, rcr, self_sim.get(p, 0))
        rows.append({
            "pmid": p,
            "year": year,
            "role": author_role(a, surname),
            "n_authors": len(a.get("authors", [])),
            "journal": a.get("journal", {}).get("iso_abbreviation", ""),
            "title": a.get("title", ""),
            "pubtypes": "; ".join(a.get("article_types", [])),
            "tier": c.tier,
            "subtype": c.subtype,
            "confidence": c.confidence,
            "needs_review": c.needs_review,
            "topics": c.topics,
            "citation_count": int(cit.get(p, {}).get("citation_count") or 0),
            "rcr": round(rcr, 2) if rcr is not None else "",
            "design": sub.design,
            "outcome": sub.outcome,
            "exposure": sub.exposure,
            "hedge": sub.hedge,
            "self_similar": sub.self_similar,
            "identity": sub.identity,
            "social": sub.social,
            "agenda": sub.agenda,
            "topic_penalty": sub.topic_penalty,
            "rescued": sub.rescued,
            "value": sub.value,
            "value_norm": sub.value_norm,
            "components": json.dumps(sub.components),
            "excluded": p in excl,
            "exclude_reason": excl.get(p, ""),
            "evidence": " | ".join(c.evidence),
            "doi": a["identifiers"].get("doi", ""),
        })

    rows.sort(key=lambda r: (str(r["year"]), r["pmid"]))
    summary = summarise(rows)
    summary["slug"] = slug
    summary["surname_matched"] = surname
    summary["excluded"] = len(excl)

    # ---- write
    fields = ["pmid", "year", "role", "n_authors", "journal", "title", "pubtypes", "tier", "subtype",
              "confidence", "needs_review", "topics", "citation_count", "rcr",
              "design", "outcome", "exposure", "hedge", "self_similar", "identity", "social", "agenda", "topic_penalty",
              "rescued", "value", "value_norm", "components", "excluded",
              "exclude_reason", "evidence", "doi"]
    with (rdir / "papers.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            r2 = dict(r)
            r2["topics"] = "; ".join(r["topics"])
            w.writerow(r2)
    (rdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (rdir / "report.md").write_text(render_report(slug, rows, summary), encoding="utf-8")
    print(f"[done] {rdir / 'papers.csv'}\n[done] {rdir / 'summary.json'}\n[done] {rdir / 'report.md'}")
    print_summary(summary)
    return 0


def print_summary(s: dict) -> None:
    for key in ("all_authorships", "lead_authorships"):
        b = s[key]
        print(f"\n== {key.replace('_', ' ')} ({b['papers']} papers) ==")
        print(f"  tiers A/B/C: {b['tiers']['A']}/{b['tiers']['B']}/{b['tiers']['C']}  "
              f"empirical {b['empirical_share']}  commentary {b['commentary_share']}")
        print(f"  h = {b['h_index']}   h_empirical = {b['h_empirical']}   h_commentary = {b['h_commentary']}   "
              f"Slop Index = {b['slop_index']}")
        print(f"  citations: total {b['total_citations']}, share to commentary {b['citations_to_commentary_share']}")
        print(f"  topic share (any flag): {b['topic_share_any']}   {b['topic_shares']}")
        print(f"  identity-topic share {b['identity_topic_share']}  penalized-topic share {b['penalized_topic_share']}  rescued full/partial {b['rescued_full']}/{b['rescued_partial']}")
        print(f"  mean paper value {b['mean_paper_value']}   share with positive value {b['share_positive_value']}   h_substantive = {b['h_substantive']}")
        print(f"  TOTAL SLOP INDEX = {b['total_slop_index']}   (citation-weighted {b['total_slop_index_citation_weighted']})")
        if b["needs_review"]:
            print(f"  {b['needs_review']} papers flagged needs_review")


def render_report(slug: str, rows: list[dict], s: dict) -> str:
    def blk(name: str, b: dict) -> str:
        return (
            f"### {name}\n\n"
            f"| Metric | Value |\n|---|---|\n"
            f"| Papers | {b['papers']} |\n"
            f"| Tier A (original data) | {b['tiers']['A']} ({b['empirical_share']}) |\n"
            f"| Tier B (synthesis/modeling) | {b['tiers']['B']} ({b['synthesis_share']}) |\n"
            f"| Tier C (commentary) | {b['tiers']['C']} ({b['commentary_share']}) |\n"
            f"| h-index (PubMed/iCite) | {b['h_index']} |\n"
            f"| Empirical h-index (Tier A only) | {b['h_empirical']} |\n"
            f"| Commentary h-index (Tier C only) | {b['h_commentary']} |\n"
            f"| **Slop Index** = 1 − hₑ/h | **{b['slop_index']}** |\n"
            f"| Share of citations going to commentary | {b['citations_to_commentary_share']} |\n"
            f"| Topic share (race/SES/policy/equity, any) | {b['topic_share_any']} |\n"
            f"| Topic shares | {', '.join(f'{k} {v}' for k, v in b['topic_shares'].items())} |\n"
            f"| Flagged for manual review | {b['needs_review']} |\n"
            f"| Identity-topic share | {b['identity_topic_share']} |\n"
            f"| Penalized-topic share (identity, SDOH, or agenda bucket) | {b['penalized_topic_share']} (rescued full {b['rescued_full']}, partial {b['rescued_partial']}) |\n"
            f"| Designs | {', '.join(f'{k} {v}' for k, v in b['designs'].items())} |\n"
            f"| Mean paper value / share positive | {b['mean_paper_value']} / {b['share_positive_value']} |\n"
            f"| Substantive h-index (positive-value papers) | {b['h_substantive']} |\n"
            f"| **TOTAL SLOP INDEX** (composite) | **{b['total_slop_index']}** (citation-weighted {b['total_slop_index_citation_weighted']}) |\n\n"
        )

    lines = [f"# Slop Index report: `{slug}`\n", blk("All authorships", s["all_authorships"]),
             blk("Lead authorships (first, last, or sole)", s["lead_authorships"]),
             "### Papers\n",
             "| Year | Role | Tier | Design | Outcome | Exposure | RCR | Penalized | Value | Title | Journal |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["excluded"]:
            continue
        flag = "*" if r["needs_review"] else ""
        tag = "identity" if r['identity'] else ("sdoh" if r['social'] else (r.get('agenda') or ""))
        ident = (tag + (f" ({r['rescued']})" if r['rescued'] in ("full", "partial") else "")) if tag else ""
        lines.append(f"| {r['year']} | {r['role']} | {r['tier']}{flag} | {r['design']} | {r['outcome']} | {r['exposure']} | "
                     f"{r['rcr']} | {ident} | {r['value']} | {r['title'][:80]} | {r['journal']} |")
    exc = [r for r in rows if r["excluded"]]
    if exc:
        lines.append("\n### Excluded (name collisions)\n")
        for r in exc:
            lines.append(f"- {r['pmid']} {r['title'][:90]} ({r['exclude_reason']})")
    lines.append("\n`*` = low-confidence classification; see `evidence` column in papers.csv and override via data/<slug>/overrides.csv.\n")
    return "\n".join(lines)


def import_bundle(args: argparse.Namespace) -> int:
    """Split a <slug>.slopindex.json bundle (from tools/browser_fetch.js) into data/<slug>/."""
    bundles = []
    for path in args.files:
        b = json.loads(Path(path).read_text(encoding="utf-8"))
        bundles.extend(b["bundles"] if "bundles" in b else [b])
    for b in bundles:
        slug = args.slug if (args.slug and len(bundles) == 1) else b["slug"]
        ddir = ROOT / "data" / slug
        ddir.mkdir(parents=True, exist_ok=True)
        (ddir / "pubmed_raw.json").write_text(json.dumps(b["records"], indent=1, ensure_ascii=False), encoding="utf-8")
        with (ddir / "icite_citations.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["pmid", "citation_count", "relative_citation_ratio", "year"])
            w.writeheader()
            for r in b.get("icite", []):
                w.writerow({k: r.get(k, "") for k in w.fieldnames})
        (ddir / "source.txt").write_text(f"term: {b.get('term','')}\nfetched: {b.get('fetched','')}\n", encoding="utf-8")
        print(f"[import] {slug}: {len(b['records'])} records, {len(b.get('icite', []))} citation rows -> {ddir}")
    return 0


LABELS = {
    "kariko-k": "Katalin Karikó (mRNA biochemistry; Nobel 2023)",
    "charpentier-e": "Emmanuelle Charpentier (CRISPR; Nobel 2020)",
    "mega-jl": "Jessica Mega (cardiology trialist, TIMI)",
    "oz-mc": "Mehmet Oz (cardiothoracic surgeon; CMS administrator)",
    "makary-ma": "Marty Makary (surgeon; FDA commissioner)",
    "kulldorff-m": "Martin Kulldorff (biostatistician; GBD author)",
    "gupta-s": "Sunetra Gupta (theoretical epidemiologist; GBD author)",
    "bhattacharya-j": "Jay Bhattacharya (health economist; NIH director; GBD author)",
    "el-sayed-am": "Abdul El-Sayed (epidemiologist; US Senator-elect)",
    "case-a": "Anne Case (economist; deaths of despair)",
    "krieger-n": "Nancy Krieger (social epidemiologist, Harvard)",
    "geronimus-at": "Arline Geronimus (weathering hypothesis, Michigan)",
    "hardeman-rr": "Rachel Hardeman (structural racism and birth outcomes, Minnesota)",
    "metzl-jm": "Jonathan Metzl (psychiatrist-sociologist, Vanderbilt)",
    "jones-cp": "Camara Phyllis Jones (levels of racism; former APHA president)",
    "bowleg-l": "Lisa Bowleg (intersectionality in public health, GWU)",
    "ford-cl": "Chandra Ford (public health critical race praxis, UCLA)",
}


def compare(args: argparse.Namespace) -> int:
    """Write results/comparison.md from every results/<slug>/summary.json."""
    rows = []
    for f in sorted((ROOT / "results").glob("*/summary.json")):
        s = json.loads(f.read_text(encoding="utf-8"))
        a, l = s["all_authorships"], s["lead_authorships"]
        rows.append((s["slug"], a, l))
    rows.sort(key=lambda r: (r[1]["total_slop_index"] is None, r[1]["total_slop_index"] or 0))
    lines = ["# Comparison\n",
             "PubMed-indexed papers only; citations from NIH iCite. Sorted by Total Slop Index, best first. "
             "Lead = first, last, or sole author. Penalized = identity, social-determinants, or agenda-bucket topic. "
             "\"No abstract\" papers count toward the h-index but not toward tier shares or the composite.\n",
             "| Author | Papers (no abstract) | A / B / C | h | hₑ | Slop Index | Penalized share | Rescued full/partial | Positive-value share | Median value | **Total Slop Index** | Cite-weighted | Lead TSI (n) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for slug, a, l in rows:
        name = LABELS.get(slug, slug)
        lines.append(f"| {name} | {a['papers']} ({a['papers_no_abstract']}) | {a['tiers']['A']} / {a['tiers']['B']} / {a['tiers']['C']} | "
                     f"{a['h_index']} | {a['h_empirical']} | {a['slop_index']} | {a['penalized_topic_share']} | "
                     f"{a['rescued_full']}/{a['rescued_partial']} | {a['share_positive_value']} | {a.get('median_paper_value', '')} | "
                     f"**{a['total_slop_index']}** | {a['total_slop_index_citation_weighted']} | {l['total_slop_index']} ({l['papers']}) |")
    out = ROOT / "results" / "comparison.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"[done] {out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="slop_index", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch (or reuse cache), classify, score")
    r.add_argument("--author", help='PubMed Full Author Name, e.g. "El-Sayed, Abdulrahman M"')
    r.add_argument("--author-variant", action="append", help="additional Full Author Name spellings")
    r.add_argument("--query", help="raw PubMed query instead of --author")
    r.add_argument("--pmids", nargs="+", help="explicit PMID list")
    r.add_argument("--slug", help="folder name under data/ and results/")
    r.add_argument("--surname", help="surname used to find the author's position (defaults from --author)")
    r.add_argument("--refresh", action="store_true", help="ignore cached PubMed records")
    r.set_defaults(func=run)
    i = sub.add_parser("import", help="import a *.slopindex.json bundle made by tools/browser_fetch.js")
    i.add_argument("files", nargs="+")
    i.add_argument("--slug", help="override the slug stored in the bundle")
    i.set_defaults(func=import_bundle)
    c = sub.add_parser("compare", help="write results/comparison.md across every scored author")
    c.set_defaults(func=compare)
    args = p.parse_args(argv)
    return args.func(args)
