import copy
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import tempfile
import unittest

from forge.fixtures import universe, example_plans
from forge.engine import Engine
from forge.failures import failure_tree, recover
from forge.regressions import run_cases
from forge.export_examples import export
from forge.economics import price_route, simulate
from forge.routes import validate_route, golden6


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.data, self.prices, self.start = universe()
        self.engine = Engine(self.data)
        self.plans = example_plans(self.data, self.start)

    def test_recovery_vs_restart_uses_actual_failure_state(self):
        failure = replace(self.start, mods=("speed", "junk"))
        result = recover(self.engine, failure, ["power", "speed"], self.prices,
                         self.plans["B-lower-total"])
        self.assertEqual("RECOVER", result["decision"])
        self.assertEqual(Fraction(3), result["recovery_expected_cost"])
        self.assertEqual(Fraction(16), result["restart_expected_cost"])

    def test_failure_graph_retains_progress(self):
        tree = failure_tree(self.engine, self.plans["C-recovery-loop"])
        miss = next(b for b in tree["branches"] if b["node"] == "roll" and b["outcome"] == "junk")
        self.assertEqual(["speed"], miss["retained_target_modifiers"])
        self.assertEqual(Fraction(1, 2), miss["probability_given_state"])
        self.assertEqual("recover", miss["next_node"])

    def test_failure_and_settle_economics_are_explicit(self):
        for terminal in ("failure", "settle"):
            plan = copy.deepcopy(self.plans["C-recovery-loop"])
            plan["nodes"]["recover"] = {"objective": "Stop deliberately", "terminal": terminal,
                                         "settle_reason": "Synthetic stop criterion"}
            self.assertEqual("VALIDATED", validate_route(self.engine, plan)["status"])
            ev = price_route(self.engine, plan, self.prices)
            self.assertEqual(Fraction(16), ev["expected_total_cost"])
            self.assertEqual(Fraction(1, 2), ev["completion_probability"])
            self.assertEqual(Fraction(1, 2), ev[terminal + "_probability"])
            report = simulate(self.engine, plan, self.prices, trials=10000, seed=42)
            self.assertFalse(report["analytical_disagreement"])

    def test_restart_branch_prices_repeated_bases(self):
        # A reset deliberately consumes another base and loses all earlier investment.
        a = self.data.actions["remove-prefix"]
        self.data.actions["restart"] = replace(a, id="restart", operation="reset", side=None,
            resources={"base": 1}, require_mods=("junk",))
        plan = copy.deepcopy(self.plans["C-recovery-loop"])
        plan["dataset_id"] = self.data.key
        plan["nodes"]["recover"] = {"objective": "Restart base", "action": "restart",
            "branches": {"reset": "first"}, "rung": "power"}
        ev = price_route(self.engine, plan, self.prices)
        # 10 initial base + 2*(5 suffix + 1 roll) + 1*10 replacement base.
        self.assertEqual(Fraction(32), ev["expected_total_cost"])
        self.assertEqual(Fraction(1), ev["expected_resource_consumption"]["base"])

    def test_golden6_does_not_publish_unreachable_actions(self):
        plan = copy.deepcopy(self.plans["B-lower-total"])
        plan["nodes"]["unreachable"] = {"objective": "Fake", "rung": "bad", "action": "fake", "branches": {}}
        output = golden6(self.engine, plan, self.prices)
        self.assertNotIn("bad", output["steps"])

    def test_data_driven_regression_store(self):
        with tempfile.TemporaryDirectory() as directory:
            export(directory)
            result = run_cases(Path(directory) / "regressions")
            self.assertEqual("VALIDATED", result["status"])
            self.assertEqual(5, len(result["cases"]))

    def test_planner_avoids_irrecoverable_branch_without_abandoning_safe_route(self):
        from forge.planner import plan_ladder
        self.data.actions.pop("remove-prefix")
        result = plan_ladder(self.engine, self.start, ["power", "speed"], self.prices, base_resource="base")
        self.assertEqual("VALIDATED", result["status"])
        self.assertEqual(Fraction(16), result["winner"]["economics"]["expected_total_cost"])

    def test_malformed_weight_rejected_during_ingestion(self):
        from forge.model import dataset_document, Dataset, ForgeError
        document = dataset_document(self.data)
        document["modifiers"][0]["weight"] = -1
        with self.assertRaises(ForgeError) as caught:
            Dataset.load(document)
        self.assertEqual("INVALID_MODIFIER_NUMBER", caught.exception.code)

    def test_unknown_special_state_blocks_action(self):
        from forge.model import ForgeError
        with self.assertRaises(ForgeError) as caught:
            self.engine.transition(replace(self.start, flags=("unmodeled-crafting-state",)), "power-first")
        self.assertEqual("UNKNOWN_INTERACTION", caught.exception.code)

    def test_ambiguous_terminal_action_is_not_ignored(self):
        plan = copy.deepcopy(self.plans["B-lower-total"])
        plan["nodes"]["first"]["terminal"] = "failure"
        self.assertEqual("AMBIGUOUS_NODE", validate_route(self.engine, plan)["code"])

    def test_typo_in_probability_claim_is_rejected(self):
        plan = copy.deepcopy(self.plans["C-recovery-loop"])
        plan["nodes"]["roll"]["claimed_probability"] = "1"
        self.assertEqual("UNKNOWN_NODE_FIELD", validate_route(self.engine, plan)["code"])


if __name__ == "__main__":
    unittest.main()
