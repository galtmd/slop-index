"""Every number that goes into the substance score and the composite.

Change these, rerun, and the results change. Nothing in the scoring code
hides a constant. The defaults encode one explicit editorial position:
papers that generate actionable science (trials, bench discoveries, strong
causal designs with hard endpoints) are rewarded heavily; papers whose
subject is a demographic identity, discrimination, or lived experience start
in deficit and are rescued only by strong design, hard endpoints, and real
impact. Anyone who disagrees can set IDENTITY_TOPIC_PENALTY to 0 and get a
topic-neutral version of the same index.
"""

# ---- design strength (base value of a paper by what it actually did)
DESIGN_BASE = {
    "major_trial":        10,   # RCT, multicenter or n >= MAJOR_TRIAL_N
    "trial":               8,
    "bench":               8,   # basic / mechanistic / discovery science
    "quasi_experimental":  6,   # natural experiment, DiD, IV, RD, ITS
    "cohort":              5,   # longitudinal / prospective with follow-up
    "registry":            3,   # vital records, claims, EHR, NIS: cross-sectional on hard records
    "survey":              1,   # self-report, questionnaire, convenience sample
    "qualitative":         0,   # interviews, focus groups, photovoice, CBPR, "critical" frameworks: no endpoint
    "case_report":         1,   # original clinical observation, no analysis
    "observational":       2,   # observational, design unclear
    "meta-analysis":       3,
    "modeling":            2,
    "review":              0,
    "methods":             1,
    "commentary":         -3,
}
MAJOR_TRIAL_N = 500

# ---- modifiers
HARD_OUTCOME_BONUS      =  2
SOFT_OUTCOME_PENALTY    = -2
MECHANISTIC_BONUS       =  2    # exposure is an intervention, drug, procedure, gene, pathway
DEMOGRAPHIC_EXPOSURE    = -3    # the "exposure" is a demographic label
HEDGE_HIGH_PENALTY      = -1    # conclusion is mostly "may", "suggests", "warrants further research"
CONCRETE_BONUS          =  1    # conclusion states an effect size or a definite finding
SELF_SIMILAR_PENALTY    = -2    # paper has >= SELF_SIMILAR_MIN near-duplicates in the same corpus
SELF_SIMILAR_MIN        =  3
SELF_SIMILAR_JACCARD    =  0.20

# ---- impact (iCite Relative Citation Ratio; 1.0 = NIH field average)
RCR_BANDS = [          # (min_rcr, points)
    (3.0,  4),
    (2.0,  3),
    (1.0,  1),
    (0.5,  0),
    (0.0, -2),
]
RCR_MISSING = 0        # very recent papers have no RCR yet
COMMENTARY_RCR_CAP = 1 # an influential opinion piece is still an opinion piece

# ---- topic penalties (applied at the outset; see rescue rules)
IDENTITY_TOPIC_PENALTY   = -5   # race/ethnicity, gender identity, sexual orientation, discrimination, lived experience, equity
SOCIAL_TOPIC_PENALTY     = -5   # social determinants of health: SES, neighborhood, housing, food insecurity,
                                # incarceration/jail/prison, insurance status. Same rescue rules as identity topics.
AGENDA_TOPIC_PENALTY     = -5   # other agenda-driven buckets (substance.AGENDA_TOPICS): climate, firearms,
                                # public-health paternalism, misinformation, reproductive policy, immigration,
                                # weight stigma, drug policy, algorithmic bias. Same rescue rules.
POLICY_TOPIC_PENALTY     =  0   # policy as a subject is not penalised by itself
COMMENTARY_ON_IDENTITY   = -3   # extra penalty: opinion piece whose subject is an identity topic

# Rescue: an identity- or SDOH-topic paper keeps its full penalty unless it clears these.
RESCUE_MIN_DESIGN   = 5          # cohort or better (DESIGN_BASE value)
RESCUE_MIN_RCR      = 1.5
RESCUE_NEEDS_HARD   = True       # must have a hard endpoint
RESCUE_FULL_WAIVER  = 1.0        # fraction of penalty waived when all criteria met
RESCUE_PARTIAL_WAIVER = 0.5      # when exactly one criterion is missed

# ---- composite normalisation. Paper value is clipped to [VALUE_MIN, VALUE_MAX]
#      and mapped to [0, 1]; Total Slop Index = 1 - mean(normalised value).
VALUE_MIN = -12
VALUE_MAX = 16
