# Slop Index

A companion to the h-index that asks the questions the h-index ignores: how much of a researcher's bibliography reports original empirical work, what is it about, and does any of it add actionable science?

The h-index counts citations without caring what was cited. A viewpoint in JAMA and a randomized trial in JAMA count the same. This tool scores every PubMed-indexed paper on three axes, reports each separately, and then combines them into one clearly labeled composite, the **Total Slop Index**.

```
Slop Index        = 1 − (h_empirical / h)          axis 1 only: how much impact comes from papers with no data
Total Slop Index  = 1 − mean(normalised paper value)  all three axes: 0 = every paper is a major trial or discovery, 1 = every paper is slop
```

## What it measures

Three axes, each reported on its own, then a composite.

**Axis 1: study type (objective).** Each paper is placed in one tier using PubMed publication types, MeSH study-design headings, and the language of the abstract.

| Tier | Meaning | Subtypes |
|---|---|---|
| A | Original empirical work | trial, bench, observational, case report |
| B | Synthesis or modeling, no primary data | review, meta-analysis, modeling, methods |
| C | Commentary | editorial, letter, perspective, viewpoint, opinion |

From this come the headline numbers: the share of papers in each tier, the h-index, the empirical h-index (Tier A only), the commentary h-index (Tier C only), the Slop Index, and the share of all citations that went to commentary. Everything is computed twice, once over all authorships and once over lead authorships (first, last, or sole author), because a middle-author slot on a large trial says little about the person being scored.

**Axis 2: topic (transparent, but a judgment call).** Each paper is flagged if its MeSH terms, keywords, or title fall into any of four buckets: `race_ethnicity`, `social_determinants`, `policy_politics`, `equity_justice`. These are reported as shares alongside the study-type numbers. They are *not* folded into the Slop Index. A rigorous cross-sectional analysis of racial disparities is still a Tier A paper, and an index that pretends otherwise would be dismissed on contact. The topic axis tells you what someone writes about; the study-type axis tells you whether they generate evidence or opine on it.

**Axis 3: substance.** Having data is a floor, not a standard. A cross-sectional survey reporting that one group says it exercises less than another, followed by a paragraph of cultural speculation, passes the Tier A gate and should not get full credit. This axis asks whether the paper adds actionable science. Each paper gets a value built from six signals, every one of which appears as its own column in `papers.csv`:

| Signal | What it detects | Points (defaults in `weights.py`) |
|---|---|---|
| Design | major trial, trial, bench, quasi-experimental, cohort, registry, survey, case report, modeling, review, commentary | +10 down to −3 |
| Outcome | hard endpoints (death, disease, birth weight, biomarkers, complications) vs soft (self-report, attitudes, perceptions, lived experience) | +2 / −2 |
| Exposure | an intervention, drug, procedure, gene or pathway vs a demographic label as the thing being studied | +2 / −3 |
| Hedge | conclusion states effect sizes vs "may", "suggests", "warrants further research" | +1 / −1 |
| Impact | iCite Relative Citation Ratio (1.0 = NIH field average) | +4 down to −2; capped at +1 for commentary |
| Self-similarity | the same dataset sliced into many near-duplicate papers | −2 when a paper has 3+ near-twins |

Then the topic penalty. A paper whose subject is an identity topic (race, ethnicity, gender identity, sexual orientation, discrimination, bigotry, lived experience, equity) or a social-determinants topic (socioeconomic position, neighborhood, housing, food insecurity, insurance status, incarceration, jail, prison, policing) **starts at −5** (−8 if it is an opinion piece). That penalty is waived only if the paper clears all three rescue criteria: a design at cohort level or better, a hard endpoint, and a Relative Citation Ratio of at least 1.5. Missing one criterion halves the penalty; missing two keeps it in full. Policy as a subject is not penalised by itself.

The social-determinants penalty is deliberate. Most of that literature establishes, at length, that poverty, bad neighborhoods, and incarceration are associated with worse health, which nobody disputed, and then frames conditions that follow from choices as things that happened to people. Treating it like identity-topic work means it has to earn credit with design, endpoints, and impact, exactly as any other paper does. A county-level cohort analysis of incarceration and cause-specific mortality with a Relative Citation Ratio above 4 does clear the bar; a cross-sectional survey of self-rated health by neighborhood does not.

