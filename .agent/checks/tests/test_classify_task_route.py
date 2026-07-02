from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKS_DIR.parents[1]
MODULE_PATH = CHECKS_DIR / "classify_task_route.py"
TEMPLATES = REPO_ROOT / ".agent" / "templates"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("classify_task_route", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
classifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = classifier
SPEC.loader.exec_module(classifier)


def fill_text(text: str, risk: str = "medium") -> str:
    replacements = {
        "{{issue}}": "42",
        "{{base_commit}}": "a" * 40,
        "{{risk}}": risk,
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return re.sub(r"\{\{[a-z0-9_]+\}\}", "Concrete bounded task evidence.", text)


def create_run(destination: Path, risk: str = "medium", approved: bool = False) -> None:
    destination.mkdir()
    for template in TEMPLATES.glob("*.md"):
        text = fill_text(template.read_text(encoding="utf-8"), risk)
        if template.name == "task.md" and approved:
            text = text.replace("status: awaiting_approval", "status: approved")
        (destination / template.name).write_text(text, encoding="utf-8")


class ClassifyTaskRouteTest(unittest.TestCase):
    def test_policy_is_exact_frontmatter_only_and_non_authorizing(self) -> None:
        policy = classifier.load_policy()

        self.assertEqual(classifier.EXPECTED_POLICY, policy)
        self.assertEqual("portable-run-frontmatter-only", policy["mode"])
        self.assertFalse(policy["authorizes"])

    def test_declared_task_risk_maps_to_routes_without_authorization(self) -> None:
        for risk, route in (("low", "A"), ("medium", "B"), ("high", "C")):
            with self.subTest(risk=risk):
                with tempfile.TemporaryDirectory() as temp_dir:
                    run = Path(temp_dir) / "run"
                    create_run(run, risk=risk, approved=False)

                    result = classifier.classify(run, classifier.load_policy())

                self.assertTrue(result["classified"], result["errors"])
                self.assertEqual(risk, result["risk"])
                self.assertEqual(route, result["route"])
                self.assertEqual("awaiting_approval", result["task_status"])
                self.assertFalse(result["task_approved"])
                for field in classifier.FALSE_FIELDS:
                    self.assertFalse(result[field])

    def test_approved_task_status_is_reported_but_not_authorizing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run, risk="low", approved=True)

            result = classifier.classify(run, classifier.load_policy())

        self.assertTrue(result["classified"], result["errors"])
        self.assertTrue(result["task_approved"])
        self.assertEqual("approved", result["task_status"])
        self.assertFalse(result["authorized"])

    def test_invalid_run_is_not_classified(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run = Path(temp_dir) / "run"
            create_run(run, risk="medium")
            (run / "plan.md").unlink()

            result = classifier.classify(run, classifier.load_policy())

        self.assertFalse(result["classified"])
        self.assertTrue(result["errors"])
        self.assertFalse(result["authorized"])

    def test_cli_refuses_policy_override(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--run",
                "run",
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
