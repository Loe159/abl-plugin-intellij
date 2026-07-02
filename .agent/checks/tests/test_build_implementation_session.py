from __future__ import annotations

import importlib.util
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "build_implementation_session.py"
REPO_ROOT = CHECKS_DIR.parents[1]
TEMPLATES = REPO_ROOT / ".agent" / "templates"
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
PROMPTS = REPO_ROOT / ".agent" / "prompts"
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("build_implementation_session", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
session = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = session
SPEC.loader.exec_module(session)
import apply_stage_output
import approve_plan
import approve_task
import test_apply_stage_output as application_helpers
import test_initialize_portable_run as initialization_helpers


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def create_repo(path: Path, binding_mismatch: bool = False) -> str:
    path.mkdir()
    git(path, "init")
    git(path, "config", "user.email", "tests@example.invalid")
    git(path, "config", "user.name", "Tests")
    policy = json.loads((POLICY_DIR / "implementation-session.json").read_text(encoding="utf-8"))
    for name in policy["policy_bindings"]:
        destination = path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO_ROOT / name, destination)
    if binding_mismatch:
        agents = path / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "\nLocal drift.\n", encoding="utf-8")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    git(path, "add", ".")
    git(path, "commit", "-m", "base")
    return git(path, "rev-parse", "HEAD")


def prepare(temp: Path, binding_mismatch: bool = False) -> tuple[Path, Path, str, Path, Path, str]:
    repo = temp / "repo"
    base = create_repo(repo, binding_mismatch)
    input_path = temp / "input.json"
    input_path.write_text(json.dumps(initialization_helpers.input_value(base)), encoding="utf-8")
    run = temp / "run"
    initialization_receipt = temp / "initialization-receipt.json"
    initialized = approve_task.initialize_portable_run.initialize(
        repo,
        input_path,
        run,
        initialization_receipt,
        approve_task.initialize_portable_run.load_policies(),
    )
    assert initialized["initialized"], initialized

    task_policies = approve_task.load_policies()
    task_approval_receipt = temp / "task-approval-receipt.json"
    task_assessment = approve_task.assess_approval(
        repo,
        run,
        initialization_receipt,
        initialized["receipt_sha256"],
        task_approval_receipt,
        "local-reviewer",
        task_policies,
    )
    assert task_assessment["approvable"], task_assessment
    task_approval = approve_task.approve(
        argparse.Namespace(
            repo=repo,
            run=run,
            receipt=initialization_receipt,
            receipt_sha256=initialized["receipt_sha256"],
            approval_receipt=task_approval_receipt,
            approver="local-reviewer",
            confirm=task_assessment["required_confirmation"],
        ),
        task_policies,
        task_assessment,
    )
    assert task_approval["task_approved"], task_approval

    application_policies = apply_stage_output.load_policies()
    research_bundle = temp / "research-bundle.json"
    research_built = apply_stage_output.build_stage_context.build_context(
        repo,
        run,
        "research",
        research_bundle,
        {
            "artifact": application_policies["artifact"],
            "prompt": application_policies["prompt"],
            "readiness": apply_stage_output.build_stage_context.check_stage_readiness.load_readiness_policy(
                POLICY_DIR / "stage-readiness.json",
                application_policies["artifact"],
            ),
            "context": application_policies["context"],
            "diff": application_policies["diff"],
        },
        PROMPTS,
        task_approval_receipt,
        task_approval["approval_receipt_sha256"],
    )
    assert research_built["produced"], research_built
    research_response = temp / "research-response.md"
    application_helpers.create_response(research_response, "research.md", base, "complete")
    research_application_receipt = temp / "research-application-receipt.json"
    research_assessment = apply_stage_output.assess_application(
        repo,
        run,
        research_bundle,
        research_built["sha256"],
        research_response,
        research_application_receipt,
        application_policies,
    )
    assert research_assessment["applicable"], research_assessment
    research_application = apply_stage_output.apply_response(
        argparse.Namespace(
            repo=repo,
            run=run,
            bundle=research_bundle,
            bundle_sha256=research_built["sha256"],
            response=research_response,
            application_receipt=research_application_receipt,
            reviewer="local-operator",
            confirm=research_assessment["required_confirmation"],
        ),
        application_policies,
        research_assessment,
    )
    assert research_application["applied"], research_application

    plan_bundle = temp / "plan-bundle.json"
    plan_built = apply_stage_output.build_stage_context.build_context(
        repo,
        run,
        "plan",
        plan_bundle,
        {
            "artifact": application_policies["artifact"],
            "prompt": application_policies["prompt"],
            "readiness": apply_stage_output.build_stage_context.check_stage_readiness.load_readiness_policy(
                POLICY_DIR / "stage-readiness.json",
                application_policies["artifact"],
            ),
            "context": application_policies["context"],
            "diff": application_policies["diff"],
        },
        PROMPTS,
        None,
        None,
        research_application_receipt,
        research_application["application_receipt_sha256"],
    )
    assert plan_built["produced"], plan_built
    plan_response = temp / "plan-response.md"
    application_helpers.create_response(plan_response, "plan.md", base, "awaiting_approval")
    plan_application_receipt = temp / "plan-application-receipt.json"
    plan_assessment = apply_stage_output.assess_application(
        repo,
        run,
        plan_bundle,
        plan_built["sha256"],
        plan_response,
        plan_application_receipt,
        application_policies,
    )
    assert plan_assessment["applicable"], plan_assessment
    plan_application = apply_stage_output.apply_response(
        argparse.Namespace(
            repo=repo,
            run=run,
            bundle=plan_bundle,
            bundle_sha256=plan_built["sha256"],
            response=plan_response,
            application_receipt=plan_application_receipt,
            reviewer="local-operator",
            confirm=plan_assessment["required_confirmation"],
        ),
        application_policies,
        plan_assessment,
    )
    assert plan_application["applied"], plan_application

    plan_policies = approve_plan.load_policies()
    plan_approval_receipt = temp / "plan-approval-receipt.json"
    plan_approval_assessment = approve_plan.assess_approval(
        repo,
        run,
        plan_application_receipt,
        plan_application["application_receipt_sha256"],
        plan_approval_receipt,
        plan_policies,
    )
    assert plan_approval_assessment["approvable"], plan_approval_assessment
    plan_approval = approve_plan.approve(
        argparse.Namespace(
            repo=repo,
            run=run,
            application_receipt=plan_application_receipt,
            application_receipt_sha256=plan_application["application_receipt_sha256"],
            approval_receipt=plan_approval_receipt,
            approver="local-reviewer",
            confirm=plan_approval_assessment["required_confirmation"],
        ),
        plan_policies,
        plan_approval_assessment,
    )
    assert plan_approval["plan_approved"], plan_approval

    handoff = temp / "handoff.json"
    result = session.build_implementation_handoff.build_handoff(
        repo,
        run,
        handoff,
        plan_approval_receipt,
        plan_approval["approval_receipt_sha256"],
        session.build_implementation_handoff.load_policies(),
    )
    assert result["produced"]
    workspace = temp / "workspace"
    worktree_receipt = temp / "worktree-receipt.json"
    worktree = session.validate_disposable_worktree.prepare_disposable_worktree.prepare(
        repo,
        base,
        workspace,
        worktree_receipt,
        session.validate_disposable_worktree.prepare_disposable_worktree.load_policy(),
    )
    assert worktree["prepared"], worktree
    return repo, handoff, result["sha256"], workspace, worktree_receipt, worktree["receipt_sha256"]


