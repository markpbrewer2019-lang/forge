"""Join canonical replay, keeper constraints, exact risks, and player presentation."""
from fractions import Fraction

from .model import require, jsonable
from .keepers import KeeperPolicy
from .routes import replay
from .economics import price_route, solve


def event_probability(result, predicate):
    """Probability of encountering an edge event at least once before absorption."""
    keys = list(result.edges)
    index = {k: i for i, k in enumerate(keys)}
    matrix = [[Fraction(int(i == j)) for j in range(len(keys))] for i in range(len(keys))]
    rhs = [Fraction() for _ in keys]
    for key, outgoing in result.edges.items():
        for probability, destination, label in outgoing:
            if predicate(key, destination, label):
                rhs[index[key]] += probability
            elif destination in index:
                matrix[index[key]][index[destination]] -= probability
    values = solve(matrix, rhs)
    return values[index[result.start]] if result.start in index else Fraction()


def audit_ladder(engine, plan, prices, valuation_at=None):
    require("keeper_policy" in plan, "MISSING_KEEPER_POLICY", "Keeper intent must be explicit")
    policy = KeeperPolicy.load(plan["keeper_policy"])
    result = replay(engine, plan)
    economics = price_route(engine, plan, prices, valuation_at)
    target = set(plan["target"])
    transitions = []
    for row in result.trace:
        key = (row["node"], row["before"])
        destination = (row["next"], row["after"])
        before, after = result.states[key], result.states[destination]
        action = engine.action(row["action"])
        classification, lost = policy.classify(before, after, target, action, result.terminals.get(destination),
                                              removed=row.get('removed_during_action', ()))
        inspection = engine.inspect(before)
        keepers = policy.keepers(before, target) & set(before.mods)
        lifecycle = {r["modifier"]: r for r in policy.lifecycle or [] if r["modifier"] in before.mods}
        transitions.append({**row, "classification": classification, "before_state": jsonable(before),
            "after_state": jsonable(after), "action_name": action.display_name or action.id,
            "mechanic_context": action.mechanic_context or {}, "resources": action.resources,
            "current_keepers": sorted(keepers), "physical_locks": {"protected": before.protected, "fractured": before.fractured},
            "earned_rungs": len(set(before.mods) & target), "locked_rungs": len(keepers & target),
            "disposable_modifiers": sorted(mid for mid in set(before.mods) - keepers
                if mid not in lifecycle or lifecycle[mid]["role"] == "DISPOSABLE"),
            "modifier_lifecycle": lifecycle, "affix_capacity": inspection["open_slots"],
            "modifier_groups": {mid: engine.modifier(mid).group for mid in before.mods},
            "objective": plan["nodes"][row["node"]]["objective"], "keeper_loss": lost,
            "advance_condition": {"new_exact_targets": sorted((set(after.mods) - set(before.mods)) & target)},
            "failure_condition": classification in {"FALLBACK_ONE_RUNG", "RESTART"} or bool(lost),
            "recovery_transition": row["next"] if classification != "ADVANCE" else None,
            "restart_condition": classification == "RESTART"})
    restart_probability = event_probability(result, lambda key, dest, label: result.actions[key] in policy.restart_actions)
    removed_events = {(r['node'], r['before'], r['label']): set(r.get('removed_during_action', ())) for r in result.trace}
    keeper_loss_probability = event_probability(result, lambda key, dest, label:
        bool((policy.keepers(result.states[key], target) - set(result.states[dest].mods))
             | (policy.keepers(result.states[key], target) & removed_events.get((*key, label), set()))))
    initial_keeper_loss_probability = event_probability(result, lambda key, dest, label:
        bool((set(policy.initial) - set(result.states[dest].mods))
             | (set(policy.initial) & removed_events.get((*key, label), set()))))
    return {"status": "VALIDATED", "domain": engine.data.domain, "fingerprint": result.fingerprint,
            "transitions": transitions, "economics": economics,
            "risks": {"keeper_loss_probability": keeper_loss_probability,
                      "initial_keeper_loss_probability": initial_keeper_loss_probability,
                      "restart_probability": restart_probability},
            "provenance_rule": "Every transition binds mechanic, state and pool evidence. Mathematical probability arithmetic remains explicitly separate."}


