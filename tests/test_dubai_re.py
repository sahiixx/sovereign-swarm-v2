"""Test suite for DubaiREAgent — unittest."""
import unittest, sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sovereign_swarm.agents.dubai_re_agent import (
    DubaiREAgent, PropertySearch, LeadProfile,
)


class TestParseQuery(unittest.TestCase):
    def setUp(self):
        self.agent = DubaiREAgent()

    def test_bedrooms(self):
        q = "2 bedroom apartment in Dubai Marina"
        s = self.agent.parse_query(q)
        self.assertEqual(s.bedrooms, 2)

    def test_studio(self):
        q = "studio in Business Bay"
        s = self.agent.parse_query(q)
        self.assertEqual(s.bedrooms, 0)

    def test_location_full(self):
        q = "villa in Palm Jumeirah"
        s = self.agent.parse_query(q)
        self.assertEqual(s.location, "palm jumeirah")

    def test_location_hint(self):
        q = "apartment in marina"
        s = self.agent.parse_query(q)
        self.assertEqual(s.location, "dubai marina")

    def test_budget_million(self):
        q = "3 bedroom for 3.5 million"
        s = self.agent.parse_query(q)
        self.assertEqual(s.budget_max, 3500000)

    def test_budget_aed(self):
        q = "apartment for 1500000 AED"
        s = self.agent.parse_query(q)
        self.assertEqual(s.budget_max, 1500000)

    def test_property_type_villa(self):
        q = "villa in Arabian Ranches"
        s = self.agent.parse_query(q)
        self.assertEqual(s.property_type, "villa")

    def test_property_type_townhouse(self):
        q = "townhouse in Damac Hills"
        s = self.agent.parse_query(q)
        self.assertEqual(s.property_type, "townhouse")

    def test_ready_status(self):
        q = "2 bedroom off-plan in JLT"
        s = self.agent.parse_query(q)
        self.assertEqual(s.ready_status, "off-plan")

    def test_amenities_pool_gym(self):
        q = "apartment with swimming pool and fitness center"
        s = self.agent.parse_query(q)
        self.assertIn("pool", s.amenities)
        self.assertIn("gym", s.amenities)

    def test_amenities_unique(self):
        q = "apartment with pool and pool"
        s = self.agent.parse_query(q)
        self.assertEqual(len(s.amenities), 1)

    def test_empty_query(self):
        q = "hello"
        s = self.agent.parse_query(q)
        self.assertIsNone(s.bedrooms)
        self.assertEqual(s.location, "")
        self.assertEqual(s.amenities, [])


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.agent = DubaiREAgent()

    def test_exact_bedroom_match(self):
        s = PropertySearch(bedrooms=2)
        r = self.agent.search(s)
        self.assertTrue(all(x["bedrooms"] == 2 for x in r))

    def test_location_filter(self):
        s = PropertySearch(location="dubai marina")
        r = self.agent.search(s)
        self.assertTrue(all(x["location"] == "dubai marina" for x in r))

    def test_budget_filter(self):
        s = PropertySearch(budget_max=2000000)
        r = self.agent.search(s)
        self.assertTrue(all(x["price_aed"] <= 2000000 for x in r))

    def test_type_filter(self):
        s = PropertySearch(property_type="villa")
        r = self.agent.search(s)
        self.assertTrue(all(x["type"] == "villa" for x in r))

    def test_ready_filter(self):
        s = PropertySearch(ready_status="ready")
        r = self.agent.search(s)
        self.assertTrue(all(x.get("ready") is True for x in r))

    def test_amenity_filter(self):
        s = PropertySearch(amenities=["pool", "gym"])
        r = self.agent.search(s)
        for x in r:
            self.assertIn("pool", x["amenities"])
            self.assertIn("gym", x["amenities"])

    def test_combined_filter(self):
        s = PropertySearch(
            bedrooms=2, location="dubai marina",
            budget_max=3000000, property_type="apartment",
        )
        r = self.agent.search(s)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["id"], "DM001")

    def test_no_results(self):
        s = PropertySearch(bedrooms=10)
        r = self.agent.search(s)
        self.assertEqual(r, [])

    def test_budget_sorting(self):
        # Under $1.7M: BB001 ($1.3M, 850sqft) and JLT001 ($1.6M, 1100sqft)
        # Sort by |price - 0.8*budget|. For $1.7M: |p - 1.36M|
        # BB001: |1.3M - 1.36M| = 60K (first)
        # JLT001: |1.6M - 1.36M| = 240K (second)
        s = PropertySearch(budget_max=1700000)
        r = self.agent.search(s)
        self.assertEqual(r[0]["location"], "business bay")
        self.assertEqual(r[1]["location"], "jlt")


