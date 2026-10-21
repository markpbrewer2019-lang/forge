"""Data-driven regression store: no executable code in case files."""
import json
from pathlib import Path

from .model import Dataset, digest, require, jsonable
from .engine import Engine
from .routes import validate_route


def check_case(case):
    require(all(key in case for key in ("name", "dataset", "plan", "expected", "invariant", "evidence")),
            "INVALID_REGRESSION_CASE", "Missing required case fields", "INVALID")
    actual = validate_route(Engine(Dataset.load(case["dataset"])), case["plan"])
    expected = case["expected"]
    passed = all(actual.get(key) == value for key, value in expected.items() if key != "node")
    if "node" in expected:
        passed = passed and (actual.get("location") or {}).get("node") == expected["node"]
    return {"name": case["name"], "passed": passed, "expected": expected, "actual": actual,
            "invariant": case["invariant"]}


def store_case(case, directory):
    report = check_case(case)
    require(report["passed"], "REGRESSION_EXPECTATION_MISMATCH", report, "INVALID")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (digest(case) + ".json")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(jsonable(case), stream, indent=2)
    return {"path": str(path.resolve()), "result": report}


def run_cases(directory):
    files = sorted(Path(directory).glob("*.json"))
    require(bool(files), "NO_REGRESSION_CASES", str(directory), "INVALID")
    reports = [check_case(json.loads(path.read_text(encoding="utf-8"))) for path in files]
    return {"status": "VALIDATED" if all(r["passed"] for r in reports) else "INVALID", "cases": reports}