The paper value is clipped to [−12, +16] and mapped to [0, 1]. The Total Slop Index is one minus the mean. A citation-weighted version is reported alongside it, as is a substantive h-index (the h-index computed only over papers with positive value).

This axis encodes an editorial position and does not pretend otherwise. The position is that trials, mechanistic discoveries, and strong causal designs with hard endpoints are what a scientific bibliography is for, and that identity-topic work has to earn its way back in with methodology and endpoints rather than with the subject alone. Every number is in `weights.py`. Setting `IDENTITY_TOPIC_PENALTY` and `SOCIAL_TOPIC_PENALTY` to zero gives a topic-neutral version of the same index, which is a useful thing to report next to the default so readers can see exactly how much of a score is the topic penalty.

## Why the rules are the way they are

PubMed's publication-type field is thin. Most observational research is tagged only "Journal Article". So the classifier leans on MeSH design headings (Cross-Sectional Studies, Cohort Studies, Logistic Models, and so on) and on abstract language that signals data collection and analysis: "we analyzed", "data were collected", sample sizes, p-values, confidence intervals, odds ratios, study-design vocabulary. Each signal adds to an `empirical_score`; the thresholds and vocabularies are all in `slop_index/classify.py` and are meant to be argued with.

The classifier is conservative in one direction: a paper lands in Tier A only when there is concrete evidence of original data. Ambiguous papers fall to Tier C with `confidence = low` and `needs_review = True`, and the `evidence` column in `papers.csv` says why. Fix them with an `overrides.csv` rather than by loosening the rules.

Known failure modes, so you don't have to discover them:

- **Name collisions.** A search on `El-Sayed AM[Author]` returns 260 papers, most of them by an Egyptian pharmacognosist, a New Zealand entomologist, and a physicist. The tool searches on PubMed's Full Author Name field, which is much cleaner, but you should still read the list and put collisions in `exclude.csv`. Google Scholar profiles are useful for cross-checking.
- **PubMed scope.** Books, book chapters, policy reports, op-eds, and most social-science journals are not in PubMed. Google Scholar h-indexes include them; this tool's h-index will usually be lower.
- **Research letters.** A "Letter" with strong empirical signals is treated as Tier A. Pure correspondence stays Tier C.
- **Modeling and simulation.** Agent-based models and projections are Tier B. They are original work but not original data. Change `classify_study_type` if you disagree.
- **Missing abstracts.** Some records (notably some Lancet pieces) have no abstract in PubMed. These are flagged.

## Website

The `site/` folder is a static page that runs the whole index in the visitor's browser: PubMed and iCite are queried directly, and the scoring package is executed in-page with Pyodide, so there is one source of truth and no server. `python tools/build_site.py` copies the package into `site/py/` and writes the precomputed comparison table; `netlify.toml` runs it on deploy. The site has a weights panel with a topic-neutral preset, so any score can be shown next to the number it would be without the editorial choices.

## Install and run

Standard library only. Python 3.9 or later.

```bash
git clone https://github.com/galtmd/slop-index.git
cd slop-index

# Score an author by PubMed Full Author Name (fetches records and citations, caches them):
python -m slop_index run --author "El-Sayed, Abdulrahman M" --author-variant "El-Sayed, Abdul M" --slug el-sayed-am

# Re-run on cached data (after editing exclude.csv or overrides.csv):
python -m slop_index run --slug el-sayed-am --surname El-Sayed

# Score an explicit PMID list:
python -m slop_index run --pmids 33502685 19643005 22819424 --slug demo --surname El-Sayed

# Tests:
python -m unittest discover tests
```

Citation counts come from the NIH iCite API (the NIH Open Citation Collection), which is free, keyless, and keyed by PMID. It undercounts relative to Google Scholar because it only counts citations from PubMed-indexed papers, but it is consistent across people, which is what matters for comparison.

## Files

```
slop_index/
  fetch.py       PubMed E-utilities and iCite clients (urllib only)
  classify.py    axis 1 and 2: study type and topic flags
  substance.py   axis 3: design, outcome, exposure, hedge, self-similarity, identity penalty and rescue
  weights.py     every constant in the substance score and composite
  score.py       h-index, empirical h-index, Slop Index, substantive h-index, Total Slop Index
  cli.py         command line
data/<slug>/
  pubmed_raw.json        cached PubMed records
  icite_citations.csv    cached citation counts
  exclude.csv            pmid,reason          (name collisions)
  overrides.csv          pmid,tier,subtype,note (manual corrections)
results/<slug>/
  papers.csv     one row per paper with tier, subtype, confidence, topics, citations, evidence
  summary.json   all scores
  report.md      readable summary with a per-paper table
```

