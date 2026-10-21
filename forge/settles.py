"""Explicit build-criteria stopping analysis, backed by validated continuation economics."""
from .model import Item, require, rational
from .economics import price_route
from .distributions import budget_distribution


def analyze_settle(engine, item, required_modifiers, prices, continuation_plan, remaining_budget,
                   minimum_completion="1", valuation_at=None):
    engine.inspect(item)
    for mid in required_modifiers:
        engine.modifier(mid)
    require(set(required_modifiers) <= set(continuation_plan["target"]),
            "BUILD_TARGET_MISMATCH", "Continuation target must satisfy the supplied build requirements", "INVALID")
    require(Item.load(continuation_plan["starting_state"]) == item,
            "CONTINUATION_STATE_MISMATCH", "Continuation must consume the actual settle item", "INVALID")
    require(continuation_plan.get("base_owned") is True and not continuation_plan.get("base_resource"),
            "CONTINUATION_BASE_ACCOUNTING", "Existing item must be owned, not repurchased", "INVALID")
    threshold = rational(minimum_completion)
    require(0 <= threshold <= 1, "INVALID_COMPLETION_THRESHOLD", str(threshold), "INVALID")
    economics = price_route(engine, continuation_plan, prices, valuation_at)
    distribution = budget_distribution(engine, continuation_plan, prices, remaining_budget, valuation_at)
    criteria_met = set(required_modifiers) <= set(item.mods)
    fits = distribution["completion_within_budget"] >= threshold
    return {"status": "VALIDATED", "build_requirements_met": criteria_met,
            "recommendation": "SETTLE" if criteria_met and not fits else ("CONTINUE" if fits else "NO_FEASIBLE_DECISION"),
            "continuation_economics": economics,
            "budget_analysis": {k: v for k, v in distribution.items() if k != "cost_cdf"},
            "market_value": None, "market_value_status": "UNKNOWN",
            "reason": "Decision uses supplied exact build requirements and exact budget-completion threshold; no invented resale value."}