def cli(
    repo: Path,
    handoff: Path,
    digest: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_digest: str,
    output: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--repo",
            str(repo),
            "--handoff",
            str(handoff),
            "--handoff-sha256",
            digest,
            "--workspace",
            str(workspace),
            "--worktree-receipt",
            str(worktree_receipt),
            "--worktree-receipt-sha256",
            worktree_digest,
            "--output",
            str(output),
            "--format",
            "json",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class BuildImplementationSessionTest(unittest.TestCase):
    def test_repository_policy_is_valid_and_non_authorizing(self) -> None:
        policy = session.load_policies()["session"]
        self.assertEqual("proposal-only", policy["mode"])
        self.assertFalse(policy["capabilities"]["network_access"])
        self.assertFalse(policy["workspace"]["git_commits"])
        self.assertEqual(12, policy["budgets"]["max_changed_files"])
        self.assertEqual(500, policy["budgets"]["max_changed_lines"])

    def test_policy_rejects_unsafe_capabilities_mode_and_budget_drift(self) -> None:
        diff_config = session.diff_policy.load_policy(POLICY_DIR / "diff-policy.json")
        for expected, mutate in [
            ("non-authorizing", lambda policy: policy.update(mode="execute")),
            ("size limits", lambda policy: policy.update(max_proposal_bytes=999999)),
            ("size limits", lambda policy: policy.update(max_proposal_bytes=150000.0)),
            (
                "bounded supervised-write",
                lambda policy: policy["capabilities"].update(network_access=True),
            ),
            (
                "bounded supervised-write",
                lambda policy: policy["capabilities"].update(network_access=0),
            ),
            ("bounded session", lambda policy: policy["budgets"].update(max_turns=999999)),
            ("bounded session", lambda policy: policy["budgets"].update(max_turns=12.0)),
            (
                "prompt_required_literals",
                lambda policy: policy["prompt_required_literals"].remove("Do not access the network"),
            ),
            (
                "policy_bindings",
                lambda policy: policy["policy_bindings"].append("private.txt"),
            ),
            (
                "required_external_controls",
                lambda policy: policy["required_external_controls"].remove(
                    "human_implementation_review"
                ),
            ),
        ]:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                policy = json.loads(
                    (POLICY_DIR / "implementation-session.json").read_text(encoding="utf-8")
                )
                mutate(policy)
                path = Path(temp_dir) / "policy.json"
                path.write_text(json.dumps(policy), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected):
                    session.load_session_policy(path, diff_config)

    def test_proposal_is_reproducible_and_all_authorizations_remain_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            first = temp / "first.json"
            second = temp / "second.json"
            policies = session.load_policies()
            first_result = session.build_proposal(
                repo,
                handoff,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                first,
                policies,
            )
            second_result = session.build_proposal(
                repo,
                handoff,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                second,
                policies,
            )
            proposal = json.loads(first.read_text(encoding="utf-8"))
            first_bytes = first.read_bytes()
            second_bytes = second.read_bytes()

        self.assertTrue(first_result["produced"])
        self.assertEqual(first_bytes, second_bytes)
        self.assertEqual(first_result["sha256"], second_result["sha256"])
        for field in (*session.FALSE_AUTHORIZATION_FIELDS, "session_start_authorized"):
            self.assertFalse(proposal[field])
        self.assertEqual("proposal-only", proposal["mode"])
        self.assertEqual("disposable-git-worktree", proposal["workspace"]["kind"])
        self.assertEqual("validated-disposable-git-worktree", proposal["prepared_workspace"]["kind"])
        self.assertEqual(worktree_digest, proposal["prepared_workspace"]["receipt_sha256"])
        self.assertFalse(proposal["capabilities"]["network_access"])
        self.assertFalse(proposal["workspace"]["git_index_writes"])
        self.assertIn("disposable_worktree_validation", proposal["required_external_controls"])
        self.assertIn("human_implementation_review", proposal["required_external_controls"])

    def test_wrong_digest_and_rehashed_authorization_injection_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            with self.assertRaisesRegex(ValueError, "does not match"):
                session.build_proposal(
                    repo,
                    handoff,
                    "0" * 64,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    temp / "wrong.json",
                    session.load_policies(),
                )
            altered = json.loads(handoff.read_text(encoding="utf-8"))
            altered["implementation_authorized"] = True
            handoff.write_text(json.dumps(altered), encoding="utf-8")
            altered_digest = session.sha256_bytes(handoff.read_bytes())
            with self.assertRaisesRegex(ValueError, "metadata"):
                session.build_proposal(
                    repo,
                    handoff,
                    altered_digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    temp / "altered.json",
                    session.load_policies(),
                )
            self.assertFalse((temp / "wrong.json").exists())
            self.assertFalse((temp / "altered.json").exists())

    def test_tampered_handoff_manifest_and_content_are_rejected_even_when_rehashed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            for expected, mutate in [
                (
                    "run snapshot",
                    lambda value: value["run_manifest"][0].update(sha256="0" * 64),
                ),
                (
                    "content record",
                    lambda value: value["artifacts"][0].update(content="changed"),
                ),
            ]:
                with self.subTest(expected=expected):
                    value = json.loads(handoff.read_text(encoding="utf-8"))
                    mutate(value)
                    candidate = temp / f"{expected.replace(' ', '-')}.json"
                    candidate.write_text(json.dumps(value), encoding="utf-8")
                    candidate_digest = session.sha256_bytes(candidate.read_bytes())
                    with self.assertRaisesRegex(ValueError, expected):
                        session.build_proposal(
                            repo,
                            candidate,
                            candidate_digest,
                            workspace,
                            worktree_receipt,
                            worktree_digest,
                            temp / f"{expected}.proposal.json",
                            session.load_policies(),
                        )

            value = json.loads(handoff.read_text(encoding="utf-8"))
            plan = next(record for record in value["artifacts"] if record["name"] == "plan.md")
            plan["content"] = plan["content"].replace("# Stop Conditions", "## Stop Conditions")
            encoded = plan["content"].encode("utf-8")
            plan["sha256"] = session.sha256_bytes(encoded)
            plan["size_bytes"] = len(encoded)
            manifest_plan = next(
                record for record in value["run_manifest"] if record["name"] == "plan.md"
            )
            manifest_plan["sha256"] = plan["sha256"]
            manifest_plan["size_bytes"] = plan["size_bytes"]
            value["run_snapshot_sha256"] = session.manifest_snapshot_sha256(value["run_manifest"])
            candidate = temp / "invalid-plan.json"
            candidate.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "artifact does not satisfy"):
                session.build_proposal(
                    repo,
                    candidate,
                    session.sha256_bytes(candidate.read_bytes()),
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    temp / "invalid-plan-proposal.json",
                    session.load_policies(),
                )

    def test_clean_workspace_with_different_bound_policy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(
                temp,
                binding_mismatch=True,
            )
            output = temp / "proposal.json"
            result = session.build_proposal(
                repo,
                handoff,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                output,
                session.load_policies(),
            )

        self.assertFalse(result["produced"])
        self.assertFalse(output.exists())
        self.assertIn("bound_policy_mismatch", [item["rule"] for item in result["failures"]])

    def test_dirty_repo_head_mismatch_and_oversize_do_not_write_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            output = temp / "dirty.json"
            result = session.build_proposal(
                repo,
                handoff,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                output,
                session.load_policies(),
            )
            self.assertIn("clean_worktree", [item["rule"] for item in result["failures"]])
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            (repo / "README.md").write_text("next\n", encoding="utf-8")
            git(repo, "add", "README.md")
            git(repo, "commit", "-m", "next")
            output = temp / "mismatch.json"
            result = session.build_proposal(
                repo,
                handoff,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                output,
                session.load_policies(),
            )
            self.assertIn("repo_head_match", [item["rule"] for item in result["failures"]])
            self.assertFalse(output.exists())

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            policies = session.load_policies()
            policies["session"]["max_proposal_bytes"] = 1
            output = temp / "large.json"
            result = session.build_proposal(
                repo,
                handoff,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                output,
                policies,
            )
            self.assertIn("max_proposal_bytes", [item["rule"] for item in result["failures"]])
            self.assertFalse(output.exists())

    def test_invalid_prepared_worktree_blocks_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            (workspace / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            output = temp / "proposal.json"
            result = session.build_proposal(
                repo,
                handoff,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                output,
                session.load_policies(),
            )

        self.assertFalse(result["produced"])
        self.assertFalse(output.exists())
        self.assertIn(
            "disposable_worktree_validation",
            [item["rule"] for item in result["failures"]],
        )

    def test_prompt_contract_and_state_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            prompts = temp / "prompts"
            prompts.mkdir()
            prompt = prompts / "implementation" / "implement.md"
            prompt.parent.mkdir()
            prompt.write_text(
                (REPO_ROOT / ".agent" / "prompts" / "implementation" / "implement.md")
                .read_text(encoding="utf-8")
                .replace("Do not access the network", "Network may be used"),
                encoding="utf-8",
            )
            with mock.patch.object(session, "PROMPTS_DIR", prompts), self.assertRaisesRegex(
                ValueError,
                "missing required literals",
            ):
                session.build_proposal(
                    repo,
                    handoff,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    temp / "bad-prompt.json",
                    session.load_policies(),
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            original = session.binding_record
            changed = False

            def drifting_binding(repo_root: Path, name: str) -> dict[str, object]:
                nonlocal changed
                record = original(repo_root, name)
                if not changed:
                    handoff.write_text(handoff.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                    changed = True
                return record

            output = temp / "drift.json"
            with mock.patch.object(session, "binding_record", side_effect=drifting_binding):
                result = session.build_proposal(
                    repo,
                    handoff,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    output,
                    session.load_policies(),
                )
            self.assertIn("state_changed", [item["rule"] for item in result["failures"]])
            self.assertFalse(output.exists())

    def test_refuses_internal_handoff_output_symlink_existing_and_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            inside = repo / "handoff.json"
            shutil.copyfile(handoff, inside)
            with self.assertRaisesRegex(ValueError, "outside"):
                session.build_proposal(
                    repo,
                    inside,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    temp / "inside.json",
                    session.load_policies(),
                )
            with self.assertRaisesRegex(ValueError, "outside"):
                session.build_proposal(
                    repo,
                    handoff,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    repo / "proposal.json",
                    session.load_policies(),
                )
            existing = temp / "existing.json"
            existing.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                session.build_proposal(
                    repo,
                    handoff,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    existing,
                    session.load_policies(),
                )
            self.assertEqual("keep", existing.read_text(encoding="utf-8"))

            link = temp / "handoff-link.json"
            try:
                link.symlink_to(handoff)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                session.build_proposal(
                    repo,
                    link,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    temp / "linked.json",
                    session.load_policies(),
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            completed = cli(
                repo,
                handoff,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                temp / "proposal.json",
                "--session-policy",
                "untrusted",
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("unrecognized arguments", completed.stderr)

    def test_cli_produces_external_proposal_without_starting_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, handoff, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            output = temp / "proposal.json"
            completed = cli(repo, handoff, digest, workspace, worktree_receipt, worktree_digest, output)
            result = json.loads(completed.stdout)

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(result["produced"])
        self.assertFalse(result["session_start_authorized"])
        self.assertFalse(result["agent_invocation_authorized"])


if __name__ == "__main__":
    unittest.main()
