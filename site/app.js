/* Slop Index — runs entirely in the browser.
   PubMed (E-utilities) and NIH iCite are called directly; the scoring is the
   same Python package as the command-line tool, executed with Pyodide. */

const E = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils";
const ICITE = "https://icite.od.nih.gov/api/pubs";
const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/pyodide.js";

const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const state = { py: null, records: null, icite: null, surname: "", weights: null, defaults: null, excluded: new Set(), last: null };

function status(msg, busy = false) { const s = $("#status"); s.textContent = msg; s.classList.toggle("busy", busy); }

/* ---------------- Pyodide ---------------- */
async function loadPy() {
  if (state.py) return state.py;
  status("Loading the scoring engine (first visit downloads ~10 MB)…", true);
  await new Promise((res, rej) => { const s = document.createElement("script"); s.src = PYODIDE_URL; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
  const py = await loadPyodide();
  const manifest = await fetch("py/manifest.json").then((r) => r.json());
  py.FS.mkdirTree("/pkg/slop_index");
  for (const f of manifest.files) {
    const src = await fetch("py/" + f).then((r) => r.text());
    py.FS.writeFile("/pkg/slop_index/" + f, src);
  }
  await py.runPythonAsync("import sys; sys.path.insert(0, '/pkg'); import slop_index.web as web");
  state.py = py;
  return py;
}

/* ---------------- PubMed + iCite ---------------- */
function q(el, sel) { const n = el.querySelector(sel); return n ? n.textContent.trim() : ""; }

function parsePubmedXml(xml) {
  const doc = new DOMParser().parseFromString(xml, "text/xml");
  const out = [];
  for (const art of doc.querySelectorAll("PubmedArticle")) {
    const med = art.querySelector("MedlineCitation"); const a = med.querySelector("Article");
    const ids = { pmid: q(med, ":scope > PMID") };
    for (const id of art.querySelectorAll("PubmedData ArticleIdList ArticleId")) { const k = id.getAttribute("IdType"); if (["doi", "pmc", "pii"].includes(k)) ids[k] = id.textContent.trim(); }
    const abstract = [...a.querySelectorAll("Abstract AbstractText")].map((x) => { const lab = x.getAttribute("Label"); return (lab ? lab + ": " : "") + x.textContent.trim(); }).join("\n\n");
    const authors = [...a.querySelectorAll("AuthorList > Author")].map((au) => ({ last_name: q(au, "LastName") || q(au, "CollectiveName"), fore_name: q(au, "ForeName"), initials: q(au, "Initials"), affiliations: [...au.querySelectorAll("AffiliationInfo Affiliation")].map((x) => x.textContent.trim()) }));
    const pd = a.querySelector("ArticleDate") || a.querySelector("Journal JournalIssue PubDate"); const publication_date = {};
    if (pd) { for (const k of ["Year", "Month", "Day"]) { const v = q(pd, k); if (v) publication_date[k.toLowerCase()] = v; } if (!publication_date.year) { const md = q(pd, "MedlineDate"); if (/^\d{4}/.test(md)) publication_date.year = md.slice(0, 4); } }
    out.push({ identifiers: ids, title: q(a, "ArticleTitle"), abstract, journal: { title: q(a, "Journal Title"), iso_abbreviation: q(a, "Journal ISOAbbreviation") }, authors, publication_date,
      keywords: [...med.querySelectorAll("KeywordList Keyword")].map((x) => x.textContent.trim()),
      mesh_terms: [...med.querySelectorAll("MeshHeadingList MeshHeading DescriptorName")].map((x) => x.textContent.trim()),
      article_types: [...a.querySelectorAll("PublicationTypeList PublicationType")].map((x) => x.textContent.trim()), language: q(a, "Language") });
  }
  return out;
}

async function fetchAuthor(term) {
  status("Searching PubMed…", true);
  const es = await fetch(`${E}/esearch.fcgi?db=pubmed&retmode=json&retmax=1000&term=${encodeURIComponent(term)}`).then((r) => r.json());
  const pmids = es.esearchresult.idlist || [];
  if (!pmids.length) throw new Error("PubMed returned no papers for that query.");
  const records = [];
  for (let i = 0; i < pmids.length; i += 50) {
    status(`Fetching records ${Math.min(i + 50, pmids.length)} of ${pmids.length}…`, true);
    const xml = await fetch(`${E}/efetch.fcgi?db=pubmed&retmode=xml&id=${pmids.slice(i, i + 50).join(",")}`).then((r) => r.text());
    records.push(...parsePubmedXml(xml)); await sleep(350);
  }
  const icite = {};
  for (let i = 0; i < pmids.length; i += 100) {
    status(`Fetching citation counts ${Math.min(i + 100, pmids.length)} of ${pmids.length}…`, true);
    const d = await fetch(`${ICITE}?pmids=${pmids.slice(i, i + 100).join(",")}&fl=pmid,citation_count,relative_citation_ratio,year`).then((r) => r.json());
    for (const row of d.data || []) icite[String(row.pmid)] = { citation_count: row.citation_count ?? 0, relative_citation_ratio: row.relative_citation_ratio ?? null };
    await sleep(350);
  }
  return { records, icite };
}

/* ---------------- scoring ---------------- */
function overrides() {
  const o = {};
  for (const [k, v] of Object.entries(state.weights)) if (JSON.stringify(v) !== JSON.stringify(state.defaults[k])) o[k] = v;
  return o;
}

async function score() {
  const py = await loadPy();
  py.globals.set("_records", JSON.stringify(state.records));
  py.globals.set("_icite", JSON.stringify(state.icite));
  py.globals.set("_overrides", JSON.stringify(overrides()));
  py.globals.set("_excluded", JSON.stringify([...state.excluded]));
  py.globals.set("_surname", state.surname);
  const out = await py.runPythonAsync("web.score_records_json(_records, _icite, _surname, _overrides, _excluded)");
  state.last = JSON.parse(out);
  // Topic-neutral companion score: same weights with the two topic penalties set to zero.
  const neutral = Object.assign({}, overrides(), { IDENTITY_TOPIC_PENALTY: 0, SOCIAL_TOPIC_PENALTY: 0, AGENDA_TOPIC_PENALTY: 0, COMMENTARY_ON_IDENTITY: 0 });
  py.globals.set("_overrides", JSON.stringify(neutral));
  const outN = await py.runPythonAsync("web.score_records_json(_records, _icite, _surname, _overrides, _excluded)");
  state.neutral = JSON.parse(outN).summary.all_authorships.total_slop_index;
  render();
}

/* ---------------- rendering ---------------- */
const fmt = (x, d = 2) => (x === null || x === undefined ? "–" : typeof x === "number" ? x.toFixed(d) : x);
function bandOf(tsi) { return tsi == null ? "" : tsi < 0.47 ? "top" : tsi < 0.65 ? "mid" : "low"; }

const BAND_NAME = { top: "research band (below 0.47)", mid: "mixed band (0.47 to 0.65)", low: "commentary band (above 0.65)" };
function scaleHtml(tsi) {
  const pct = Math.max(0, Math.min(1, tsi ?? 0)) * 100;
  return `<div class="scale-bar"><span class="seg top" style="width:47%"></span><span class="seg mid" style="width:18%"></span><span class="seg low" style="width:35%"></span><i class="tick" style="left:57%" title="0.57: neutral"></i>${tsi == null ? "" : `<i class="marker" style="left:${pct.toFixed(1)}%" title="${fmt(tsi)}"></i>`}</div>
  <div class="scale-labels"><span>0</span><span style="left:47%">0.47</span><span style="left:57%">0.57</span><span style="left:65%">0.65</span><span>1</span></div>
  <div class="scale-words"><span>research</span><span>mixed</span><span>commentary</span></div>`;
}
function verdictHtml(a, l) {
  const band = bandOf(a.total_slop_index);
  const who = state.surname ? esc(state.surname) : "This author";
  const emp = a.papers ? Math.round(100 * a.tiers.A / Math.max(1, a.tiers.A + a.tiers.B + a.tiers.C)) : 0;
  const pen = Math.round(100 * (a.penalized_topic_share ?? 0));
  const opening = band === "top" ? `<b>${who}'s record is built on original data.</b>` : band === "mid" ? `<b>${who}'s record is mixed.</b>` : `<b>${who}'s record is mostly commentary and highly politicized topics.</b>`;
  return `${opening} ${a.tiers.A} of ${a.tiers.A + a.tiers.B + a.tiers.C} classified papers (${emp}%) report original data, ${pen}% fall under highly politicized topics and political agenda, and ${a.rescued_full} of those clear every rescue bar. The h-index is ${a.h_index}; over empirical papers alone it is ${a.h_empirical}. ${state.neutral == null ? "" : `With the topic penalties switched off the score would be <b>${fmt(state.neutral)}</b>; the gap of ${fmt(Math.abs(a.total_slop_index - state.neutral))} is the size of the editorial position.`}`;
}

function render() {
  const { rows, summary } = state.last; const a = summary.all_authorships, l = summary.lead_authorships;
  const band = bandOf(a.total_slop_index);
  $("#results").hidden = false;
  $("#tsi").textContent = fmt(a.total_slop_index);
  const bEl = $("#tsi-band"); bEl.className = `band ${band}`; bEl.textContent = BAND_NAME[band] || "";
  $("#verdict").innerHTML = verdictHtml(a, l);
  $("#hero-scale").innerHTML = scaleHtml(a.total_slop_index);
  $("#stats").innerHTML = [
    ["Topic-neutral TSI", fmt(state.neutral)],
    ["Citation-weighted TSI", fmt(a.total_slop_index_citation_weighted)],
    ["Slop Index (axis 1)", fmt(a.slop_index)],
    ["h-index / empirical h", `${a.h_index} / ${a.h_empirical}`],
    ["Papers A / B / C", `${a.tiers.A} / ${a.tiers.B} / ${a.tiers.C}`],
    ["Politicized-topic share", fmt(a.penalized_topic_share)],
    ["Rescued full / partial", `${a.rescued_full} / ${a.rescued_partial}`],
    ["Median paper value", fmt(a.median_paper_value, 1)],
    ["Lead-author TSI (n)", `${fmt(l.total_slop_index)} (${l.papers})`],
  ].map(([k, v]) => `<div class="stat"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  const tbody = rows.map((r) => `<tr class="${r.excluded ? "excluded" : ""}">
    <td><input type="checkbox" data-pmid="${r.pmid}" ${r.excluded ? "" : "checked"} title="uncheck to exclude (name collision)"></td>
    <td>${r.year || ""}</td><td>${r.role}</td>
    <td><span class="pill ${r.tier}">${r.tier}</span>${r.design}</td>
    <td>${r.outcome}</td><td>${r.exposure}</td>
    <td class="num">${r.citation_count}</td><td class="num">${fmt(r.rcr)}</td>
    <td>${r.identity ? "identity" : r.social ? "sdoh" : (r.agenda || "").replace(/_/g, " ")}${r.rescued === "full" || r.rescued === "partial" ? ` (${r.rescued})` : ""}</td>
    <td class="num ${r.value > 0 ? "pos" : r.value < 0 ? "neg" : ""}">${fmt(r.value, 1)}</td>
    <td>${r.doi ? `<a href="https://doi.org/${r.doi}" target="_blank" rel="noopener">${esc(r.title)}</a>` : esc(r.title)}<div class="note">${esc(r.journal)}${r.needs_review ? " · low confidence" : ""}</div></td>
  </tr>`).join("");
  $("#papers tbody").innerHTML = tbody;
  $("#papers").querySelectorAll("input[type=checkbox]").forEach((cb) => cb.addEventListener("change", (e) => { const p = e.target.dataset.pmid; if (e.target.checked) state.excluded.delete(p); else state.excluded.add(p); score(); }));
  $("#count").textContent = `${a.papers} papers (${a.papers_no_abstract} without an abstract, held out of the shares)`;
}
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

function csv() {
  const cols = ["pmid", "year", "role", "tier", "design", "outcome", "exposure", "hedge", "citation_count", "rcr", "identity", "social", "agenda", "rescued", "topic_penalty", "value", "excluded", "journal", "title", "doi"];
  const lines = [cols.join(",")].concat(state.last.rows.map((r) => cols.map((c) => { const v = r[c]; const s = v === null || v === undefined ? "" : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }).join(",")));
  return lines.join("\n");
}

/* ---------------- weights panel ---------------- */
const SLIDERS = [
  ["IDENTITY_TOPIC_PENALTY", -10, 0, 1], ["SOCIAL_TOPIC_PENALTY", -10, 0, 1], ["AGENDA_TOPIC_PENALTY", -10, 0, 1], ["QUALITATIVE_PENALTY", -10, 0, 1], ["COMMENTARY_ON_IDENTITY", -6, 0, 1],
  ["RESCUE_MIN_RCR", 0, 4, 0.25], ["RESCUE_MIN_DESIGN", 1, 8, 1],
  ["HARD_OUTCOME_BONUS", 0, 4, 1], ["SOFT_OUTCOME_PENALTY", -4, 0, 1], ["MECHANISTIC_BONUS", 0, 4, 1], ["DEMOGRAPHIC_EXPOSURE", -6, 0, 1],
  ["HEDGE_HIGH_PENALTY", -3, 0, 1], ["SELF_SIMILAR_PENALTY", -4, 0, 1], ["COMMENTARY_RCR_CAP", 0, 4, 1],
];
function buildWeights() {
  $("#weights").innerHTML = SLIDERS.map(([k, lo, hi, st]) => `<div><label><span>${k.toLowerCase().replace(/_/g, " ")}</span><b id="w-${k}">${state.weights[k]}</b></label><input type="range" min="${lo}" max="${hi}" step="${st}" value="${state.weights[k]}" data-k="${k}"></div>`).join("");
  $("#weights").querySelectorAll("input[type=range]").forEach((inp) => inp.addEventListener("input", (e) => { const k = e.target.dataset.k; state.weights[k] = Number(e.target.value); $("#w-" + k).textContent = e.target.value; }));
  $("#weights").querySelectorAll("input[type=range]").forEach((inp) => inp.addEventListener("change", () => { if (state.last) score(); }));
}
function presetNeutral() { state.weights.IDENTITY_TOPIC_PENALTY = 0; state.weights.SOCIAL_TOPIC_PENALTY = 0; state.weights.AGENDA_TOPIC_PENALTY = 0; state.weights.COMMENTARY_ON_IDENTITY = 0; buildWeights(); if (state.last) score(); }
function presetDefault() { state.weights = JSON.parse(JSON.stringify(state.defaults)); buildWeights(); if (state.last) score(); }

/* ---------------- wiring ---------------- */
async function run() {
  const name = $("#author").value.trim(); const variant = $("#variant").value.trim(); const surnameIn = $("#surname").value.trim();
  if (!name) { status("Enter an author as PubMed lists them, e.g. Smith, John A"); return; }
  $("#run").disabled = true;
  try {
    const terms = [name].concat(variant ? [variant] : []).map((n) => `"${n}"[Full Author Name]`);
    const term = $("#raw").checked ? name : terms.join(" OR ");
    state.surname = surnameIn || name.split(",")[0].trim();
    state.excluded = new Set();
    const { records, icite } = await fetchAuthor(term);
    state.records = records; state.icite = icite;
    status("Scoring…", true); await score();
    status(`Done. ${records.length} papers scored in your browser; nothing was sent anywhere else.`);
  } catch (e) { status("Error: " + e.message); console.error(e); }
  $("#run").disabled = false;
}

document.addEventListener("DOMContentLoaded", async () => {
  state.defaults = await fetch("data/weights.json").then((r) => r.json());
  state.weights = JSON.parse(JSON.stringify(state.defaults));
  buildWeights();
  $("#run").addEventListener("click", run);
  $("#author").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  $("#neutral").addEventListener("click", presetNeutral);
  $("#defaults").addEventListener("click", presetDefault);
  $("#copycsv").addEventListener("click", async () => { try { await navigator.clipboard.writeText(csv()); status("CSV copied to clipboard."); } catch { status("Clipboard blocked; use Download."); } });
  $("#dlcsv").addEventListener("click", () => { const b = new Blob([csv()], { type: "text/csv" }); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = `slop-index-${state.surname || "author"}.csv`; a.click(); });
  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => { $("#author").value = c.dataset.author; $("#variant").value = c.dataset.variant || ""; $("#surname").value = c.dataset.surname || ""; $("#raw").checked = false; run(); }));
  const params = new URLSearchParams(location.search); if (params.get("author")) { $("#author").value = params.get("author"); if (params.get("variant")) $("#variant").value = params.get("variant"); if (params.get("surname")) $("#surname").value = params.get("surname"); run(); }
});
