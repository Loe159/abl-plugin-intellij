from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_prompts.py"
REPO_ROOT = CHECKS_DIR.parents[1]
PROMPTS = REPO_ROOT / ".agent" / "prompts"
PROMPT_CONTRACT_PATH = REPO_ROOT / ".agent" / "policies" / "prompt-contract.json"
ARTIFACT_CONTRACT_PATH = REPO_ROOT / ".agent" / "policies" / "artifact-contract.json"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("validate_prompts", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class PromptContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.artifact_contract = validator.validate_artifacts.load_contract(ARTIFACT_CONTRACT_PATH)
        self.prompt_contract = validator.load_prompt_contract(
            PROMPT_CONTRACT_PATH,
            self.artifact_contract,
        )

    def validate(self, directory: Path) -> dict[str, object]:
        return validator.validate_prompts(directory, self.prompt_contract, self.artifact_contract)

    def test_repository_prompts_are_valid(self) -> None:
        result = self.validate(PROMPTS)

        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(
            ["compact-progress.md", "plan.md", "research.md", "review.md"],
            result["prompts"],
        )

    def test_rejects_missing_and_unexpected_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts = Path(temp_dir) / "prompts"
            shutil.copytree(PROMPTS, prompts)
            (prompts / "research.md").unlink()
            (prompts / "implement.md").write_text("unexpected", encoding="utf-8")
            result = self.validate(prompts)

        rules = [error["rule"] for error in result["errors"]]
        self.assertIn("required_prompt", rules)
        self.assertIn("unexpected_prompt", rules)

    def test_rejects_wrong_identity_and_missing_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts = Path(temp_dir) / "prompts"
            shutil.copytree(PROMPTS, prompts)
            plan = prompts / "plan.md"
            text = plan.read_text(encoding="utf-8")
            text = text.replace("stage: plan", "stage: research")
            text = text.replace("# Stop Conditions", "# Removed Stop Conditions")
            plan.write_text(text, encoding="utf-8")
            result = self.validate(prompts)

        rules = [error["rule"] for error in result["errors"]]
        self.assertIn("prompt_stage", rules)
        self.assertIn("required_sections", rules)

    def test_rejects_missing_reference_guardrail_output_section_and_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts = Path(temp_dir) / "prompts"
            shutil.copytree(PROMPTS, prompts)
            research = prompts / "research.md"
            text = research.read_text(encoding="utf-8")
            text = text.replace("AGENTS.md", "repository rules")
            text = text.replace("Do not implement", "Avoid implementation")
            text = text.replace("- `# Evidence`", "- Evidence")
            text += "\n{{unresolved}}\n"
            research.write_text(text, encoding="utf-8")
            result = self.validate(prompts)

        rules = [error["rule"] for error in result["errors"]]
        self.assertIn("required_reference", rules)
        self.assertIn("required_guardrail", rules)
        self.assertIn("output_sections", rules)
        self.assertIn("no_placeholders", rules)

    def test_rejects_oversized_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts = Path(temp_dir) / "prompts"
            shutil.copytree(PROMPTS, prompts)
            plan = prompts / "plan.md"
            plan.write_text(
                plan.read_text(encoding="utf-8") + ("x" * self.prompt_contract["max_prompt_bytes"]),
                encoding="utf-8",
            )
            result = self.validate(prompts)

        self.assertIn("max_prompt_bytes", [error["rule"] for error in result["errors"]])

    def test_contract_rejects_write_mode_unknown_output_and_duplicate_stage(self) -> None:
        mutations = [
            ("mode", lambda contract: contract["prompts"]["research.md"].update(mode="write")),
            (
                "unknown output artifact",
                lambda contract: contract["prompts"]["research.md"].update(
                    output="unknown.md",
                    output_artifact="unknown.md",
                ),
            ),
            (
                "unique non-empty string",
                lambda contract: contract["prompts"]["plan.md"].update(stage="research"),
            ),
        ]
        for expected, mutate in mutations:
            with self.subTest(expected=expected):
                contract = json.loads(PROMPT_CONTRACT_PATH.read_text(encoding="utf-8"))
                mutate(contract)
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = Path(temp_dir) / "contract.json"
                    path.write_text(json.dumps(contract), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, expected):
                        validator.load_prompt_contract(path, self.artifact_contract)

    def test_cli_exit_codes(self) -> None:
        valid = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--format", "json"],
            check=False,
            capture_output=True,
            text=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            invalid = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--prompts", temp_dir],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertTrue(json.loads(valid.stdout)["valid"])
        self.assertEqual(2, invalid.returncode)


if __name__ == "__main__":
    unittest.main()
