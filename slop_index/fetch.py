"""Data access: PubMed E-utilities (esearch/efetch) and NIH iCite citations.

Everything here uses urllib so the tool runs on a bare Python install.
Both APIs are free and need no key. NCBI asks for no more than 3 requests
per second without a key; we sleep between calls to stay polite.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Iterable

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ICITE = "https://icite.od.nih.gov/api/pubs"
USER_AGENT = "slop-index/0.1 (https://github.com/galtmd/slop-index)"


def _get(url: str, retries: int = 3) -> bytes:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} tries: {url}\n{last}")


# ---------------------------------------------------------------- PubMed

def esearch(term: str, retmax: int = 1000) -> list[str]:
    """Return PMIDs matching a PubMed query string."""
    q = urllib.parse.urlencode({"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json"})
    data = json.loads(_get(f"{EUTILS}/esearch.fcgi?{q}"))
    return data["esearchresult"]["idlist"]


def efetch(pmids: Iterable[str], batch: int = 100) -> list[dict]:
    """Fetch PubMed XML for PMIDs and normalise to plain dicts."""
    pmids = list(pmids)
    out: list[dict] = []
    for i in range(0, len(pmids), batch):
        chunk = pmids[i : i + batch]
        q = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(chunk), "retmode": "xml"})
        xml = _get(f"{EUTILS}/efetch.fcgi?{q}")
        out.extend(parse_pubmed_xml(xml))
        time.sleep(0.4)
    return out


def _text(el, path, default=""):
    node = el.find(path)
    return (node.text or default) if node is not None else default


def parse_pubmed_xml(xml: bytes) -> list[dict]:
    root = ET.fromstring(xml)
    articles = []
    for art in root.findall(".//PubmedArticle"):
        med = art.find("MedlineCitation")
        a = med.find("Article")
        pmid = _text(med, "PMID")

        ids = {"pmid": pmid}
        for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
            t = aid.get("IdType")
            if t in ("doi", "pmc", "pii"):
                ids[t] = aid.text or ""

        # Abstract: join all sections (structured abstracts have several).
        abstract = "\n\n".join(
            ("".join(sec.itertext())).strip() for sec in a.findall("Abstract/AbstractText")
        ).strip()

        authors = []
        for au in a.findall("AuthorList/Author"):
            if au.find("CollectiveName") is not None:
                authors.append({"last_name": _text(au, "CollectiveName"), "fore_name": "", "initials": "", "affiliations": []})
                continue
            authors.append(
                {
                    "last_name": _text(au, "LastName"),
                    "fore_name": _text(au, "ForeName"),
                    "initials": _text(au, "Initials"),
                    "affiliations": [(_text(af, ".")).strip() for af in au.findall("AffiliationInfo/Affiliation")],
                }
            )

        pub_date = {}
        pd = a.find("ArticleDate")
        if pd is None:
            pd = a.find("Journal/JournalIssue/PubDate")
        if pd is not None:
            for k in ("Year", "Month", "Day"):
                v = _text(pd, k)
                if v:
                    pub_date[k.lower()] = v
            if "year" not in pub_date:
                md = _text(pd, "MedlineDate")
                if md[:4].isdigit():
                    pub_date["year"] = md[:4]

        articles.append(
            {
                "identifiers": ids,
                "title": "".join(a.find("ArticleTitle").itertext()).strip() if a.find("ArticleTitle") is not None else "",
                "abstract": abstract,
                "journal": {
                    "title": _text(a, "Journal/Title"),
                    "iso_abbreviation": _text(a, "Journal/ISOAbbreviation"),
                },
                "authors": authors,
                "publication_date": pub_date,
                "keywords": [(k.text or "").strip() for k in med.findall("KeywordList/Keyword")],
                "mesh_terms": [_text(m, "DescriptorName") for m in med.findall("MeshHeadingList/MeshHeading")],
                "article_types": [(pt.text or "").strip() for pt in a.findall("PublicationTypeList/PublicationType")],
                "language": _text(a, "Language"),
            }
        )
    return articles


# ----------------------------------------------------------------- iCite

def icite_citations(pmids: Iterable[str], batch: int = 200) -> dict[str, dict]:
    """Citation counts from the NIH Open Citation Collection via iCite.

    Returns {pmid: {"citation_count": int, "relative_citation_ratio": float|None, "year": int}}.
    """
    pmids = list(pmids)
    out: dict[str, dict] = {}
    for i in range(0, len(pmids), batch):
        chunk = pmids[i : i + batch]
        q = urllib.parse.urlencode({"pmids": ",".join(chunk), "fl": "pmid,citation_count,relative_citation_ratio,year"})
        data = json.loads(_get(f"{ICITE}?{q}"))
        for row in data.get("data", []):
            out[str(row["pmid"])] = {
                "citation_count": int(row.get("citation_count") or 0),
                "relative_citation_ratio": row.get("relative_citation_ratio"),
                "year": row.get("year"),
            }
        time.sleep(0.4)
    return out
