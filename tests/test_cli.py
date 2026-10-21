import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from forge.fixtures import universe, example_plans
from forge.model import dataset_document


class CliTests(unittest.TestCase):
    def invoke(self, command, request):
        return subprocess.run([sys.executable, "-m", "forge", command], input=json.dumps(request),
                              text=True, capture_output=True, check=False)

    def test_json_cli_success(self):
        data, _, start = universe()
        result = self.invoke("validate-route", {"dataset": dataset_document(data),
                             "plan": example_plans(data, start)["B-lower-total"]})
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("VALIDATED", json.loads(result.stdout)["status"])

    def test_json_cli_blocked(self):
        data, _, start = universe()
        data.pools = ()
        result = self.invoke("eligible-mods", {"dataset": dataset_document(data), "item": {
                             "base": start.base, "ilvl": start.ilvl, "rarity": start.rarity}, "action": "roll-prefix"})
        self.assertEqual(2, result.returncode)
        self.assertEqual("INSUFFICIENT_VERIFIED_DATA", json.loads(result.stdout)["code"])

    def test_malformed_input_is_json_error(self):
        result = self.invoke("validate-route", {})
        self.assertEqual(2, result.returncode)
        self.assertEqual("MALFORMED_INPUT", json.loads(result.stdout)["code"])


if __name__ == "__main__":
    unittest.main()
