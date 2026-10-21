"""Exact budget completion probabilities, including zero-cost transition cycles."""
from fractions import Fraction
import math

from .model import require, rational
from .routes import replay
from .economics import price_route, solve


def budget_distribution(engine, plan, prices, budget, valuation_at=None, max_units=10000,
                        max_work=2000000, quantiles=("1/2", "19/20", "99/100")):
    economics = price_route(engine, plan, prices, valuation_at)
    result = replay(engine, plan)
    budget = rational(budget)
    require(budget >= 0, "INVALID_BUDGET", str(budget), "INVALID")
    keys = list(result.edges)
    idx = {k: i for i, k in enumerate(keys)}
    costs = {k: sum((rational(q) * prices.price(r) for r, q in engine.action(result.actions[k]).resources.items()), Fraction())
             for k in keys}
    base = economics["base_cost"]
    available = budget - base
    if available < 0:
        return {"status": "VALIDATED", "budget": budget, "unit": prices.unit,
                "completion_within_budget": Fraction(), "stop_within_budget": Fraction(),
                "settle_within_budget": Fraction(), "quantiles": {}, "cost_cdf": [],
                "reason": "Initial base exceeds budget"}
    scale = math.lcm(*(v.denominator for v in [*costs.values(), available]))
    units = int(available * scale)
    require(units <= max_units and (units + 1) * max(1, len(keys)) ** 3 <= max_work,
            "DISTRIBUTION_LIMIT", "Exact budget lattice exceeds explicit work bound")
    action_units = {k: int(v * scale) for k, v in costs.items()}
    n = len(keys)
    zero = [[Fraction(int(i == j)) for j in range(n)] for i in range(n)]
    for key in keys:
        if not action_units[key]:
            for p, dest, _ in result.edges[key]:
                if dest in idx:
                    zero[idx[key]][idx[dest]] -= p
    tables = {"success": [], "settle": [], "any": []}
    cdf = []
    for remaining in range(units + 1):
        entry_values = {}
        for terminal_type in tables:
            rhs = []
            for key in keys:
                spend = action_units[key]
                value = Fraction()
                if spend <= remaining:
                    for probability, dest, _ in result.edges[key]:
                        if dest in result.terminals:
                            terminal = result.terminals[dest]
                            value += probability * int(terminal_type == "any" or terminal_type == terminal)
                        elif spend:
                            value += probability * tables[terminal_type][remaining - spend][idx[dest]]
                        # Zero-cost nonterminal edges are in the linear system.
                rhs.append(value)
            values = solve(zero, rhs)
            tables[terminal_type].append(values)
            entry_values[terminal_type] = values[idx[result.start]] if result.start in idx else Fraction(
                int(terminal_type == "any" or terminal_type == result.terminals[result.start]))
        cdf.append({"cost": base + Fraction(remaining, scale), "success": entry_values["success"],
                    "settle": entry_values["settle"], "any_terminal": entry_values["any"]})
    qs = {}
    for value in quantiles:
        q = rational(value)
        require(0 < q <= 1, "INVALID_QUANTILE", str(q), "INVALID")
        qs[str(q)] = next((r["cost"] for r in cdf if r["any_terminal"] >= q), None)
    return {"status": "VALIDATED", "domain": engine.data.domain, "budget": budget, "unit": prices.unit,
            "completion_within_budget": cdf[-1]["success"], "settle_within_budget": cdf[-1]["settle"],
            "stop_within_budget": cdf[-1]["any_terminal"], "quantiles": qs, "cost_cdf": cdf,
            "note": "Exact absorption-cost CDF through budget. Missing quantile means above this bound, not zero. No Monte Carlo inference."}