## Calibration: seventeen authors side by side

`results/comparison.md` is produced by `python -m slop_index compare` from every scored author. The roster was chosen to anchor the scale with real people at different points: two Nobel-winning bench scientists, a cardiology trialist, three Great Barrington Declaration authors, two surgeon-administrators, a senator-elect epidemiologist, eight social epidemiologists and sociologists of health whose subject is race, structural racism, intersectionality, or socioeconomic position, and one economist (Anne Case) who works the same social-determinants territory with hard mortality data.


| Author | Papers (no abstract) | A / B / C | h | hₑ | Slop Index | Penalized share | Rescued full/partial | Positive-value share | Median value | **Total Slop Index** | Cite-weighted | Lead TSI (n) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Katalin Karikó (mRNA biochemistry; Nobel 2023) | 66 (4) | 52 / 5 / 5 | 45 | 40 | 0.111 | 0.032 | 0/1 | 0.919 | 13.0 | **0.178** | 0.099 | 0.214 (26) |
| Emmanuelle Charpentier (CRISPR; Nobel 2020) | 87 (2) | 55 / 19 / 11 | 40 | 25 | 0.375 | 0.035 | 0/2 | 0.847 | 9.0 | **0.32** | 0.257 | 0.332 (49) |
| Jessica Mega (cardiology trialist, TIMI) | 74 (2) | 45 / 18 / 9 | 37 | 25 | 0.324 | 0.125 | 1/0 | 0.792 | 7.5 | **0.339** | 0.223 | 0.3 (33) |
| Mehmet Oz (cardiothoracic surgeon; CMS administrator) | 130 (3) | 94 / 15 / 18 | 47 | 42 | 0.106 | 0.031 | 0/0 | 0.78 | 5.0 | **0.396** | 0.37 | 0.461 (44) |
| Marty Makary (surgeon; FDA commissioner) | 323 (12) | 224 / 14 / 73 | 69 | 63 | 0.087 | 0.064 | 2/7 | 0.73 | 6.0 | **0.411** | 0.312 | 0.5 (128) |
| Martin Kulldorff (biostatistician; GBD author) | 170 (0) | 129 / 17 / 24 | 50 | 46 | 0.08 | 0.059 | 0/1 | 0.8 | 5.0 | **0.427** | 0.34 | 0.507 (53) |
| Sunetra Gupta (theoretical epidemiologist; GBD author) | 95 (2) | 44 / 34 / 15 | 32 | 24 | 0.25 | 0.118 | 0/2 | 0.72 | 3.0 | **0.443** | 0.262 | 0.453 (36) |
| Jay Bhattacharya (health economist; NIH director; GBD author) | 129 (1) | 99 / 2 / 27 | 36 | 34 | 0.056 | 0.266 | 5/7 | 0.648 | 4.0 | **0.472** | 0.34 | 0.51 (52) |
| Anne Case (economist; deaths of despair) | 31 (5) | 16 / 2 / 8 | 22 | 13 | 0.409 | 0.654 | 1/6 | 0.577 | 2.0 | **0.578** | 0.5 | 0.572 (30) |
| Abdul El-Sayed (epidemiologist; US Senator-elect) | 70 (1) | 47 / 10 / 12 | 27 | 22 | 0.185 | 0.696 | 1/5 | 0.304 | -2 | **0.625** | 0.513 | 0.658 (45) |
| Nancy Krieger (social epidemiologist, Harvard) | 240 (5) | 135 / 19 / 81 | 67 | 52 | 0.224 | 0.8 | 6/48 | 0.362 | -2.0 | **0.65** | 0.614 | 0.679 (178) |
| Arline Geronimus (weathering hypothesis, Michigan) | 60 (1) | 38 / 5 / 16 | 30 | 22 | 0.267 | 0.966 | 4/13 | 0.339 | -3 | **0.663** | 0.609 | 0.694 (36) |
| Rachel Hardeman (structural racism and birth outcomes, Minnesota) | 105 (7) | 56 / 9 / 33 | 41 | 32 | 0.22 | 0.918 | 1/20 | 0.296 | -3.8 | **0.695** | 0.608 | 0.751 (46) |
| Jonathan Metzl (psychiatrist-sociologist, Vanderbilt) | 33 (2) | 9 / 6 / 16 | 15 | 7 | 0.533 | 0.548 | 0/3 | 0.161 | -5.0 | **0.729** | 0.701 | 0.726 (28) |
| Camara Phyllis Jones (levels of racism; former APHA president) | 37 (5) | 9 / 6 / 17 | 19 | 9 | 0.526 | 0.844 | 0/0 | 0.125 | -7.0 | **0.784** | 0.658 | 0.779 (12) |
| Chandra Ford (public health critical race praxis, UCLA) | 72 (2) | 29 / 10 / 31 | 24 | 13 | 0.458 | 0.957 | 0/4 | 0.129 | -6.5 | **0.794** | 0.813 | 0.821 (42) |
| Lisa Bowleg (intersectionality in public health, GWU) | 99 (4) | 44 / 14 / 37 | 30 | 21 | 0.3 | 0.947 | 0/3 | 0.084 | -7 | **0.8** | 0.747 | 0.809 (68) |

