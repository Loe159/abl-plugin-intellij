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
MODULE_PATH = CHECKS_DIR / "validate_stage_output.py"
REPO_ROOT = CHECKS_DIR.parents[1]
TEMPLATES = REPO_ROOT / ".agent" / "templates"
PROMPTS = REPO_ROOT / ".agent" / "prompts"
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
sys.path.insert(0, str(CHECKS_DIR))
SPEC = importlib.util.spec_from_file_location("validate_stage_output", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_validate_task_approval as approval_helpers
import test_validate_stage_application as application_helpers


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def create_repo(path: Path) -> str:
    path.mkdir()
    git(path, "init")
    git(path, "config", "user.email", "tests@example.invalid")
    git(path, "config", "user.name", "Tests")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    git(path, "add", "README.md")
    git(path, "commit", "-m", "base")
    return git(path, "rev-parse", "HEAD")


def fill_text(text: str, base: str, risk: str = "medium") -> str:
    text = text.replace("{{issue}}", "123")
    text = text.replace("{{base_commit}}", base)
    text = text.replace("{{risk}}", risk)
    return re.sub(r"\{\{[a-z0-9_]+\}\}", "Concrete recorded evidence.", text)


def create_run(destination: Path, base: str) -> None:
    shutil.copytree(TEMPLATES, destination)
    for path in destination.glob("*.md"):
        text = fill_text(path.read_text(encoding="utf-8"), base)
        if path.name == "task.md":
            text = text.replace("status: awaiting_approval", "status: approved")
        if path.name == "research.md":
            text = text.replace("status: pending", "status: complete")
        path.write_text(text, encoding="utf-8")


def create_response(path: Path, artifact: str, base: str, status: str) -> None:
    text = fill_text((TEMPLATES / artifact).read_text(encoding="utf-8"), base)
    if artifact == "research.md":
        text = text.replace("status: pending", f"status: {status}")
    elif artifact in {"progress.md", "review.md"}:
        text = text.replace("status: pending", f"status: {status}")
    else:
        text = text.replace("status: awaiting_approval", f"status: {status}")
    path.write_text(text, encoding="utf-8")


class StageOutputValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        artifact = validator.validate_artifacts.load_contract(POLICY_DIR / "artifact-contract.json")
        prompt = validator.validate_prompts.load_prompt_contract(
            POLICY_DIR / "prompt-contract.json",
            artifact,
        )
        context = validator.build_stage_context.load_context_policy(
            POLICY_DIR / "stage-context.json",
            prompt,
            artifact,
        )
        self.policies = {
            "artifact": artifact,
            "prompt": prompt,
            "context": context,
            "output": validator.load_output_policy(
                POLICY_DIR / "stage-output.json",
                context,
                prompt,
                artifact,
            ),
            "diff": validator.diff_policy.load_policy(POLICY_DIR / "diff-policy.json"),
        }

    def prepare(
        self,
        temp: Path,
        stage: str = "research",
    ) -> tuple[Path, Path, Path, str]:
        receipt = None
        digest = None
        if stage == "research":
            repo, run, receipt, digest = approval_helpers.prepare(temp)
            application_receipt = None
            application_digest = None
        else:
            repo, run, application_receipt, application_digest = application_helpers.apply_stage(
                temp,
                "research",
            )
            receipt = None
            digest = None
        bundle = temp / ("bundle.json" if stage == "research" else "plan-bundle.json")
        build_result = validator.build_stage_context.build_context(
            repo,
            run,
            stage,
            bundle,
            {
                "artifact": self.policies["artifact"],
                "prompt": self.policies["prompt"],
                "readiness": validator.build_stage_context.check_stage_readiness.load_readiness_policy(
                    POLICY_DIR / "stage-readiness.json",
                    self.policies["artifact"],
                ),
                "context": self.policies["context"],
                "diff": self.policies["diff"],
            },
            PROMPTS,
            receipt,
            digest,
            application_receipt,
            application_digest,
        )
        self.assertTrue(build_result["produced"])
        return repo, run, bundle, build_result["sha256"]

    def validate(
        self,
        bundle: Path,
        digest: str,
        response: Path,
        repo: Path,
    ) -> dict[str, object]:
        return validator.validate_output(bundle, digest, response, repo, self.policies, PROMPTS)

    def test_repository_output_policy_is_valid_and_non_approving(self) -> None:
        self.assertEqual(
            ["compact-progress", "plan", "research", "review"],
            sorted(self.policies["output"]["stages"]),
        )
        self.assertNotIn("approved", self.policies["output"]["stages"]["plan"]["allowed_statuses"])

    def test_output_policy_rejects_self_approval_and_stage_mismatch(self) -> None:
        artifact = self.policies["artifact"]
        prompt = self.policies["prompt"]
        context = self.policies["context"]
        for expected, mutate in [
            (
                "never self-approve",
                lambda policy: policy["stages"]["plan"]["allowed_statuses"].append("approved"),
            ),
            (
                "exactly match",
                lambda policy: policy["stages"].pop("plan"),
            ),
        ]:
            with self.subTest(expected=expected):
                policy = json.loads((POLICY_DIR / "stage-output.json").read_text(encoding="utf-8"))
                mutate(policy)
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = Path(temp_dir) / "policy.json"
                    path.write_text(json.dumps(policy), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, expected):
                        validator.load_output_policy(path, context, prompt, artifact)

    def test_valid_research_and_plan_responses_are_accepted_not_authorized(self) -> None:
        for stage, artifact, status in [
            ("research", "research.md", "complete"),
            ("plan", "plan.md", "awaiting_approval"),
        ]:
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                repo, run, bundle, digest = self.prepare(temp, stage)
                base = json.loads(bundle.read_text(encoding="utf-8"))["base_commit"]
                response = temp / "response.md"
                create_response(response, artifact, base, status)

                result = self.validate(bundle, digest, response, repo)

                self.assertTrue(result["valid"], result["failures"])
                self.assertTrue(result["accepted"])
                self.assertFalse(result["authorized"])

    def test_valid_review_response_is_accepted_not_authorized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            base = create_repo(repo)
            run = temp / "run"
            create_run(run, base)
            for artifact, before, after in [
                ("plan.md", "status: awaiting_approval", "status: approved"),
                ("verification.md", "status: pending", "status: failed"),
            ]:
                path = run / artifact
                path.write_text(
                    path.read_text(encoding="utf-8").replace(before, after),
                    encoding="utf-8",
                )
            bundle = temp / "review-bundle.json"
            build_result = validator.build_stage_context.build_context(
                repo,
                run,
                "review",
                bundle,
                {
                    "artifact": self.policies["artifact"],
                    "prompt": self.policies["prompt"],
                    "readiness": validator.build_stage_context.check_stage_readiness.load_readiness_policy(
                        POLICY_DIR / "stage-readiness.json",
                        self.policies["artifact"],
                    ),
                    "context": self.policies["context"],
                    "diff": self.policies["diff"],
                },
                PROMPTS,
                None,
                None,
                None,
                None,
            )
            response = temp / "review-response.md"
            create_response(response, "review.md", base, "complete")

            result = self.validate(bundle, build_result["sha256"], response, repo)

        self.assertTrue(build_result["produced"], build_result.get("failures"))
        self.assertTrue(result["valid"], result["failures"])
        self.assertTrue(result["accepted"])
        self.assertEqual("review.md", result["artifact"])
        self.assertEqual("complete", result["status"])
        self.assertFalse(result["authorized"])

    def test_blocked_response_is_valid_but_never_authorized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest = self.prepare(temp)
            base = json.loads(bundle.read_text(encoding="utf-8"))["base_commit"]
            response = temp / "response.md"
            create_response(response, "research.md", base, "blocked")

            result = self.validate(bundle, digest, response, repo)

        self.assertTrue(result["valid"], result["failures"])
        self.assertEqual("blocked", result["status"])
        self.assertFalse(result["authorized"])

    def test_rejects_wrong_digest_before_parsing_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            create_repo(repo)
            bundle = temp / "bundle.json"
            bundle.write_text("not json and not trusted", encoding="utf-8")
            response = temp / "response.md"
            response.write_text("unused", encoding="utf-8")

            result = self.validate(bundle, "a" * 64, response, repo)

        self.assertEqual("bundle_sha256", result["failures"][0]["rule"])

    def test_rejects_tampered_record_and_bundle_metadata(self) -> None:
        for mutate, expected in [
            (lambda bundle: bundle["artifacts"][0].update(content="changed"), "bundle_record_size"),
            (lambda bundle: bundle.update(authorized=True), "bundle_metadata"),
            (
                lambda bundle: bundle["provenance"].update(
                    task_approval_receipt_sha256=12
                ),
                "bundle_provenance",
            ),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                repo, run, bundle_path, digest = self.prepare(temp)
                bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
                mutate(bundle)
                bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
                digest = validator.file_sha256(bundle_path)
                response = temp / "response.md"
                response.write_text("unused", encoding="utf-8")

                result = self.validate(bundle_path, digest, response, repo)

                self.assertIn(expected, [failure["rule"] for failure in result["failures"]])

    def test_rejects_bundle_with_altered_prompt_even_when_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle_path, digest = self.prepare(temp)
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            bundle["prompt"]["content"] += "\nAltered instructions.\n"
            content = bundle["prompt"]["content"].encode("utf-8")
            bundle["prompt"]["size_bytes"] = len(content)
            bundle["prompt"]["sha256"] = validator.hashlib.sha256(content).hexdigest()
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            digest = validator.file_sha256(bundle_path)
            response = temp / "response.md"
            response.write_text("unused", encoding="utf-8")

            result = self.validate(bundle_path, digest, response, repo)

        self.assertIn("bundle_prompt_content", [failure["rule"] for failure in result["failures"]])

    def test_rejects_wrong_context_status_identity_extra_section_and_frontmatter(self) -> None:
        mutations = [
            ("response_context", lambda text: text.replace("issue: 123", "issue: 456")),
            ("response_status", lambda text: text.replace("status: complete", "status: approved")),
            ("response_identity", lambda text: text.replace("artifact: research", "artifact: plan")),
            ("response_sections", lambda text: text + "\n# Unexpected\n\nNo.\n"),
            ("response_frontmatter", lambda text: text.replace("status: complete", "status: complete\nextra: value")),
        ]
        for expected, mutate in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                repo, run, bundle, digest = self.prepare(temp)
                base = json.loads(bundle.read_text(encoding="utf-8"))["base_commit"]
                response = temp / "response.md"
                create_response(response, "research.md", base, "complete")
                response.write_text(mutate(response.read_text(encoding="utf-8")), encoding="utf-8")

                result = self.validate(bundle, digest, response, repo)

                self.assertFalse(result["valid"])
                self.assertIn(expected, [failure["rule"] for failure in result["failures"]])

    def test_rejects_preface_placeholder_oversize_and_secret_without_echo(self) -> None:
        cases = [
            ("parse_response", lambda text: "Here is the artifact:\n" + text),
            (
                "parse_response",
                lambda text: text.replace("---\n\n# Scope", "---\n\nHere is the result.\n\n# Scope", 1),
            ),
            ("response_placeholders", lambda text: text.replace("Concrete recorded evidence.", "{{unknown}}", 1)),
            ("max_response_bytes", lambda text: text + ("x" * 21000)),
        ]
        for expected, mutate in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                repo, run, bundle, digest = self.prepare(temp)
                base = json.loads(bundle.read_text(encoding="utf-8"))["base_commit"]
                response = temp / "response.md"
                create_response(response, "research.md", base, "complete")
                response.write_text(mutate(response.read_text(encoding="utf-8")), encoding="utf-8")

                result = self.validate(bundle, digest, response, repo)

                self.assertIn(expected, [failure["rule"] for failure in result["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest = self.prepare(temp)
            base = json.loads(bundle.read_text(encoding="utf-8"))["base_commit"]
            response = temp / "response.md"
            create_response(response, "research.md", base, "complete")
            secret = "github_" + "pat_" + ("A" * 24)
            response.write_text(response.read_text(encoding="utf-8") + secret, encoding="utf-8")
            result = self.validate(bundle, digest, response, repo)

        self.assertEqual("high_confidence_secret", result["failures"][0]["rule"])
        self.assertNotIn(secret, json.dumps(result))

    def test_refuses_inputs_in_repo_and_symbolic_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest = self.prepare(temp)
            base = json.loads(bundle.read_text(encoding="utf-8"))["base_commit"]
            response = temp / "response.md"
            create_response(response, "research.md", base, "complete")
            inside = repo / "response.md"
            inside.write_text(response.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside"):
                self.validate(bundle, digest, inside, repo)
            link = temp / "response-link.md"
            try:
                link.symlink_to(response)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                self.validate(bundle, digest, link, repo)

    def test_cli_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, run, bundle, digest = self.prepare(temp)
            base = json.loads(bundle.read_text(encoding="utf-8"))["base_commit"]
            response = temp / "response.md"
            create_response(response, "research.md", base, "complete")
            valid = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--bundle",
                    str(bundle),
                    "--bundle-sha256",
                    digest,
                    "--response",
                    str(response),
                    "--format",
                    "json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            response.write_text("invalid", encoding="utf-8")
            invalid = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--repo",
                    str(repo),
                    "--bundle",
                    str(bundle),
                    "--bundle-sha256",
                    digest,
                    "--response",
                    str(response),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertTrue(json.loads(valid.stdout)["accepted"])
        self.assertEqual(2, invalid.returncode)


if __name__ == "__main__":
    unittest.main()
