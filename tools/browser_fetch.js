// Fetch an author's PubMed records and iCite citation counts from inside a
// browser (DevTools console on any https://eutils.ncbi.nlm.nih.gov page), and
// download one JSON bundle that `python -m slop_index import` understands.
//
// Use this when your shell cannot reach the NIH APIs directly.
//
//   await slopFetch("kulldorff-m", '"Kulldorff, Martin"[Full Author Name]')
//
async function slopFetch(slug, term, opts = {}) {
  const E = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils";
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const t = s => (s == null ? "" : s);

  const es = await fetch(`${E}/esearch.fcgi?db=pubmed&retmode=json&retmax=${opts.retmax || 1000}&term=${encodeURIComponent(term)}`).then(r => r.json());
  const pmids = es.esearchresult.idlist;
  const records = [];
  for (let i = 0; i < pmids.length; i += 50) {
    const chunk = pmids.slice(i, i + 50);
    const xml = await fetch(`${E}/efetch.fcgi?db=pubmed&retmode=xml&id=${chunk.join(",")}`).then(r => r.text());
    const doc = new DOMParser().parseFromString(xml, "text/xml");
    for (const art of doc.querySelectorAll("PubmedArticle")) {
      const q = (el, sel) => { const n = el.querySelector(sel); return n ? n.textContent.trim() : ""; };
      const med = art.querySelector("MedlineCitation");
      const a = med.querySelector("Article");
      const ids = { pmid: q(med, ":scope > PMID") };
      for (const id of art.querySelectorAll("PubmedData ArticleIdList ArticleId")) {
        const k = id.getAttribute("IdType"); if (["doi", "pmc", "pii"].includes(k)) ids[k] = id.textContent.trim();
      }
      const abstract = [...a.querySelectorAll("Abstract AbstractText")].map(x => {
        const lab = x.getAttribute("Label"); return (lab ? lab + ": " : "") + x.textContent.trim();
      }).join("\n\n");
      const authors = [...a.querySelectorAll("AuthorList > Author")].map(au => ({
        last_name: q(au, "LastName") || q(au, "CollectiveName"),
        fore_name: q(au, "ForeName"), initials: q(au, "Initials"),
        affiliations: [...au.querySelectorAll("AffiliationInfo Affiliation")].map(x => x.textContent.trim()),
      }));
      let pd = a.querySelector("ArticleDate") || a.querySelector("Journal JournalIssue PubDate");
      const publication_date = {};
      if (pd) { for (const k of ["Year", "Month", "Day"]) { const v = q(pd, k); if (v) publication_date[k.toLowerCase()] = v; }
        if (!publication_date.year) { const md = q(pd, "MedlineDate"); if (/^\d{4}/.test(md)) publication_date.year = md.slice(0, 4); } }
      records.push({
        identifiers: ids,
        title: q(a, "ArticleTitle"),
        abstract,
        journal: { title: q(a, "Journal Title"), iso_abbreviation: q(a, "Journal ISOAbbreviation") },
        authors, publication_date,
        keywords: [...med.querySelectorAll("KeywordList Keyword")].map(x => x.textContent.trim()),
        mesh_terms: [...med.querySelectorAll("MeshHeadingList MeshHeading DescriptorName")].map(x => x.textContent.trim()),
        article_types: [...a.querySelectorAll("PublicationTypeList PublicationType")].map(x => x.textContent.trim()),
        language: q(a, "Language"),
      });
    }
    await sleep(400);
  }
  const icite = [];
  for (let i = 0; i < pmids.length; i += 100) {
    const chunk = pmids.slice(i, i + 100);
    const d = await fetch(`https://icite.od.nih.gov/api/pubs?pmids=${chunk.join(",")}&fl=pmid,citation_count,relative_citation_ratio,year`).then(r => r.json());
    for (const row of d.data || []) icite.push({ pmid: String(row.pmid), citation_count: row.citation_count ?? 0, relative_citation_ratio: row.relative_citation_ratio ?? "", year: row.year ?? "" });
    await sleep(400);
  }
  const bundle = { slug, term, fetched: new Date().toISOString(), count: records.length, records, icite };
  const blob = new Blob([JSON.stringify(bundle)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const aEl = document.createElement("a"); aEl.href = url; aEl.download = `${slug}.slopindex.json`; document.body.appendChild(aEl); aEl.click(); aEl.remove();
  return { slug, searched: pmids.length, fetched: records.length, icite: icite.length, bytes: blob.size };
}
