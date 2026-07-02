#!/usr/bin/env python3
"""Prove selected supervised-runner sequencing on bounded local fixtures."""

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
import run_supervised_implementation


REPO_ROOT = Path(__file__).resolve().parents[2]

POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "supervised-runner-execution-proof.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
    "publication_authorized",
    "network_authorized",
    "merge_authorized",
)
EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "supervised_runner_execution_fixture_proof",
    "mode": "fixture-only",
    "proven_control": "runner_enforced_output_post_validation",
    "related_controls": [
        "supervised_runner_quality_gate_sequence",
        "cleanup_after_successful_runner_completion",
        "cleanup_after_controlled_blocked_completion",
        "cleanup_receipt_validation_after_runner_cleanup",
        "supervised_runner_consumption_launch_before_adapter_sequence",
        "final_receipt_validation_after_runner_write",
        "controlled_adapter_timeout_blocks_before_patch",
        "cleanup_after_controlled_adapter_timeout",
    ],
    "unproven_controls": [
        "real_agent_result_compatibility",
        "real_gradle_quality_gate_execution",
        "provider_credential_descendant_noninheritance",
        "network_isolation",
        "authorization_consumption_to_process_start_atomicity",
        "cleanup_after_failed_runner_completion",
        "cleanup_after_timeout_or_process_termination",
        "cleanup_after_host_crash",
    ],
    "bindings": [
        ".agent/checks/prove_supervised_runner_execution.py",
        ".agent/policies/supervised-runner-execution-proof.json",
        ".agent/checks/run_supervised_implementation.py",
        ".agent/policies/supervised-implementation-runner.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Supervised-runner execution proof policy does not match")
    return policy


def child_environment() -> dict[str, str]:
    return {
        "ALLUSERSPROFILE": os.environ.get("ALLUSERSPROFILE", r"C:\ProgramData"),
        "COMSPEC": os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
        "PATH": os.environ.get("PATH", ""),
        "PROGRAMDATA": os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
        "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", "C:"),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        "SECRET_TOKEN": "must-not-be-inherited",
    }


def output_paths(temp: Path) -> dict[str, Path]:
    out = temp / "out"
    out.mkdir(parents=True)
    return {
        "expected_session": out / "expected-session.json",
        "result": out / "result.json",
        "patch": out / "patch.diff",
        "patch_receipt": out / "patch-receipt.json",
        "quality_gate": out / "quality-gate.json",
        "final": out / "final-receipt.json",
        "cleanup": out / "cleanup-receipt.json",
        "gradle_home": out / "gradle-home",
    }


def allowed_adapter_command() -> list[str]:
    return [
        sys.executable,
        str(REPO_ROOT / ".agent" / "adapters" / "local_implementation_adapter.py"),
    ]


def execution(stdout: bytes) -> dict[str, Any]:
    return {
        "completed": True,
        "timed_out": False,
        "output_limit_exceeded": False,
        "kill_requested": False,
        "direct_child_reaped": True,
        "returncode": 0,
        "stdout": stdout,
        "stderr": b"",
        "capture_complete": True,
        "captured_stdout_bytes": len(stdout),
        "captured_stderr_bytes": 0,
    }


def timed_out_execution() -> dict[str, Any]:
    return {
        "completed": False,
        "timed_out": True,
        "output_limit_exceeded": False,
        "kill_requested": True,
        "direct_child_reaped": True,
        "returncode": None,
        "stdout": b"",
        "stderr": b"",
        "capture_complete": True,
        "captured_stdout_bytes": 0,
        "captured_stderr_bytes": 0,
    }


def result_bytes(session: dict[str, Any]) -> bytes:
    return run_supervised_implementation.validate_implementation_result.canonical_result_bytes(
        {
            "result_version": 1,
            "purpose": "implementation_session_result",
            "mode": "untrusted-runner-output",
            "status": "completed",
            **session,
            "summary": "Supervised runner execution fixture.",
            "workspace_changed": True,
            "patch_generated": False,
            "deterministic_checks_run": False,
            "publication_requested": False,
            "network_requested": False,
            "next_action": "deterministic_patch_generation",
        }
    )


