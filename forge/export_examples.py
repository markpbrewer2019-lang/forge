"""Regenerate synthetic request files and persisted regression cases."""
import copy
import json
from pathlib import Path

from .fixtures import universe, example_plans
from .model import dataset_document, jsonable
from .regressions import store_case


def export(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    data, prices, start = universe()
    plans = example_plans(data, start)
    shared = {"dataset": dataset_document(data), "prices": jsonable(prices), "options": {"valuation_at": prices.as_of}}
    def write(name, value):
        (destination / name).write_text(json.dumps(jsonable(value), indent=2), encoding="utf-8")
    write("dataset.json", shared["dataset"])
    write("prices.json", shared["prices"])
    write("inspect.json", {"dataset": shared["dataset"], "item": start})
    write("pool.json", {"dataset": shared["dataset"], "item": start, "action": "roll-prefix"})
    write("plan.json", {**shared, "item": start, "target": ["power", "speed"],
                        "options": {"base_resource": "base", "valuation_at": prices.as_of}})
    write("compare.json", {**shared, "plans": plans})
    write("route.json", {**shared, "plan": plans["C-recovery-loop"]})
    failures = []
    for name, node, mutation, code in [
        ("fake recovery", "recover", {"action": "power-after-speed"}, "NO_OPEN_PREFIX"),
        ("missing mechanic", "recover", {"action": "made-up-orb"}, "UNVERIFIED_MECHANIC"),
        ("false probability", "roll", {"claimed_probabilities": {"power": "9/10", "junk": "1/10"}}, "FALSE_CLAIMED_PROBABILITY"),
        ("forgotten miss", "roll", {"branches": {"power": "done"}}, "INCOMPLETE_OR_FAKE_BRANCHES"),
        ("wrong final state", "roll", {"branches": {"power": "done", "junk": "done"}}, "FINAL_TARGET_MISMATCH")]:
        plan = copy.deepcopy(plans["C-recovery-loop"])
        plan["nodes"][node].update(mutation)
        case = {"name": name, "dataset": shared["dataset"], "plan": plan,
                "expected": {"status": "BLOCKED" if code == "UNVERIFIED_MECHANIC" else "INVALID", "code": code},
                "invariant": name + " must be rejected using the actual intermediate state",
                "evidence": "Synthetic adversarial regression; not a real PoE2 experiment."}
        failures.append(store_case(case, destination / "regressions"))
    return failures


if __name__ == "__main__":
    export("examples")
