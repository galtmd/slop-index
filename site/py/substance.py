"""Axis 3: substance. Does the paper add actionable science, or did someone
merely collect some data?

Signals (each reported separately in papers.csv, then combined into a
per-paper value using the numbers in weights.py):

    design        major_trial | trial | bench | quasi_experimental | cohort |
                  registry | survey | observational | meta-analysis | modeling |
                  review | methods | commentary
    outcome       hard | soft | unclear
    exposure      mechanistic | demographic | other
    hedge         high | low | n/a
    self_similar  number of near-duplicate papers in the same corpus
    rcr           iCite relative citation ratio
    identity      whether the paper's subject is an identity topic
    rescued       none | partial | full  (identity penalty waived?)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field

from . import weights as W

# ------------------------------------------------------------ vocabularies

RE_QUASI = re.compile(
    r"\b(natural experiment|difference-in-differences|difference in differences|instrumental variable|"
    r"regression discontinuity|interrupted time series|before and after|pre-post|pre/post|"
    r"synthetic control|event study|quasi-experimental|policy change|implementation of|"
    r"after the (passage|introduction|implementation|enactment))\b", re.I)
RE_COHORT = re.compile(
    r"\b(cohort|longitudinal|prospective|follow-up|followed (for|over|up)|incident|person-years|"
    r"hazard ratio|survival analysis|time to event)\b", re.I)
RE_REGISTRY = re.compile(
    r"\b(vital statistics|birth certificates?|birth records|death certificates?|death records|"
    r"nationwide inpatient sample|national inpatient sample|\bNIS\b|claims data|administrative data|"
    r"electronic health records?|\bEHR\b|medical records|registry|registries|census|surveillance data|"
    r"linked (data|records)|hospital discharge|discharge data|county-level|state-level|"
    r"national (health|survey|database)|BRFSS|NHANES|NHIS|CDC WONDER|mortality (data|files|records))\b", re.I)
RE_SURVEY = re.compile(
    r"\b(self-report\w*|questionnaire|survey(ed|s)?\b|respondents|convenience sample|interviews?|"
    r"focus groups?|qualitative|thematic|narratives?|lived experience|perceived|perceptions?|"
    r"attitudes?|beliefs|awareness|knowledge, attitudes|likert|online survey|web-based survey)\b", re.I)
MESH_SURVEY = {"Surveys and Questionnaires", "Self Report", "Attitude", "Attitude to Health",
               "Health Knowledge, Attitudes, Practice", "Qualitative Research", "Interviews as Topic",
               "Focus Groups", "Perception", "Social Perception", "Attitude of Health Personnel"}
MESH_REGISTRY = {"Registries", "Databases, Factual", "Vital Statistics", "Birth Certificates",
                 "Death Certificates", "Electronic Health Records", "Medical Records",
                 "Hospital Mortality", "Insurance Claim Review", "Patient Discharge"}
MESH_COHORT = {"Cohort Studies", "Longitudinal Studies", "Prospective Studies", "Follow-Up Studies"}
MESH_QUASI = {"Interrupted Time Series Analysis", "Controlled Before-After Studies", "Non-Randomized Controlled Trials as Topic"}

RE_HARD = re.compile(
    r"\b(mortality|death|deaths|died|survival|case fatality|incidence|hospitali[sz]ation|readmission|"
    r"complications?|infarction|stroke|sepsis|birth ?weight|preterm birth|low birth weight|"
    r"infant mortality|stillbirth|gestational age|length of stay|intubation|ventilat\w+|"
    r"\bICU\b|biomarkers?|HbA1c|hemoglobin|blood pressure|cholesterol|BMI|body mass index|"
    r"laboratory|serum|plasma|imaging|\bMRI\b|\bCT\b|histolog\w+|tumou?r|cancer incidence|"
    r"fracture|amputation|dialysis|transplant|recurrence|relapse|cure rate|viral load|"
    r"seroconversion|IC50|protein expression|phosphorylation|cell (death|viability|proliferation)|"
    r"receptor binding|enzyme activity|gene expression|methylation|surgical outcomes?|"
    r"postoperative|30-day|1-year|in-hospital)\b", re.I)
MESH_HARD = {"Mortality", "Hospital Mortality", "Infant Mortality", "Premature Birth", "Birth Weight",
             "Survival Analysis", "Biomarkers", "Postoperative Complications", "Treatment Outcome",
             "Cause of Death", "Length of Stay", "Patient Readmission", "Suicide", "Pregnancy Outcome",
             "Infant, Low Birth Weight", "Infant, Very Low Birth Weight", "Incidence", "Mortality, Premature"}
RE_SOFT = re.compile(
    r"\b(self-reported|self-rated|perceived|perception|attitudes?|beliefs?|awareness|knowledge|"
    r"satisfaction|quality of life|well-being|wellbeing|psychological distress|symptoms of|"
    r"experiences? of|lived experience|discrimination experiences|stigma|microaggressions?|"
    r"identity|sense of|trust in|intentions?|willingness|preferences|opinions?|views|"
    r"mental health indicators|subjective)\b", re.I)
MESH_SOFT = {"Self Report", "Attitude", "Attitude to Health", "Quality of Life", "Perception",
             "Social Perception", "Health Knowledge, Attitudes, Practice", "Personal Satisfaction",
             "Self Concept", "Stress, Psychological", "Social Stigma", "Trust"}

RE_MECHANISTIC = re.compile(
    r"\b(intervention|treatment|therapy|drug|dose|dosing|surgery|surgical|procedure|vaccin\w+|"
    r"screening program|randomi[sz]ed to|administered|receptor|ligand|kinase|pathway|protein|"
    r"gene|genetic variant|allele|enzyme|antibod\w+|inhibitor|agonist|antagonist|compound|"
    r"molecule|mechanism|physiolog\w+|pharmacolog\w+|biochemical|metabolic|immune|inflammat\w+|"
    r"smoking|cigarette|hyperglycemia|glucose|obesity|hypertension|diabetes|prenatal care|"
    r"policy|program|advertis\w+|tax|price)\b", re.I)
RE_DEMOGRAPHIC_EXPOSURE = re.compile(
    r"\b(among (arab|black|white|hispanic|latino|asian|immigrant|foreign-born|minority|muslim|"
    r"lgbt\w*|transgender|women|men|female|male)|"
    r"(racial|ethnic|gender|sex|nativity|immigrant|minority) (differences|disparities|inequalities|inequities|gap)|"
    r"by race|by ethnicity|by gender|by nativity|race/ethnicity|racial/ethnic|"
    r"race (and|or) ethnicity|non-hispanic (white|black)|black-white|white-black|"
    r"arab[- ]americans?|african[- ]americans?|sexual (minority|orientation)|gender identity|"
    r"intersectional\w*|structural racism|systemic racism|acculturat\w+)\b", re.I)

RE_HEDGE = re.compile(
    r"\b(may|might|could|possibly|potentially|suggests?|suggesting|appears?|seems?|likely|"
    r"warrant(s|ed)? (further|additional|more)|further (research|study|studies|work) (is|are) (needed|warranted|required)|"
    r"highlights? the (need|importance)|underscores? the (need|importance)|should (consider|be considered)|"
    r"call(s)? for|more research|future (research|studies|work))\b", re.I)
RE_CONCRETE = re.compile(
    r"(\d+(\.\d+)?\s?%|\bOR\s?[=:]?\s?\d|odds ratio|hazard ratio|\bHR\s?[=:]?\s?\d|relative risk|"
    r"\bRR\s?[=:]?\s?\d|95\s?%\s?CI|p\s?[<=]\s?0?\.\d|\d+(\.\d+)?-fold|per 100,?000|"
    r"significantly (higher|lower|increased|decreased|reduced|greater|associated)|"
    r"(increased|decreased|reduced|lowered|raised) by \d|no (significant )?(association|difference|effect))", re.I)

MESH_IDENTITY = {
    "Racial Groups", "Ethnic Groups", "Ethnicity", "Race Factors", "Arabs", "Black or African American",
    "African Americans", "Hispanic or Latino", "Hispanic Americans", "White People", "Black People",
    "Minority Groups", "Minority Health", "Ethnic and Racial Minorities", "Racism", "Social Discrimination",
    "Prejudice", "Sexism", "Gender Identity", "Sexual and Gender Minorities", "Transgender Persons",
    "Homosexuality", "Sexual Behavior", "Health Equity", "Social Justice", "Healthcare Disparities",
    "Health Status Disparities", "Health Inequities", "Social Marginalization", "Emigrants and Immigrants",
    "Acculturation", "Social Stigma", "Cultural Competency", "Diversity, Equity, Inclusion",
    "Intersectional Framework", "Social Segregation", "Microaggression",
}
RE_IDENTITY = re.compile(
    r"\b(racial|racism|racist|race|ethnic\w*|arab|black|white|hispanic|latin[oax]|immigrant|nativity|"
    r"minorit\w+|disparit\w+|inequit\w+|equity|justice|discriminat\w+|prejudice|bigotry|stigma|"
    r"gender|transgender|\bLGBT\w*|sexual (orientation|minority|minorities)|queer|lived experience|"
    r"intersectional\w*|marginali[sz]\w+|oppress\w+|structural|microaggression\w*|acculturat\w+|"
    r"diversity|inclusion|cultural (competenc\w+|humility)|implicit bias)\b", re.I)

MESH_SDOH = {
    "Social Determinants of Health", "Socioeconomic Factors", "Poverty", "Social Class", "Income",
    "Residence Characteristics", "Social Environment", "Social Support", "Educational Status",
    "Employment", "Unemployment", "Food Supply", "Food Insecurity", "Housing", "Social Isolation",
    "Neighborhood Characteristics", "Social Conditions", "Social Capital", "Socioeconomic Disparities in Health",
    "Prisons", "Prisoners", "Jails", "Criminal Law", "Law Enforcement", "Police", "Incarceration",
    "Medically Uninsured", "Insurance Coverage", "Health Services Accessibility", "Social Segregation",
    "Homeless Persons", "Ill-Housed Persons", "Adverse Childhood Experiences", "Social Vulnerability",
}
RE_SDOH = re.compile(
    r"\b(social determinants?|socioeconomic|socio-economic|poverty|low-income|income inequality|"
    r"neighbou?rhood|deprivation|disadvantage\w*|food insecurity|housing|homeless\w*|"
    r"incarcerat\w+|jail\w*|prison\w*|carceral|police|policing|criminal (justice|legal)|"
    r"social (environment|support|network|capital|conditions|context|vulnerability)|"
    r"uninsured|underinsured|adverse childhood|allostatic|weathering|structural (determinants|violence)|"
    r"upstream|place-based|area-level)\b", re.I)


@dataclass
class Substance:
    pmid: str
    design: str
    design_base: int
    outcome: str
    exposure: str
    hedge: str
    hedge_ratio: float
    self_similar: int
    rcr: float | None
    rcr_points: int
    identity: bool
    social: bool
    topic_penalty: float
    rescued: str
    value: float
    value_norm: float
    components: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


# --------------------------------------------------------------- helpers

def _n(rx: re.Pattern, text: str) -> int:
    return len(rx.findall(text or ""))


def _max_sample(abstract: str) -> int:
    best = 0
    for m in re.finditer(r"\b(?:n\s?=\s?|a total of\s+)?([\d]{2,3}(?:,\d{3})+|\d{3,7})\s*(?:participants|patients|"
                         r"subjects|adults|women|men|children|individuals|respondents|people|persons|"
                         r"births|infants|mothers|cases|records|admissions|visits|encounters)?\b",
                         abstract or "", re.I):
        try:
            v = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if 1900 <= v <= 2100 and not m.group(0).lower().endswith(("participants", "patients")):
            continue  # years
        best = max(best, v)
    return best


def _conclusion(abstract: str) -> str:
    if not abstract:
        return ""
    cut = int(len(abstract) * 0.6)
    return abstract[cut:]


# -------------------------------------------------------------- detectors

def design_of(tier: str, subtype: str, article: dict) -> str:
    mesh = set(article.get("mesh_terms") or [])
    pubtypes = set(article.get("article_types") or [])
    abstract = article.get("abstract") or ""
    if subtype == "trial":
        if "Multicenter Study" in pubtypes or _max_sample(abstract) >= W.MAJOR_TRIAL_N:
            return "major_trial"
        return "trial"
    if subtype in ("bench", "meta-analysis", "modeling", "review", "methods", "commentary", "case_report"):
        return subtype
    # observational: refine
    if mesh & MESH_QUASI or _n(RE_QUASI, abstract) >= 1:
        return "quasi_experimental"
    if mesh & MESH_COHORT or _n(RE_COHORT, abstract) >= 2:
        return "cohort"
    reg = len(mesh & MESH_REGISTRY) * 2 + _n(RE_REGISTRY, abstract)
    sur = len(mesh & MESH_SURVEY) * 2 + _n(RE_SURVEY, abstract)
    if reg >= 2 and reg >= sur:
        return "registry"
    if sur >= 2:
        return "survey"
    if reg >= 1:
        return "registry"
    return "observational"


def outcome_of(article: dict) -> str:
    mesh = set(article.get("mesh_terms") or [])
    text = f"{article.get('title','')}\n{article.get('abstract','')}"
    hard = len(mesh & MESH_HARD) * 2 + _n(RE_HARD, text)
    soft = len(mesh & MESH_SOFT) * 2 + _n(RE_SOFT, text)
    if hard == 0 and soft == 0:
        return "unclear"
    if (hard >= 2 and hard >= 1.5 * soft) or (hard >= 1 and soft == 0):
        return "hard"
    if soft >= 2 and soft > hard:
        return "soft"
    return "unclear"


def exposure_of(article: dict) -> str:
    title = article.get("title", "") or ""
    abstract = article.get("abstract", "") or ""
    demo = _n(RE_DEMOGRAPHIC_EXPOSURE, title) * 2 + _n(RE_DEMOGRAPHIC_EXPOSURE, abstract[:600])
    mech = _n(RE_MECHANISTIC, title) * 2 + _n(RE_MECHANISTIC, abstract[:600])
    if demo >= 2 and demo >= mech:
        return "demographic"
    if mech >= 2:
        return "mechanistic"
    return "other"


def hedge_of(article: dict) -> tuple[str, float]:
    concl = _conclusion(article.get("abstract") or "")
    if len(concl) < 80:
        return "n/a", 0.0
    words = max(len(concl.split()), 1)
    h = _n(RE_HEDGE, concl)
    c = _n(RE_CONCRETE, concl)
    ratio = round(h * 100 / words, 2)
    if c >= 2 and h <= c:
        return "low", ratio
    if h >= 3 and h > c:
        return "high", ratio
    return "mid", ratio


def identity_of(article: dict) -> bool:
    mesh = set(article.get("mesh_terms") or [])
    title = article.get("title", "") or ""
    kws = " ".join(article.get("keywords") or [])
    return bool(mesh & MESH_IDENTITY) or _n(RE_IDENTITY, title) >= 1 or _n(RE_IDENTITY, kws) >= 1


def sdoh_of(article: dict) -> bool:
    mesh = set(article.get("mesh_terms") or [])
    title = article.get("title", "") or ""
    kws = " ".join(article.get("keywords") or [])
    return bool(mesh & MESH_SDOH) or _n(RE_SDOH, title) >= 1 or _n(RE_SDOH, kws) >= 1


def rcr_points(rcr: float | None) -> int:
    if rcr is None:
        return W.RCR_MISSING
    for lo, pts in W.RCR_BANDS:
        if rcr >= lo:
            return pts
    return W.RCR_BANDS[-1][1]


def self_similarity(articles: list[dict]) -> dict[str, int]:
    """Count, for each paper, how many others in the corpus share >= JACCARD of MeSH+title tokens."""
    stop = {"the", "of", "and", "in", "a", "an", "among", "for", "to", "on", "with", "from", "by", "at", "or",
            "study", "studies", "humans", "female", "male", "adult", "united", "states", "analysis", "risk"}
    bags = {}
    for a in articles:
        toks = set(w.lower() for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", a.get("title", "")))
        toks |= set(m.lower() for m in (a.get("mesh_terms") or []))
        bags[a["identifiers"]["pmid"]] = toks - stop
    out = {}
    ids = list(bags)
    for i in ids:
        n = 0
        for j in ids:
            if i == j or not bags[i] or not bags[j]:
                continue
            jac = len(bags[i] & bags[j]) / len(bags[i] | bags[j])
            if jac >= W.SELF_SIMILAR_JACCARD:
                n += 1
        out[i] = n
    return out


# ------------------------------------------------------------------ score

def score(article: dict, tier: str, subtype: str, topics: list[str], rcr: float | None,
          self_sim: int) -> Substance:
    pmid = article["identifiers"]["pmid"]
    design = design_of(tier, subtype, article)
    base = W.DESIGN_BASE.get(design, 0)
    outcome = outcome_of(article)
    exposure = exposure_of(article)
    hedge, hedge_ratio = hedge_of(article)
    identity = identity_of(article) or "race_ethnicity" in topics or "equity_justice" in topics
    social = sdoh_of(article) or "social_determinants" in topics
    pts = rcr_points(rcr)

    comp = {"design_base": base}
    v = float(base)
    if tier != "C":
        if outcome == "hard":
            comp["outcome"] = W.HARD_OUTCOME_BONUS
        elif outcome == "soft":
            comp["outcome"] = W.SOFT_OUTCOME_PENALTY
        if exposure == "mechanistic":
            comp["exposure"] = W.MECHANISTIC_BONUS
        elif exposure == "demographic":
            comp["exposure"] = W.DEMOGRAPHIC_EXPOSURE
        if hedge == "high":
            comp["hedge"] = W.HEDGE_HIGH_PENALTY
        elif hedge == "low":
            comp["hedge"] = W.CONCRETE_BONUS
    if self_sim >= W.SELF_SIMILAR_MIN:
        comp["self_similar"] = W.SELF_SIMILAR_PENALTY
    comp["rcr"] = min(pts, W.COMMENTARY_RCR_CAP) if tier == "C" else pts

    # topic penalty with rescue
    penalty = 0.0
    rescued = "n/a"
    if identity or social:
        penalty = W.IDENTITY_TOPIC_PENALTY if identity else W.SOCIAL_TOPIC_PENALTY
        if tier == "C":
            penalty += W.COMMENTARY_ON_IDENTITY
            rescued = "none"
        else:
            criteria = [base >= W.RESCUE_MIN_DESIGN,
                        (outcome == "hard") or not W.RESCUE_NEEDS_HARD,
                        (rcr or 0) >= W.RESCUE_MIN_RCR]
            missed = criteria.count(False)
            if missed == 0:
                penalty *= (1 - W.RESCUE_FULL_WAIVER)
                rescued = "full"
            elif missed == 1:
                penalty *= (1 - W.RESCUE_PARTIAL_WAIVER)
                rescued = "partial"
            else:
                rescued = "none"
    if "policy_politics" in topics and not identity and not social:
        penalty += W.POLICY_TOPIC_PENALTY
    comp["topic_penalty"] = penalty

    v = sum(comp.values())
    norm = (min(max(v, W.VALUE_MIN), W.VALUE_MAX) - W.VALUE_MIN) / (W.VALUE_MAX - W.VALUE_MIN)
    return Substance(pmid, design, base, outcome, exposure, hedge, hedge_ratio, self_sim, rcr, pts,
                     identity, social, penalty, rescued, round(v, 2), round(norm, 3), comp)
