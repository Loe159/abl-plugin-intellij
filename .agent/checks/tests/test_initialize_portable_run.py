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
MODULE_PATH = CHECKS_DIR / "initialize_portable_run.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("initialize_portable_run", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
initializer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = initializer
SPEC.loader.exec_module(initializer)
import test_build_stage_context as helpers


def input_value(base: str, **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "input_version": 1,
        "purpose": "portable_run_normalized_task_input",
        "mode": "normalized-task-only",
        "issue": 123,
        "risk": "medium",
        "base_commit": base,
        "source": {
            "kind": "human_normalized_input",
            "reference": "local:issue-123",
        },
        "task": {
            "goal": "Fix the verified behavior.",
            "expected_behavior": "The focused behavior is correct.",
            "acceptance_criteria": "- Focused test passes.",
            "constraints": "- Do not change protected files.",
            "out_of_scope": "- Unrelated refactors.",
        },
    }
    value.update(updates)
    return value


def prepare(temp: Path) -> tuple[Path, Path, Path, Path]:
    repo = temp / "repo"
    base = helpers.create_repo(repo)
    input_path = temp / "input.json"
    input_path.write_text(json.dumps(input_value(base)), encoding="utf-8")
    return repo, input_path, temp / "run", temp / "receipt.json"


class InitializePortableRunTest(unittest.TestCase):
    def test_repository_policy_is_exact_initialization_only_and_non_authorizing(self) -> None:
        policies = initializer.load_policies()

        self.assertEqual(initializer.EXPECTED_POLICY, policies["initialization"])
        self.assertEqual("initialization-only", policies["initialization"]["mode"])
        self.assertNotIn("codex", json.dumps(policies["initialization"]).lower())

    def test_real_initialization_creates_valid_not_approved_not_ready_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, input_path, run, receipt = prepare(Path(temp_dir))
            result = initializer.initialize(
                repo,
                input_path,
                run,
                receipt,
                initializer.load_policies(),
            )
            policies = initializer.load_policies()
            contract = initializer.validate_artifacts.validate_directory(
                run,
                policies["artifact"],
                False,
            )
            readiness = initializer.check_stage_readiness.check_readiness(
                run,
                "research",
                policies["artifact"],
                policies["readiness"],
            )
            task = initializer.validate_artifacts.parse_artifact(run / "task.md")
            receipt_value = json.loads(receipt.read_text(encoding="utf-8"))

            self.assertTrue(result["initialized"])
            self.assertTrue(contract["valid"], contract["errors"])
            self.assertFalse(readiness["ready"])
            self.assertEqual("awaiting_approval", task.frontmatter["status"])
            self.assertIn("Fix the verified behavior.", task.sections["Goal"])
            self.assertFalse(receipt_value["task_approved"])
            self.assertFalse(receipt_value["research_ready"])
            for field in initializer.FALSE_FIELDS:
                self.assertFalse(receipt_value[field])

    def test_same_input_produces_identical_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = helpers.create_repo(repo)
            input_path = temp / "input.json"
            input_path.write_text(json.dumps(input_value(base)), encoding="utf-8")
            first = temp / "first"
            second = temp / "second"
            initializer.initialize(
                repo,
                input_path,
                first,
                temp / "first-receipt.json",
                initializer.load_policies(),
            )
            initializer.initialize(
                repo,
                input_path,
                second,
                temp / "second-receipt.json",
                initializer.load_policies(),
            )

            self.assertEqual(
                [path.read_bytes() for path in sorted(first.glob("*.md"))],
                [path.read_bytes() for path in sorted(second.glob("*.md"))],
            )

    def test_invalid_schema_section_heading_and_oversize_do_not_write(self) -> None:
        mutations = [
            lambda value: value.update(mode="raw-issue"),
            lambda value: value["task"].update(goal="# Unexpected Heading"),
            lambda value: value["task"].update(goal="Literal {{issue}} placeholder"),
            lambda value: value["task"].update(goal="x" * 5001),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as temp_dir:
                repo, input_path, run, receipt = prepare(Path(temp_dir))
                value = json.loads(input_path.read_text(encoding="utf-8"))
                mutate(value)
                input_path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    initializer.initialize(
                        repo,
                        input_path,
                        run,
                        receipt,
                        initializer.load_policies(),
                    )
                self.assertFalse(run.exists())
                self.assertFalse(receipt.exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, input_path, run, receipt = prepare(Path(temp_dir))
            input_path.write_text(" " * 30001, encoding="utf-8")
            result = initializer.initialize(
                repo,
                input_path,
                run,
                receipt,
                initializer.load_policies(),
            )
            self.assertIn("max_input_bytes", [item["rule"] for item in result["failures"]])
            self.assertFalse(run.exists())
            self.assertFalse(receipt.exists())

    def test_secret_dirty_repo_and_head_mismatch_do_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, input_path, run, receipt = prepare(Path(temp_dir))
            value = json.loads(input_path.read_text(encoding="utf-8"))
            value["task"]["goal"] = "github_pat_" + ("A" * 24)
            input_path.write_text(json.dumps(value), encoding="utf-8")
            result = initializer.initialize(
                repo,
                input_path,
                run,
                receipt,
                initializer.load_policies(),
            )
            self.assertIn("high_confidence_secret", [item["rule"] for item in result["failures"]])
            self.assertNotIn(value["task"]["goal"], json.dumps(result))
            self.assertFalse(run.exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, input_path, run, receipt = prepare(Path(temp_dir))
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            result = initializer.initialize(
                repo,
                input_path,
                run,
                receipt,
                initializer.load_policies(),
            )
            self.assertIn("clean_worktree", [item["rule"] for item in result["failures"]])
            self.assertFalse(run.exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            repo, input_path, run, receipt = prepare(Path(temp_dir))
            value = json.loads(input_path.read_text(encoding="utf-8"))
            value["base_commit"] = "0" * 40
            input_path.write_text(json.dumps(value), encoding="utf-8")
            result = initializer.initialize(
                repo,
                input_path,
                run,
                receipt,
                initializer.load_policies(),
            )
            self.assertIn("repo_head_match", [item["rule"] for item in result["failures"]])
            self.assertFalse(run.exists())

    def test_internal_existing_symlink_and_policy_override_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, input_path, run, receipt = prepare(temp)
            cases = [
                (repo / "input.json", run, receipt),
                (input_path, repo / "run", receipt),
                (input_path, run, repo / "receipt.json"),
            ]
            (repo / "input.json").write_bytes(input_path.read_bytes())
            for current_input, current_run, current_receipt in cases:
                with self.subTest(run=current_run), self.assertRaisesRegex(ValueError, "outside"):
                    initializer.initialize(
                        repo,
                        current_input,
                        current_run,
                        current_receipt,
                        initializer.load_policies(),
                    )
            run.mkdir()
            with self.assertRaisesRegex(ValueError, "already exists"):
                initializer.initialize(
                    repo,
                    input_path,
                    run,
                    receipt,
                    initializer.load_policies(),
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, input_path, run, receipt = prepare(temp)
            link = temp / "input-link.json"
            try:
                link.symlink_to(input_path)
            except OSError:
                link = None
            if link is not None:
                with self.assertRaisesRegex(ValueError, "symbolic links"):
                    initializer.initialize(
                        repo,
                        link,
                        run,
                        receipt,
                        initializer.load_policies(),
                    )

            policy = json.loads(
                (initializer.POLICY_PATH).read_text(encoding="utf-8")
            )
            policy["require_clean_worktree"] = False
            drifted = temp / "policy.json"
            drifted.write_text(json.dumps(policy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pilot contract"):
                initializer.load_policy(drifted)

        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--repo",
                str(REPO_ROOT),
                "--input",
                str(REPO_ROOT / "none.json"),
                "--run",
                str(REPO_ROOT.parent / "run"),
                "--receipt",
                str(REPO_ROOT.parent / "receipt.json"),
                "--policy",
                "untrusted.json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unrecognized arguments", completed.stderr)

    def test_receipt_failure_rolls_back_created_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, input_path, run, receipt = prepare(Path(temp_dir))

            def failing_writer(_path: Path, _content: bytes) -> None:
                raise OSError("fixture failure")

            with self.assertRaisesRegex(ValueError, "rollback succeeded"):
                initializer.initialize(
                    repo,
                    input_path,
                    run,
                    receipt,
                    initializer.load_policies(),
                    receipt_writer=failing_writer,
                )
            self.assertFalse(run.exists())
            self.assertFalse(receipt.exists())

    def test_state_drift_before_creation_rolls_back(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, input_path, run, receipt = prepare(Path(temp_dir))
            original = initializer.check_stage_readiness.check_readiness

            def drifting_readiness(*args: object, **kwargs: object) -> dict[str, object]:
                input_path.write_text(
                    input_path.read_text(encoding="utf-8") + "\n",
                    encoding="utf-8",
                )
                return original(*args, **kwargs)

            with mock.patch.object(
                initializer.check_stage_readiness,
                "check_readiness",
                side_effect=drifting_readiness,
            ), self.assertRaisesRegex(ValueError, "rollback succeeded"):
                initializer.initialize(
                    repo,
                    input_path,
                    run,
                    receipt,
                    initializer.load_policies(),
                )
            self.assertFalse(run.exists())
            self.assertFalse(receipt.exists())

    def test_real_cli_initializes_without_approval_or_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo, input_path, run, receipt = prepare(Path(temp_dir))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--input",
                    str(input_path),
                    "--run",
                    str(run),
                    "--receipt",
                    str(receipt),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            result = json.loads(completed.stdout)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(result["initialized"])
            self.assertFalse(result["task_approved"])
            self.assertFalse(result["research_ready"])
            self.assertFalse(result["authorized"])


if __name__ == "__main__":
    unittest.main()
