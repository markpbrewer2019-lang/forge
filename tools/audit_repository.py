"""Scan exact staged blobs; report locations/categories, never matched credential text."""
import argparse
import json
from pathlib import Path
import re
import subprocess


PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "openai_key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "google_api_key": re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"),
    "credential_assignment": re.compile(r"(?i)(?:api[_-]?key|api[_-]?token|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"][A-Za-z0-9_+/=-]{16,}['\"]"),
    "url_credentials": re.compile(r"https?://[^\s/:]+:[^\s/@]+@"),
}


def scan_file(path, content):
    findings = []
    lower = path.lower().replace("\\", "/")
    name = lower.rsplit("/", 1)[-1]
    forbidden = (name == ".env" or (name.startswith(".env.") and name != ".env.example")
                 or name in {"credentials.json", "id_rsa", "id_ed25519"}
                 or name.endswith((".pem", ".key", ".p12", ".pfx"))
                 or any(part in {".aws", ".ssh", ".codex", "__pycache__", ".venv"} for part in lower.split("/")))
    if forbidden:
        findings.append({"path": path, "line": 0, "kind": "forbidden_filename"})
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return findings + [{"path": path, "line": 0, "kind": "unexpected_binary"}]
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in PATTERNS.items():
            if pattern.search(line):
                findings.append({"path": path, "line": number, "kind": kind})
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--git-executable", default="git")
    parser.add_argument("--output", default="reports/source-control-audit.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    def git(*arguments):
        return subprocess.check_output([args.git_executable, *arguments], cwd=root)
    files = [v.decode("utf-8") for v in git("ls-files", "--cached", "-z").split(b"\0") if v]
    findings = []
    for file in files:
        findings.extend(scan_file(file, git("show", ":" + file)))
    result = {"files_scanned": len(files), "findings": findings, "passed": bool(files) and not findings,
              "scope": "Exact Git index blobs; known credential patterns, secret filenames and unexpected binary data. No secret values are logged."}
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
