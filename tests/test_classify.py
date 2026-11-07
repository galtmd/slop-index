"""Minimal sanity tests. Run: python -m unittest discover tests"""
import unittest
from slop_index.classify import classify
from slop_index.score import h_index, summarise
from slop_index import substance, weights as W


def art(**kw):
    base = {"identifiers": {"pmid": "1"}, "title": "", "abstract": "", "journal": {"iso_abbreviation": ""},
            "authors": [{"last_name": "Doe"}], "publication_date": {"year": "2020"}, "keywords": [],
            "mesh_terms": [], "article_types": ["Journal Article"]}
    base.update(kw)
    return base


class ClassifyTests(unittest.TestCase):
    def test_editorial_is_commentary(self):
        c = classify(art(article_types=["Editorial"], title="Why we must act now"))
        self.assertEqual(c.tier, "C")

    def test_rct_is_trial(self):
        c = classify(art(article_types=["Journal Article", "Randomized Controlled Trial"]))
        self.assertEqual((c.tier, c.subtype), ("A", "trial"))

    def test_cross_sectional_mesh_is_observational(self):
        c = classify(art(mesh_terms=["Humans", "Cross-Sectional Studies"], abstract="We analyzed 4913 patients."))
        self.assertEqual((c.tier, c.subtype), ("A", "observational"))

    def test_abstract_signals_without_mesh(self):
        a = ("We assessed relations between nativity and preterm birth over 17 years. Adjusted multivariable "
             "models were fit. There was a significant interaction (P < 0.01). 95% CI 1.1-1.4.")
        c = classify(art(abstract=a))
        self.assertEqual(c.tier, "A")

    def test_review_title(self):
        c = classify(art(title="The health of Arab Americans: a systematic review", abstract="We searched PubMed."))
        self.assertEqual(c.tier, "B")

    def test_opinion_with_no_signal(self):
        c = classify(art(title="Rethinking our research paradigm", abstract="We argue that the field should change."))
        self.assertEqual(c.tier, "C")

    def test_topic_flags(self):
        c = classify(art(title="Racial disparities in mortality", mesh_terms=["Health Status Disparities"]))
        self.assertIn("race_ethnicity", c.topics)
        self.assertIn("equity_justice", c.topics)


class ScoreTests(unittest.TestCase):
    def test_h_index(self):
        self.assertEqual(h_index([10, 8, 5, 4, 3]), 4)
        self.assertEqual(h_index([]), 0)

    def test_summary_slop(self):
        def row(tier, cites, value):
            return {"tier": tier, "subtype": "x", "role": "first", "citation_count": cites, "topics": [],
                    "value": value, "value_norm": (value - W.VALUE_MIN) / (W.VALUE_MAX - W.VALUE_MIN),
                    "design": "x", "identity": False, "rescued": "n/a"}
        rows = [row("A", 10, 5), row("A", 2, 5), row("C", 50, -5), row("C", 20, -5)]
        s = summarise(rows)["all_authorships"]
        self.assertEqual(s["h_index"], 3)
        self.assertEqual(s["h_empirical"], 2)
        self.assertEqual(s["slop_index"], 0.333)
        self.assertEqual(s["h_substantive"], 2)
        self.assertAlmostEqual(s["total_slop_index"], 1 - ((5 - W.VALUE_MIN) / 28 + (-5 - W.VALUE_MIN) / 28) / 2, places=3)


class SubstanceTests(unittest.TestCase):
    def test_major_trial_scores_high(self):
        a = art(article_types=["Journal Article", "Randomized Controlled Trial", "Multicenter Study"],
                abstract="We randomized 2400 patients to drug or placebo. Mortality at 1 year was 12% vs 15% (HR 0.80, 95% CI 0.70-0.92).")
        c = classify(a)
        s = substance.score(a, c.tier, c.subtype, c.topics, rcr=2.5, self_sim=0)
        self.assertEqual(s.design, "major_trial")
        self.assertEqual(s.outcome, "hard")
        self.assertGreater(s.value, 10)

    def test_identity_survey_starts_in_deficit(self):
        a = art(title="Perceived discrimination and self-rated health among Arab Americans",
                mesh_terms=["Arabs", "Self Report", "Surveys and Questionnaires", "Humans"],
                abstract="We surveyed 300 respondents. Perceived discrimination was associated with poorer self-rated health "
                         "(OR 1.4, 95% CI 1.1-1.8). Findings suggest that interventions may be warranted.")
        c = classify(a)
        s = substance.score(a, c.tier, c.subtype, c.topics, rcr=0.4, self_sim=0)
        self.assertTrue(s.identity)
        self.assertEqual(s.rescued, "none")
        self.assertLess(s.value, -5)

    def test_identity_paper_can_be_rescued(self):
        a = art(title="Racial differences in 30-day mortality after myocardial infarction: a national cohort",
                mesh_terms=["Cohort Studies", "Hospital Mortality", "Black or African American", "Humans"],
                abstract="We followed 120000 patients. 30-day mortality was 8.1% vs 6.9% (HR 1.15, 95% CI 1.08-1.22) after adjusting for comorbidity.")
        c = classify(a)
        s = substance.score(a, c.tier, c.subtype, c.topics, rcr=2.0, self_sim=0)
        self.assertEqual(s.rescued, "full")
        self.assertEqual(s.topic_penalty, 0)

    def test_commentary_impact_is_capped(self):
        a = art(article_types=["Editorial"], title="Why epidemiology must change", abstract="We argue that the field should change.")
        c = classify(a)
        s = substance.score(a, c.tier, c.subtype, c.topics, rcr=5.0, self_sim=0)
        self.assertLessEqual(s.components["rcr"], W.COMMENTARY_RCR_CAP)
        self.assertLess(s.value, 0)


if __name__ == "__main__":
    unittest.main()


def test_agenda_buckets_and_qualitative_design():
    from slop_index.substance import agenda_of, design_of
    gun = {"title": "State firearm laws and firearm mortality: an ecological analysis", "abstract": "", "mesh_terms": [], "keywords": []}
    assert "firearms" in agenda_of(gun)
    tax = {"title": "Projected health impact of a sugar-sweetened beverage tax", "abstract": "", "mesh_terms": [], "keywords": []}
    assert "paternalism" in agenda_of(tax)
    bench = {"title": "Machine learning predicts protein folding from sequence", "abstract": "We trained a model. Accuracy was high.",
             "mesh_terms": ["Machine Learning", "Algorithms"], "keywords": []}
    assert agenda_of(bench) == []   # broad MeSH alone must not trigger
    qual = {"title": "Lived experiences of discrimination: a photovoice study", "mesh_terms": ["Qualitative Research"],
            "article_types": ["Journal Article"],
            "abstract": "We conducted semi-structured interviews and focus groups with 24 participants. Thematic analysis identified three themes."}
    assert design_of("A", "observational", qual) == "qualitative"


def test_qualitative_is_the_floor():
    from slop_index.substance import score
    qual = {"identifiers": {"pmid": "q1"}, "title": "Community-based participatory research on neighborhood health: a photovoice study",
            "mesh_terms": ["Qualitative Research", "Community-Based Participatory Research"], "article_types": ["Journal Article"], "keywords": [],
            "abstract": "We conducted semi-structured interviews and focus groups with 24 participants. Thematic analysis identified three themes."}
    r = score(qual, "A", "observational", [], 8.0, 0)
    assert r.design == "qualitative"
    assert r.value_norm == 0.0          # clipped to VALUE_MIN whatever the citation count
    assert r.rescued == "none"
