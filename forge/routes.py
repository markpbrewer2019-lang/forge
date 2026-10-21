"""Branch-complete route replay. Expected states are assertions, never assignments."""
from collections import deque
from dataclasses import dataclass
from fractions import Fraction

from .model import ForgeError, Item, require, digest, rational
from .engine import explain


@dataclass
class Replay:
    start: tuple
    states: dict
    edges: dict
    terminals: dict
    actions: dict
    trace: list
    fingerprint: str


def target_matches(item, target):
    # Exact targets are modifier IDs (tiers belong to immutable modifier records).
    return set(item.mods) == set(target)


def replay(engine, plan, max_states=1000):
    require(plan.get("schema_version") == 1, "UNSUPPORTED_PLAN_SCHEMA", "Expected schema_version=1", "INVALID")
    require(set(plan) <= {"schema_version", "dataset_id", "starting_state", "target", "target_rarity",
                        "entry", "nodes", "base_resource", "base_owned", "claimed_total_cost", "keeper_policy",
                        "acceptable_settles"},
            "UNKNOWN_PLAN_FIELD", str(sorted(set(plan))), "INVALID")
    require(plan.get("dataset_id") == engine.data.key, "DATASET_MISMATCH", "Plan must pin the complete dataset hash")
    start = Item.load(plan["starting_state"])
    engine.inspect(start)
    target = plan["target"]
    from .keepers import KeeperPolicy
    policy = KeeperPolicy.load(plan["keeper_policy"]) if "keeper_policy" in plan else None
    if policy:
        policy.validate_start(start, target)
    require(len(target) == len(set(target)) and bool(target), "INVALID_TARGET", str(target), "INVALID")
    for mid in target:
        engine.modifier(mid)
    # Reject an intrinsically impossible final item before exploring its route.
    engine.inspect(Item(start.base, start.ilvl, plan.get("target_rarity", start.rarity),
                        start.quality, tuple(target)))
    nodes = plan["nodes"]
    require(plan["entry"] in nodes, "MISSING_NODE", plan["entry"], "INVALID")
    initial = (plan["entry"], start.key)
    queue = deque([(plan["entry"], start, None)])
    states, edges, terminals, actions, trace = {}, {}, {}, {}, []
    while queue:
        node_id, item, origin = queue.popleft()
        key = (node_id, item.key)
        if key in states:
            continue
        require(len(states) < max_states, "STATE_LIMIT", "Replay incomplete; raise explicit bound")
        states[key] = item
        try:
            require(node_id in nodes, "MISSING_NODE", node_id, "INVALID")
            node = nodes[node_id]
            require(set(node) <= {"objective", "objective_mods", "rung", "action", "branches", "terminal",
                                 "expected_state", "claimed_probabilities", "settle_reason"},
                    "UNKNOWN_NODE_FIELD", node_id, "INVALID")
            require(("terminal" in node) != ("action" in node), "AMBIGUOUS_NODE",
                    "Exactly one of action or terminal required", "INVALID")
            require(bool(node.get("objective")), "MISSING_OBJECTIVE", node_id, "INVALID")
            if "expected_state" in node:
                expected = Item.load(node["expected_state"])
                require(item == expected, "EXPECTED_STATE_MISMATCH",
                        {"actual": item.key, "expected": expected.key, "origin": origin}, "INVALID")
            if "terminal" in node:
                terminal = node["terminal"]
                require(terminal in {"success", "failure", "settle"}, "INVALID_TERMINAL", terminal, "INVALID")
                if terminal == "success":
                    require(target_matches(item, target), "FINAL_TARGET_MISMATCH", node_id, "INVALID")
                    require(item.rarity == plan.get("target_rarity", start.rarity), "FINAL_RARITY_MISMATCH", node_id, "INVALID")
                if terminal == "settle":
                    require(bool(node.get("settle_reason")), "UNJUSTIFIED_SETTLE", node_id, "INVALID")
                    if policy:
                        require(any(set(s["required_modifiers"]) <= set(item.mods) for s in plan.get("acceptable_settles", [])),
                                "UNAPPROVED_SETTLE", node_id, "INVALID")
                terminals[key] = terminal
                continue
            outcomes = engine.transition(item, node["action"])
            labels = {o.label for o in outcomes}
            branches = node.get("branches", {})
            require(set(branches) == labels, "INCOMPLETE_OR_FAKE_BRANCHES",
                    {"actual": sorted(labels), "declared": sorted(branches)}, "INVALID")
            if "claimed_probabilities" in node:
                claims = node["claimed_probabilities"]
                require(set(claims) == labels and all(rational(claims[o.label]) == o.probability for o in outcomes),
                        "FALSE_CLAIMED_PROBABILITY", node_id, "INVALID")
            actions[key] = node["action"]
            edges[key] = []
            for outcome in outcomes:
                next_id = branches[outcome.label]
                dest = (next_id, outcome.state.key)
                classification, keeper_loss = (None, [])
                if policy:
                    classification, keeper_loss = policy.classify(item, outcome.state, target, engine.action(node["action"]),
                                                                 nodes.get(next_id, {}).get("terminal"))
                edges[key].append((outcome.probability, dest, outcome.label))
                trace.append({"node": node_id, "rung": node.get("rung"), "action": node["action"],
                              "before": item.key, "after": outcome.state.key, "label": outcome.label,
                              "probability": outcome.probability, "next": next_id,
                              "classification": classification, "keeper_loss": keeper_loss,
                              "provenance": engine.transition_provenance(item, node["action"]),
                              "change": explain(item, outcome.state, engine),
                              "future": engine.future_conflicts(outcome.state, target)})
                queue.append((next_id, outcome.state, {"node": node_id, "action": node["action"], "outcome": outcome.label}))
        except ForgeError as exc:
            exc.location = {"node": node_id, "rung": nodes.get(node_id, {}).get("rung"),
                            "actual_state": item.key, "origin": origin}
            raise
    # Every reachable branch must be capable of reaching a declared terminal.
    can_finish = set(terminals)
    while True:
        expanded = can_finish | {k for k, outgoing in edges.items() if any(d in can_finish for _, d, _ in outgoing)}
        if expanded == can_finish:
            break
        can_finish = expanded
    require(set(states) <= can_finish, "NONTERMINATING_RECOVERY", "Reachable closed cycle has no terminal", "INVALID")
    require(any(t == "success" for t in terminals.values()), "NO_SUCCESS_PATH", "Target never reached", "INVALID")
    if policy and not policy.lock_on_acquire:
        # Bound regression from the highest earned rung along any reachable history, not just one edge.
        peaks = {initial: len(set(start.mods) & set(target))}
        changed = True
        while changed:
            changed = False
            for key, outgoing in edges.items():
                if key not in peaks:
                    continue
                for _, dest, _ in outgoing:
                    level = len(set(states[dest].mods) & set(target))
                    restart = actions[key] in policy.restart_actions
                    require(restart or level >= peaks[key] - policy.max_fallback_rungs,
                            "UNCONTROLLED_REGRESSION", {"node": key[0], "peak": peaks[key], "level": level}, "INVALID")
                    peak = level if restart else max(peaks[key], level)
                    if peak > peaks.get(dest, -1):
                        peaks[dest] = peak
                        changed = True
    return Replay(initial, states, edges, terminals, actions, trace, digest({"plan": plan, "data": engine.data.key}))


