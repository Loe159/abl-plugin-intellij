#!/usr/bin/env python3
"""Prove independent validation of implementation patch receipts."""

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
import validate_implementation_patch_receipt
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-patch-post-validation-validation-proof.json"
)
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_patch_post_validation_receipt_validation_proof",
    "mode": "enforcement-proof",
    "proven_control": "implementation_patch_receipt_validation",
    "unproven_controls": [
        "runner_enforced_output_post_validation",
        "implementation_quality_gate_execution",
        "real_agent_patch_post_validation",
    ],
    "bindings": [
        ".agent/checks/validate_implementation_patch.py",
        ".agent/policies/implementation-patch-post-validation.json",
        ".agent/checks/validate_implementation_patch_receipt.py",
        ".agent/policies/implementation-patch-post-validation-validation.json",
        ".agent/checks/prove_implementation_patch_receipt_validation.py",
        ".agent/policies/implementation-patch-post-validation-validation-proof.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation patch receipt proof policy does not match")
    return policy


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def prepare_fixture(root: Path, protected: bool) -> dict[str, Any]:
    workspace = root / "workspace"
    workspace.mkdir()
    git(workspace, "init")
    git(workspace, "config", "user.email", "proof@example.invalid")
    git(workspace, "config", "user.name", "Proof Fixture")
    (workspace / "app.txt").write_text("base\n", encoding="utf-8")
    git(workspace, "add", "app.txt")
    git(workspace, "commit", "-m", "base")
    base = git(workspace, "rev-parse", "HEAD")
    if protected:
        target = workspace / ".agent" / "blocked.txt"
        target.parent.mkdir()
        target.write_text("blocked\n", encoding="utf-8")
    else:
        (workspace / "app.txt").write_text("base\nchange\n", encoding="utf-8")
    workspace = workspace.resolve()
    identity = {
        "issue": 59,
        "risk": "medium",
        "base_commit": base,
        "workspace": str(workspace),
        "runner_id": "receipt-proof-runner",
        "preflight_sha256": "2" * 64,
        "start_authorization_receipt_sha256": "3" * 64,
    }
    result_value = {
        "result_version": 1,
        "purpose": "implementation_session_result",
        "mode": "untrusted-runner-output",
        "status": "completed",
        **identity,
        "summary": "Synthetic implementation completed; checks remain pending.",
        "workspace_changed": True,
        "patch_generated": False,
        "deterministic_checks_run": False,
        "publication_requested": False,
        "network_requested": False,
        "next_action": "deterministic_patch_generation",
    }
    result_path = root / "result.json"
    session_path = root / "session.json"
    patch = root / "candidate.patch"
    receipt = root / "receipt.json"
    result_path.write_bytes(
        validate_implementation_result.canonical_result_bytes(result_value)
    )
    session_path.write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    produced = validate_implementation_patch.validate_patch(
        REPO_ROOT,
        validate_implementation_patch.captured_execution(
            result_path.read_bytes(),
            b"",
        ),
        identity,
        patch,
        receipt,
        validate_implementation_patch.load_policy(),
    )
    return {
        "workspace": workspace,
        "result": result_path,
        "session": session_path,
        "patch": patch,
        "receipt": receipt,
        "receipt_sha256": produced["receipt_sha256"],
    }


def validate_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    return validate_implementation_patch_receipt.validate(
        REPO_ROOT,
        fixture["result"],
        fixture["session"],
        fixture["patch"],
        fixture["receipt"],
        fixture["receipt_sha256"],
        validate_implementation_patch_receipt.load_policy(),
    )


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    with tempfile.TemporaryDirectory(prefix="allowed-patch-receipt-") as temp_dir:
        allowed_fixture = prepare_fixture(Path(temp_dir), False)
        allowed = validate_fixture(allowed_fixture)
    with tempfile.TemporaryDirectory(prefix="blocked-patch-receipt-") as temp_dir:
        blocked_fixture = prepare_fixture(Path(temp_dir), True)
        blocked = validate_fixture(blocked_fixture)
    with tempfile.TemporaryDirectory(prefix="tampered-patch-receipt-") as temp_dir:
        tampered_fixture = prepare_fixture(Path(temp_dir), False)
        tampered_fixture["patch"].write_bytes(
            tampered_fixture["patch"].read_bytes() + b"\n"
        )
        tampered = validate_fixture(tampered_fixture)

    fixtures = [
        {
            "id": "allowed_receipt_valid",
            "matched": (
                allowed["valid"] is True
                and allowed["patch_candidate_ready"] is True
                and allowed["patch_policy_allowed"] is True
            ),
        },
        {
            "id": "policy_blocked_receipt_valid",
            "matched": (
                blocked["valid"] is True
                and blocked["patch_candidate_ready"] is False
                and blocked["patch_policy_allowed"] is False
                and blocked["risk"] == "high"
                and blocked["route"] == "C"
            ),
        },
        {
            "id": "tampered_patch_rejected",
            "matched": (
                tampered["valid"] is False
                and any(
                    item["rule"] == "patch_record"
                    for item in tampered["failures"]
                )
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
            "validates_current_receipt_bytes": True,
            "revalidates_implementation_result": True,
            "revalidates_patch_against_worktree": True,
            "reclassifies_supervision_risk": True,
            "proves_historical_producer": False,
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
        f"implementation-patch-receipt-proof: {assessment.upper()}",
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
        print(f"implementation-patch-receipt-proof: ERROR\n- {error}", file=sys.stderr)
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