def compile_golden6(engine, plan, prices, valuation_at=None):
    """Compile an already proven full route into target-progress objectives."""
    audit = audit_ladder(engine, plan, prices, valuation_at)
    require(len(plan["target"]) <= 6, "GOLDEN6_TARGET_LIMIT", "Explicit objective grouping is required above six targets")
    groups = {}
    for row in audit["transitions"]:
        action = engine.action(row["action"])
        if engine.data.domain == "POE2":
            require(bool(action.display_name), "MISSING_ACTION_NAME", action.id)
        name = action.display_name or "Synthetic action: " + action.id
        number = row["earned_rungs"] + 1
        require(number <= 6, "GOLDEN6_REQUIRES_OBJECTIVE_GROUPING", str(number))
        group = groups.setdefault(number, {"actions": {}, "gain": set(), "recovery": set(), "keepers": set(), "rows": []})
        group["rows"].append(row)
        group["actions"][action.id] = name
        group["gain"].update(row["advance_condition"]["new_exact_targets"])
        group["keepers"].update(row["current_keepers"])
        if row["classification"] == "RETRY_SAME_RUNG":
            group["recovery"].add(name)
    steps = []
    for number, group in sorted(groups.items()):
        names = list(group["actions"].values())
        objective = "Reach " + str(number) + " exact target modifiers while retaining earned keepers"
        all_present = set().union(*(set(r["before_state"]["mods"]) for r in group["rows"]))
        rules, sentences = [], []
        for aid, name in group["actions"].items():
            rows = [r for r in group["rows"] if r["action"] == aid]
            before_sets = [set(r["before_state"]["mods"]) for r in rows]
            required = set.intersection(*before_sets)
            forbidden = all_present - set.union(*before_sets)
            condition = "With " + (", ".join(sorted(required)) if required else "the validated entry item")
            if forbidden:
                condition += " and without " + ", ".join(sorted(forbidden))
            sentences.append(condition + ", use " + name + ".")
            outcomes = []
            seen = set()
            for row in rows:
                signature = (row["label"], row["classification"], row["next"])
                if signature in seen:
                    continue
                seen.add(signature)
                next_node = plan["nodes"][row["next"]]
                next_action_id = next_node.get("action")
                change = row["change"]
                if change["added"]:
                    trigger = "If " + ", ".join(change["added"]) + " is added"
                elif change["removed"]:
                    trigger = "If " + ", ".join(change["removed"]) + " is removed"
                else:
                    trigger = "On outcome " + row["label"]
                if row["classification"] == "ADVANCE":
                    instruction = "stop this objective immediately and advance; do not perform its miss recovery"
                    next_action_id = None  # Advance is a step boundary, never a recovery instruction.
                elif row["classification"] == "ACCEPT_SETTLE":
                    instruction = "stop at the explicitly accepted settle"
                elif row["classification"] == "RESTART":
                    instruction = "restart only under the declared restart condition"
                elif row["classification"] == "FALLBACK_ONE_RUNG":
                    instruction = "return to the previous objective under its validated entry condition"
                elif next_action_id:
                    next_action = engine.action(next_action_id)
                    next_name = next_action.display_name or "Synthetic action: " + next_action_id
                    instruction = "continue with " + next_name + " under its entry condition, then retry this objective"
                else:
                    instruction = "stop at the declared terminal"
                outcomes.append({"label": row["label"], "classification": row["classification"],
                                 "instruction": trigger + ", " + instruction + ".", "next_action_id": next_action_id})
                sentences.append(outcomes[-1]["instruction"])
            rules.append({"action_id": aid, "action_name": name,
                          "when": {"required_modifiers": sorted(required), "forbidden_modifiers": sorted(forbidden)},
                          "outcomes": outcomes})
        instructions = " ".join(sentences)
        steps.append({"step": len(steps) + 1, "objective": objective, "instructions": instructions,
                      "rules": rules,
                      "action_ids": list(group["actions"]), "actions": names,
                      "exact_modifiers_this_objective": sorted(group["gain"]),
                      "advance_when": {"exact_target_count_at_least": number},
                      "preserve": sorted(group["keepers"])})
    return {"status": "VALIDATED", "domain": engine.data.domain, "fingerprint": audit["fingerprint"],
            "steps": steps, "expected_spend": audit["economics"]["expected_total_cost"],
            "unit": prices.unit, "completion_probability": audit["economics"]["completion_probability"],
            "risks": audit["risks"], "synthetic_only": engine.data.domain == "SYNTHETIC",
            "details_available": "Full branch graph is retained in the validated ladder audit."}
