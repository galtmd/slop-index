"""Scores built on top of the per-paper classifications."""

from __future__ import annotations


def h_index(citations: list[int]) -> int:
    cites = sorted((c for c in citations if c is not None), reverse=True)
    h = 0
    for i, c in enumerate(cites, start=1):
        if c >= i:
            h = i
        else:
            break
    return h


def summarise(rows: list[dict]) -> dict:
    """rows: dicts with keys tier, subtype, role, citation_count, topics, excluded."""
    rows = [r for r in rows if not r.get("excluded")]
    lead = [r for r in rows if r["role"] in ("first", "last", "sole")]

    def block(subset_all: list[dict]) -> dict:
        n_total = len(subset_all)
        unknown = sum(1 for r in subset_all if r["tier"] == "U")
        subset = [r for r in subset_all if r["tier"] != "U"]   # classified papers only
        n = len(subset)
        tiers = {t: sum(1 for r in subset if r["tier"] == t) for t in "ABC"}
        subtypes: dict[str, int] = {}
        for r in subset:
            subtypes[r["subtype"]] = subtypes.get(r["subtype"], 0) + 1
        cites_all = [r["citation_count"] for r in subset_all]   # h-index over every paper
        cites_a = [r["citation_count"] for r in subset if r["tier"] == "A"]
        cites_c = [r["citation_count"] for r in subset if r["tier"] == "C"]
        h = h_index(cites_all)
        h_e = h_index(cites_a)
        h_c = h_index(cites_c)
        total_c = sum(cites_all)
        topic_any = sum(1 for r in subset if r["topics"])
        vals = [r["value_norm"] for r in subset if r.get("value_norm") is not None]
        cw = [(r["value_norm"], r["citation_count"]) for r in subset if r.get("value_norm") is not None]
        cw_total = sum(c for _, c in cw)
        pos_cites = [r["citation_count"] for r in subset if (r.get("value") or 0) > 0]
        identity_n = sum(1 for r in subset if r.get("identity"))
        penalized_n = sum(1 for r in subset if r.get("identity") or r.get("social"))
        designs: dict[str, int] = {}
        for r in subset:
            d = r.get("design", "")
            designs[d] = designs.get(d, 0) + 1
        topic_counts: dict[str, int] = {}
        for r in subset:
            for t in r["topics"]:
                topic_counts[t] = topic_counts.get(t, 0) + 1
        return {
            "papers": n_total,
            "papers_classified": n,
            "papers_no_abstract": unknown,
            "tiers": tiers,
            "subtypes": dict(sorted(subtypes.items(), key=lambda kv: -kv[1])),
            "empirical_share": round(tiers["A"] / n, 3) if n else None,
            "synthesis_share": round(tiers["B"] / n, 3) if n else None,
            "commentary_share": round(tiers["C"] / n, 3) if n else None,
            "h_index": h,
            "h_empirical": h_e,
            "h_commentary": h_c,
            "slop_index": round(1 - h_e / h, 3) if h else None,
            "total_citations": total_c,
            "citations_to_commentary_share": round(sum(cites_c) / total_c, 3) if total_c else None,
            "citations_to_empirical_share": round(sum(cites_a) / total_c, 3) if total_c else None,
            "topic_share_any": round(topic_any / n, 3) if n else None,
            "topic_counts": topic_counts,
            "topic_shares": {k: round(v / n, 3) for k, v in topic_counts.items()} if n else {},
            "needs_review": sum(1 for r in subset if r.get("needs_review")),
            # ---- substance axis and composite
            "designs": dict(sorted(designs.items(), key=lambda kv: -kv[1])),
            "identity_topic_share": round(identity_n / n, 3) if n else None,
            "penalized_topic_share": round(penalized_n / n, 3) if n else None,
            "rescued_full": sum(1 for r in subset if r.get("rescued") == "full"),
            "rescued_partial": sum(1 for r in subset if r.get("rescued") == "partial"),
            "mean_paper_value": round(sum(r["value"] for r in subset) / n, 2) if n else None,
            "median_paper_value": (sorted(r["value"] for r in subset)[n // 2] if n % 2 else
                                   round((sorted(r["value"] for r in subset)[n // 2 - 1] + sorted(r["value"] for r in subset)[n // 2]) / 2, 1)) if n else None,
            "share_positive_value": round(sum(1 for r in subset if r["value"] > 0) / n, 3) if n else None,
            "h_substantive": h_index(pos_cites),
            "total_slop_index": round(1 - sum(vals) / len(vals), 3) if vals else None,
            "total_slop_index_citation_weighted": round(1 - sum(v * c for v, c in cw) / cw_total, 3) if cw_total else None,
        }

    return {"all_authorships": block(rows), "lead_authorships": block(lead)}
