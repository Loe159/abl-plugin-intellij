from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_stage_application.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("validate_stage_application", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validation
SPEC.loader.exec_module(validation)
import test_apply_stage_output as application_helpers


def apply_stage(temp: Path, stage: str = "research") -> tuple[Path, Path, Path, str]:
    repo, run, bundle, digest, response = application_helpers.prepare(temp, stage)
    checked = json.loads(
        application_helpers.cli("check", repo, run, bundle, digest, response).stdout
    )
    completed = application_helpers.cli(
        "apply",
        repo,
        run,
        bundle,
        digest,
        response,
        "--reviewer",
        "local-operator",
        "--confirm",
        checked["required_confirmation"],
    )
    assert completed.returncode == 0, completed.stderr
    receipt = run.parent / "application-receipt.json"
    applied = json.loads(completed.stdout)
    return repo, run, receipt, applied["application_receipt_sha256"]


def check(repo: Path, run: Path, receipt: Path, digest: str) -> dict[str, object]:
    return validation.validate(repo, run, receipt, digest, validation.load_policies())


def snapshot(run: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in run.glob("*.md")}


class ValidateStageApplicationTest(unittest.TestCase):
    def test_repository_policy_is_exact_validation_only_and_non_authorizing(self) -> None:
        policies = validation.load_policies()

        self.assertEqual(validation.EXPECTED_POLICY, policies["application_validation"])
        self.assertEqual("validation-only", policies["application_validation"]["mode"])
        self.assertEqual(2, policies["application"]["version"])
        self.assertNotIn("codex", json.dumps(policies["application_validation"]).lower())

    def test_valid_research_and_plan_receipts_are_accepted_without_authorization(self) -> None:
        for stage, artifact, status in [
            ("research", "research.md", "complete"),
            ("plan", "plan.md", "awaiting_approval"),
        ]:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temp_dir:
                repo, run, receipt, digest = apply_stage(Path(temp_dir), stage)

                result = check(repo, run, receipt, digest)

                self.assertTrue(result["valid"], result["failures"])
                self.assertTrue(result["response_applied"])
                self.assertTrue(result["copy_confirmed"])
                self.assertFalse(result["authorized"])
                self.assertFalse(result["stage_authorized"])
                self.assertEqual(artifact, result["artifact"])
                self.assertEqual(status, result["status"])

    def test_wrong_digest_rejects_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, _digest = apply_stage(Path(temp_dir))
            receipt.write_text("not json", encoding="utf-8")

            result = check(repo, run, receipt, "0" * 64)

        self.assertFalse(result["valid"])
        self.assertEqual("receipt_sha256", result["failures"][0]["rule"])

    def test_tampered_metadata_identity_confirmation_and_bindings_are_rejected(self) -> None:
        cases = [
            ("receipt_metadata", lambda value: value.update(authorized=True)),
            ("receipt_identity", lambda value: value.update(application_receipt="elsewhere.json")),
            ("application_mismatch", lambda value: value.update(confirmation_sha256="0" * 64)),
            ("trusted_binding_mismatch", lambda value: value["bindings"][0].update(sha256="0" * 64)),
        ]
        for expected, mutate in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                repo, run, receipt, _digest = apply_stage(Path(temp_dir))
                value = json.loads(receipt.read_text(encoding="utf-8"))
                mutate(value)
                receipt.write_text(json.dumps(value), encoding="utf-8")
                digest = validation.apply_stage_output.sha256_bytes(receipt.read_bytes())

                result = check(repo, run, receipt, digest)

                self.assertFalse(result["valid"])
                self.assertIn(expected, [item["rule"] for item in result["failures"]])

    def test_run_repository_and_secret_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = apply_stage(Path(temp_dir))
            target = run / "research.md"
            target.write_text(
                target.read_text(encoding="utf-8").replace(
                    "New reviewed evidence.",
                    "Changed after receipt.",
                    1,
                ),
                encoding="utf-8",
            )

            result = check(repo, run, receipt, digest)

        self.assertFalse(result["valid"])
        self.assertIn("application_mismatch", [item["rule"] for item in result["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = apply_stage(Path(temp_dir))
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = check(repo, run, receipt, digest)

        self.assertIn("clean_worktree", [item["rule"] for item in dirty["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = apply_stage(Path(temp_dir))
            secret = "github_" + "pat_" + ("A" * 24)
            value = json.loads(receipt.read_text(encoding="utf-8"))
            value["reviewer_declaration"] = secret
            receipt.write_text(json.dumps(value), encoding="utf-8")
            rehashed = validation.apply_stage_output.sha256_bytes(receipt.read_bytes())
            secret_result = check(repo, run, receipt, rehashed)

        self.assertIn(
            "high_confidence_secret",
            [item["rule"] for item in secret_result["failures"]],
        )
        self.assertNotIn(secret, json.dumps(secret_result))

    def test_refuses_internal_paths_symlinks_and_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = apply_stage(Path(temp_dir))
            inside = repo / "application-receipt.json"
            inside.write_text(receipt.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside"):
                check(repo, run, inside, digest)

            link = Path(temp_dir) / "receipt-link.json"
            try:
                link.symlink_to(receipt)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                check(repo, run, link, digest)

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--run",
                str(REPO_ROOT),
                "--application-receipt",
                str(REPO_ROOT / "none.json"),
                "--application-receipt-sha256",
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

    def test_real_cli_validates_without_authorizing_or_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, run, receipt, digest = apply_stage(Path(temp_dir))
            before = snapshot(run)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--run",
                    str(run),
                    "--application-receipt",
                    str(receipt),
                    "--application-receipt-sha256",
                    digest,
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            after = snapshot(run)
            result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(before, after)
        self.assertTrue(result["valid"])
        self.assertFalse(result["authorized"])
        self.assertFalse(result["stage_authorized"])


if __name__ == "__main__":
    unittest.main()
