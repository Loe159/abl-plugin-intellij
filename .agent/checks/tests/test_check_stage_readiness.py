from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "check_stage_readiness.py"
REPO_ROOT = CHECKS_DIR.parents[1]
TEMPLATES = REPO_ROOT / ".agent" / "templates"
ARTIFACT_CONTRACT_PATH = REPO_ROOT / ".agent" / "policies" / "artifact-contract.json"
READINESS_POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "stage-readiness.json"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("check_stage_readiness", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readiness
SPEC.loader.exec_module(readiness)


def create_run(destination: Path, risk: str = "low") -> None:
    shutil.copytree(TEMPLATES, destination)
    replacements = {
        "{{issue}}": "123",
        "{{base_commit}}": "a" * 40,
        "{{risk}}": risk,
    }
    for path in destination.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"\{\{[a-z0-9_]+\}\}", "Concrete recorded evidence.", text)
        if path.name == "task.md":
            text = text.replace("status: awaiting_approval", "status: approved")
        if path.name == "research.md":
            text = text.replace("status: pending", "status: complete")
        path.write_text(text, encoding="utf-8")


def set_status(run: Path, artifact: str, old: str, new: str) -> None:
    path = run / artifact
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(f"status: {old}", f"status: {new}", 1), encoding="utf-8")


class StageReadinessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = readiness.validate_artifacts.load_contract(ARTIFACT_CONTRACT_PATH)
        self.policy = readiness.load_readiness_policy(READINESS_POLICY_PATH, self.contract)

    def check(self, run: Path, stage: str) -> dict[str, object]:
        return readiness.check_readiness(run, stage, self.contract, self.policy)

    def test_repository_policy_is_valid(self) -> None:
        self.assertEqual(
            [
                "compact-progress",
                "complete",
                "implement",
                "plan",
                "research",
                "review",
                "verify",
            ],
            sorted(self.policy["stages"]),
        )

    def test_research_is_ready_from_approved_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run)
            result = self.check(run, "research")

        self.assertTrue(result["ready"], result["failures"])
        self.assertFalse(result["authorized"])

    def test_filled_templates_are_not_ready_without_declared_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            shutil.copytree(TEMPLATES, run)
            for path in run.glob("*.md"):
                text = path.read_text(encoding="utf-8")
                text = text.replace("{{issue}}", "123")
                text = text.replace("{{base_commit}}", "a" * 40)
                text = text.replace("{{risk}}", "low")
                text = re.sub(r"\{\{[a-z0-9_]+\}\}", "Concrete recorded evidence.", text)
                path.write_text(text, encoding="utf-8")
            result = self.check(run, "research")

        self.assertFalse(result["ready"])
        self.assertEqual("required_status", result["failures"][0]["rule"])

    def test_low_risk_plan_and_implement_allow_pending_research(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run, "low")
            set_status(run, "research.md", "complete", "pending")
            plan = self.check(run, "plan")
            implement = self.check(run, "implement")

        self.assertTrue(plan["ready"], plan["failures"])
        self.assertTrue(implement["ready"], implement["failures"])

    def test_medium_plan_requires_completed_research(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run, "medium")
            set_status(run, "research.md", "complete", "blocked")
            blocked = self.check(run, "plan")
            set_status(run, "research.md", "blocked", "complete")
            ready = self.check(run, "plan")

        self.assertFalse(blocked["ready"])
        self.assertTrue(ready["ready"], ready["failures"])

    def test_medium_implement_requires_approved_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run, "medium")
            awaiting = self.check(run, "implement")
            set_status(run, "plan.md", "awaiting_approval", "approved")
            approved = self.check(run, "implement")

        self.assertFalse(awaiting["ready"])
        self.assertTrue(approved["ready"], approved["failures"])

    def test_any_blocked_artifact_stops_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run)
            set_status(run, "verification.md", "pending", "blocked")
            result = self.check(run, "research")

        self.assertFalse(result["ready"])
        self.assertEqual(["verification.md"], result["failures"][0]["artifacts"])

    def test_verify_and_complete_require_declared_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run)
            verify_before = self.check(run, "verify")
            set_status(run, "progress.md", "not_started", "complete")
            verify_after = self.check(run, "verify")
            complete_before = self.check(run, "complete")
            set_status(run, "verification.md", "pending", "passed")
            complete_after = self.check(run, "complete")

        self.assertFalse(verify_before["ready"])
        self.assertTrue(verify_after["ready"], verify_after["failures"])
        self.assertFalse(complete_before["ready"])
        self.assertTrue(complete_after["ready"], complete_after["failures"])

    def test_compact_progress_and_review_have_declared_prerequisites(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run, "medium")
            compact = self.check(run, "compact-progress")
            review_before = self.check(run, "review")
            set_status(run, "plan.md", "awaiting_approval", "approved")
            set_status(run, "verification.md", "pending", "failed")
            review_after = self.check(run, "review")

        self.assertTrue(compact["ready"], compact["failures"])
        self.assertFalse(review_before["ready"])
        self.assertTrue(review_after["ready"], review_after["failures"])

    def test_invalid_artifact_contract_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run)
            (run / "task.md").unlink()
            result = self.check(run, "research")

        self.assertFalse(result["artifact_contract_valid"])
        self.assertEqual("artifact_contract", result["failures"][0]["rule"])

    def test_policy_rejects_unknown_artifact_and_invalid_status(self) -> None:
        for artifact, statuses in (("unknown.md", ["approved"]), ("task.md", ["invented"])):
            with self.subTest(artifact=artifact, statuses=statuses):
                policy = json.loads(READINESS_POLICY_PATH.read_text(encoding="utf-8"))
                policy["stages"]["research"]["low"] = {artifact: statuses}
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = Path(temp_dir) / "policy.json"
                    path.write_text(json.dumps(policy), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        readiness.load_readiness_policy(path, self.contract)

    def test_cli_exit_codes_and_unknown_stage(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run, "medium")
            not_ready = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--run", str(run), "--stage", "implement"],
                check=False,
                capture_output=True,
                text=True,
            )
            set_status(run, "plan.md", "awaiting_approval", "approved")
            ready = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--run",
                    str(run),
                    "--stage",
                    "implement",
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            unknown = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--run", str(run), "--stage", "publish"],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(2, not_ready.returncode)
        self.assertEqual(0, ready.returncode, ready.stderr)
        self.assertTrue(json.loads(ready.stdout)["ready"])
        self.assertEqual(1, unknown.returncode)


if __name__ == "__main__":
    unittest.main()
