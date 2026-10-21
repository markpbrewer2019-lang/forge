import copy
from dataclasses import replace
from fractions import Fraction
import unittest

from forge.fixtures import universe, example_plans
from forge.engine import Engine
from forge.distributions import budget_distribution
from forge.adversarial import adversarial_test
from forge.settles import analyze_settle
from forge.model import ForgeError, jsonable


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.data, self.prices, self.start = universe()
        self.engine = Engine(self.data)
        self.plans = example_plans(self.data, self.start)

    def test_recovery_budget_tail_is_exact(self):
        result = budget_distribution(self.engine, self.plans["C-recovery-loop"], self.prices, "28")
        self.assertEqual(Fraction(31, 32), result["completion_within_budget"])
        self.assertEqual(Fraction(16), result["quantiles"]["1/2"])
        self.assertEqual(Fraction(28), result["quantiles"]["19/20"])
        self.assertIsNone(result["quantiles"]["99/100"])

    def test_deterministic_boundary(self):
        for budget, expected in (("15", 0), ("16", 1), ("20", 1)):
            result = budget_distribution(self.engine, self.plans["B-lower-total"], self.prices, budget)
            self.assertEqual(expected, result["completion_within_budget"])

    def test_zero_cost_recovery_cycle_is_solved_not_unrolled(self):
        self.prices.quotes["roll-prefix"] = "0"
        self.prices.quotes["remove-prefix"] = "0"
        result = budget_distribution(self.engine, self.plans["C-recovery-loop"], self.prices, "15")
        self.assertEqual(1, result["completion_within_budget"])

    def test_fractional_lattice_and_work_limit(self):
        self.prices.quotes["power-after-speed"] = "1/2"
        self.assertEqual(1, budget_distribution(self.engine, self.plans["B-lower-total"], self.prices, "31/2")["completion_within_budget"])
        with self.assertRaises(ForgeError) as caught:
            budget_distribution(self.engine, self.plans["B-lower-total"], self.prices, "1000000")
        self.assertEqual("DISTRIBUTION_LIMIT", caught.exception.code)

    def test_budget_below_base(self):
        self.assertEqual(0, budget_distribution(self.engine, self.plans["B-lower-total"], self.prices, "9")["completion_within_budget"])

    def test_automatic_adversarial_mutations(self):
        result = adversarial_test(self.engine, self.plans["C-recovery-loop"])
        self.assertEqual("VALIDATED", result["status"])
        self.assertEqual(15, result["generated"])
        self.assertEqual(15, result["rejected"])

    def test_settle_uses_actual_state_and_budget(self):
        item = replace(self.start, mods=("speed",))
        continuation = copy.deepcopy(self.plans["C-recovery-loop"])
        continuation.update(starting_state=jsonable(item), entry="roll", base_owned=True)
        continuation.pop("base_resource")
        result = analyze_settle(self.engine, item, ["speed"], self.prices, continuation, "1")
        self.assertEqual("SETTLE", result["recommendation"])
        self.assertEqual(Fraction(1, 2), result["budget_analysis"]["completion_within_budget"])
        self.assertIsNone(result["market_value"])


if __name__ == "__main__":
    unittest.main()