def gate_pass(
    _source: Path,
    _result: Path,
    _session: Path,
    _patch: Path,
    _patch_receipt: Path,
    patch_receipt_sha256: str,
    quality_gate_receipt: Path,
    gradle_user_home: Path,
    _policy: dict[str, Any],
    **_kwargs: Any,
) -> dict[str, Any]:
    value = {
        "quality_gate_receipt_version": 1,
        "purpose": "implementation_quality_gate_execution",
        "mode": "controlled-gradle-execution-only",
        **{
            field: False
            for field in run_supervised_implementation.run_implementation_quality_gate.FALSE_FIELDS
        },
        "execution_attempted": True,
        "quality_gate_passed": True,
        "network_requested": False,
        "identity": {},
        "patch_receipt_sha256": patch_receipt_sha256,
        "patch_sha256": run_supervised_implementation.validate_implementation_result.sha256_bytes(
            _patch.read_bytes()
        ),
        "gradle_user_home": str(gradle_user_home),
        "commands": [],
        "bindings": [],
    }
    content = run_supervised_implementation.canonical_bytes(value)
    quality_gate_receipt.write_bytes(content)
    return {
        "execution_attempted": True,
        "quality_gate_passed": True,
        "receipt_written": True,
        "receipt_sha256": run_supervised_implementation.validate_implementation_result.sha256_bytes(
            content
        ),
        "commands": [],
        "failures": [],
    }


def cleanup_pass(
    _source: Path,
    workspace: Path,
    _receipt: Path,
    _receipt_sha256: str,
    cleanup_receipt: Path,
    _confirm_workspace: str,
    _policy: dict[str, Any],
    **_kwargs: Any,
) -> dict[str, Any]:
    value = {
        "cleanup_receipt_version": 1,
        "purpose": "disposable_implementation_worktree_cleanup",
        "mode": "fixture-only",
        "cleanup_performed": True,
        "workspace": str(workspace),
    }
    content = run_supervised_implementation.canonical_bytes(value)
    cleanup_receipt.write_bytes(content)
    return {
        "cleaned": True,
        "cleanup_receipt_sha256": (
            run_supervised_implementation.validate_implementation_result.sha256_bytes(
                content
            )
        ),
        "failures": [],
    }


def quality_gate_valid(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"valid": True, "quality_gate_passed": True, "failures": []}


