import importlib.util
from pathlib import Path
import unittest


class RepositoryAuditTests(unittest.TestCase):
    def scanner(self):
        path = Path(__file__).resolve().parents[1] / "tools/audit_repository.py"
        self.assertTrue(path.exists(), "Repository audit scanner is not implemented")
        spec = importlib.util.spec_from_file_location("forge_repository_audit", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.scan_file

    def test_detects_key_without_echoing_secret(self):
        secret = "gh" + "p_" + "A7b2C9d4E1f6G3h8I5j0K7l2M9n4O1p6Q3r8"
        findings = self.scanner()("config.py", ("api_token = '" + secret + "'").encode())
        self.assertTrue(findings)
        self.assertNotIn(secret, str(findings))

    def test_rejects_credential_file_even_with_unknown_format(self):
        findings = self.scanner()(".env", b"UNRELATED_SETTING=local")
        self.assertTrue(any(f["kind"] == "forbidden_filename" for f in findings))

    def test_normal_fixture_is_not_a_secret(self):
        self.assertEqual([], self.scanner()("examples/dataset.json", b'{"domain":"SYNTHETIC","weight":1}'))
