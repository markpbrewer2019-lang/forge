"""Bounded exhaustive stationary-policy search; no recipe-specific logic."""
from collections import deque
from itertools import product
import math

from .model import ForgeError, Item, require, jsonable, rational
from fractions import Fraction
from .routes import target_matches
from .economics import price_route


def plan_ladder(engine, start, target, prices, max_states=30, max_policies=10000,
                base_resource=None, base_owned=False, valuation_at=None, keeper_policy=None,
                optimizer="enumerate", max_iterations=100, acceptable_settles=None):
    engine.inspect(start)
    require(optimizer in {"enumerate", "policy_iteration"}, "UNKNOWN_OPTIMIZER", optimizer, "INVALID")
    from .keepers import KeeperPolicy
    policy = KeeperPolicy.load(keeper_policy) if keeper_policy is not None else None
    if policy:
        policy.validate_start(start, target)
        require(policy.lock_on_acquire and policy.max_fallback_rungs == 0 and not policy.restart_actions,
                "UNSUPPORTED_SEARCH_KEEPER_POLICY", "Search currently proves strict monotone keeper accumulation. Replay supports explicit fallbacks/restarts.")
    rejected = []
    # Final requirements constrain the search before any action is selected.
    engine.inspect(Item(start.base, start.ilvl, start.rarity, start.quality, tuple(target)))
    states, options, blocked = {}, {}, []
    queue = deque([start])
    while queue:
        item = queue.popleft()
        if item.key in states:
            continue
        require(len(states) < max_states, "SEARCH_STATE_LIMIT", "No optimality claim; search incomplete")
        states[item.key] = item
        if target_matches(item, target):
            continue
        options[item.key] = []
        for action_id in sorted(engine.data.actions):
            try:
                outcomes = engine.transition(item, action_id)
                if policy:
                    for outcome in outcomes:
                        policy.classify(item, outcome.state, target, engine.action(action_id))
            except ForgeError as exc:
                if exc.status != "INVALID":
                    blocked.append({"state": item.key, "action": action_id, "classification": "BLOCKED_UNKNOWN", **exc.report()})
                else:
                    rejected.append({"state": item.key, "action": action_id, **exc.report()})
                continue
            options[item.key].append((action_id, outcomes))
            queue.extend(o.state for o in outcomes)
    dead_ends = {k for k, value in options.items() if not value}
    if optimizer == "policy_iteration":
        return _policy_iteration(engine, start, target, prices, states, options, blocked, rejected,
                                 base_resource, base_owned, valuation_at, policy, acceptable_settles or [], max_iterations)
    options = {k: value for k, value in options.items() if value}
    count = math.prod(len(v) for v in options.values())
    require(count <= max_policies, "SEARCH_POLICY_LIMIT", f"{count} policies > {max_policies}; no partial winner")
    keys = list(options)
    candidates, invalid = [], 0
    for selection in product(*(options[k] for k in keys)):
        nodes = {}
        for state_id, item in states.items():
            if target_matches(item, target):
                nodes[state_id] = {"objective": "Exact target", "terminal": "success", "expected_state": jsonable(item)}
            elif state_id in dead_ends:
                nodes[state_id] = {"objective": "No legal continuation in loaded action set", "terminal": "failure",
                                   "expected_state": jsonable(item)}
        for state_id, (action_id, outcomes) in zip(keys, selection):
            nodes[state_id] = {"objective": "Reach exact final target with validated recovery", "rung": state_id,
                               "action": action_id, "expected_state": jsonable(states[state_id]),
                               "branches": {o.label: o.state.key for o in outcomes}}
        candidate = {"schema_version": 1, "dataset_id": engine.data.key,
                     "starting_state": jsonable(start), "target": list(target), "entry": start.key,
                     "base_owned": base_owned, "nodes": nodes}
        if policy:
            candidate["keeper_policy"] = jsonable(policy)
        if base_resource:
            candidate["base_resource"] = base_resource
        try:
            economics = price_route(engine, candidate, prices, valuation_at)
        except ForgeError as exc:
            if exc.status == "INVALID":
                invalid += 1
                continue
            raise
        if economics["completion_probability"] == 1:
            candidates.append({"plan": candidate, "economics": economics})
    candidates.sort(key=lambda c: c["economics"]["expected_total_cost"])
    # Different policies on unreachable states are the same route: deduplicate by trace fingerprint.
    unique, seen = [], set()
    from .routes import replay
    from .model import digest
    for candidate in candidates:
        signature = digest(replay(engine, candidate["plan"]).trace)
        if signature not in seen:
            seen.add(signature)
            unique.append(candidate)
    return {"status": "PARTIALLY_VALIDATED" if blocked else ("VALIDATED" if unique else "BLOCKED"),
            "domain": engine.data.domain, "search_states": len(states), "enumerated_policies": count,
            "invalid_policies": invalid, "valid_routes": len(unique), "blocked_actions": blocked,
            "rejected_actions": rejected,
            "winner": unique[0] if unique and not blocked else None, "candidates": unique,
            "optimality_scope": "All deterministic stationary policies over the complete reachable finite graph of loaded actions; almost-sure completion, expected spend objective. No budget/tail optimization."}


