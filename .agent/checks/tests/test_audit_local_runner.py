from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "audit_local_runner.py"
REPO_ROOT = CHECKS_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location("audit_local_runner", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def successful_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
    arguments = command[1:]
    probe = next(
        item
        for item in audit.EXPECTED_POLICY["probes"]
        if Path(command[0]).name == item["command"][0]
        and arguments
        == [part.replace("{repo}", REPO_ROOT.as_posix()) for part in item["command"][1:]]
    )
    stdout = "\n".join(probe["markers"]).encode("utf-8")
    return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=b"")


def fake_which(command: str) -> str:
    return command


class AuditLocalRunnerTest(unittest.TestCase):
    def test_repository_policy_is_exact_metadata_only_and_non_invoking(self) -> None:
        policy = audit.load_policy()

        self.assertEqual("metadata-only", policy["mode"])
        self.assertEqual(audit.EXPECTED_POLICY, policy)
        self.assertNotIn(["codex", "exec"], [probe["command"] for probe in policy["probes"]])
        self.assertTrue(
            all(
                probe["command"][-1] in {"--version", "--help", "--porcelain", "--status"}
                for probe in policy["probes"]
            )
        )

    def test_successful_metadata_is_observed_but_enforcement_is_never_proven(self) -> None:
        result = audit.audit(REPO_ROOT, audit.load_policy(), fake_which, successful_runner)

        self.assertTrue(result["audit_complete"])
        self.assertTrue(
            all(
                item["assessment"] == "observed_metadata"
                for item in result["metadata_assessments"]
            )
        )
        self.assertTrue(
            all(
                item["assessment"] == "not_proven"
                for item in result["enforcement_assessments"]
            )
        )
        for field in audit.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_missing_command_and_raw_output_are_safely_summarized(self) -> None:
        secret = "SENSITIVE_OUTPUT_DO_NOT_RETURN_THIS_VALUE"

        def selective_which(command: str) -> str | None:
            return None if command == "podman" else command

        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
            return subprocess.CompletedProcess(command, 0, stdout=secret.encode(), stderr=b"")

        result = audit.audit(REPO_ROOT, audit.load_policy(), selective_which, runner)
        encoded = json.dumps(result)
        podman = next(item for item in result["probes"] if item["id"] == "podman_version")

        self.assertEqual("missing", podman["status"])
        self.assertNotIn(secret, encoded)
        self.assertNotIn(str(REPO_ROOT), encoded)
        podman_assessment = next(
            item for item in result["metadata_assessments"] if item["id"] == "podman_cli_metadata"
        )
        self.assertEqual("not_observed", podman_assessment["assessment"])

    def test_timeout_nonzero_error_and_output_limit_remain_non_authorizing(self) -> None:
        def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
            executable = Path(command[0]).name
            if executable == "codex":
                raise subprocess.TimeoutExpired(command, 5)
            if executable == "git":
                return subprocess.CompletedProcess(command, 2, stdout=b"", stderr=b"failed")
            if executable == "wsl":
                return subprocess.CompletedProcess(command, 0, stdout=b"x" * 120001, stderr=b"")
            raise OSError("unavailable")

        result = audit.audit(REPO_ROOT, audit.load_policy(), fake_which, runner)
        statuses = {item["id"]: item["status"] for item in result["probes"]}

        self.assertEqual("timeout", statuses["codex_version"])
        self.assertEqual("nonzero", statuses["git_version"])
        self.assertEqual("output_limit", statuses["wsl_status"])
        self.assertEqual("error", statuses["docker_version"])
        self.assertFalse(result["runner_selected"])
        self.assertFalse(result["agent_invocation_authorized"])

    def test_policy_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "policy.json"
            policy = json.loads(json.dumps(audit.EXPECTED_POLICY))
            policy["unproven_enforcement_controls"].remove("network_isolation")
            path.write_text(json.dumps(policy), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "metadata-only contract"):
                audit.load_policy(path)

    def test_cli_refuses_policy_override_before_running_probes(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--policy",
                "untrusted.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
