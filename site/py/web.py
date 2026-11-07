"""Entry point for running the index inside a browser (Pyodide) or any
caller that already holds PubMed records and citation counts in memory.

    score_records(records, icite, surname, overrides=None) -> dict

records   list of PubMed record dicts in the shape data/<slug>/pubmed_raw.json uses
icite     {pmid: {"citation_count": int, "relative_citation_ratio": float|None}}
surname   used to find the author's position on each paper
overrides optional {WEIGHT_NAME: value} applied to slop_index.weights for this call
"""

from __future__ import annotations

import json

from . import weights as W
from . import substance
from .classify import classify, author_role
from .score import summarise


def score_records(records, icite, surname, overrides=None, excluded=None):
    if isinstance(records, str):
        records = json.loads(records)
    if isinstance(icite, str):
        icite = json.loads(icite)
    if isinstance(overrides, str):
        overrides = json.loads(overrides) if overrides else None
    excluded = set(excluded or [])

    saved = {}
    for k, v in (overrides or {}).items():
        if hasattr(W, k):
            saved[k] = getattr(W, k)
            setattr(W, k, v)
    try:
        kept = [a for a in records if a["identifiers"]["pmid"] not in excluded]
        self_sim = substance.self_similarity(kept)
        rows = []
        for a in records:
            p = a["identifiers"]["pmid"]
            c = classify(a)
            cit = icite.get(p) or {}
            rcr = cit.get("relative_citation_ratio")
            rcr = float(rcr) if rcr not in ("", None) else None
            sub = substance.score(a, c.tier, c.subtype, c.topics, rcr, self_sim.get(p, 0))
            rows.append({
                "pmid": p,
                "year": a.get("publication_date", {}).get("year", ""),
                "role": author_role(a, surname),
                "journal": a.get("journal", {}).get("iso_abbreviation", ""),
                "title": a.get("title", ""),
                "tier": c.tier, "subtype": c.subtype, "confidence": c.confidence,
                "needs_review": c.needs_review, "topics": c.topics,
                "citation_count": int(cit.get("citation_count") or 0),
                "rcr": round(rcr, 2) if rcr is not None else None,
                "design": sub.design, "outcome": sub.outcome, "exposure": sub.exposure,
                "hedge": sub.hedge, "self_similar": sub.self_similar,
                "identity": sub.identity, "social": sub.social,
                "topic_penalty": sub.topic_penalty, "rescued": sub.rescued,
                "value": sub.value, "value_norm": sub.value_norm,
                "components": sub.components,
                "excluded": p in excluded,
                "evidence": c.evidence,
                "doi": a["identifiers"].get("doi", ""),
            })
        rows.sort(key=lambda r: (str(r["year"]), r["pmid"]))
        summary = summarise(rows)
        return {"rows": rows, "summary": summary}
    finally:
        for k, v in saved.items():
            setattr(W, k, v)


def score_records_json(records_json, icite_json, surname, overrides_json="", excluded_json="[]"):
    """String-in, string-out wrapper that is convenient to call from JavaScript."""
    return json.dumps(score_records(json.loads(records_json), json.loads(icite_json), surname,
                                    json.loads(overrides_json) if overrides_json else None,
                                    json.loads(excluded_json)))


def default_weights():
    return {k: getattr(W, k) for k in dir(W) if k.isupper() and not k.startswith("_")}
