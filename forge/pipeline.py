"""One end-to-end gate from exact target to selected, replayed, keeper-safe Golden 6."""
from datetime import datetime, timezone

from .model import require, rational, ForgeError
from .planner import plan_ladder
from .economics import compare_routes
from .ladder import audit_ladder, compile_golden6


def exact_targets(engine, specifications, require_six=True):
    require(isinstance(specifications, (list, tuple)) and bool(specifications), "INVALID_TARGET", "Exact targets required", "INVALID")
    result = []
    for spec in specifications:
        if isinstance(spec, str):
            mid, spec = spec, {"modifier": spec}
        else:
            require(isinstance(spec, dict) and set(spec) <= {"modifier", "tier", "values"}, "INVALID_TARGET", str(spec), "INVALID")
            mid = spec["modifier"]
        modifier = engine.modifier(mid)
        require("tier" not in spec or spec["tier"] == modifier.tier, "TARGET_TIER_MISMATCH", mid, "INVALID")
        require(not spec.get("values"), "UNSUPPORTED_TARGET_VALUES", "Canonical numeric stat rolls are not implemented; exact values cannot be promised")
        result.append(mid)
    require(len(result) == len(set(result)), "DUPLICATE_TARGET", str(result), "INVALID")
    require(not require_six or len(result) == 6, "SIX_EXACT_TARGETS_REQUIRED", str(len(result)), "INVALID")
    return result


def build_craft(engine, start, target, prices, keeper_policy=None, acceptable_settles=None,
                selected_league=None, budget=None, min_completion="1", min_budget_completion="1",
                base_resource=None, base_owned=False, max_states=256, max_iterations=100,
                valuation_at=None, require_six=True, simulation_trials=0, seed=0):
    targets = exact_targets(engine, target, require_six)
    constraints = keeper_policy if keeper_policy is not None else {"initial": [], "lock_on_acquire": True}
    settles = acceptable_settles or []
    for settle in settles:
        require(set(settle) <= {"name", "required_modifiers"} and bool(settle.get("name"))
                and bool(settle.get("required_modifiers")), "INVALID_SETTLE", str(settle), "INVALID")
        for mid in settle["required_modifiers"]:
            engine.modifier(mid)
    if engine.data.domain == "POE2":
        require(selected_league is not None and selected_league == engine.data.league == prices.league,
                "SELECTED_LEAGUE_REQUIRED", "Recommendations require matching explicit league and source prices")
        require(valuation_at is None, "HISTORICAL_PRICES_NOT_RECOMMENDATION", "Authoritative real planning uses current time")
        require(engine.data.version != "UNKNOWN", "UNKNOWN_GAME_VERSION", "Real crafting must pin a verified version")
        observed = datetime.fromisoformat(prices.as_of.replace("Z", "+00:00"))
        require(observed.tzinfo is not None and 0 <= (datetime.now(timezone.utc) - observed).total_seconds() <= 3600,
                "CURRENT_PRICES_REQUIRED", "Refresh the selected league: price observation must be within one hour")
    search = plan_ladder(engine, start, targets, prices, max_states=max_states, base_resource=base_resource,
                         base_owned=base_owned, valuation_at=valuation_at, keeper_policy=constraints,
                         optimizer="policy_iteration", max_iterations=max_iterations, acceptable_settles=settles)
    if search["status"] != "VALIDATED":
        return {"status": search["status"], "phase": "PLANNING", "search": search, "golden6": None}
    plans = {"candidate-" + str(i + 1): c["plan"] for i, c in enumerate(search["candidates"])}
    comparison = compare_routes(engine, plans, prices, min_completion=min_completion, budget=budget,
                                 valuation_at=valuation_at, min_budget_completion=min_budget_completion)
    if comparison["winner"] is None:
        return {"status": "BLOCKED", "phase": "ROUTE_CONSTRAINTS", "comparison": comparison,
                "search": search, "golden6": None}
    plan = plans[comparison["winner"]]
    audit = audit_ladder(engine, plan, prices, valuation_at)
    economics = audit["economics"]
    drivers = sorted(({"resource": resource, "expected_quantity": count,
                       "expected_cost": count * prices.price(resource)}
                      for resource, count in economics["expected_resource_consumption"].items()),
                     key=lambda r: r["expected_cost"], reverse=True)
    visits = economics.get("expected_action_visits", {})
    restarts = sum((count for key, count in visits.items()
                    if plan["nodes"][key.split("|")[0]]["action"] in constraints.get("restart_actions", [])), rational(0))
    result = {"status": "VALIDATED", "domain": engine.data.domain, "selected_plan": plan, "ladder": audit,
              "golden6": compile_golden6(engine, plan, prices, valuation_at), "comparison": comparison,
              "economic_summary": {"expected_spend_until_terminal": economics["expected_total_cost"],
                  "expected_cost_per_completion_with_external_restart": economics["expected_cost_per_completion_with_external_restart"],
                  "expected_actions": economics["expected_actions"], "expected_restarts": restarts,
                  "expected_base_attempts": 1 + restarts, "major_cost_drivers": drivers,
                  "completion_probability": economics["completion_probability"], "settle_probability": economics["settle_probability"]},
              "search_summary": {k: v for k, v in search.items() if k not in {"candidates", "winner"}},
              "optimality_limits": "Exact mean-cost optimum over the loaded strict keeper-safe finite graph when unconstrained. Budget and partial-completion selection uses validated candidate policies, not a globally constrained optimizer."}
    if simulation_trials:
        from .economics import simulate
        result["simulation"] = simulate(engine, plan, prices, trials=simulation_trials, seed=seed, valuation_at=valuation_at, budget=budget)
        require(not result["simulation"]["analytical_disagreement"], "SIMULATION_DISAGREEMENT", "Do not promote inconsistent route estimates")
    return result
