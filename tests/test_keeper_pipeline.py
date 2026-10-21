import copy
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import unittest

from forge.model import Dataset, Evidence, ForgeError, Item, digest, jsonable, dataset_document
from forge.engine import Engine
from forge.pipeline import build_craft
from forge.planner import plan_ladder
from forge.routes import replay, validate_route
from forge.cli import dispatch
from tests.keeper_fixture import six_mod_universe


class KeeperPipelineTests(unittest.TestCase):
    def setUp(self):
        self.data, self.prices, self.start, self.target = six_mod_universe()
        self.engine = Engine(self.data)

    def craft(self, **options):
        return build_craft(self.engine, self.start, self.target, self.prices, base_resource="base", **options)

    def test_six_mod_route_retains_all_earned_keepers_and_selects_global_cost(self):
        before = dataset_document(self.data)
        result = self.craft()
        self.assertEqual("VALIDATED", result["status"])
        self.assertEqual(Fraction(23), result["economic_summary"]["expected_spend_until_terminal"])
        self.assertEqual(1, result["economic_summary"]["completion_probability"])
        self.assertEqual(0, result["ladder"]["risks"]["keeper_loss_probability"])
        plan = result["selected_plan"]
        self.assertEqual("speed-first", plan["nodes"][plan["entry"]]["action"])
        self.assertEqual(before, dataset_document(self.data), "Planning must not mutate source facts or weights")
        for row in result["ladder"]["transitions"]:
            self.assertTrue(set(row["current_keepers"]) <= set(row["after_state"]["mods"]))
            self.assertIn("provenance", row)

    def test_misses_recover_with_exact_victim_and_never_uniform_keeper_risk(self):
        result = self.craft()
        actions = {row["action"] for row in result["ladder"]["transitions"]}
        self.assertIn("remove-junk", actions)
        self.assertNotIn("remove-prefix", actions)
        self.assertIn("RETRY_SAME_RUNG", {r["classification"] for r in result["ladder"]["transitions"]})
        self.assertTrue(any(r.get("code") == "EARNED_KEEPER_LOSS" for r in result["search_summary"]["rejected_actions"]))

    def test_golden6_names_every_selected_action_and_hides_branch_graph(self):
        result = self.craft()
        golden = result["golden6"]
        self.assertEqual(6, len(golden["steps"]))
        self.assertNotIn("transitions", golden)
        actual = {r["action"] for r in result["ladder"]["transitions"]}
        compiled = {aid for s in golden["steps"] for aid in s["action_ids"]}
        self.assertEqual(actual, compiled)
        self.assertTrue(all(s["actions"] and "Synthetic" in s["instructions"] for s in golden["steps"]))

    def test_initial_keeper_cannot_be_treated_as_disposable(self):
        start = replace(self.start, mods=("power",))
        result = build_craft(self.engine, start, self.target, self.prices,
                             keeper_policy={"initial": ["power"]}, base_owned=True)
        self.assertEqual("VALIDATED", result["status"])
        self.assertEqual(0, result["ladder"]["risks"]["initial_keeper_loss_probability"])

    def test_numeric_values_are_blocked_instead_of_invented(self):
        target = [{"modifier": mid, "tier": 1} for mid in self.target]
        target[0]["values"] = {"damage": 500}
        with self.assertRaises(ForgeError) as caught:
            build_craft(self.engine, self.start, target, self.prices, base_owned=True)
        self.assertEqual("UNSUPPORTED_TARGET_VALUES", caught.exception.code)

    def test_unknown_essential_mechanic_never_produces_golden6(self):
        self.data.actions["add-speed3"] = replace(self.data.actions["add-speed3"],
            evidence=replace(self.data.actions["add-speed3"].evidence, category="UNKNOWN"))
        result = self.craft()
        self.assertIsNone(result["golden6"])
        self.assertNotEqual("VALIDATED", result["status"])

    def test_simulator_observation_cannot_be_verified_live_mechanic(self):
        action = self.data.actions["power-first"]
        self.data.domain = "POE2"
        self.data.actions[action.id] = replace(action, evidence=replace(action.evidence, domain="POE2",
            category="SIMULATOR_OBSERVATION", status="VERIFIED"))
        with self.assertRaises(ForgeError) as caught:
            self.engine.action(action.id)
        self.assertEqual("UNVERIFIED_MECHANIC_PROVENANCE", caught.exception.code)

    def test_source_fact_kind_does_not_override_unverified_status(self):
        action = self.data.actions["power-first"]
        self.data.actions[action.id] = replace(action, evidence=replace(action.evidence,
            category="SOURCE_FACT", status="HYPOTHESIS"))
        with self.assertRaises(ForgeError) as caught:
            self.engine.action(action.id)
        self.assertEqual("INSUFFICIENT_VERIFIED_DATA", caught.exception.code)

    def test_omen_context_without_interaction_fact_blocks(self):
        action = self.data.actions["power-first"]
        self.data.actions[action.id] = replace(action, mechanic_context={"omens": ["unverified omen"]})
        with self.assertRaises(ForgeError) as caught:
            self.engine.transition(self.start, action.id)
        self.assertEqual("UNKNOWN_INTERACTION", caught.exception.code)

    def test_special_pool_cannot_be_shortlisted_into_generic_addition(self):
        action = self.data.actions["roll-prefix"]
        self.data.actions[action.id] = replace(action, mechanic_context={"special_pool": "Desecration"})
        with self.assertRaises(ForgeError) as caught:
            self.engine.action(action.id)
        self.assertEqual("UNSUPPORTED_SPECIAL_POOL", caught.exception.code)

    def test_policy_iteration_limit_suppresses_optimality_and_golden6(self):
        result = self.craft(max_iterations=1)
        self.assertNotEqual("VALIDATED", result["status"])
        self.assertIsNone(result["golden6"])

    def test_legacy_saved_dataset_hashes_remain_valid(self):
        root = Path(__file__).resolve().parents[1]
        request = json.loads((root / "examples/route.json").read_text())
        self.assertEqual(request["plan"]["dataset_id"], Dataset.load(request["dataset"]).key)
        self.assertEqual("VALIDATED", validate_route(Engine(Dataset.load(request["dataset"])), request["plan"])["status"])

    def test_end_to_end_cli_dispatch_is_connected(self):
        request = {"dataset": dataset_document(self.data), "prices": jsonable(self.prices),
                   "item": jsonable(self.start), "target": self.target, "options": {"base_resource": "base"}}
        result = dispatch("build-craft", request)
        self.assertEqual("VALIDATED", result["status"])
        self.assertEqual(Fraction(23), result["economic_summary"]["expected_spend_until_terminal"])

    def test_simulator_observation_cannot_supply_live_modifier_facts(self):
        modifier = self.data.modifiers["power"]
        self.data.domain = "POE2"
        self.data.modifiers[modifier.id] = replace(modifier, evidence=replace(modifier.evidence,
            domain="POE2", category="SIMULATOR_OBSERVATION", status="VERIFIED"))
        with self.assertRaises(ForgeError) as caught:
            self.engine.modifier(modifier.id)
        self.assertEqual("UNVERIFIED_STATE_PROVENANCE", caught.exception.code)

    def test_simulator_observation_cannot_supply_live_base_facts(self):
        base = self.data.bases[self.start.base]
        self.data.domain = "POE2"
        self.data.bases[base.id] = replace(base, evidence=replace(base.evidence,
            domain="POE2", category="SIMULATOR_OBSERVATION", status="VERIFIED"))
        with self.assertRaises(ForgeError) as caught:
            self.engine.base(self.start)
        self.assertEqual("UNVERIFIED_STATE_PROVENANCE", caught.exception.code)

    def test_six_mod_simulation_matches_analytical_full_route(self):
        result = self.craft(simulation_trials=20000, seed=42)
        self.assertEqual("VALIDATED", result["status"])
        self.assertFalse(result["simulation"]["analytical_disagreement"])
        self.assertEqual(1, result["simulation"]["completion_frequency"])
        self.assertAlmostEqual(23, result["simulation"]["mean_spend"], delta=.2)

    def test_golden6_miss_removal_is_conditional_not_an_action_after_success(self):
        result = self.craft()
        step = next(s for s in result["golden6"]["steps"] if "roll-prefix" in s["action_ids"])
        self.assertIn("rules", step, "A flat list of actions gives illegal recovery instructions after success")
        removal = next(rule for rule in step["rules"] if rule["action_id"] == "remove-junk")
        self.assertIn("junk", removal["when"]["required_modifiers"])
        roll = next(rule for rule in step["rules"] if rule["action_id"] == "roll-prefix")
        self.assertIn("junk", roll["when"]["forbidden_modifiers"])
        success = next(outcome for outcome in roll["outcomes"] if outcome["label"] == "power2")
        self.assertEqual("ADVANCE", success["classification"])
        self.assertNotEqual("remove-junk", success.get("next_action_id"))


if __name__ == "__main__":
    unittest.main()
