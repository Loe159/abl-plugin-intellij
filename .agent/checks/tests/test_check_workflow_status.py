from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "check_workflow_status.py"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("check_workflow_status", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
status = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = status
SPEC.loader.exec_module(status)


def unready_runner(repo: Path, policy: dict[str, object]) -> dict[str, object]:
    return {
        "assessment_complete": True,
        "controls_ready": False,
        **{field: False for field in status.assess_runner_readiness.FALSE_FIELDS},
    }


def ready_runner(repo: Path, policy: dict[str, object]) -> dict[str, object]:
    result = unready_runner(repo, policy)
    result["controls_ready"] = True
    return result


class CheckWorkflowStatusTest(unittest.TestCase):
    def test_policy_is_exact_status_only_and_non_authorizing(self) -> None:
        policy = status.load_policy()
        self.assertEqual(status.EXPECTED_POLICY, policy)
        self.assertEqual("status-only", policy["mode"])
        self.assertTrue(all(item["required_for_pilot"] for item in policy["capabilities"]))

    def test_current_status_is_incomplete_and_names_missing_capabilities(self) -> None:
        result = status.check_status(REPO_ROOT, status.load_policy(), unready_runner)

        self.assertFalse(result["pilot_ready"])
        self.assertFalse(result["runner_controls_ready"])
        self.assertIn("enforced_implementation_runner", result["missing_required_capabilities"])
        self.assertIn("historical_golden_set", result["missing_required_capabilities"])
        self.assertIn("multi_adapter_comparison", result["missing_required_capabilities"])
        self.assertNotIn(
            "approved_github_issue_ingestion",
            result["missing_required_capabilities"],
        )
        self.assertNotIn("run_metrics", result["missing_required_capabilities"])
        self.assertNotIn(
            "explicit_session_start_authorization",
            result["missing_required_capabilities"],
        )
        start_authorization = next(
            item
            for item in result["capabilities"]
            if item["id"] == "explicit_session_start_authorization"
        )
        implementation = next(
            item
            for item in result["capabilities"]
            if item["id"] == "supervised_implementation_contract"
        )
        self.assertEqual(
            "post_consumption_readiness_only",
            implementation["status"],
        )
        self.assertIn(
            ".agent/checks/check_implementation_launch_readiness.py",
            implementation["evidence"],
        )
        self.assertEqual(
            "validated_exclusive_local_consumption",
            start_authorization["status"],
        )
        self.assertIn(
            ".agent/checks/consume_implementation_session_start_authorization.py",
            start_authorization["evidence"],
        )
        self.assertIn(
            ".agent/checks/validate_implementation_session_start_consumption.py",
            start_authorization["evidence"],
        )
        self.assertTrue(start_authorization["implemented"])
        metrics = next(
            item for item in result["capabilities"] if item["id"] == "run_metrics"
        )
        self.assertEqual("manual_evidence_recording_only", metrics["status"])
        self.assertTrue(metrics["implemented"])
        publication = next(
            item
            for item in result["capabilities"]
            if item["id"] == "deterministic_draft_pr_publisher"
        )
        self.assertEqual("local_preflight_only", publication["status"])
        self.assertFalse(publication["implemented"])
        self.assertIn(
            ".agent/checks/check_draft_pr_publication_readiness.py",
            publication["evidence"],
        )
        golden_set = next(
            item for item in result["capabilities"] if item["id"] == "historical_golden_set"
        )
        self.assertEqual("local_preflight_only", golden_set["status"])
        self.assertFalse(golden_set["implemented"])
        self.assertIn(
            ".agent/checks/check_historical_golden_set_readiness.py",
            golden_set["evidence"],
        )
        comparison = next(
            item
            for item in result["capabilities"]
            if item["id"] == "multi_adapter_comparison"
        )
        self.assertEqual("local_preflight_only", comparison["status"])
        self.assertFalse(comparison["implemented"])
        self.assertIn(
            ".agent/checks/check_multi_adapter_comparison_readiness.py",
            comparison["evidence"],
        )
        ingestion = next(
            item
            for item in result["capabilities"]
            if item["id"] == "approved_github_issue_ingestion"
        )
        self.assertEqual("manual_snapshot_approval_only", ingestion["status"])
        self.assertTrue(ingestion["implemented"])
        for field in status.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(result[field])

    def test_ready_runner_alone_does_not_make_pilot_ready(self) -> None:
        result = status.check_status(REPO_ROOT, status.load_policy(), ready_runner)
        runner = next(
            item for item in result["capabilities"] if item["id"] == "enforced_implementation_runner"
        )

        self.assertTrue(result["runner_controls_ready"])
        self.assertTrue(runner["implemented"])
        self.assertEqual("controls_ready_not_authorized", runner["status"])
        self.assertFalse(result["pilot_ready"])
        self.assertNotIn("enforced_implementation_runner", result["missing_required_capabilities"])
        self.assertNotIn(
            "explicit_session_start_authorization",
            result["missing_required_capabilities"],
        )

    def test_cli_refuses_policy_override(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--workflow-status-policy",
                "untrusted",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
