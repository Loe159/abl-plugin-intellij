#!/usr/bin/env python3
"""Prove independent validation of implementation quality-gate receipts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

import initialize_portable_run
import run_implementation_quality_gate
import validate_implementation_patch
import validate_implementation_quality_gate
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-quality-gate-validation-proof.json"
)
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_quality_gate_receipt_validation_proof",
    "mode": "enforcement-proof",
    "proven_control": "quality_gate_receipt_validation",
    "unproven_controls": [
        "implementation_quality_gate_execution",
        "historical_quality_gate_output_authenticity",
        "quality_gate_network_isolation",
        "quality_gate_descendant_cleanup",
    ],
    "bindings": [
        ".agent/checks/run_implementation_quality_gate.py",
        ".agent/policies/implementation-quality-gate.json",
        ".agent/checks/validate_implementation_quality_gate.py",
        ".agent/policies/implementation-quality-gate-validation.json",
        ".agent/checks/prove_implementation_quality_gate_validation.py",
        ".agent/policies/implementation-quality-gate-validation-proof.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Quality-gate validation proof policy does not match")
    return policy


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def execution(returncode: int) -> dict[str, Any]:
    return {
        "completed": True,
        "timed_out": False,
        "output_limit_exceeded": False,
        "tree_kill_requested": False,
        "tree_kill_returncode": None,
        "direct_kill_requested": False,
        "root_reaped": True,
        "returncode": returncode,
        "capture_complete": True,
        "stdout": b"fixture-output",
        "stderr": b"",
        "captured_stdout_bytes": 14,
        "captured_stderr_bytes": 0,
        "duration_seconds": 0.01,
    }


def prepare_fixture(root: Path, returncode: int) -> dict[str, Any]:
    workspace = root / "workspace"
    workspace.mkdir()
    git(workspace, "init")
    git(workspace, "config", "user.email", "proof@example.invalid")
    git(workspace, "config", "user.name", "Proof Fixture")
    (workspace / "app.txt").write_text("base\n", encoding="utf-8")
    (workspace / "gradlew.bat").write_text("@echo off\r\nexit /b 0\r\n", encoding="ascii")
    git(workspace, "add", "app.txt", "gradlew.bat")
    git(workspace, "commit", "-m", "base")
    base = git(workspace, "rev-parse", "HEAD")
    (workspace / "app.txt").write_text("base\nchange\n", encoding="utf-8")
    workspace = workspace.resolve()
    identity = {
        "issue": 63,
        "risk": "medium",
        "base_commit": base,
        "workspace": str(workspace),
        "runner_id": "quality-gate-validation-proof",
        "preflight_sha256": "2" * 64,
        "start_authorization_receipt_sha256": "3" * 64,
    }
    result_value = {
        "result_version": 1,
        "purpose": "implementation_session_result",
        "mode": "untrusted-runner-output",
        "status": "completed",
        **identity,
        "summary": "Synthetic quality-gate receipt validation fixture.",
        "workspace_changed": True,
        "patch_generated": False,
        "deterministic_checks_run": False,
        "publication_requested": False,
        "network_requested": False,
        "next_action": "deterministic_patch_generation",
    }
    fixture = {
        "workspace": workspace,
        "result": root / "result.json",
        "session": root / "session.json",
        "patch": root / "candidate.patch",
        "patch_receipt": root / "patch-receipt.json",
        "quality_receipt": root / "quality-receipt.json",
        "gradle_home": root / "gradle-home",
    }
    fixture["result"].write_bytes(
        validate_implementation_result.canonical_result_bytes(result_value)
    )
    fixture["session"].write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    patch_result = validate_implementation_patch.validate_patch(
        REPO_ROOT,
        validate_implementation_patch.captured_execution(
            fixture["result"].read_bytes(),
            b"",
        ),
        identity,
        fixture["patch"],
        fixture["patch_receipt"],
        validate_implementation_patch.load_policy(),
    )
    distribution = (
        fixture["gradle_home"]
        / "wrapper"
        / "dists"
        / "gradle-8.11.1-bin"
        / "fixture"
        / "gradle-8.11.1"
        / "bin"
    )
    distribution.mkdir(parents=True)
    (distribution / "gradle.bat").write_text("@echo off\r\n", encoding="ascii")
    quality_result = run_implementation_quality_gate.execute(
        REPO_ROOT,
        fixture["result"],
        fixture["session"],
        fixture["patch"],
        fixture["patch_receipt"],
        patch_result["receipt_sha256"],
        fixture["quality_receipt"],
        fixture["gradle_home"],
        run_implementation_quality_gate.load_policy(),
        parent_environment={
            "COMSPEC": os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
            "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        },
        which=lambda _name: r"C:\Windows\System32\taskkill.exe",
        command_runner=mock.Mock(return_value=execution(returncode)),
    )
    fixture.update(
        patch_receipt_sha256=patch_result["receipt_sha256"],
        quality_receipt_sha256=quality_result["receipt_sha256"],
    )
    return fixture


def validate_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    return validate_implementation_quality_gate.validate(
        REPO_ROOT,
        fixture["result"],
        fixture["session"],
        fixture["patch"],
        fixture["patch_receipt"],
        fixture["patch_receipt_sha256"],
        fixture["quality_receipt"],
        fixture["quality_receipt_sha256"],
        fixture["gradle_home"],
        validate_implementation_quality_gate.load_policy(),
    )


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    with tempfile.TemporaryDirectory(prefix="passed-quality-receipt-") as temp_dir:
        passed = validate_fixture(prepare_fixture(Path(temp_dir), 0))
    with tempfile.TemporaryDirectory(prefix="failed-quality-receipt-") as temp_dir:
        failed = validate_fixture(prepare_fixture(Path(temp_dir), 1))
    with tempfile.TemporaryDirectory(prefix="tampered-quality-receipt-") as temp_dir:
        fixture = prepare_fixture(Path(temp_dir), 0)
        value = json.loads(fixture["quality_receipt"].read_text(encoding="utf-8"))
        value["commands"][0]["tasks"] = ["publishPlugin"]
        fixture["quality_receipt"].write_bytes(
            validate_implementation_patch.canonical_bytes(value)
        )
        fixture["quality_receipt_sha256"] = (
            validate_implementation_result.sha256_bytes(
                fixture["quality_receipt"].read_bytes()
            )
        )
        tampered = validate_fixture(fixture)
    fixtures = [
        {
            "id": "passed_receipt_valid",
            "matched": passed["valid"] is True and passed["quality_gate_passed"] is True,
        },
        {
            "id": "failed_receipt_valid",
            "matched": failed["valid"] is True and failed["quality_gate_passed"] is False,
        },
        {
            "id": "rehashed_command_tampering_rejected",
            "matched": (
                tampered["valid"] is False
                and any(
                    item["rule"] in {"command_record", "not_run_command"}
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
            "revalidates_candidate_patch": True,
            "validates_receipt_digest": True,
            "validates_command_sequence": True,
            "validates_current_bindings": True,
            "proves_historical_output_authenticity": False,
            "runs_gradle": False,
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
        f"implementation-quality-gate-validation-proof: {assessment.upper()}",
        "implementation_quality_gate_execution=not_proven",
        "historical_quality_gate_output_authenticity=not_proven",
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
        print(f"implementation-quality-gate-validation-proof: ERROR\n- {error}", file=sys.stderr)
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
