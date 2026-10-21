"""Fresh offline suite plus six-mod end-to-end proof; generated evidence stays in reports/."""
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forge.cli import dispatch
from forge.model import dataset_document, jsonable
from tests.keeper_fixture import six_mod_universe


def main():
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    started = time.monotonic()
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (reports / "tests.log").write_text(stream.getvalue(), encoding="utf-8")
    summary = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "success": result.wasSuccessful(), "elapsed_seconds": round(time.monotonic() - started, 3)}
    if result.wasSuccessful():
        data, prices, start, targets = six_mod_universe()
        request = {"dataset": dataset_document(data), "prices": jsonable(prices), "item": jsonable(start),
                   "target": [{"modifier": mid, "tier": 1} for mid in targets],
                   "options": {"base_resource": "base", "simulation_trials": 20000, "seed": 42}}
        proof = dispatch("build-craft", request)
        assert proof["status"] == "VALIDATED"
        for name, value in (("keeper-request.json", request), ("keeper-pipeline.json", proof), ("golden6.json", proof["golden6"])):
            (reports / name).write_text(json.dumps(jsonable(value), indent=2), encoding="utf-8")
        summary["six_mod_proof"] = {"domain": proof["domain"], "status": proof["status"],
            "expected_cost": str(proof["economic_summary"]["expected_spend_until_terminal"]),
            "keeper_loss_probability": str(proof["ladder"]["risks"]["keeper_loss_probability"]),
            "golden6_steps": len(proof["golden6"]["steps"]), "simulation_mean": proof["simulation"]["mean_spend"],
            "simulation_disagreement": proof["simulation"]["analytical_disagreement"]}
        # A durable source checkpoint independent of absent Git metadata.
        summary["source_sha256"] = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in ("forge", "tests", "schemas", "tools") for p in sorted((ROOT / directory).rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".py", ".json"}}
    (reports / "verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "source_sha256"}, indent=2))
    if not result.wasSuccessful():
        print(stream.getvalue()[-10000:])
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
