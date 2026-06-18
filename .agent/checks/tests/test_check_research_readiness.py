from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "check_research_readiness.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("check_research_readiness", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readiness
SPEC.loader.exec_module(readiness)
import test_validate_task_approval as approval_helpers


def prepare(temp: Path) -> tuple[Path, Path, Path, str]:
    return approval_helpers.prepare(temp)


def check(repo: Path, run: Path, receipt: Path, digest: str) -> dict[str, object]:
    return readiness.check(repo, run, receipt, digest, readiness.load_policies())


class CheckResearchReadinessTest(unittest.TestCase):
    def test_repository_policy_is_exact_readiness_only_and_non_authorizing(self) -> None:
        policies = readiness.load_policies()

        self.assertEqual(readiness.EXPECTED_POLICY, policies["research_readiness"])
        self.assertEqual("readiness-only", policies["research_readiness"]["mode"])
        self.assertNotIn("codex", json.dumps(policies["research_readiness"]).lower())

    def test_valid_approval_makes_research_ready_without_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            result = check(repo, run, receipt, digest)

        self.assertTrue(result["ready"], result["failures"])
        self.assertTrue(result["declared_ready"])
        self.assertTrue(result["task_approval_valid"])
        for field in readiness.FALSE_FIELDS:
            self.assertFalse(result[field])

    def test_manually_approved_status_is_not_provenance_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, receipt, digest = prepare(temp)
            receipt.unlink()
            result = check(repo, run, receipt, digest)

        self.assertFalse(result["ready"])
        self.assertTrue(result["declared_ready"])
        self.assertFalse(result["task_approval_valid"])

    def test_invalid_receipt_and_declared_status_are_distinguished(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            wrong = check(repo, run, receipt, "0" * 64)
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "status: approved",
                    "status: awaiting_approval",
                ),
                encoding="utf-8",
            )
            unapproved = check(repo, run, receipt, digest)

        self.assertTrue(wrong["declared_ready"])
        self.assertFalse(wrong["task_approval_valid"])
        self.assertEqual("task_approval_provenance", wrong["failures"][0]["rule"])
        self.assertFalse(unapproved["declared_ready"])
        self.assertFalse(unapproved["task_approval_valid"])
        self.assertEqual(
            ["declared_readiness", "task_approval_provenance"],
            [item["rule"] for item in unapproved["failures"]],
        )

    def test_policy_bindings_and_receipt_drift_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["authorized"] = True
            receipt.write_text(json.dumps(value), encoding="utf-8")
            tampered = check(
                repo,
                run,
                receipt,
                readiness.validate_task_approval.sha256_bytes(receipt.read_bytes()),
            )

        self.assertFalse(tampered["ready"])
        self.assertFalse(tampered["task_approval_valid"])
        self.assertEqual("task_approval_provenance", tampered["failures"][0]["rule"])

    def test_readiness_control_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            original = readiness.initialize_portable_run.binding_records
            first = original(readiness.load_policies()["research_readiness"]["bindings"])
            second = json.loads(json.dumps(first))
            second[0]["sha256"] = "0" * 64

            with mock.patch.object(
                readiness.initialize_portable_run,
                "binding_records",
                side_effect=[first, second],
            ), mock.patch.object(
                readiness.check_stage_readiness,
                "check_readiness",
                return_value={
                    "ready": True,
                    "risk": "medium",
                    "directory": str(run),
                    "failures": [],
                },
            ), mock.patch.object(
                readiness.validate_task_approval,
                "validate",
                return_value={"valid": True, "failures": []},
            ):
                result = check(repo, run, receipt, digest)

        self.assertFalse(result["ready"])
        self.assertEqual("readiness_controls_changed", result["failures"][-1]["rule"])

    def test_real_cli_reports_ready_without_authorizing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = prepare(Path(temp_dir))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--run",
                    str(run),
                    "--approval-receipt",
                    str(receipt),
                    "--approval-receipt-sha256",
                    digest,
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["ready"])
        self.assertFalse(result["stage_start_authorized"])
        self.assertFalse(result["authorized"])

    def test_cli_refuses_policy_override(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--run",
                str(REPO_ROOT),
                "--approval-receipt",
                str(REPO_ROOT / "none.json"),
                "--approval-receipt-sha256",
                "0" * 64,
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