def cleanup_valid(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {"valid": True, "failures": []}


def patch_candidate(
    _source_checkout: Path,
    _execution: dict[str, Any],
    _expected_session: dict[str, Any],
    patch_output: Path,
    receipt_output: Path,
    _policy: dict[str, Any],
) -> dict[str, Any]:
    patch_bytes = b"diff --git a/supervised-runner-proof.txt b/supervised-runner-proof.txt\n"
    receipt = {
        "post_validation_version": 1,
        "purpose": "implementation_patch_post_validation",
        "mode": "fixture-only",
        **{
            field: False
            for field in run_supervised_implementation.validate_implementation_patch.FALSE_FIELDS
        },
        "post_validation_complete": True,
        "patch_candidate_ready": True,
        "fixture": "supervised_runner_execution_proof",
    }
    receipt_bytes = run_supervised_implementation.canonical_bytes(receipt)
    patch_output.write_bytes(patch_bytes)
    receipt_output.write_bytes(receipt_bytes)
    return {
        "post_validation_complete": True,
        "patch_candidate_ready": True,
        "receipt_written": True,
        "receipt_sha256": run_supervised_implementation.validate_implementation_result.sha256_bytes(
            receipt_bytes
        ),
        "failures": [],
    }


def git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def write_json(path: Path, value: dict[str, Any]) -> str:
    content = run_supervised_implementation.canonical_bytes(value)
    path.write_bytes(content)
    return run_supervised_implementation.validate_implementation_result.sha256_bytes(content)


def fixture_values(
    temp: Path,
    authorization_name: str,
) -> tuple[
    tuple[Path, Path, str, Path, Path, str, Path, str, Path, str, Path, str],
    str,
]:
    repo = temp / "repo"
    repo.mkdir(exist_ok=True)
    if not (repo / ".git").is_dir():
        git(repo, "init")
        git(repo, "config", "user.email", "tests@example.invalid")
        git(repo, "config", "user.name", "Supervised Runner Fixture")
        (repo / "README.md").write_text("base\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-m", "base")
    base_commit = git(repo, "rev-parse", "HEAD")
    workspace = temp / "workspace"
    workspace.mkdir(exist_ok=True)
    proposal = temp / "proposal.json"
    worktree_receipt = temp / "worktree-receipt.json"
    approval_receipt = temp / "approval-receipt.json"
    preflight = temp / "preflight.json"
    authorization_receipt = temp / authorization_name
    proposal_sha = write_json(proposal, {"fixture": "proposal"})
    worktree_sha = write_json(worktree_receipt, {"fixture": "worktree"})
    approval_sha = write_json(approval_receipt, {"fixture": "approval"})
    preflight_sha = write_json(preflight, {"fixture": "preflight"})
    authorization_sha = write_json(authorization_receipt, {"fixture": authorization_name})
    return (
        (
            repo,
            proposal,
            proposal_sha,
            workspace,
            worktree_receipt,
            worktree_sha,
            approval_receipt,
            approval_sha,
            preflight,
            preflight_sha,
            authorization_receipt,
            authorization_sha,
        ),
        base_commit,
    )


def fixture_consumption(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    marker = Path(_args[10]).with_suffix(".consumed.json")
    marker_bytes = run_supervised_implementation.canonical_bytes({"fixture": "consumed"})
    marker.write_bytes(marker_bytes)
    return {
        "consumed": True,
        "consumption_marker": str(marker),
        "consumption_marker_sha256": (
            run_supervised_implementation.validate_implementation_result.sha256_bytes(
                marker_bytes
            )
        ),
    }


def fixture_launch(workspace: Path, base_commit: str) -> Any:
    def launch(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "launch_ready": True,
            "issue": 1,
            "risk": "low",
            "base_commit": base_commit,
            "workspace": str(workspace.resolve()),
            "candidate_runner": {"id": "fixture-local-runner"},
        }

    return launch


def invalid_output_fixture(
    values: tuple[Path, Path, str, Path, Path, str, Path, str, Path, str, Path, str],
    out: dict[str, Path],
    launch_readiness_runner: Any,
) -> dict[str, Any]:
    gate_called = False
    events: list[str] = []

    def gate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal gate_called
        gate_called = True
        return {}

    def consumption(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        events.append("consume_authorization")
        return fixture_consumption(*_args, **_kwargs)

    def launch(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        events.append("check_launch_readiness")
        return launch_readiness_runner(*_args, **_kwargs)

    def adapter(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        events.append("run_adapter")
        return execution(b"not json\n")

    result = run_supervised_implementation.run_supervised(
        *values,
        allowed_adapter_command(),
        out["expected_session"],
        out["result"],
        out["patch"],
        out["patch_receipt"],
        out["quality_gate"],
        out["final"],
        out["gradle_home"],
        run_supervised_implementation.load_policy(),
        cleanup_receipt_output=out["cleanup"],
        parent_environment=child_environment(),
        consumption_runner=consumption,
        launch_readiness_runner=launch,
        adapter_runner=adapter,
        quality_gate_executor=gate,
        cleanup_runner=cleanup_pass,
        cleanup_validator=cleanup_valid,
    )
    receipt = json.loads(out["final"].read_text(encoding="utf-8"))
    matched = (
        result["stage"] == "implementation_result"
        and result["implementation_result_valid"] is False
        and result["cleanup_performed"] is True
        and result["cleanup_receipt_valid"] is True
        and result["cleanup_required"] is False
        and out["result"].exists() is False
        and out["patch"].exists() is False
        and out["cleanup"].is_file()
        and gate_called is False
        and events
        == ["consume_authorization", "check_launch_readiness", "run_adapter"]
        and receipt["stage"] == "implementation_result"
        and result["final_receipt_valid"] is True
        and receipt["cleanup_performed"] is True
        and "cleanup_receipt" in receipt["artifacts"]
    )
    return {
        "id": "invalid_output_rejected_before_retention",
        "matched": matched,
        "stage": result["stage"],
        "result_written": out["result"].exists(),
        "patch_written": out["patch"].exists(),
        "cleanup_performed": result["cleanup_performed"],
        "cleanup_receipt_valid": result["cleanup_receipt_valid"],
        "final_receipt_valid": result["final_receipt_valid"],
        "quality_gate_called": gate_called,
        "events": events,
    }


def controlled_timeout_fixture(
    values: tuple[Path, Path, str, Path, Path, str, Path, str, Path, str, Path, str],
    out: dict[str, Path],
    launch_readiness_runner: Any,
) -> dict[str, Any]:
    gate_called = False
    patch_called = False

    def gate(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal gate_called
        gate_called = True
        return {}

    def patch_validator(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal patch_called
        patch_called = True
        return {}

    def adapter(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return timed_out_execution()

    result = run_supervised_implementation.run_supervised(
        *values,
        allowed_adapter_command(),
        out["expected_session"],
        out["result"],
        out["patch"],
        out["patch_receipt"],
        out["quality_gate"],
        out["final"],
        out["gradle_home"],
        run_supervised_implementation.load_policy(),
        cleanup_receipt_output=out["cleanup"],
        parent_environment=child_environment(),
        consumption_runner=fixture_consumption,
        launch_readiness_runner=launch_readiness_runner,
        adapter_runner=adapter,
        patch_validator=patch_validator,
        quality_gate_executor=gate,
        cleanup_runner=cleanup_pass,
        cleanup_validator=cleanup_valid,
    )
    receipt = json.loads(out["final"].read_text(encoding="utf-8"))
    matched = (
        result["stage"] == "implementation_result"
        and result["adapter_executed"] is True
        and result["implementation_result_valid"] is False
        and result["cleanup_performed"] is True
        and result["cleanup_receipt_valid"] is True
        and result["cleanup_required"] is False
        and out["result"].exists() is False
        and out["patch"].exists() is False
        and out["patch_receipt"].exists() is False
        and out["quality_gate"].exists() is False
        and out["cleanup"].is_file()
        and patch_called is False
        and gate_called is False
        and receipt["stage"] == "implementation_result"
        and result["final_receipt_valid"] is True
        and receipt["cleanup_performed"] is True
        and "cleanup_receipt" in receipt["artifacts"]
    )
    return {
        "id": "controlled_adapter_timeout_rejected_before_patch",
        "matched": matched,
        "stage": result["stage"],
        "adapter_executed": result["adapter_executed"],
        "implementation_result_valid": result["implementation_result_valid"],
        "result_written": out["result"].exists(),
        "patch_written": out["patch"].exists(),
        "patch_receipt_written": out["patch_receipt"].exists(),
        "quality_gate_written": out["quality_gate"].exists(),
        "cleanup_performed": result["cleanup_performed"],
        "cleanup_receipt_valid": result["cleanup_receipt_valid"],
        "final_receipt_valid": result["final_receipt_valid"],
        "patch_called": patch_called,
        "quality_gate_called": gate_called,
    }


def candidate_quality_gate_fixture(
    values: tuple[Path, Path, str, Path, Path, str, Path, str, Path, str, Path, str],
    out: dict[str, Path],
    launch_readiness_runner: Any,
) -> dict[str, Any]:
    def adapter(_command: Any, workspace: Path, *_args: Any) -> dict[str, Any]:
        session = json.loads(out["expected_session"].read_text(encoding="utf-8"))
        (workspace / "supervised-runner-proof.txt").write_text("changed\n", encoding="utf-8")
        return execution(result_bytes(session))

    with mock.patch.object(
        run_supervised_implementation.validate_implementation_quality_gate,
        "validate",
        side_effect=quality_gate_valid,
    ):
        result = run_supervised_implementation.run_supervised(
            *values,
            allowed_adapter_command(),
            out["expected_session"],
            out["result"],
            out["patch"],
            out["patch_receipt"],
            out["quality_gate"],
            out["final"],
            out["gradle_home"],
            run_supervised_implementation.load_policy(),
            cleanup_receipt_output=out["cleanup"],
            parent_environment=child_environment(),
            consumption_runner=fixture_consumption,
            launch_readiness_runner=launch_readiness_runner,
            adapter_runner=adapter,
            patch_validator=patch_candidate,
            quality_gate_executor=gate_pass,
            cleanup_runner=cleanup_pass,
            cleanup_validator=cleanup_valid,
        )
    receipt = json.loads(out["final"].read_text(encoding="utf-8"))
    matched = (
        result["runner_complete"] is True
        and result["patch_candidate_ready"] is True
        and result["quality_gate_executed"] is True
        and result["quality_gate_receipt_valid"] is True
        and result["cleanup_performed"] is True
        and result["cleanup_receipt_valid"] is True
        and result["cleanup_required"] is False
        and out["patch"].is_file()
        and out["quality_gate"].is_file()
        and out["cleanup"].is_file()
        and receipt["runner_complete"] is True
        and result["final_receipt_valid"] is True
        and receipt["cleanup_performed"] is True
        and "cleanup_receipt" in receipt["artifacts"]
    )
    return {
        "id": "candidate_patch_reaches_quality_gate_sequence",
        "matched": matched,
        "stage": result["stage"],
        "patch_candidate_ready": result["patch_candidate_ready"],
        "quality_gate_executed": result["quality_gate_executed"],
        "quality_gate_receipt_valid": result["quality_gate_receipt_valid"],
        "cleanup_performed": result["cleanup_performed"],
        "cleanup_receipt_valid": result["cleanup_receipt_valid"],
        "final_receipt_valid": result["final_receipt_valid"],
    }


def prove(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        invalid_values, invalid_base = fixture_values(temp, "session-start-authorization.json")
        candidate_values, candidate_base = fixture_values(
            temp,
            "session-start-authorization-candidate.json",
        )
        timeout_values, timeout_base = fixture_values(
            temp,
            "session-start-authorization-timeout.json",
        )
        invalid = invalid_output_fixture(
            invalid_values,
            output_paths(temp / "invalid"),
            fixture_launch(invalid_values[3], invalid_base),
        )
        timeout = controlled_timeout_fixture(
            timeout_values,
            output_paths(temp / "timeout"),
            fixture_launch(timeout_values[3], timeout_base),
        )
        candidate = candidate_quality_gate_fixture(
            candidate_values,
            output_paths(temp / "candidate"),
            fixture_launch(candidate_values[3], candidate_base),
        )
    enforcement_verified = invalid["matched"] is True
    quality_gate_sequence = candidate["matched"] is True
    blocked_cleanup = invalid["matched"] is True
    consumption_launch_adapter_sequence = (
        invalid["events"]
        == ["consume_authorization", "check_launch_readiness", "run_adapter"]
    )
    final_receipt_validation = (
        invalid["final_receipt_valid"] is True
        and timeout["final_receipt_valid"] is True
        and candidate["final_receipt_valid"] is True
    )
    controlled_timeout_blocks_before_patch = timeout["matched"] is True
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "executes_supervised_runner": True,
            "uses_fixture_adapter": True,
            "uses_fixture_patch_validator": True,
            "uses_fixture_quality_gate_executor": True,
            "uses_fixture_cleanup_runner": True,
            "validates_invalid_output_before_retention": enforcement_verified,
            "observes_quality_gate_sequence_after_patch_candidate": quality_gate_sequence,
            "observes_cleanup_after_successful_completion": quality_gate_sequence,
            "observes_cleanup_after_controlled_blocked_completion": blocked_cleanup,
            "observes_cleanup_receipt_validation_after_cleanup": (
                quality_gate_sequence and blocked_cleanup
            ),
            "observes_consumption_launch_before_adapter_sequence": (
                consumption_launch_adapter_sequence
            ),
            "observes_final_receipt_validation_after_write": final_receipt_validation,
            "observes_controlled_adapter_timeout_blocks_before_patch": (
                controlled_timeout_blocks_before_patch
            ),
            "observes_cleanup_after_controlled_adapter_timeout": (
                controlled_timeout_blocks_before_patch
            ),
            "runs_real_agent": False,
            "runs_real_gradle": False,
            "proves_network_isolation": False,
            "proves_provider_credential_descendant_noninheritance": False,
            "proves_cleanup_after_failure_timeout_or_crash": False,
        },
        "fixtures": [invalid, timeout, candidate],
        "control_assessments": [
            {
                "id": policy["proven_control"],
                "assessment": "verified_enforcement" if enforcement_verified else "not_proven",
            },
            {
                "id": "supervised_runner_quality_gate_sequence",
                "assessment": "verified_fixture" if quality_gate_sequence else "not_proven",
            },
            {
                "id": "cleanup_after_successful_runner_completion",
                "assessment": "verified_fixture" if quality_gate_sequence else "not_proven",
            },
            {
                "id": "cleanup_after_controlled_blocked_completion",
                "assessment": "verified_fixture" if blocked_cleanup else "not_proven",
            },
            {
                "id": "cleanup_receipt_validation_after_runner_cleanup",
                "assessment": (
                    "verified_fixture"
                    if quality_gate_sequence and blocked_cleanup
                    else "not_proven"
                ),
            },
            {
                "id": "supervised_runner_consumption_launch_before_adapter_sequence",
                "assessment": (
                    "verified_fixture"
                    if consumption_launch_adapter_sequence
                    else "not_proven"
                ),
            },
            {
                "id": "final_receipt_validation_after_runner_write",
                "assessment": "verified_fixture" if final_receipt_validation else "not_proven",
            },
            {
                "id": "controlled_adapter_timeout_blocks_before_patch",
                "assessment": (
                    "verified_fixture"
                    if controlled_timeout_blocks_before_patch
                    else "not_proven"
                ),
            },
            {
                "id": "cleanup_after_controlled_adapter_timeout",
                "assessment": (
                    "verified_fixture"
                    if controlled_timeout_blocks_before_patch
                    else "not_proven"
                ),
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
        f"supervised-runner-execution-proof: {assessment.upper()}",
        "real_agent_result_compatibility=not_proven",
        "real_gradle_quality_gate_execution=not_proven",
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
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"supervised-runner-execution-proof: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["control_assessments"][0]["assessment"] == "verified_enforcement" else 2


if __name__ == "__main__":
    raise SystemExit(main())
