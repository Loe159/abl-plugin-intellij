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
MODULE_PATH = CHECKS_DIR / "validate_artifacts.py"
REPO_ROOT = CHECKS_DIR.parents[1]
TEMPLATES = REPO_ROOT / ".agent" / "templates"
CONTRACT_PATH = REPO_ROOT / ".agent" / "policies" / "artifact-contract.json"
SPEC = importlib.util.spec_from_file_location("validate_artifacts", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def create_filled_run(destination: Path) -> None:
    shutil.copytree(TEMPLATES, destination)
    replacements = {
        "{{issue}}": "123",
        "{{base_commit}}": "a" * 40,
        "{{risk}}": "low",
    }
    for path in destination.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"\{\{[a-z0-9_]+\}\}", "Concrete recorded evidence.", text)
        path.write_text(text, encoding="utf-8")


class ArtifactContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = validator.load_contract(CONTRACT_PATH)

    def test_repository_templates_are_valid(self) -> None:
        result = validator.validate_directory(TEMPLATES, self.contract, True)

        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(
            [
                "plan.md",
                "progress.md",
                "research.md",
                "review.md",
                "task.md",
                "verification.md",
            ],
            result["artifacts"],
        )

    def test_filled_portable_run_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_filled_run(run)

            result = validator.validate_directory(run, self.contract, False)

        self.assertTrue(result["valid"], result["errors"])

    def test_filled_run_accepts_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_filled_run(run)
            task = run / "task.md"
            task.write_text(task.read_text(encoding="utf-8"), encoding="utf-8-sig")

            result = validator.validate_directory(run, self.contract, False)

        self.assertTrue(result["valid"], result["errors"])

    def test_run_rejects_missing_artifact_and_unresolved_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_filled_run(run)
            (run / "verification.md").unlink()
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8").replace("Concrete recorded evidence.", "{{goal}}", 1),
                encoding="utf-8",
            )

            result = validator.validate_directory(run, self.contract, False)

        rules = [error["rule"] for error in result["errors"]]
        self.assertIn("required_artifact", rules)
        self.assertIn("no_placeholders", rules)

    def test_run_rejects_inconsistent_issue_and_base_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_filled_run(run)
            research = run / "research.md"
            text = research.read_text(encoding="utf-8")
            text = text.replace("issue: 123", "issue: 456")
            text = text.replace("base_commit: " + ("a" * 40), "base_commit: " + ("b" * 40))
            research.write_text(text, encoding="utf-8")

            result = validator.validate_directory(run, self.contract, False)

        rules = [error["rule"] for error in result["errors"]]
        self.assertIn("consistent_issue", rules)
        self.assertIn("consistent_base_commit", rules)

    def test_run_rejects_empty_required_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_filled_run(run)
            plan = run / "plan.md"
            text = plan.read_text(encoding="utf-8")
            text = text.replace(
                "# Out Of Scope\n\nConcrete recorded evidence.",
                "# Out Of Scope\n\n",
            )
            plan.write_text(text, encoding="utf-8")

            result = validator.validate_directory(run, self.contract, False)

        self.assertIn("non_empty_sections", [error["rule"] for error in result["errors"]])

    def test_run_rejects_unexpected_markdown_and_oversized_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_filled_run(run)
            (run / "transcript.md").write_text("raw transcript", encoding="utf-8")
            task = run / "task.md"
            task.write_text(
                task.read_text(encoding="utf-8") + ("x" * self.contract["max_artifact_bytes"]),
                encoding="utf-8",
            )

            result = validator.validate_directory(run, self.contract, False)

        rules = [error["rule"] for error in result["errors"]]
        self.assertIn("unexpected_artifact", rules)
        self.assertIn("max_artifact_bytes", rules)

    def test_run_rejects_wrong_status_artifact_identity_and_risk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_filled_run(run)
            task = run / "task.md"
            text = task.read_text(encoding="utf-8")
            text = text.replace("artifact: task", "artifact: research")
            text = text.replace("status: awaiting_approval", "status: invented")
            text = text.replace("risk: low", "risk: impossible")
            task.write_text(text, encoding="utf-8")

            result = validator.validate_directory(run, self.contract, False)

        rules = [error["rule"] for error in result["errors"]]
        self.assertIn("artifact_identity", rules)
        self.assertIn("allowed_status", rules)
        self.assertIn("valid_risk", rules)

    def test_cli_exit_codes(self) -> None:
        valid = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--templates",
                str(TEMPLATES),
                "--format",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_run = Path(temp_dir) / "run"
            invalid_run.mkdir()
            invalid = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--run",
                    str(invalid_run),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertTrue(json.loads(valid.stdout)["valid"])
        self.assertEqual(2, invalid.returncode)
        self.assertIn("artifact-contract: INVALID", invalid.stdout)

    def test_contract_rejects_duplicate_or_invalid_schema_values(self) -> None:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        contract["common_frontmatter"].append("status")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "common_frontmatter"):
                validator.load_contract(path)

        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        contract["artifacts"]["research.md"]["artifact"] = "task"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique non-empty string"):
                validator.load_contract(path)

        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
        contract["artifacts"]["task.md"]["required_sections"].append("Goal")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "contract.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "required_sections"):
                validator.load_contract(path)


if __name__ == "__main__":
    unittest.main()