class TestQualifyLead(unittest.TestCase):
    def setUp(self):
        self.agent = DubaiREAgent()

    def test_budget_indicated(self):
        q = "buy villa for 5 million"
        lead = self.agent.qualify_lead(q, [])
        self.assertTrue(lead.budget_indicated)
        self.assertGreaterEqual(lead.confidence, 0.3)

    def test_specific_location(self):
        q = "apartment in Dubai Marina"
        lead = self.agent.qualify_lead(q, [])
        self.assertGreaterEqual(lead.confidence, 0.2)

    def test_amenity_signals(self):
        q = "with pool and gym"
        lead = self.agent.qualify_lead(q, [])
        self.assertGreaterEqual(lead.confidence, 0.2)

    def test_urgency_immediate(self):
        q = "need apartment urgently"
        lead = self.agent.qualify_lead(q, [])
        self.assertEqual(lead.urgency, "immediate")

    def test_urgency_soon(self):
        q = "looking for next month"
        lead = self.agent.qualify_lead(q, [])
        self.assertEqual(lead.urgency, "soon")

    def test_intent_buy(self):
        q = "want to buy"
        lead = self.agent.qualify_lead(q, [])
        self.assertEqual(lead.intent, "buy")

    def test_intent_rent(self):
        q = "want to rent"
        lead = self.agent.qualify_lead(q, [])
        self.assertEqual(lead.intent, "rent")

    def test_intent_sell(self):
        q = "listing my villa"
        lead = self.agent.qualify_lead(q, [])
        self.assertEqual(lead.intent, "sell")

    def test_qualified(self):
        q = "buy 2 bed in Dubai Marina for 3 million"
        lead = self.agent.qualify_lead(q, [])
        self.assertTrue(lead.qualified)

    def test_not_qualified(self):
        q = "hello"
        lead = self.agent.qualify_lead(q, [])
        self.assertFalse(lead.qualified)

    def test_confidence_capped(self):
        q = "urgent buy villa in Dubai Marina for 5 million with pool and gym"
        lead = self.agent.qualify_lead(q, [])
        self.assertLessEqual(lead.confidence, 1.0)


class TestFormatResults(unittest.TestCase):
    def setUp(self):
        self.agent = DubaiREAgent()

    def test_empty_results(self):
        lead = LeadProfile()
        msg = self.agent.format_results([], lead)
        self.assertIn("No properties found", msg)

    def test_result_count_line(self):
        results = self.agent.listings_db[:2]
        lead = LeadProfile(qualified=False, confidence=0.0)
        msg = self.agent.format_results(results, lead)
        self.assertIn(f"Found {len(results)} properties", msg)

    def test_qualified_shows_score(self):
        results = self.agent.listings_db[:1]
        lead = LeadProfile(qualified=True, confidence=0.8)
        msg = self.agent.format_results(results, lead)
        self.assertIn("Lead score:", msg)
        self.assertIn("qualified buyer", msg)

    def test_property_details(self):
        results = [self.agent.listings_db[0]]
        lead = LeadProfile()
        msg = self.agent.format_results(results, lead)
        self.assertIn("DM001", msg)
        self.assertIn("dubai marina", msg.lower())
        self.assertIn("AED 2.4M", msg)

    def test_max_five_results(self):
        results = self.agent.listings_db
        lead = LeadProfile()
        msg = self.agent.format_results(results, lead)
        lines_with_id = [l for l in msg.splitlines() if l.strip().startswith("ID ")]
        self.assertLessEqual(len(lines_with_id), 5)


class TestHandleVoiceQuery(unittest.TestCase):
    def setUp(self):
        self.agent = DubaiREAgent()

    def test_e2e_ok(self):
        q = "2 bedroom apartment in Dubai Marina with pool and gym budget 3 million"
        res = self.agent.handle_voice_query(q)
        self.assertTrue(res["ok"])
        self.assertEqual(res["search_params"]["bedrooms"], 2)
        self.assertEqual(res["search_params"]["location"], "dubai marina")
        self.assertIn("pool", res["search_params"]["amenities"])
        self.assertGreater(res["results_count"], 0)
        self.assertIn("lead", res)
        self.assertIn("message", res)
        self.assertIsInstance(res["message"], str)

    def test_e2e_no_results(self):
        q = "10 bedroom villa on the moon"
        res = self.agent.handle_voice_query(q)
        self.assertTrue(res["ok"])
        self.assertEqual(res["results_count"], 0)

    def test_handle_text_query(self):
        q = "2 bedroom apartment in Dubai Marina"
        text = self.agent.handle_text_query(q)
        self.assertIsInstance(text, str)
        self.assertIn("Found", text)
        self.assertIn("DM001", text)
        self.assertIn("Found", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
