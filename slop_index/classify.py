"""Rule-based classification of a PubMed record on two independent axes.

Axis 1, study type (the objective axis):
    A  original empirical work  (subtypes: trial, bench, observational)
    B  synthesis or modeling    (subtypes: review, meta-analysis, modeling, methods)
    C  commentary               (editorial, letter, perspective, viewpoint, opinion)

Axis 2, topic flags (transparent but value-laden; reported separately):
    race_ethnicity, social_determinants, policy_politics, equity_justice

Every rule lives in this file so the method can be read, criticised, and
changed. The classifier is deliberately conservative: a paper gets Tier A
only when the metadata or abstract carries concrete evidence of original
data collection or analysis. Ambiguous papers fall to Tier C with
confidence "low" and a `needs_review` flag so a human can override them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

# ----------------------------------------------------------- vocabularies

COMMENTARY_PUBTYPES = {
    "Editorial", "Comment", "Letter", "News", "Interview", "Personal Narrative",
    "Lecture", "Address", "Legal Case", "Biography", "Historical Article",
    "Introductory Journal Article", "Newspaper Article", "Portrait", "Congress",
    "Consensus Development Conference", "Guideline", "Practice Guideline",
}
TRIAL_PUBTYPES = {
    "Randomized Controlled Trial", "Clinical Trial", "Controlled Clinical Trial",
    "Clinical Trial, Phase I", "Clinical Trial, Phase II", "Clinical Trial, Phase III",
    "Clinical Trial, Phase IV", "Pragmatic Clinical Trial", "Equivalence Trial",
    "Clinical Trial Protocol",
}
REVIEW_PUBTYPES = {"Review", "Systematic Review", "Meta-Analysis", "Scoping Review"}
OBSERVATIONAL_PUBTYPES = {
    "Observational Study", "Multicenter Study", "Validation Study", "Evaluation Study",
    "Twin Study", "Clinical Study",
}
CASE_REPORT_PUBTYPES = {"Case Reports"}

DESIGN_MESH = {
    "Cross-Sectional Studies", "Cohort Studies", "Case-Control Studies",
    "Longitudinal Studies", "Retrospective Studies", "Prospective Studies",
    "Follow-Up Studies", "Surveys and Questionnaires", "Health Surveys",
    "Registries", "Databases, Factual", "Interrupted Time Series Analysis",
    "Epidemiologic Studies", "Seroepidemiologic Studies", "Birth Certificates",
    "Death Certificates", "Vital Statistics", "Electronic Health Records",
    "Hospital Mortality", "Medical Records", "Interviews as Topic",
    "Focus Groups", "Qualitative Research", "Pilot Projects",
}
STATS_MESH = {
    "Logistic Models", "Regression Analysis", "Odds Ratio", "Risk Factors",
    "Prevalence", "Incidence", "Multivariate Analysis", "Models, Statistical",
    "Proportional Hazards Models", "Linear Models", "Risk Assessment",
    "Sensitivity and Specificity", "Confidence Intervals", "Risk",
    "Survival Analysis", "Analysis of Variance", "Least-Squares Analysis",
    "Bayes Theorem", "Spatial Analysis", "Small-Area Analysis",
}
BENCH_MESH = {
    "Animals", "Mice", "Rats", "Cell Line", "Cells, Cultured", "In Vitro Techniques",
    "Cell Line, Tumor", "Mice, Inbred C57BL", "Mice, Knockout", "Disease Models, Animal",
    "Blotting, Western", "Polymerase Chain Reaction", "Flow Cytometry",
    "Microscopy", "Gene Expression", "DNA Methylation", "Epigenesis, Genetic",
    "Proteomics", "Metabolomics", "Molecular Dynamics Simulation",
    "Chromatography, Liquid", "Mass Spectrometry", "Signal Transduction",
    # molecular biology / microbiology / structural biology
    "Bacterial Proteins", "RNA, Bacterial", "DNA, Bacterial", "Escherichia coli", "Streptococcus pyogenes",
    "Streptococcus", "Bacillus subtilis", "Listeria monocytogenes", "Staphylococcus aureus", "Pseudomonas aeruginosa",
    "Saccharomyces cerevisiae", "CRISPR-Cas Systems", "Gene Editing", "Endonucleases", "DNA Cleavage",
    "Gene Expression Regulation, Bacterial", "Gene Expression Regulation", "Mutation", "Plasmids", "Protein Binding",
    "Models, Molecular", "Amino Acid Sequence", "Base Sequence", "Protein Conformation", "Crystallography, X-Ray",
    "Cryoelectron Microscopy", "RNA, Guide, CRISPR-Cas Systems", "RNA, Small Untranslated", "RNA, Messenger",
    "Recombinant Proteins", "Protein Structure, Tertiary", "Binding Sites", "Catalytic Domain", "Nucleic Acid Conformation",
    "Molecular Sequence Data", "Sequence Alignment", "Phylogeny", "Genome, Bacterial", "Transcription, Genetic",
    "Protein Biosynthesis", "Ribosomes", "Virulence Factors", "Bacteriophages", "Virulence", "Enzyme Activation",
    "Substrate Specificity", "Kinetics", "HEK293 Cells", "HeLa Cells", "Cell Culture Techniques", "Mice, Inbred BALB C",
    "Mice, Transgenic", "Rats, Sprague-Dawley", "Rats, Wistar", "Dogs", "Swine", "Sheep", "Rabbits", "Macaca",
    "Myocytes, Cardiac", "Immunohistochemistry", "Enzyme-Linked Immunosorbent Assay", "Reverse Transcriptase Polymerase Chain Reaction",
    "Real-Time Polymerase Chain Reaction", "Transfection", "Gene Knockdown Techniques", "RNA Interference",
    "Dendritic Cells", "Toll-Like Receptors", "Cytokines", "Nucleosides", "Pseudouridine", "Nanoparticles",
    "Liposomes", "Vaccines, Synthetic", "mRNA Vaccines", "Lipids", "Protein Engineering", "Operon", "Regulon",
    "Mutagenesis, Site-Directed", "Sequence Analysis, RNA", "Sequence Analysis, DNA", "High-Throughput Nucleotide Sequencing",
    "Proteome", "Metabolome", "Cell Survival", "Apoptosis", "Cell Proliferation", "Signal Transduction",
}
MODELING_MESH = {
    "Computer Simulation", "Models, Theoretical", "Systems Analysis",
    "Models, Biological", "Models, Economic", "Monte Carlo Method",
    "Markov Chains", "Decision Support Techniques", "Cost-Benefit Analysis",
    "Forecasting",
}

# Journals that publish essays and opinion almost exclusively.
COMMENTARY_JOURNALS = {
    "Sci Am", "Virtual Mentor", "AMA J Ethics", "Hastings Cent Rep", "N Engl J Med",  # NEJM Perspective pieces
    "JAMA", "Lancet", "BMJ", "Health Aff Forefr", "Milbank Q",
}
# NEJM/JAMA/Lancet/BMJ also publish trials; they are only a tiebreaker when
# no empirical signal is present at all.

TITLE_COMMENTARY = re.compile(
    r"^(commentary|editorial|comment on|reply|response|in reply|authors? (reply|respond)|"
    r"three authors reply|letter|perspective|viewpoint|rethinking|putting the|toward|towards|"
    r"what is|why we|the case for|the case against|lessons from|a call|time to|on the|"
    r"in defen[cs]e|beyond|the importance of|the road to|the need for|the future of)\b",
    re.I,
)
TITLE_COMMENTARY_ANY = re.compile(
    r"\b(commentary|editorial|reply|respond|viewpoint|perspective|opinion|call to action|"
    r"need(s)? (better|more|to)|should|must|lessons)\b|\?$",
    re.I,
)

TITLE_SELF_COMMENTARY = re.compile(
    r"^(commentary|editorial|comment on|reply|response|in reply|authors? (reply|respond)|"
    r"\w+ authors reply|letter to|invited commentary|perspective|viewpoint)\b|--reply$|: reply$",
    re.I,
)
TITLE_SELF_REVIEW = re.compile(
    r"\b(systematic review|literature review|meta-analys[ie]s|scoping review|narrative review|"
    r"a review|review of the|comprehensive review|an? (updated )?review|state of the (science|evidence))\b",
    re.I,
)

RE_WE_DID = re.compile(
    r"\b(we|the authors?|this study|the study|our study|this analysis|our analysis|this paper|the paper|this article|"
    r"these analyses|our (data|results|estimates|findings))\s+"
    r"(then\s+|also\s+|first\s+|further\s+|here\s+|therefore\s+)?"
    r"(analy[sz]ed|analy[sz]e|used|use|examined|examine|estimated|estimate|conducted|conduct|"
    r"collected|collect|fit|fitted|compared|compare|calculated|calculate|measured|measure|"
    r"assessed|assess|surveyed|survey|modeled|modelled|model|simulated|simulate|performed|perform|"
    r"tested|test|identified|identify|investigated|investigate|evaluated|evaluate|characteri[sz]ed|"
    r"quantified|quantify|developed|develop|validated|validate|linked|link|pooled|pool|sampled|sample|"
    r"recruited|recruit|enrolled|enroll|randomi[sz]ed|randomi[sz]e|interviewed|interview|"
    r"reviewed|searched|screened|extracted|synthesi[sz]ed|aim(ed)? to|sought to|hypothesi[sz]ed?|"
    r"explored|explore|applied|apply|obtained|obtain|abstracted|drew|draw|ran|run|constructed|construct|"
    r"report|reported|present|presented|describe|described|tracked|followed|enrolled|"
    r"find|finds|found|show|showed|document|documented|exploit|exploited|leverage|leveraged|"
    r"estimate|estimated|quantify|quantified|regress|regressed)\b",
    re.I,
)
RE_PASSIVE = re.compile(
    r"\b(were|was|are|is)\s+(then\s+|also\s+|prospectively\s+|retrospectively\s+)?(collected|obtained|drawn|abstracted|analy[sz]ed|extracted|linked|used|included|"
    r"recruited|enrolled|identified|estimated|fit|fitted|conducted|performed|compared|measured|"
    r"assessed|derived|pooled|merged|calculated|examined|modeled|modelled|tested|run|constructed|"
    r"ascertained|classified|coded|weighted|tracked|reported|recorded|followed|screened|observed|"
    r"documented|counted|audited|reviewed|evaluated|surveyed|interviewed|randomi[sz]ed|assigned)\b",
    re.I,
)
RE_SAMPLE = re.compile(
    r"\b(n\s?=\s?[\d,]+|a total of\s+[\d,]+|[\d][\d,]{1,}\s+(participants|patients|respondents|individuals|women|men|"
    r"infants|births|subjects|adults|children|deaths|cases|counties|hospitals|records|"
    r"admissions|encounters|visits|students|mothers|persons|people|articles|studies|trials|"
    r"procedures|operations|samples|specimens|mice|rats|cells))\b",
    re.I,
)
RE_STATS = re.compile(
    r"(\bp\s?[<=>]\s?0?\.\d|95\s?%\s?(CI|confidence)|odds ratio|\bOR\s?[=:]|hazard ratio|"
    r"relative risk|risk ratio|rate ratio|\bRR\s?[=:]|\bHR\s?[=:]|\bIRR\b|\bβ\s?=|"
    r"\bb\s?=\s?-?\d|coefficient|standard deviation|\bSD\b|interquartile|\bIQR\b|"
    r"prevalence of|incidence of|adjusted for|after adjust|multivariable|multivariate|"
    r"statistically significant|significantly (higher|lower|greater|more|less|associated)|"
    r"\bIC\s?50\b|fold (change|increase|decrease)|mean\s?\(|median\s?\(|\bP\s?\(|"
    r"predicted probabilit|adjusted models?|stratified by|interaction (term|between)|"
    r"age-adjusted|age-standardi[sz]ed|per 100,?000|percentage points?|point estimate)",
    re.I,
)
RE_DESIGN = re.compile(
    r"\b(cross-sectional|cohort|case-control|longitudinal|retrospective|prospective|"
    r"randomi[sz]ed|randomi[sz]ed controlled|controlled trial|regression|logistic|"
    r"survey data|vital statistics|birth certificates?|birth records|death records|death certificates?|"
    r"using data (from|on)|data from the|secondary data|panel data|longitudinal survey|expenditure panel|"
    r"outcome variables?|explanatory variables?|dependent variable|natural experiment|"
    r"(between|from)\s+(19|20)\d{2}\s+(and|to|through)\s+(19|20)\d{2}|(19|20)\d{2}\s?[-–]\s?(19|20)\d{2}|"
    r"(mortality|death|enrollment|prevalence|incidence|suicide|overdose|employment) rates?|time series|"
    r"life expectancy|years of life|person-years|age-adjusted|age-specific|"
    r"surveillance data|individual-level|county-level|state-level|administrative data|claims data|"
    r"national (inpatient|health|survey)|nationwide inpatient sample|\bNIS\b|BRFSS|NHANES|"
    r"electronic health record|\bEHR\b|medical records|database|registry|census|"
    r"data (from|set|sets|were|was) |secondary (analysis|data)|time series|difference-in-differences|"
    r"instrumental variable|fixed effects|multilevel|hierarchical (linear|model)|"
    r"generalized linear|generalised linear|GEE|propensity|sensitivity analys[ie]s|"
    r"we (link|linked|merged|pooled)|linked (data|records)|interviews|focus groups|"
    r"thematic analysis|qualitative)\b",
    re.I,
)
RE_BENCH = re.compile(
    r"\b(in vitro|in vivo|cell lines?|cultured|knockout|transgenic|western blot|immunoblot|"
    r"endonuclease|nuclease|cleav\w+|guide RNA|crRNA|tracrRNA|CRISPR|Cas9|Cas\d+|Cpf1|plasmid|operon|promoter|"
    r"transcript\w*|translation|ribosom\w+|mRNA|tRNA|rRNA|sRNA|small RNA|RNA-seq|proteom\w+|metabolom\w+|"
    r"mutant|mutants|mutation|deletion|strain|strains|wild[- ]type|bacteri\w+|Streptococc\w+|Staphylococc\w+|"
    r"E\. coli|Escherichia|Bacillus|Listeria|Pseudomonas|Salmonella|yeast|virus|viral|phage|"
    r"enzyme|enzymatic|catalytic|substrate|binding|binds|bound|structure|structural|crystal|cryo-EM|"
    r"domain|residues?|amino acid|nucleotide|oligonucleotide|peptide|polypeptide|protein|proteins|"
    r"purified|recombinant|expression|expressed|overexpress\w+|knock-?down|siRNA|shRNA|"
    r"pathway|signaling|signalling|immune|immunity|cytokine|interferon|TLR|toll-like|dendritic|"
    r"lipid nanoparticle|LNP|liposome|nucleoside|pseudouridine|modified nucleosides?|immunogenic\w*|"
    r"myocyt\w+|cardiomyocyt\w+|perfusion|ischemi\w+|reperfusion|infarct\w+|canine|porcine|ovine|murine|rat model|"
    r"histolog\w+|immunohistochem\w+|ELISA|flow cytometry|microscop\w+|"
    r"qPCR|RT-PCR|PCR|flow cytometry|microscopy|assay|assays|mice|murine|rats?|zebrafish|"
    r"drosophila|C\. elegans|expression (of|levels)|phosphorylation|receptor|ligand|"
    r"kinase|chromatograph|spectrometry|spectroscopy|nanoparticles?|synthesi[sz]ed|"
    r"crystal structure|molecular docking|methylation|sequencing|genotyp|SNP|allele|"
    r"polymorphism|biomarker|serum levels|plasma levels|concentration[s]? of)\b",
    re.I,
)
RE_MODELING = re.compile(
    r"\b(agent-based|agent based|microsimulation|simulations?|simulated|we (model|modeled|modelled)|"
    r"mathematical|theoretical|theory|modelling|modeling|(a|the|our) model|models? (of|for|that|which)|"
    r"dynamics|equilibri(um|a)|analytical(ly)?|we show that|we demonstrate that|framework|"
    r"transmission model|strain dynamics|coevolution\w*|epistasis|selection pressure|fitness landscape|"
    r"mathematical model|compartmental|SEIR|SIR model|Monte Carlo|projected|projection|projecting|"
    r"forecast|scenario[s]?|decision analytic|Markov|system dynamics|network model)\b",
    re.I,
)
RE_REVIEW = re.compile(
    r"\b(systematic review|meta-analys[ie]s|scoping review|narrative review|literature review|"
    r"we (review|reviewed|searched|summari[sz]e)|this review|PRISMA|PubMed, |MEDLINE|Embase|"
    r"databases were searched|included studies|eligible studies)\b",
    re.I,
)
RE_METHODS_HEADINGS = re.compile(r"\b(METHODS?|RESULTS?|DESIGN|SETTING|PARTICIPANTS|MEASUREMENTS?)\b:?")

# ----- topic vocabularies (MeSH, keywords, and title) -----

TOPIC_TERMS: dict[str, tuple[set[str], re.Pattern]] = {
    "race_ethnicity": (
        {
            "Racial Groups", "Ethnic Groups", "Ethnicity", "Race Factors", "Arabs",
            "Black or African American", "African Americans", "Hispanic or Latino",
            "Hispanic Americans", "White People", "European Continental Ancestry Group",
            "African Continental Ancestry Group", "Minority Groups", "Minority Health",
            "Emigrants and Immigrants", "Acculturation", "Ethnic and Racial Minorities",
            "Racism", "Black People", "Asian", "American Indian or Alaska Native",
        },
        re.compile(r"\b(racial|race|ethnic|ethnicity|arab|black|white|hispanic|latino|immigrant|"
                   r"minority|minorities|african american|racism)\b", re.I),
    ),
    "social_determinants": (
        {
            "Social Determinants of Health", "Socioeconomic Factors", "Poverty", "Social Class",
            "Income", "Residence Characteristics", "Social Environment", "Social Support",
            "Educational Status", "Employment", "Unemployment", "Food Supply", "Food Insecurity",
            "Housing", "Social Isolation", "Social Networking", "Social Networks",
            "Neighborhood Characteristics", "Social Conditions", "Social Capital",
            "Insurance Coverage", "Medically Uninsured", "Social Segregation",
        },
        re.compile(r"\b(socioeconomic|social (determinant|network|environment|support|class|context)|"
                   r"poverty|income|neighborhood|neighbourhood|food insecurity|insurance status|"
                   r"uninsured|inequalit|inequit|stigma)\w*", re.I),
    ),
    "policy_politics": (
        {
            "Health Policy", "Public Policy", "Politics", "Government", "Federal Government",
            "State Government", "Local Government", "Policy Making", "Policy",
            "Health Care Reform", "Universal Health Insurance", "Insurance, Health",
            "Medicaid", "Medicare", "Patient Protection and Affordable Care Act",
            "Legislation as Topic", "Government Regulation", "Public Health Administration",
            "Health Services Accessibility", "Delivery of Health Care", "Public Health",
            "Prisons", "Prisoners", "Law Enforcement", "Jails", "Environmental Policy",
            "Nutrition Policy", "Health Promotion", "Advertising",
        },
        re.compile(r"\b(policy|policies|politic|government|legislat|regulat|medicaid|medicare|"
                   r"universal (coverage|health)|single.payer|affordable care act|insurance|"
                   r"incarcerat|jail|prison|public health)\w*", re.I),
    ),
    "equity_justice": (
        {
            "Health Equity", "Social Justice", "Healthcare Disparities", "Health Status Disparities",
            "Health Inequities", "Social Discrimination", "Prejudice", "Racism", "Sexism",
            "Human Rights", "Vulnerable Populations", "Social Marginalization",
        },
        re.compile(r"\b(disparit|inequalit|inequit|equity|justice|discriminat|marginali[sz]|"
                   r"vulnerable|structural|oppress|racism)\w*", re.I),
    ),
}


@dataclass
class Classification:
    pmid: str
    tier: str                  # A, B, C
    subtype: str               # trial, bench, observational, review, modeling, methods, commentary
    confidence: str            # high, medium, low
    needs_review: bool
    evidence: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    topic_hits: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


# ------------------------------------------------------------- helpers

def author_role(article: dict, surname: str) -> str:
    """first | last | sole | middle | none, matching on surname (case/hyphen tolerant)."""
    import unicodedata
    def norm(x: str) -> str:
        x = unicodedata.normalize("NFKD", x or "").encode("ascii", "ignore").decode()
        return x.lower().replace("-", " ").replace(" ", "")
    key = norm(surname)
    authors = article.get("authors", [])
    idx = [i for i, a in enumerate(authors) if key == norm(a.get("last_name", ""))]
    if not idx:  # fall back to substring for compound surnames (e.g. "El Sayed" vs "El-Sayed")
        idx = [i for i, a in enumerate(authors) if key in norm(a.get("last_name", ""))]
    if not idx:
        return "none"
    i = idx[0]
    if len(authors) == 1:
        return "sole"
    if i == 0:
        return "first"
    if i == len(authors) - 1:
        return "last"
    return "middle"


def _count(pattern: re.Pattern, text: str) -> int:
    return len(pattern.findall(text or ""))


# ---------------------------------------------------------- study type

def classify_study_type(article: dict) -> Classification:
    pmid = article["identifiers"]["pmid"]
    pubtypes = set(article.get("article_types", []))
    mesh = set(article.get("mesh_terms", []))
    title = article.get("title", "") or ""
    abstract = article.get("abstract", "") or ""
    if abstract.strip().lower() in ("[abstract not available]", "abstract not available", "n/a"):
        abstract = ""
    journal = article.get("journal", {}).get("iso_abbreviation", "")
    text = f"{title}\n{abstract}"
    ev: list[str] = []

    design_mesh = mesh & DESIGN_MESH
    stats_mesh = mesh & STATS_MESH
    bench_mesh = mesh & BENCH_MESH
    model_mesh = mesh & MODELING_MESH

    n_we = _count(RE_WE_DID, abstract) + _count(RE_PASSIVE, abstract)
    n_sample = _count(RE_SAMPLE, abstract)
    n_stats = _count(RE_STATS, abstract)
    n_design = _count(RE_DESIGN, abstract)
    n_bench = _count(RE_BENCH, text)
    n_model = _count(RE_MODELING, text)
    n_review = _count(RE_REVIEW, abstract)
    n_headings = _count(RE_METHODS_HEADINGS, abstract)

    empirical_score = (
        min(n_we, 3) + min(n_sample, 2) + min(n_stats, 3) + min(n_design, 3)
        + 2 * len(design_mesh) + len(stats_mesh) + 2 * min(n_headings, 2)
    )
    ev.append(f"empirical_score={empirical_score} (we_did={n_we}, sample={n_sample}, stats={n_stats}, "
              f"design_words={n_design}, design_mesh={sorted(design_mesh)}, stats_mesh={len(stats_mesh)})")

    # 0. Titles that announce themselves.
    if TITLE_SELF_COMMENTARY.search(title):
        ev.append("title announces commentary")
        return Classification(pmid, "C", "commentary", "high", False, ev)
    if TITLE_SELF_REVIEW.search(title) and empirical_score < 8:
        ev.append("title announces review")
        sub = "meta-analysis" if re.search(r"meta-analys", title, re.I) else "review"
        return Classification(pmid, "B", sub, "high", False, ev)

    # 1. Explicit commentary publication types win, unless it is a research letter.
    if pubtypes & COMMENTARY_PUBTYPES:
        if "Letter" in pubtypes and empirical_score >= 6 and not ({"Comment"} & pubtypes):
            ev.append("Letter with strong empirical signal: treated as research letter")
            return Classification(pmid, "A", "observational", "medium", True, ev)
        ev.append(f"commentary pubtype: {sorted(pubtypes & COMMENTARY_PUBTYPES)}")
        return Classification(pmid, "C", "commentary", "high", False, ev)

    # 1b. Case reports and small case series: original clinical observation, no analysis.
    if pubtypes & CASE_REPORT_PUBTYPES:
        ev.append("case report pubtype")
        return Classification(pmid, "A", "case_report", "high", False, ev)

    # 2. Trials.
    if pubtypes & TRIAL_PUBTYPES:
        ev.append(f"trial pubtype: {sorted(pubtypes & TRIAL_PUBTYPES)}")
        return Classification(pmid, "A", "trial", "high", False, ev)

    # 3. Reviews and meta-analyses.
    if pubtypes & REVIEW_PUBTYPES:
        sub = "meta-analysis" if "Meta-Analysis" in pubtypes else "review"
        ev.append(f"review pubtype: {sorted(pubtypes & REVIEW_PUBTYPES)}")
        return Classification(pmid, "B", sub, "high", False, ev)
    if n_review >= 2 and empirical_score < 6:
        ev.append(f"review language in abstract ({n_review} hits)")
        sub = "meta-analysis" if re.search(r"meta-analys", abstract, re.I) else "review"
        return Classification(pmid, "B", sub, "medium", False, ev)

    # 3b. Titles that read as opinion with almost no empirical signal.
    if TITLE_COMMENTARY.search(title) and empirical_score < 3 and n_bench < 8:
        ev.append("commentary-style title with no empirical signal")
        return Classification(pmid, "C", "commentary", "medium", True, ev)

    clinical_pop = bool(re.search(r"\b(patients?|participants?|respondents|enrollees|beneficiaries|admissions|"
                                   r"discharges|hospitals?|insurance|disparit\w+|cohort|registry|claims)\b", abstract, re.I))

    # 4. Bench and basic science. Strong molecular/organism vocabulary with no
    #    epidemiological design signal is bench work, whether or not MeSH is present.
    bench_strength = 2 * len(bench_mesh) + n_bench
    if not design_mesh and n_design == 0 and not (clinical_pop and n_bench < 10) and (
        (bench_mesh and n_bench >= 2) or len(bench_mesh) >= 3 or n_bench >= 8 or (n_bench >= 5 and "Humans" not in mesh)
    ):
        ev.append(f"bench signal: mesh={sorted(bench_mesh)[:6]}, words={n_bench}")
        return Classification(pmid, "A", "bench", "high" if bench_strength >= 10 else "medium", False, ev)
    if n_bench >= 5 and empirical_score >= 3 and not design_mesh and not clinical_pop:
        ev.append(f"bench language ({n_bench} hits) alongside analytic signals")
        return Classification(pmid, "A", "bench", "medium", False, ev)

    # 5. Modeling / simulation without primary data.
    if ((model_mesh and n_model >= 1) or n_model >= 3 or (n_model >= 2 and empirical_score < 4)) and not design_mesh and n_stats < 2 and not clinical_pop:
        ev.append(f"modeling signal: mesh={sorted(model_mesh)}, words={n_model}")
        return Classification(pmid, "B", "modeling", "medium", False, ev)

    if not abstract and RE_MODELING.search(title) and not design_mesh:
        ev.append("no abstract; modeling language in title")
        return Classification(pmid, "B", "modeling", "low", True, ev)

    # 6. Observational / analytic empirical work.
    if pubtypes & OBSERVATIONAL_PUBTYPES and empirical_score >= 3:
        ev.append(f"observational pubtype: {sorted(pubtypes & OBSERVATIONAL_PUBTYPES)}")
        return Classification(pmid, "A", "observational", "high", False, ev)
    if design_mesh or (stats_mesh and empirical_score >= 4) or empirical_score >= 5 or (empirical_score >= 4 and n_we >= 2) or n_design >= 3:
        conf = "high" if design_mesh or empirical_score >= 8 else "medium"
        return Classification(pmid, "A", "observational", conf, conf == "medium" and empirical_score < 6, ev)

    # 6b. Terse abstracts (economics, demography): two first-person analytic statements plus a
    #     rich MeSH indexing (commentaries rarely get 10+ headings) is treated as empirical, flagged.
    if n_we >= 2 and len(mesh) >= 10 and not TITLE_COMMENTARY.search(title) and not TITLE_COMMENTARY_ANY.search(title):
        ev.append(f"terse analytic abstract with {len(mesh)} MeSH headings")
        return Classification(pmid, "A", "observational", "low", True, ev)

    # 7. Methods pieces (new technique, no data, no opinion) are rare; treat as B when flagged.
    if re.search(r"\b(we|this (paper|article)|the authors?)\s+(propose|proposes|present|presents|introduce|introduces|"
                 r"develop|develops|describe|describes|derive|derives|extend|extends|evaluate|evaluates)d?\s+"
                 r"(a|an|the|two|several|new|novel|simple|general)?\s*\w*\s*(method|methods|statistic|statistics|test|tests|"
                 r"approach|algorithm|tool|framework|software|package|estimator|procedure|technique|metric|index|score)\b",
                 abstract, re.I) or re.search(r"\b(scan statistic|permutation test|R package|software package|likelihood ratio test)\b", text, re.I):
        ev.append("methods language")
        return Classification(pmid, "B", "methods", "medium", False, ev)

    # 7b. No abstract and no publication-type cue: unclassifiable, not commentary.
    if not abstract and not (TITLE_COMMENTARY.search(title) or TITLE_COMMENTARY_ANY.search(title) or journal in COMMENTARY_JOURNALS):
        ev.append("no abstract in PubMed; tier unknown")
        return Classification(pmid, "U", "no_abstract", "low", True, ev)

    # 8. Otherwise, commentary. Confidence depends on how commentary-like it looks.
    looks_comment = bool(TITLE_COMMENTARY.search(title)) or bool(TITLE_COMMENTARY_ANY.search(title)) \
        or journal in COMMENTARY_JOURNALS or not abstract
    ev.append(f"no empirical signal; title/journal commentary cue={looks_comment}")
    if empirical_score >= 3:
        # Some signal but not enough to be sure. Flag it.
        return Classification(pmid, "C", "commentary", "low", True, ev)
    return Classification(pmid, "C", "commentary", "high" if looks_comment else "medium", not looks_comment, ev)


# --------------------------------------------------------------- topics

def classify_topics(article: dict) -> tuple[list[str], dict]:
    mesh = set(article.get("mesh_terms", []))
    kws = " ; ".join(article.get("keywords", []) or [])
    title = article.get("title", "") or ""
    flags, hits = [], {}
    for name, (mesh_set, rx) in TOPIC_TERMS.items():
        m = sorted(mesh & mesh_set)
        t = sorted(set(m.group(0).lower() for m in rx.finditer(title)))
        k = sorted(set(m.group(0).lower() for m in rx.finditer(kws)))
        if m or t or k:
            flags.append(name)
            hits[name] = {"mesh": m, "title": t, "keywords": k}
    return flags, hits


def classify(article: dict) -> Classification:
    c = classify_study_type(article)
    c.topics, c.topic_hits = classify_topics(article)
    return c