def _policy_iteration(engine, start, target, prices, states, options, blocked, rejected,
                      base_resource, base_owned, valuation_at, keeper_policy, settles, max_iterations):
    """Exact stochastic shortest path with an almost-sure proper initial policy."""
    from .economics import solve
    from .routes import replay
    from .model import digest
    require(type(max_iterations) is int and max_iterations > 0, "INVALID_SEARCH_BOUND", str(max_iterations), "INVALID")
    prices.verify(engine, valuation_at)
    targets = {k for k, item in states.items() if target_matches(item, target)}
    settle_states = {k for k, choices in options.items() if not choices and any(
        set(s["required_modifiers"]) <= set(states[k].mods) for s in settles)}
    goals = targets | settle_states
    winning = set(states)
    ranks = {}
    while True:
        reachable = goals & winning
        ranks = {k: 0 for k in reachable}
        depth = 0
        while True:
            depth += 1
            added = {k for k in winning - reachable if any(
                all(o.state.key in winning for o in outcomes) and any(o.state.key in reachable for o in outcomes)
                for _, outcomes in options.get(k, []))}
            if not added:
                break
            ranks.update({k: depth for k in added})
            reachable |= added
        if reachable == winning:
            break
        winning = reachable
    if start.key not in winning:
        return {"status": "BLOCKED", "code": "NO_KEEPER_SAFE_COMPLETION", "winner": None, "candidates": [],
                "search_states": len(states), "blocked_actions": blocked, "rejected_actions": rejected,
                "detail": "No almost-sure route to target or declared dead-end settle within loaded mechanics and keeper constraints."}
    active = sorted(winning - goals)
    index = {k: i for i, k in enumerate(active)}
    choices = {k: [(aid, outcomes) for aid, outcomes in options[k]
                   if all(o.state.key in winning for o in outcomes)] for k in active}
    selected = {k: next(pair for pair in choices[k] if any(ranks[o.state.key] < ranks[k] for o in pair[1])) for k in active}
    def cost(aid):
        return sum((rational(q) * prices.price(r) for r, q in engine.action(aid).resources.items()), Fraction())
    candidates, seen, converged = [], set(), False
    for iteration in range(1, max_iterations + 1):
        matrix = [[Fraction(int(i == j)) for j in range(len(active))] for i in range(len(active))]
        for key, (_, outcomes) in selected.items():
            for outcome in outcomes:
                if outcome.state.key in index:
                    matrix[index[key]][index[outcome.state.key]] -= outcome.probability
        values = solve(matrix, [cost(selected[k][0]) for k in active])
        steps = solve(matrix, [Fraction(1) for _ in active])
        nodes = {}
        for key in winning:
            item = states[key]
            if key in goals:
                nodes[key] = {"objective": "Exact target" if key in targets else "Approved fallback settle",
                              "terminal": "success" if key in targets else "settle", "expected_state": jsonable(item)}
                if key in settle_states:
                    nodes[key]["settle_reason"] = "Matches a supplied acceptable settle with no keeper-safe continuation"
            else:
                aid, outcomes = selected[key]
                acquired = sorted(set(item.mods) & set(target))
                nodes[key] = {"objective": "Preserve " + ", ".join(acquired) + "; complete the exact target",
                              "rung": str(len(acquired) + 1), "action": aid, "expected_state": jsonable(item),
                              "branches": {o.label: o.state.key for o in outcomes}}
        plan = {"schema_version": 1, "dataset_id": engine.data.key, "starting_state": jsonable(start),
                "target": list(target), "entry": start.key, "nodes": nodes, "base_owned": base_owned}
        if keeper_policy:
            plan["keeper_policy"] = jsonable(keeper_policy)
        if settles:
            plan["acceptable_settles"] = settles
        if base_resource:
            plan["base_resource"] = base_resource
        try:
            economics = price_route(engine, plan, prices, valuation_at)
            signature = digest(replay(engine, plan).trace)
            if signature not in seen:
                candidates.append({"plan": plan, "economics": economics})
                seen.add(signature)
        except ForgeError as exc:
            if exc.code != "NO_SUCCESS_PATH":
                raise
        changes = {}
        for key in active:
            def score(pair):
                aid, outcomes = pair
                return (cost(aid) + sum((o.probability * values[index[o.state.key]] for o in outcomes if o.state.key in index), Fraction()),
                        Fraction(1) + sum((o.probability * steps[index[o.state.key]] for o in outcomes if o.state.key in index), Fraction()), aid)
            best = min(choices[key], key=score)
            if score(best)[:2] < (values[index[key]], steps[index[key]]):
                changes[key] = best
        if not changes:
            converged = True
            break
        selected.update(changes)
    candidates.sort(key=lambda c: (c["economics"]["expected_total_cost"], c["economics"]["failure_probability"]))
    status = "VALIDATED" if converged and candidates and not blocked else ("PARTIALLY_VALIDATED" if candidates else "BLOCKED")
    return {"status": status, "domain": engine.data.domain, "optimizer": "exact_policy_iteration",
            "iterations": iteration, "converged": converged, "search_states": len(states), "winning_states": len(winning),
            "valid_routes": len(candidates), "candidates": candidates, "winner": candidates[0] if status == "VALIDATED" else None,
            "blocked_actions": blocked, "rejected_actions": rejected,
            "optimality_scope": "Minimum expected spend, then expected actions, over loaded keeper-safe finite stationary policies. Budget-constrained candidates are not exhaustively optimized; settles are dead-end fallbacks."}


def analyze_target(engine, item, modifier_id):
    m = engine.modifier(modifier_id)
    methods = []
    for aid in sorted(engine.data.actions):
        try:
            outcomes = engine.transition(item, aid)
            probability = sum(o.probability for o in outcomes if modifier_id in o.state.mods)
            if probability:
                methods.append({"action": aid, "probability": probability})
        except ForgeError as exc:
            methods.append({"action": aid, **exc.report()})
    return {"modifier": jsonable(m), "current_state_methods": methods,
            "future": engine.future_conflicts(item, [modifier_id]),
            "placement": "Use plan-ladder for full-route ordering; current eligibility alone does not establish rational acquisition order."}
