from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


CHECKS_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = CHECKS_DIR / "validate_implementation_session.py"
REPO_ROOT = CHECKS_DIR.parents[1]
sys.path.insert(0, str(CHECKS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))
SPEC = importlib.util.spec_from_file_location("validate_implementation_session", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)
import test_build_implementation_session as helpers


def prepare(temp: Path) -> tuple[Path, Path, str, Path, Path, str]:
    repo, handoff, digest, workspace, worktree_receipt, worktree_digest = helpers.prepare(temp)
    proposal = temp / "proposal.json"
    result = validator.build_implementation_session.build_proposal(
        repo,
        handoff,
        digest,
        workspace,
        worktree_receipt,
        worktree_digest,
        proposal,
        validator.build_implementation_session.load_policies(),
    )
    assert result["produced"]
    return repo, proposal, result["sha256"], workspace, worktree_receipt, worktree_digest


def cli(
    repo: Path,
    proposal: Path,
    digest: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_digest: str,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--repo",
            str(repo),
            "--proposal",
            str(proposal),
            "--proposal-sha256",
            digest,
            "--workspace",
            str(workspace),
            "--worktree-receipt",
            str(worktree_receipt),
            "--worktree-receipt-sha256",
            worktree_digest,
            "--format",
            "json",
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


class ValidateImplementationSessionTest(unittest.TestCase):
    def test_valid_proposal_is_accepted_without_authorization_or_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            before = helpers.git(repo, "status", "--porcelain=v1", "--untracked-files=all")
            result = validator.validate_proposal(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                validator.build_implementation_session.load_policies(),
            )
            after = helpers.git(repo, "status", "--porcelain=v1", "--untracked-files=all")

        self.assertTrue(result["valid"], result["failures"])
        self.assertEqual(before, after)
        for field in validator.FALSE_AUTHORIZATION_FIELDS:
            self.assertFalse(result[field])

    def test_handoff_proposal_and_validation_chain_remains_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            (
                repo,
                handoff,
                handoff_digest,
                workspace,
                worktree_receipt,
                worktree_digest,
            ) = helpers.prepare(temp)
            proposal = temp / "proposal.json"
            proposal_result = validator.build_implementation_session.build_proposal(
                repo,
                handoff,
                handoff_digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                proposal,
                validator.build_implementation_session.load_policies(),
            )
            result = validator.validate_proposal(
                repo,
                proposal,
                proposal_result["sha256"],
                workspace,
                worktree_receipt,
                worktree_digest,
                validator.build_implementation_session.load_policies(),
            )

        self.assertTrue(proposal_result["produced"])
        self.assertTrue(result["valid"], result["failures"])

    def test_wrong_digest_is_rejected_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo = temp / "repo"
            helpers.create_repo(repo)
            proposal = temp / "proposal.json"
            proposal.write_text("not json", encoding="utf-8")
            result = validator.validate_proposal(
                repo,
                proposal,
                "0" * 64,
                temp / "workspace",
                temp / "worktree-receipt.json",
                "0" * 64,
                validator.build_implementation_session.load_policies(),
            )

        self.assertEqual("proposal_sha256", result["failures"][0]["rule"])

    def test_rehashed_authorization_prompt_capability_and_budget_changes_are_rejected(self) -> None:
        mutations = [
            ("proposal_metadata", lambda value: value.update(session_start_authorized=True)),
            ("proposal_prompt", lambda value: value["prompt"].update(content="changed")),
            ("proposal_prompt", lambda value: value["prompt"].update(size_bytes=1.0)),
            (
                "proposal_capabilities",
                lambda value: value["capabilities"].update(network_access=True),
            ),
            (
                "proposal_capabilities",
                lambda value: value["capabilities"].update(network_access=0),
            ),
            ("proposal_budgets", lambda value: value["budgets"].update(max_turns=999)),
            ("proposal_budgets", lambda value: value["budgets"].update(max_turns=12.0)),
        ]
        for expected, mutate in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
                value = json.loads(proposal.read_text(encoding="utf-8"))
                mutate(value)
                proposal.write_text(json.dumps(value), encoding="utf-8")
                result = validator.validate_proposal(
                    repo,
                    proposal,
                    validator.build_implementation_session.sha256_bytes(proposal.read_bytes()),
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    validator.build_implementation_session.load_policies(),
                )

                self.assertFalse(result["valid"])
                self.assertIn(expected, [item["rule"] for item in result["failures"]])

    def test_rehashed_handoff_and_policy_bindings_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            value = json.loads(proposal.read_text(encoding="utf-8"))
            value["handoff"]["content"]["implementation_authorized"] = True
            proposal.write_text(json.dumps(value), encoding="utf-8")
            result = validator.validate_proposal(
                repo,
                proposal,
                validator.build_implementation_session.sha256_bytes(proposal.read_bytes()),
                workspace,
                worktree_receipt,
                worktree_digest,
                validator.build_implementation_session.load_policies(),
            )
            self.assertIn("proposal_handoff", [item["rule"] for item in result["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            value = json.loads(proposal.read_text(encoding="utf-8"))
            value["policy_bindings"][0]["sha256"] = "0" * 64
            proposal.write_text(json.dumps(value), encoding="utf-8")
            result = validator.validate_proposal(
                repo,
                proposal,
                validator.build_implementation_session.sha256_bytes(proposal.read_bytes()),
                workspace,
                worktree_receipt,
                worktree_digest,
                validator.build_implementation_session.load_policies(),
            )
            self.assertIn("proposal_policy_bindings", [item["rule"] for item in result["failures"]])

    def test_rehashed_prepared_workspace_record_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            value = json.loads(proposal.read_text(encoding="utf-8"))
            value["prepared_workspace"]["receipt_sha256"] = "0" * 64
            proposal.write_text(json.dumps(value), encoding="utf-8")
            result = validator.validate_proposal(
                repo,
                proposal,
                validator.build_implementation_session.sha256_bytes(proposal.read_bytes()),
                workspace,
                worktree_receipt,
                worktree_digest,
                validator.build_implementation_session.load_policies(),
            )

        self.assertFalse(result["valid"])
        self.assertIn("proposal_prepared_workspace", [item["rule"] for item in result["failures"]])

    def test_dirty_head_mismatch_and_workspace_policy_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
            dirty = validator.validate_proposal(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                validator.build_implementation_session.load_policies(),
            )
            self.assertIn("clean_worktree", [item["rule"] for item in dirty["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            (repo / "README.md").write_text("next\n", encoding="utf-8")
            helpers.git(repo, "add", "README.md")
            helpers.git(repo, "commit", "-m", "next")
            mismatch = validator.validate_proposal(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                validator.build_implementation_session.load_policies(),
            )
            self.assertIn("repo_head_match", [item["rule"] for item in mismatch["failures"]])

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            agents = repo / "AGENTS.md"
            agents.write_text(agents.read_text(encoding="utf-8") + "\nDrift.\n", encoding="utf-8")
            helpers.git(repo, "add", "AGENTS.md")
            helpers.git(repo, "commit", "-m", "drift")
            drift = validator.validate_proposal(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                validator.build_implementation_session.load_policies(),
            )
            rules = [item["rule"] for item in drift["failures"]]
            self.assertIn("proposal_policy_bindings", rules)
            self.assertIn("bound_policy_mismatch", rules)

    def test_state_change_during_validation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            original = validator.build_implementation_session.binding_records
            calls = 0

            def drifting_bindings(repo_root: Path, names: list[str]) -> list[dict[str, object]]:
                nonlocal calls
                records = original(repo_root, names)
                calls += 1
                if calls == 3:
                    proposal.write_text(proposal.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                return records

            with mock.patch.object(
                validator.build_implementation_session,
                "binding_records",
                side_effect=drifting_bindings,
            ):
                result = validator.validate_proposal(
                    repo,
                    proposal,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    validator.build_implementation_session.load_policies(),
                )

        self.assertFalse(result["valid"])
        self.assertIn("state_changed", [item["rule"] for item in result["failures"]])

    def test_refuses_internal_symlink_and_policy_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            inside = repo / "proposal.json"
            shutil.copyfile(proposal, inside)
            with self.assertRaisesRegex(ValueError, "outside"):
                validator.validate_proposal(
                    repo,
                    inside,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    validator.build_implementation_session.load_policies(),
                )
            link = temp / "proposal-link.json"
            try:
                link.symlink_to(proposal)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                validator.validate_proposal(
                    repo,
                    link,
                    digest,
                    workspace,
                    worktree_receipt,
                    worktree_digest,
                    validator.build_implementation_session.load_policies(),
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            completed = cli(
                repo,
                proposal,
                digest,
                workspace,
                worktree_receipt,
                worktree_digest,
                "--session-policy",
                "untrusted",
            )
            self.assertEqual(2, completed.returncode)
            self.assertIn("unrecognized arguments", completed.stderr)

    def test_cli_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            repo, proposal, digest, workspace, worktree_receipt, worktree_digest = prepare(temp)
            valid = cli(repo, proposal, digest, workspace, worktree_receipt, worktree_digest)
            proposal.write_text(proposal.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            invalid = cli(repo, proposal, digest, workspace, worktree_receipt, worktree_digest)

        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertTrue(json.loads(valid.stdout)["valid"])
        self.assertEqual(2, invalid.returncode)


if __name__ == "__main__":
    unittest.main()
