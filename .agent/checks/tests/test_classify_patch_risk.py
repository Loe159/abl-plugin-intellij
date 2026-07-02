from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "classify_patch_risk.py"
REPOSITORY_RISK_POLICY_PATH = CHECKS_DIR.parent / "policies" / "risk-rules.json"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("classify_patch_risk", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
classifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = classifier
SPEC.loader.exec_module(classifier)


RISK_POLICY = {
    "version": 1,
    "medium_file_count": 4,
    "medium_changed_lines": 51,
    "high_path_patterns": [
        "src/main/kotlin/com/example/parser/**",
        "src/main/kotlin/com/example/core/ParserFacade.kt",
    ],
    "medium_path_patterns": ["src/main/**"],
}


def policy_result(
    path: str,
    changed_lines: int = 2,
    violations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "allowed": not violations,
        "facts": {
            "file_count": 1,
            "changed_lines": changed_lines,
            "paths": [path],
        },
        "violations": violations or [],
    }


def patch_for(path: str) -> str:
    return "\n".join(
        [
            f"diff --git a/{path} b/{path}",
            f"--- a/{path}",
            f"+++ b/{path}",
            "@@ -1 +1 @@",
            "-old",
            "+new",
            "",
        ]
    )


class PatchRiskClassifierTest(unittest.TestCase):
    def test_small_documentation_patch_is_low_route_a(self) -> None:
        result = classifier.classify(policy_result("docs/user-guide.md"), RISK_POLICY)

        self.assertEqual("low", result["risk"])
        self.assertEqual("A", result["route"])
        self.assertEqual(["implementation_review"], result["human_gates"]["required"])
        self.assertEqual([], result["human_gates"]["recommended"])

    def test_application_code_is_medium_route_b(self) -> None:
        result = classifier.classify(
            policy_result("src/main/kotlin/com/example/Feature.kt"),
            RISK_POLICY,
        )

        self.assertEqual("medium", result["risk"])
        self.assertEqual("B", result["route"])
        self.assertIn("plan_review", result["human_gates"]["required"])
        self.assertEqual(["research_review"], result["human_gates"]["recommended"])

    def test_parser_path_is_high_even_when_small(self) -> None:
        result = classifier.classify(
            policy_result("src/main/kotlin/com/example/parser/Parser.kt"),
            RISK_POLICY,
        )

        self.assertEqual("high", result["risk"])
        rules = [reason["rule"] for reason in result["reasons"]]
        self.assertIn("high_risk_paths", rules)
        self.assertIn("application_code", rules)

    def test_policy_block_always_forces_high(self) -> None:
        result = classifier.classify(
            policy_result(
                "docs/blocked.md",
                violations=[{"rule": "protected_paths", "message": "blocked"}],
            ),
            RISK_POLICY,
        )

        self.assertEqual("high", result["risk"])
        self.assertFalse(result["policy_allowed"])
        self.assertEqual("policy_blocked", result["reasons"][0]["rule"])

    def test_size_thresholds_raise_but_never_lower_risk(self) -> None:
        large_docs = policy_result("docs/large.md", changed_lines=51)
        large_docs["facts"]["file_count"] = 4

        result = classifier.classify(large_docs, RISK_POLICY)

        self.assertEqual("medium", result["risk"])
        rules = [reason["rule"] for reason in result["reasons"]]
        self.assertIn("medium_file_count", rules)
        self.assertIn("medium_changed_lines", rules)

    def test_load_policy_rejects_invalid_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "risk.json"
            path.write_text(
                json.dumps({**RISK_POLICY, "medium_file_count": 0}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "positive integer"):
                classifier.load_risk_policy(path)

    def test_repository_policy_classifies_verified_sensitive_paths_high(self) -> None:
        repository_policy = classifier.load_risk_policy(REPOSITORY_RISK_POLICY_PATH)
        high_paths = [
            "src/main/kotlin/com/ablls/plugin/parser/AblPsiParser.kt",
            "src/main/kotlin/com/ablls/plugin/core/AblParserFacade.kt",
            "src/main/kotlin/com/ablls/plugin/core/AblProjectAnalysisService.kt",
            "src/main/kotlin/com/ablls/plugin/debug/AblDebugConnection.kt",
            "src/main/resources/abl/oe-debug-bootstrap.p",
        ]

        for path in high_paths:
            with self.subTest(path=path):
                result = classifier.classify(policy_result(path), repository_policy)
                self.assertEqual("high", result["risk"])

    def test_repository_policy_classifies_other_application_code_medium(self) -> None:
        repository_policy = classifier.load_risk_policy(REPOSITORY_RISK_POLICY_PATH)

        result = classifier.classify(
            policy_result("src/main/kotlin/com/ablls/plugin/highlight/AblCommenter.kt"),
            repository_policy,
        )

        self.assertEqual("medium", result["risk"])

    def test_cli_classifies_small_patch_without_changing_policy_exit_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patch = temp / "patch.diff"
            patch.write_text(patch_for("docs/user-guide.md"), encoding="utf-8")
            diff_policy_path = temp / "diff-policy.json"
            repository_policy = classifier.diff_policy.load_policy(
                CHECKS_DIR.parent / "policies" / "diff-policy.json"
            )
            diff_policy_path.write_text(json.dumps(repository_policy), encoding="utf-8")
            risk_policy_path = temp / "risk-policy.json"
            risk_policy_path.write_text(json.dumps(RISK_POLICY), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(patch),
                    "--diff-policy",
                    str(diff_policy_path),
                    "--risk-policy",
                    str(risk_policy_path),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual("low", json.loads(completed.stdout)["risk"])

    def test_cli_returns_high_with_zero_exit_for_blocked_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            patch = temp / "patch.diff"
            patch.write_text(patch_for(".agent/config.json"), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(patch),
                    "--risk-policy",
                    str(REPOSITORY_RISK_POLICY_PATH),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual("high", result["risk"])
        self.assertFalse(result["policy_allowed"])

    def test_cli_does_not_echo_secret_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            secret = "github_" + "pat_" + ("A" * 24)
            patch = temp / "patch.diff"
            patch.write_text(
                "\n".join(
                    [
                        "diff --git a/credentials.txt b/credentials.txt",
                        "--- /dev/null",
                        "+++ b/credentials.txt",
                        "@@ -0,0 +1 @@",
                        f"+token={secret}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--patch",
                    str(patch),
                    "--risk-policy",
                    str(REPOSITORY_RISK_POLICY_PATH),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertNotIn(secret, completed.stdout + completed.stderr)
        self.assertEqual("high", json.loads(completed.stdout)["risk"])


if __name__ == "__main__":
    unittest.main()
