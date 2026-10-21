"""Generate invalid plans from any mechanically validated baseline."""
from copy import deepcopy

from .model import dataset_document
from .routes import replay, validate_route


def adversarial_test(engine, plan):
    replay(engine, plan)
    action_nodes = [k for k, n in plan["nodes"].items() if "action" in n]
    mutations = []
    for node_id in action_nodes:
        node = plan["nodes"][node_id]
        mutations += [
            ("unsupported mechanic", node_id, {"action": "forge:deliberately-unsupported"}),
            ("missing outcomes", node_id, {"branches": {}}),
            ("false probability", node_id, {"claimed_probabilities": {label: "0" for label in node["branches"]}}),
            ("invented expected state", node_id, {"expected_state": {**plan["starting_state"], "quality": -1}}),
            ("ambiguous success", node_id, {"terminal": "success"}),
        ]
    reports = []
    for name, node_id, modification in mutations:
        broken = deepcopy(plan)
        broken["nodes"][node_id].update(modification)
        actual = validate_route(engine, broken)
        # Unreachable nodes are not hypotheses about execution and are deliberately skipped.
        reachable = {key[0] for key in replay(engine, plan).states}
        if node_id not in reachable:
            continue
        reports.append({"mutation": name, "node": node_id, "rejected": actual["status"] in {"INVALID", "BLOCKED"},
                        "actual": actual, "regression_case": {"name": name, "dataset": dataset_document(engine.data),
                        "plan": broken, "expected": {"status": actual["status"] if actual["status"] in {"INVALID", "BLOCKED"} else "INVALID",
                        **({"code": actual["code"]} if "code" in actual else {})},
                        "invariant": name + " must not validate", "evidence": "Automatically generated adversarial mutation"}})
    return {"status": "VALIDATED" if all(r["rejected"] for r in reports) else "INVALID",
            "generated": len(reports), "rejected": sum(r["rejected"] for r in reports), "results": reports}