def validate_route(engine, plan):
    try:
        result = replay(engine, plan)
        return {"status": "VALIDATED", "scope": "MECHANICS", "domain": engine.data.domain,
                "fingerprint": result.fingerprint, "reachable_states": len(result.states),
                "branches": len(result.trace), "terminal_types": sorted(set(result.terminals.values()))}
    except ForgeError as exc:
        return exc.report()


def golden6(engine, plan, prices):
    # Recompute all barriers instead of accepting a caller-supplied status string.
    from .economics import price_route
    result = replay(engine, plan)
    economics = price_route(engine, plan, prices)
    require(economics["completion_probability"] > 0, "NO_SUCCESS_PATH", "No completion")
    rungs = {}
    reachable_nodes = {key[0] for key in result.actions}
    for node_id, node in plan["nodes"].items():
        if node_id not in reachable_nodes:
            continue
        if "action" in node:
            require(bool(node.get("rung")), "MISSING_RUNG", node_id, "INVALID")
            rungs.setdefault(node["rung"], []).append({"node": node_id, "objective": node["objective"],
                                                      "action": node["action"], "branches": node["branches"]})
    require(len(rungs) <= 6, "GOLDEN6_REQUIRES_OBJECTIVE_GROUPING", "Cannot omit required actions")
    return {"status": "VALIDATED", "domain": engine.data.domain, "steps": rungs, "economics": economics,
            "note": "Developer representation; branches preserved. Synthetic output is never a PoE2 recipe."}
