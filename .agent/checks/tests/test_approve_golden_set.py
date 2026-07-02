from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


CHECKS_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "approve_golden_set.py"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(TESTS_DIR))
SPEC = importlib.util.spec_from_file_location("approve_golden_set", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
adopter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = adopter
SPEC.loader.exec_module(adopter)

import test_assess_golden_set_readiness as golden_fixtures  # noqa: E402


class ApproveGoldenSetTest(unittest.TestCase):
    def test_policy_is_exact_local_adoption_only(self) -> None:
        policy = adopter.load_policy()

        self.assertEqual(adopter.EXPECTED_POLICY, policy)
        self.assertEqual("exact-local-adoption-only", policy["mode"])
        self.assertTrue(policy["require_candidate_manifest_valid"])
        self.assertTrue(policy["require_issue_reference_equivalence_reviewed"])

    def test_check_and_adopt_write_non_authorizing_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            repo, manifest, _value = golden_fixtures.prepare(parent)
            receipt = parent / "golden-set-adoption.json"
            policy = adopter.load_policy()

            checked = adopter.assess_adoption(repo, manifest, receipt, policy)
            self.assertTrue(checked["adoptable"], checked["failures"])
            self.assertIn("ADOPT-HISTORICAL-GOLDEN-SET", checked["required_confirmation"])

            args = SimpleNamespace(
                repo=repo,
                manifest=manifest,
                receipt=receipt,
                approver="human-reviewer",
                confirm=checked["required_confirmation"],
                source_state_authenticated=True,
                issue_closure_independently_verified=True,
                issue_reference_equivalence_reviewed=True,
            )
            adopted = adopter.adopt(args, policy, checked)

            self.assertTrue(adopted["golden_set_adopted"])
            self.assertTrue(adopted["receipt_written"])
            self.assertTrue(receipt.is_file())
            value = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertTrue(value["golden_set_adopted"])
            self.assertTrue(value["candidate_manifest_valid"])
            self.assertTrue(value["source_state_authenticated"])
            self.assertTrue(value["issue_closure_independently_verified"])
            self.assertTrue(value["issue_reference_equivalence_reviewed"])
            self.assertEqual(5, value["case_count"])
            self.assertNotIn("task", value["case_summaries"][0])
            for field in adopter.FALSE_FIELDS:
                self.assertFalse(value[field])

    def test_missing_attestation_or_cli_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            parent = Path(temp_dir)
            repo, manifest, _value = golden_fixtures.prepare(parent)
            receipt = parent / "golden-set-adoption.json"
            policy = adopter.load_policy()
            checked = adopter.assess_adoption(repo, manifest, receipt, policy)
            args = SimpleNamespace(
                repo=repo,
                manifest=manifest,
                receipt=receipt,
                approver="human-reviewer",
                confirm=checked["required_confirmation"],
                source_state_authenticated=True,
                issue_closure_independently_verified=False,
                issue_reference_equivalence_reviewed=True,
            )

            result = adopter.adopt(args, policy, checked)
            self.assertFalse(result["golden_set_adopted"])
            self.assertFalse(receipt.exists())
            self.assertEqual("manual_attestations", result["failures"][0]["rule"])

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "check",
                "--repo",
                str(REPO_ROOT),
                "--manifest",
                "candidate.json",
                "--receipt",
                "receipt.json",
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