How to read it. The Total Slop Index runs from 0 (every paper a major trial or discovery) to 1 (every paper identity-topic commentary); a bibliography of papers with nothing to recommend and nothing to penalize scores 0.57. The table falls into three bands.

The top band (0.18 to 0.44) is bench science, trials, and clinical or statistical research with hard endpoints: Karikó, Charpentier, Mega, Oz, Makary, Kulldorff, Gupta. These people disagree about plenty, but their bibliographies are built the same way: mostly original data, low topic penalties, positive median paper value.

The middle (0.47 to 0.63) is where the topic penalty begins to bite but strong design still rescues papers: Bhattacharya, Case, El-Sayed. Bhattacharya has the highest count of fully rescued papers on the list (five), which is what quasi-experimental health economics with mortality endpoints earns. Case is the instructive control: nearly two thirds of her papers are penalized social-determinants topics, but her median paper value stays positive because the work is cohort and time-series analysis of death rates, and her deaths-of-despair papers carry Relative Citation Ratios in the 20s and 50s.

The bottom band (0.65 to 0.80) is the social-epidemiology and critical-race literature: Krieger, Geronimus, Hardeman, Metzl, Jones, Ford, Bowleg. Every one of them has a negative median paper value, and the pattern is consistent: 80 to 97 percent of their papers are penalized topics; a third to a half of their output is commentary; and the empirical papers are mostly cross-sectional surveys with self-reported outcomes and a demographic label as the exposure. Krieger is the exception that proves the rule: a 240-paper record with 135 empirical papers and an h-index of 67, but 81 commentaries and only six papers that clear all three rescue bars, so the composite lands at 0.65 despite real productivity. Geronimus's weathering work sits highest in this band because several of her allostatic-load papers use measured biomarkers and clear the hard-endpoint bar.

El-Sayed, the record that motivated the tool, lands at 0.63, at the boundary between the middle and bottom bands: his bibliography is more empirical than the sociologists' and less rescued than the economists'. Anyone who disagrees with the topic weighting can set the two topic penalties to zero in `weights.py` and rerun; the README says so because the comparison is only credible if the lever is visible.

Caveats that apply to every row: PubMed does not index books, op-eds, policy reports, or many economics and social-science journals, so Bhattacharya's, Case's, and Gupta's records are undercounted and Makary's commentary is overcounted relative to a full CV; PubMed full-name indexing begins around 2002, which clips the early careers of Oz, Charpentier, and Krieger; and papers without an abstract in PubMed cannot be classified and are held out of the shares. The classifier was tuned on these seventeen records; every rule change is in the commit history.

## Extending it

- Change any weight in `weights.py`; rerun; the per-paper `components` column shows exactly where each paper's value came from.
- Add vocabularies or adjust thresholds in `classify.py` and `substance.py`; the tests in `tests/` should keep passing.
- To use an LLM for the gray cases, write a function that takes an article dict and returns `(tier, subtype)`, and apply it only where `needs_review` is true. Publish the prompt with the results.
- OpenAlex (`api.openalex.org`) has author IDs, which solve the disambiguation problem, and broader citation counts. A fetcher for it would be a natural next step.

## License

MIT.
