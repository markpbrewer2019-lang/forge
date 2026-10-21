import copy
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest

from forge.model import Dataset, ForgeError, Item, dataset_document, jsonable
from forge.engine import Engine, explain
from forge.routes import replay, validate_route, golden6
from forge.economics import price_route, simulate, compare_routes
from forge.planner import plan_ladder
from forge.fixtures import universe, example_plans
from forge.data import coverage, ingest_local, normalize_ninja_exchange


class ForgeTests(unittest.TestCase):
    def setUp(self):
        self.data, self.prices, self.start = universe()
        self.engine = Engine(self.data)
        self.plans = example_plans(self.data, self.start)
        self.plan = self.plans["C-recovery-loop"]

    def assertCode(self, code, function, *args, **kwargs):
        with self.assertRaises(ForgeError) as caught:
            function(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)
        return caught.exception

    def repin(self, plan):
        plan["dataset_id"] = self.data.key
        return plan

    def test_canonical_roundtrip(self):
        item = replace(self.start, mods=("speed", "power"), fractured=("power",))
        self.assertEqual(item, Item.load(json.loads(json.dumps(jsonable(item)))))
        self.assertEqual(item.key, replace(item, mods=("power", "speed")).key)
        self.assertEqual({"prefix": 0, "suffix": 0}, self.engine.inspect(item)["open_slots"])
        self.assertCode("DUPLICATE_STATE_ENTRY", replace, self.start, mods=("power", "power"))

    def test_state_invariants(self):
        cases = [(replace(self.start, mods=("power", "junk")), "AFFIX_CAPACITY_EXCEEDED"),
                 (replace(self.start, fractured=("power",)), "INVALID_PROTECTION"),
                 (replace(self.start, mods=("power",), rarity="normal"), "AFFIX_CAPACITY_EXCEEDED")]
        for item, code in cases:
            with self.subTest(code=code):
                self.assertCode(code, self.engine.inspect, item)

    def test_pool_probability_and_exclusion(self):
        pool = self.engine.pool(self.start, "roll-prefix")
        self.assertEqual(2, pool["total_weight"])
        self.assertEqual(Fraction(1, 2), self.engine.probability(self.start, "roll-prefix", ["power"]))
        full = replace(self.start, mods=("power",))
        self.assertIn("NO_OPEN_PREFIX", self.engine.pool(full, "roll-prefix")["excluded"]["junk"])

    def test_missing_weight_blocks_complete_pool(self):
        self.data.modifiers["junk"] = replace(self.data.modifiers["junk"], weight=None)
        self.assertCode("INSUFFICIENT_VERIFIED_DATA", self.engine.probability, self.start, "roll-prefix", ["power"])
        self.assertEqual(["junk"], coverage(self.data)["missing"]["weight"])

    def test_no_certificate_no_probability(self):
        self.data.pools = ()
        self.assertCode("INSUFFICIENT_VERIFIED_DATA", self.engine.pool, self.start, "roll-prefix")

    def test_conflicted_evidence_blocks(self):
        m = self.data.modifiers["junk"]
        self.data.modifiers["junk"] = replace(m, evidence=replace(m.evidence, status="CONFLICTED"))
        self.assertCode("INSUFFICIENT_VERIFIED_DATA", self.engine.pool, self.start, "roll-prefix")

    def test_domain_and_version_are_barriers(self):
        self.assertCode("WRONG_GAME", Dataset, "POE1", "x", "x", {}, {}, {}, ())
        self.data.domain = "POE2"
        self.assertCode("EVIDENCE_SCOPE_MISMATCH", self.engine.inspect, self.start)
        self.data.domain = "SYNTHETIC"
        self.data.version = "other"
        self.assertCode("EVIDENCE_SCOPE_MISMATCH", self.engine.inspect, self.start)

    def test_ilvl_and_group_conflict(self):
        self.data.modifiers["power"] = replace(self.data.modifiers["power"], ilvl=10)
        self.assertCode("MODIFIER_ILVL_REQUIREMENT_NOT_MET", self.engine.legality, self.start, "power-first")
        self.data.modifiers["power"] = replace(self.data.modifiers["power"], ilvl=1, group="speed")
        self.assertCode("MODIFIER_GROUP_CONFLICT", self.engine.inspect, replace(self.start, mods=("power", "speed")))

    def test_symmetric_explicit_conflicts(self):
        self.data.modifiers["power"] = replace(self.data.modifiers["power"], conflicts=("speed",))
        self.assertCode("MODIFIER_GROUP_CONFLICT", self.engine.legality,
                        replace(self.start, mods=("power",)), "speed-after-power")

    def test_wrong_rarity_and_missing_mechanic(self):
        self.assertCode("WRONG_ITEM_RARITY", self.engine.legality, replace(self.start, rarity="normal"), "roll-prefix")
        self.assertCode("UNVERIFIED_MECHANIC", self.engine.transition, self.start, "imaginary-annul")

    def test_protections_preserved(self):
        locked = replace(self.start, mods=("power",), fractured=("power",))
        self.assertCode("NO_ELIGIBLE_REMOVAL", self.engine.transition, locked, "remove-prefix")

    def test_transition_explains_actual_state(self):
        after = self.engine.transition(self.start, "power-first")[0].state
        change = explain(self.start, after, self.engine)
        self.assertEqual(["power"], change["added"])
        self.assertEqual([1, 0], change["open_slots"]["prefix"])

    def test_future_conflicts(self):
        item = replace(self.start, mods=("junk",))
        result = self.engine.future_conflicts(item, ["power", "speed"])
        self.assertTrue(any(i["reason"] == "FUTURE_SLOT_DEFICIT" for i in result["issues"]))

    def test_replay_keeps_actual_miss_state(self):
        plan = copy.deepcopy(self.plan)
        plan["nodes"]["recover"]["expected_state"] = jsonable(replace(self.start, mods=("speed",)))
        report = validate_route(self.engine, plan)
        self.assertEqual("EXPECTED_STATE_MISMATCH", report["code"])
        self.assertEqual("roll", report["location"]["origin"]["node"])

    def test_missing_and_fake_branches_rejected(self):
        for branches in ({"power": "done"}, {"power": "done", "junk": "recover", "fake": "done"}):
            plan = copy.deepcopy(self.plan)
            plan["nodes"]["roll"]["branches"] = branches
            self.assertEqual("INCOMPLETE_OR_FAKE_BRANCHES", validate_route(self.engine, plan)["code"])

    def test_false_probability_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["nodes"]["roll"]["claimed_probabilities"] = {"power": "3/4", "junk": "1/4"}
        self.assertEqual("FALSE_CLAIMED_PROBABILITY", validate_route(self.engine, plan)["code"])

    def test_impossible_recovery_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["nodes"]["recover"]["action"] = "power-after-speed"
        self.assertEqual("NO_OPEN_PREFIX", validate_route(self.engine, plan)["code"])

    def test_wrong_final_target(self):
        plan = copy.deepcopy(self.plan)
        plan["nodes"]["roll"]["branches"]["junk"] = "done"
        self.assertEqual("FINAL_TARGET_MISMATCH", validate_route(self.engine, plan)["code"])

    def test_closed_loop_rejected(self):
        plan = copy.deepcopy(self.plans["A-cheap-first"])
        a = self.data.actions["power-first"]
        self.data.actions["wait"] = replace(a, id="wait", operation="flags", fixed_mod=None, side=None, resources={})
        self.repin(plan)
        plan["nodes"]["second"] = {"objective": "Fake recovery", "action": "wait", "branches": {"flags": "second"}}
        self.assertEqual("NONTERMINATING_RECOVERY", validate_route(self.engine, plan)["code"])

    def test_dataset_pin(self):
        self.data.modifiers["junk"] = replace(self.data.modifiers["junk"], weight=2)
        self.assertEqual("DATASET_MISMATCH", validate_route(self.engine, self.plan)["code"])

    def test_exact_loop_economics(self):
        result = price_route(self.engine, self.plan, self.prices)
        # base 10 + suffix 5 + two rolls 2 + one removal 2 = 19
        self.assertEqual(Fraction(19), result["expected_total_cost"])
        self.assertEqual(Fraction(1), result["completion_probability"])
        self.assertEqual(Fraction(2), result["expected_resource_consumption"]["roll-prefix"])
        self.assertEqual(Fraction(1), result["expected_resource_consumption"]["remove-prefix"])

    def test_full_route_beats_cheaper_first_rung(self):
        comparison = compare_routes(self.engine, self.plans, self.prices)
        self.assertEqual("B-lower-total", comparison["winner"])
        costs = {r["name"]: r["economics"]["expected_total_cost"] for r in comparison["candidates"]}
        self.assertEqual(Fraction(111), costs["A-cheap-first"])
        self.assertEqual(Fraction(16), costs["B-lower-total"])

    def test_independent_planner_finds_best_acquisition_order(self):
        planned = plan_ladder(self.engine, self.start, ["power", "speed"], self.prices, base_resource="base")
        self.assertEqual("VALIDATED", planned["status"])
        winner = planned["winner"]
        self.assertEqual(Fraction(16), winner["economics"]["expected_total_cost"])
        entry = winner["plan"]["entry"]
        self.assertEqual("speed-first", winner["plan"]["nodes"][entry]["action"])
        self.assertGreater(planned["valid_routes"], 1)

    def test_search_bounds_fail_closed(self):
        self.assertCode("SEARCH_STATE_LIMIT", plan_ladder, self.engine, self.start, ["power", "speed"],
                        self.prices, max_states=1, base_owned=True)
        self.assertCode("SEARCH_POLICY_LIMIT", plan_ladder, self.engine, self.start, ["power", "speed"],
                        self.prices, max_policies=1, base_owned=True)

    def test_price_gates(self):
        self.prices.quotes.pop("roll-prefix")
        self.assertCode("MISSING_PRICE", price_route, self.engine, self.plan, self.prices)
        self.prices.league = "wrong"
        self.assertCode("PRICE_SCOPE_MISMATCH", price_route, self.engine, self.plan, self.prices)

    def test_stale_price_and_false_cost(self):
        self.assertCode("STALE_OR_FUTURE_PRICE", price_route, self.engine, self.plan, self.prices,
                        valuation_at="2099-01-01T00:00:00Z")
        plan = copy.deepcopy(self.plan)
        plan["claimed_total_cost"] = "1"
        self.assertCode("FALSE_CLAIMED_COST", price_route, self.engine, plan, self.prices)

    def test_validation_precedes_price_lookup(self):
        plan = copy.deepcopy(self.plan)
        plan["nodes"]["recover"]["action"] = "fake"
        self.prices.quotes = {}
        self.assertCode("UNVERIFIED_MECHANIC", price_route, self.engine, plan, self.prices)

    def test_budget_uses_distribution_instead_of_ev(self):
        result = compare_routes(self.engine, self.plans, self.prices, budget="20")
        self.assertEqual("B-lower-total", result["winner"])
        self.assertTrue(all(r["reason"] == "BUDGET_COMPLETION_CONSTRAINT" for r in result["rejected"]))

    def test_seeded_monte_carlo_matches_exact_20000(self):
        report = simulate(self.engine, self.plan, self.prices, trials=20000, seed=42, budget="25")
        self.assertEqual(0, report["censored"])
        self.assertEqual(1, report["completion_frequency"])
        self.assertFalse(report["analytical_disagreement"])
        self.assertAlmostEqual(19, report["mean_spend"], delta=.15)
        self.assertGreater(report["p95_spend"], report["median_spend"])
        a = simulate(self.engine, self.plan, self.prices, trials=100, seed=6)
        b = simulate(self.engine, self.plan, self.prices, trials=100, seed=6)
        self.assertEqual(a, b)

    def test_simulation_censoring_is_not_completion(self):
        report = simulate(self.engine, self.plan, self.prices, trials=100, max_steps=1)
        self.assertEqual(100, report["censored"])
        self.assertEqual("PARTIALLY_VALIDATED", report["status"])
        self.assertTrue(report["analytical_disagreement"])

    def test_golden6_requires_actual_validation(self):
        result = golden6(self.engine, self.plan, self.prices)
        self.assertEqual(2, len(result["steps"]))
        plan = copy.deepcopy(self.plan)
        plan["nodes"]["recover"]["action"] = "fake"
        self.assertCode("UNVERIFIED_MECHANIC", golden6, self.engine, plan, self.prices)

    def test_local_ingestion_preserves_provenance_and_unknowns(self):
        self.data.modifiers["junk"] = replace(self.data.modifiers["junk"], weight=None)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "export.json"
            source.write_text(json.dumps(dataset_document(self.data)), encoding="utf-8")
            receipt = ingest_local(source, Path(directory) / "local")
            loaded = Dataset.load(json.loads((Path(directory) / "local/dataset.json").read_text()))
            self.assertEqual(self.data.key, loaded.key)
            self.assertEqual(source.read_bytes(), Path(receipt["snapshot"]).read_bytes())
            self.assertIsNone(loaded.modifiers["junk"].weight)

    def test_duplicate_records_are_not_overwritten(self):
        document = dataset_document(self.data)
        document["modifiers"].append(document["modifiers"][0])
        self.assertCode("CONFLICTING_RECORD", Dataset.load, document)

    def test_normalized_market_observation_requires_review(self):
        raw = {"core": {"primary": "divine"}, "lines": [{"id": "test", "primaryValue": "0.25"}]}
        result = normalize_ninja_exchange(raw, league="Standard", version="unverified-patch",
                    as_of="2026-10-20T00:00:00Z", source_reference="https://poe.ninja/poe2/api/economy/exchange/current/overview?league=Standard&type=Currency")
        self.assertEqual("1/4", result["price_book"]["quotes"]["test"])
        self.assertEqual("INFERRED", result["price_book"]["evidence"]["status"])


if __name__ == "__main__":
    unittest.main()
