from fractions import Fraction

from .model import jsonable, require
from .routes import replay
from .planner import plan_ladder
from .economics import price_route


def failure_tree(engine, plan):
    result = replay(engine, plan)
    branches = []
    target = set(plan["target"])
    for key, outgoing in result.edges.items():
        before = result.states[key]
        objective = set(plan["nodes"][key[0]].get("objective_mods", plan["target"]))
        for probability, destination, label in outgoing:
            after = result.states[destination]
            retained = sorted(set(before.mods) & set(after.mods) & target)
            branches.append({"node": key[0], "state": before.key, "outcome": label,
                "probability_given_state": probability, "after": jsonable(after),
                "objective_met": objective <= set(after.mods), "retained_target_modifiers": retained,
                "lost_target_modifiers": sorted((set(before.mods) & target) - set(after.mods)),
                "next_node": destination[0], "terminal": result.terminals.get(destination),
                "recovery_status": "Route replay validated all downstream actions; terminal may still be failure or settle."})
    return {"status": "VALIDATED", "representation": "Finite graph; cycles are edges, not unbounded tree expansion",
            "branches": branches, "fingerprint": result.fingerprint}


def recover(engine, failure_state, target, prices, restart_plan=None, **options):
    require(not options.get("base_resource"), "RECOVERY_BASE_ACCOUNTING", "Existing failure item is already owned", "INVALID")
    options["base_owned"] = True
    search = plan_ladder(engine, failure_state, target, prices, **options)
    restart = price_route(engine, restart_plan, prices, options.get("valuation_at")) if restart_plan else None
    winner = search["winner"]
    recovery_cost = winner["economics"]["expected_total_cost"] if winner else None
    restart_cost = restart["expected_cost_per_completion_with_external_restart"] if restart else None
    decision = None
    if recovery_cost is not None:
        decision = "RECOVER" if restart_cost is None or recovery_cost <= restart_cost else "RESTART"
    return {"status": search["status"], "decision": decision, "recovery_expected_cost": recovery_cost,
            "restart_expected_cost": restart_cost, "search": search,
            "note": "Incremental spend only; sunk investment excluded. Existing failure-item resale value is not modeled."}
