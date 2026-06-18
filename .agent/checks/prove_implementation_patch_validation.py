#!/usr/bin/env python3
"""Prove deterministic post-implementation patch generation and policy handling."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import initialize_portable_run
import validate_implementation_patch
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-patch-post-validation-proof.json"
)
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS
EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_patch_post_validation_proof",
    "mode": "enforcement-proof",
    "proven_control": "implementation_patch_post_validation",
    "unproven_controls": [
        "runner_enforced_output_post_validation",
        "implementation_quality_gate_execution",
        "real_agent_patch_post_validation",
    ],
    "bindings": [
        ".agent/checks/validate_implementation_patch.py",
        ".agent/policies/implementation-patch-post-validation.json",
        ".agent/checks/prove_implementation_patch_validation.py",
        ".agent/policies/implementation-patch-post-validation-proof.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation patch validation proof policy does not match")
    return policy


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def prepare_repo(
    root: Path,
    protected_change: bool,
    changed: bool = True,
) -> tuple[Path, str]:
    repo = root / "workspace"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.email", "proof@example.invalid")
    git(repo, "config", "user.name", "Proof Fixture")
    (repo / "app.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    git(repo, "commit", "-m", "base")
    base = git(repo, "rev-parse", "HEAD")
    if protected_change:
        protected = repo / ".agent"
        protected.mkdir()
        (protected / "blocked.txt").write_text("blocked\n", encoding="utf-8")
    elif changed:
        (repo / "app.txt").write_text("base\nchange\n", encoding="utf-8")
    return repo.resolve(), base


def session(repo: Path, base: str) -> dict[str, Any]:
    return {
        "issue": 58,
        "risk": "medium",
        "base_commit": base,
        "workspace": str(repo),
        "runner_id": "synthetic-runner",
        "preflight_sha256": "2" * 64,
        "start_authorization_receipt_sha256": "3" * 64,
    }


def result_bytes(identity: dict[str, Any]) -> bytes:
    value = {
        "result_version": 1,
        "purpose": "implementation_session_result",
        "mode": "untrusted-runner-output",
        "status": "completed",
        **identity,
        "summary": "Synthetic implementation completed; deterministic checks remain pending.",
        "workspace_changed": True,
        "patch_generated": False,
        "deterministic_checks_run": False,
        "publication_requested": False,
        "network_requested": False,
        "next_action": "deterministic_patch_generation",
    }
    return validate_implementation_result.canonical_result_bytes(value)


def run_fixture(root: Path, protected: bool) -> dict[str, Any]:
    repo, base = prepare_repo(root, protected)
    identity = session(repo, base)
    stdout = result_bytes(identity)
    result = validate_implementation_patch.validate_patch(
        REPO_ROOT,
        validate_implementation_patch.captured_execution(stdout, b""),
        identity,
        root / "patch.diff",
        root / "receipt.json",
        validate_implementation_patch.load_policy(),
    )
    return result


def run_empty_fixture(root: Path) -> dict[str, Any]:
    repo, base = prepare_repo(root, False, changed=False)
    identity = session(repo, base)
    stdout = result_bytes(identity)
    return validate_implementation_patch.validate_patch(
        REPO_ROOT,
        validate_implementation_patch.captured_execution(stdout, b""),
        identity,
        root / "patch.diff",
        root / "receipt.json",
        validate_implementation_patch.load_policy(),
    )


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    with tempfile.TemporaryDirectory(prefix="allowed-post-validation-") as allowed_dir:
        allowed = run_fixture(Path(allowed_dir), False)
    with tempfile.TemporaryDirectory(prefix="blocked-post-validation-") as blocked_dir:
        blocked = run_fixture(Path(blocked_dir), True)
    with tempfile.TemporaryDirectory(prefix="empty-post-validation-") as empty_dir:
        empty = run_empty_fixture(Path(empty_dir))
    with tempfile.TemporaryDirectory(prefix="invalid-result-") as invalid_dir:
        root = Path(invalid_dir)
        workspace, base = prepare_repo(root, False)
        identity = session(workspace, base)
        invalid_identity = dict(identity)
        invalid_identity["preflight_sha256"] = "4" * 64
        stdout = result_bytes(invalid_identity)
        patch = root / "patch.diff"
        receipt = root / "receipt.json"
        invalid = validate_implementation_patch.validate_patch(
            REPO_ROOT,
            validate_implementation_patch.captured_execution(stdout, b""),
            identity,
            patch,
            receipt,
            validate_implementation_patch.load_policy(),
        )
        invalid_outputs_absent = not patch.exists() and not receipt.exists()

    fixtures = [
        {
            "id": "allowed_complete_patch",
            "matched": (
                allowed["post_validation_complete"] is True
                and allowed["patch_candidate_ready"] is True
                and allowed["patch"]["policy_allowed"] is True
                and allowed["receipt_written"] is True
                and allowed["quality_gate"]["completed"] is False
            ),
        },
        {
            "id": "protected_path_policy_block",
            "matched": (
                blocked["post_validation_complete"] is True
                and blocked["patch_candidate_ready"] is False
                and blocked["patch"]["policy_allowed"] is False
                and blocked["risk"]["risk"] == "high"
                and blocked["risk"]["route"] == "C"
                and blocked["receipt_written"] is True
            ),
        },
        {
            "id": "empty_patch_not_candidate",
            "matched": (
                empty["post_validation_complete"] is True
                and empty["patch_candidate_ready"] is False
                and empty["patch"]["policy_allowed"] is True
                and empty["patch"]["nonempty"] is False
                and empty["receipt_written"] is True
            ),
        },
        {
            "id": "invalid_result_no_artifacts",
            "matched": (
                invalid["post_validation_complete"] is False
                and invalid["patch_candidate_ready"] is False
                and invalid_outputs_absent
            ),
        },
    ]
    verified = all(item["matched"] for item in fixtures)
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "revalidates_implementation_result": True,
            "generates_complete_patch": True,
            "applies_diff_policy": True,
            "classifies_supervision_risk": True,
            "runs_quality_gate": False,
            "invokes_agent": False,
            "publishes": False,
        },
        "fixtures": fixtures,
        "control_assessments": [
            {
                "id": policy["proven_control"],
                "assessment": "verified_enforcement" if verified else "not_proven",
            },
            *[
                {"id": control, "assessment": "not_proven"}
                for control in policy["unproven_controls"]
            ],
        ],
        "bindings": initialize_portable_run.binding_records(policy["bindings"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    assessment = result["control_assessments"][0]["assessment"]
    lines = [
        f"implementation-patch-validation-proof: {assessment.upper()}",
        "implementation_quality_gate_execution=not_proven",
        "runner_enforced_output_post_validation=not_proven",
    ]
    lines.extend(
        f"- {fixture['id']}: {'matched' if fixture['matched'] else 'not_matched'}"
        for fixture in result["fixtures"]
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prove(args.repo, load_policy())
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        print(f"implementation-patch-validation-proof: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return (
        0
        if result["control_assessments"][0]["assessment"] == "verified_enforcement"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
