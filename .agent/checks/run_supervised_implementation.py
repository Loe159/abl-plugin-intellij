#!/usr/bin/env python3
"""Run one minimal supervised local implementation session end to end."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import check_implementation_launch_readiness
import cleanup_disposable_worktree
import consume_implementation_session_start_authorization
import diff_policy
import initialize_portable_run
import isolated_process
import run_implementation_quality_gate
import validate_implementation_patch
import validate_implementation_quality_gate
import validate_disposable_worktree_cleanup
import validate_implementation_result
import validate_supervised_runner_receipt


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "supervised-implementation-runner.json"

FALSE_FIELDS = [
    "authorized",
    "publication_authorized",
    "network_authorized",
    "merge_authorized",
]

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "supervised_local_implementation_runner",
    "mode": "bounded-local-orchestration",
    "adapter_timeout_seconds": 600.0,
    "require_launch_ready": True,
    "require_consumed_authorization": True,
    "require_valid_implementation_result": True,
    "require_candidate_ready_result_for_patch": True,
    "require_candidate_ready_patch_for_quality_gate": True,
    "require_external_outputs": True,
    "require_outputs_outside_workspace": True,
    "require_absent_outputs": True,
    "require_distinct_outputs": True,
    "require_allowed_adapter_entrypoint": True,
    "adapter_entrypoint_interpreters": [
        "bash",
        "py",
        "python",
        "python.exe",
        "python3",
        "sh",
    ],
    "allowed_adapter_entrypoints": [
        ".agent/adapters/aider.sh",
        ".agent/adapters/claude-code.sh",
        ".agent/adapters/codex.sh",
        ".agent/adapters/local_implementation_adapter.py",
        ".agent/adapters/mini-swe-agent.sh",
        ".agent/adapters/opencode.sh",
    ],
    "write_result_only_after_valid_result": True,
    "write_final_receipt_on_blocked_stage": True,
    "allow_success_cleanup": True,
    "allow_blocked_cleanup": True,
    "network_requested": False,
    "publication_requested": False,
    "cleanup_performed": False,
    "bindings": [
        ".agent/checks/run_supervised_implementation.py",
        ".agent/policies/supervised-implementation-runner.json",
        ".agent/checks/isolated_process.py",
        ".agent/policies/parent-environment-isolation.json",
        ".agent/checks/consume_implementation_session_start_authorization.py",
        ".agent/policies/implementation-session-start-consumption.json",
        ".agent/checks/check_implementation_launch_readiness.py",
        ".agent/policies/implementation-launch-readiness.json",
        ".agent/checks/validate_implementation_result.py",
        ".agent/policies/implementation-result-validation.json",
        ".agent/checks/validate_implementation_patch.py",
        ".agent/policies/implementation-patch-post-validation.json",
        ".agent/checks/run_implementation_quality_gate.py",
        ".agent/policies/implementation-quality-gate.json",
        ".agent/checks/validate_implementation_quality_gate.py",
        ".agent/policies/implementation-quality-gate-validation.json",
        ".agent/checks/cleanup_disposable_worktree.py",
        ".agent/policies/disposable-worktree-cleanup.json",
        ".agent/checks/validate_disposable_worktree_cleanup.py",
        ".agent/policies/disposable-worktree-cleanup-validation.json",
        ".agent/checks/validate_supervised_runner_receipt.py",
        ".agent/policies/supervised-runner-receipt-validation.json",
        ".agent/adapters/aider.sh",
        ".agent/adapters/claude-code.sh",
        ".agent/adapters/codex.sh",
        ".agent/adapters/local_implementation_adapter.py",
        ".agent/adapters/mini-swe-agent.sh",
        ".agent/adapters/opencode.sh",
        ".agent/policies/local-implementation-adapter.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Supervised implementation runner policy does not match")
    return policy


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, separators=(",", ": ")).encode(
        "utf-8"
    ) + b"\n"


def write_exclusive(path: Path, content: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    return validate_implementation_result.sha256_bytes(path.read_bytes())


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"rule": rule, "message": message}
    item.update(details)
    return item


def is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def source_root(repo: Path) -> Path:
    return Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip()
    ).resolve()


def validate_outputs(
    source_checkout: Path,
    workspace: Path,
    outputs: Sequence[Path],
    policy: dict[str, Any],
) -> dict[str, Path]:
    labels = [
        "expected_session",
        "result",
        "patch",
        "patch_receipt",
        "quality_gate_receipt",
        "final_receipt",
    ]
    if len(outputs) != len(labels):
        raise ValueError("Output target list does not match")
    resolved: dict[str, Path] = {}
    seen: set[Path] = set()
    source_checkout = source_checkout.resolve()
    workspace = workspace.resolve()
    for label, output in zip(labels, outputs):
        if output.is_symlink():
            raise ValueError(f"{label} output must not be a symbolic link")
        parent = output.parent.resolve()
        if not parent.is_dir():
            raise ValueError(f"{label} output parent does not exist")
        path = (parent / output.name).resolve()
        if policy["require_external_outputs"] and is_relative_to(path, source_checkout):
            raise ValueError(f"{label} output must be outside the source checkout")
        if policy["require_outputs_outside_workspace"] and is_relative_to(path, workspace):
            raise ValueError(f"{label} output must be outside the implementation workspace")
        if policy["require_absent_outputs"] and path.exists():
            raise ValueError(f"{label} output already exists")
        if path in seen:
            raise ValueError("Output paths must be distinct")
        seen.add(path)
        resolved[label] = path
    return resolved


def validate_optional_cleanup_output(
    source_checkout: Path,
    workspace: Path,
    cleanup_receipt_output: Path | None,
    existing_outputs: dict[str, Path],
    policy: dict[str, Any],
) -> Path | None:
    if cleanup_receipt_output is None:
        return None
    path = cleanup_receipt_output.resolve()
    if cleanup_receipt_output.is_symlink():
        raise ValueError("cleanup_receipt output must not be a symbolic link")
    if not path.parent.is_dir():
        raise ValueError("cleanup_receipt output parent does not exist")
    if policy["require_external_outputs"] and is_relative_to(path, source_checkout):
        raise ValueError("cleanup_receipt output must be outside the source checkout")
    if policy["require_outputs_outside_workspace"] and is_relative_to(path, workspace):
        raise ValueError("cleanup_receipt output must be outside the implementation workspace")
    if policy["require_absent_outputs"] and path.exists():
        raise ValueError("cleanup_receipt output already exists")
    if path in set(existing_outputs.values()):
        raise ValueError("Output paths must be distinct")
    return path


def expected_session_from_launch(
    launch: dict[str, Any],
    preflight_sha256: str,
    authorization_receipt_sha256: str,
) -> dict[str, Any]:
    runner = launch.get("candidate_runner")
    session = {
        "issue": launch.get("issue"),
        "risk": launch.get("risk"),
        "base_commit": launch.get("base_commit"),
        "workspace": launch.get("workspace"),
        "runner_id": runner.get("id") if isinstance(runner, dict) else None,
        "preflight_sha256": preflight_sha256,
        "start_authorization_receipt_sha256": authorization_receipt_sha256,
    }
    return validate_implementation_result.validate_expected_session(session)


def adapter_entrypoint(
    source_checkout: Path,
    command: Sequence[str],
    policy: dict[str, Any],
) -> tuple[str, list[str]]:
    if not command:
        raise ValueError("Adapter command is required")
    first = Path(command[0]).name.lower()
    index = 1 if first in policy["adapter_entrypoint_interpreters"] else 0
    if len(command) <= index:
        raise ValueError("Adapter command entrypoint is missing")
    raw = Path(command[index])
    candidate = raw if raw.is_absolute() else source_checkout / raw
    if candidate.is_symlink():
        raise ValueError("Adapter command entrypoint must not be a symbolic link")
    candidate = candidate.resolve()
    for allowed in policy["allowed_adapter_entrypoints"]:
        for root in (source_checkout, REPO_ROOT):
            allowed_path = (root / allowed).resolve()
            if candidate == allowed_path and allowed_path.is_file():
                normalized = list(command)
                if index == 1:
                    interpreter = shutil.which(command[0])
                    if interpreter is None:
                        raise ValueError("Adapter command interpreter was not found")
                    normalized[0] = str(Path(interpreter).resolve())
                normalized[index] = str(allowed_path)
                return allowed, normalized
    raise ValueError("Adapter command entrypoint is not allowlisted")


def base_result(final_receipt: Path) -> dict[str, Any]:
    return {
        "runner_complete": False,
        "final_receipt_written": False,
        "final_receipt_valid": False,
        "final_receipt": str(final_receipt),
        "final_receipt_sha256": None,
        **{field: False for field in FALSE_FIELDS},
        "authorization_consumed": False,
        "launch_ready": False,
        "adapter_executed": False,
        "implementation_result_valid": False,
        "implementation_candidate_ready": False,
        "result_written": False,
        "patch_post_validation_complete": False,
        "patch_candidate_ready": False,
        "quality_gate_executed": False,
        "quality_gate_passed": False,
        "quality_gate_receipt_valid": False,
        "network_requested": False,
        "publication_requested": False,
        "cleanup_performed": False,
        "cleanup_receipt_valid": False,
        "cleanup_required": True,
        "stage": "initial",
        "issue": None,
        "risk": None,
        "base_commit": None,
        "workspace": None,
        "runner_id": None,
        "adapter_entrypoint": None,
        "consumption": None,
        "launch_readiness": None,
        "implementation_result_validation": None,
        "patch_validation": None,
        "quality_gate": None,
        "quality_gate_validation": None,
        "cleanup": None,
        "cleanup_validation": None,
        "final_receipt_validation": None,
        "artifacts": {},
        "failures": [],
    }


def final_receipt_value(
    result: dict[str, Any],
    expected_session: dict[str, Any] | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    return {
        "runner_receipt_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "runner_complete": result["runner_complete"],
        "stage": result["stage"],
        "identity": expected_session,
        "authorization_consumed": result["authorization_consumed"],
        "launch_ready": result["launch_ready"],
        "adapter_executed": result["adapter_executed"],
        "implementation_result_valid": result["implementation_result_valid"],
        "implementation_candidate_ready": result["implementation_candidate_ready"],
        "patch_post_validation_complete": result["patch_post_validation_complete"],
        "patch_candidate_ready": result["patch_candidate_ready"],
        "quality_gate_executed": result["quality_gate_executed"],
        "quality_gate_passed": result["quality_gate_passed"],
        "quality_gate_receipt_valid": result["quality_gate_receipt_valid"],
        "network_requested": policy["network_requested"],
        "publication_requested": policy["publication_requested"],
        "cleanup_performed": result["cleanup_performed"],
        "cleanup_receipt_valid": result["cleanup_receipt_valid"],
        "cleanup_required": result["cleanup_required"],
        "authorization_consumption_to_process_start_atomic": False,
        "cross_host_replay_prevention_enforced": False,
        "provider_credential_descendant_noninheritance_proven": False,
        "artifacts": result["artifacts"],
        "failures": result["failures"],
        "bindings": initialize_portable_run.binding_records(policy["bindings"]),
    }


def complete_with_receipt(
    result: dict[str, Any],
    expected_session: dict[str, Any] | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    receipt = Path(result["final_receipt"])
    content = canonical_bytes(final_receipt_value(result, expected_session, policy))
    write_exclusive(receipt, content)
    result.update(
        final_receipt_written=True,
        final_receipt_sha256=validate_implementation_result.sha256_bytes(content),
    )
    validation = validate_supervised_runner_receipt.validate(
        receipt,
        result["final_receipt_sha256"],
        validate_supervised_runner_receipt.load_policy(),
    )
    result["final_receipt_validation"] = validation
    result["final_receipt_valid"] = validation.get("valid") is True
    return result


def cleanup_then_complete(
    result: dict[str, Any],
    expected_session: dict[str, Any] | None,
    source_checkout: Path,
    workspace: Path,
    worktree_receipt: Path,
    worktree_receipt_sha256: str,
    cleanup_receipt_output: Path | None,
    cleanup_runner: Callable[..., dict[str, Any]],
    cleanup_validator: Callable[..., dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    if (
        cleanup_receipt_output is not None
        and policy["allow_blocked_cleanup"]
        and not result["cleanup_performed"]
    ):
        cleanup = cleanup_runner(
            source_checkout,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            cleanup_receipt_output,
            str(workspace),
            cleanup_disposable_worktree.load_policy(),
        )
        result["cleanup"] = cleanup
        result["cleanup_performed"] = cleanup.get("cleaned") is True
        result["cleanup_required"] = not result["cleanup_performed"]
        if cleanup.get("cleaned") is True:
            cleanup_validation = cleanup_validator(
                source_checkout,
                workspace,
                worktree_receipt,
                worktree_receipt_sha256,
                cleanup_receipt_output,
                cleanup["cleanup_receipt_sha256"],
                validate_disposable_worktree_cleanup.load_policy(),
            )
            result["cleanup_validation"] = cleanup_validation
            result["cleanup_receipt_valid"] = cleanup_validation.get("valid") is True
            result["artifacts"]["cleanup_receipt"] = {
                "path": str(cleanup_receipt_output),
                "sha256": cleanup["cleanup_receipt_sha256"],
            }
            if not result["cleanup_receipt_valid"]:
                result["failures"].append(
                    failure("cleanup_validation", "Cleanup receipt did not validate.")
                )
        else:
            result["failures"].append(
                failure("cleanup", "Disposable worktree cleanup did not complete.")
            )
    return complete_with_receipt(result, expected_session, policy)


def run_supervised(
    repo: Path,
    proposal: Path,
    proposal_sha256: str,
    workspace: Path,
    worktree_receipt: Path,
    worktree_receipt_sha256: str,
    approval_receipt: Path,
    approval_receipt_sha256: str,
    preflight: Path,
    preflight_sha256: str,
    authorization_receipt: Path,
    authorization_receipt_sha256: str,
    adapter_command: Sequence[str],
    expected_session_output: Path,
    result_output: Path,
    patch_output: Path,
    patch_receipt_output: Path,
    quality_gate_receipt_output: Path,
    final_receipt_output: Path,
    gradle_user_home: Path,
    policy: dict[str, Any],
    cleanup_receipt_output: Path | None = None,
    parent_environment: Mapping[str, str] = os.environ,
    consumption_runner: Callable[..., dict[str, Any]] = (
        consume_implementation_session_start_authorization.consume
    ),
    launch_readiness_runner: Callable[..., dict[str, Any]] = (
        check_implementation_launch_readiness.check_launch
    ),
    adapter_runner: Callable[..., dict[str, Any]] = isolated_process.run,
    patch_validator: Callable[..., dict[str, Any]] = validate_implementation_patch.validate_patch,
    quality_gate_executor: Callable[..., dict[str, Any]] = run_implementation_quality_gate.execute,
    cleanup_runner: Callable[..., dict[str, Any]] = cleanup_disposable_worktree.cleanup,
    cleanup_validator: Callable[..., dict[str, Any]] = validate_disposable_worktree_cleanup.validate,
    readiness_runner: Callable[[Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_checkout = source_root(repo)
    workspace = workspace.resolve()
    outputs = validate_outputs(
        source_checkout,
        workspace,
        [
            expected_session_output,
            result_output,
            patch_output,
            patch_receipt_output,
            quality_gate_receipt_output,
            final_receipt_output,
        ],
        policy,
    )
    cleanup_receipt_output = validate_optional_cleanup_output(
        source_checkout,
        workspace,
        cleanup_receipt_output,
        outputs,
        policy,
    )
    result = base_result(outputs["final_receipt"])
    expected_session: dict[str, Any] | None = None
    try:
        adapter_label, normalized_adapter_command = adapter_entrypoint(
            source_checkout,
            adapter_command,
            policy,
        )
        result["adapter_entrypoint"] = adapter_label
    except ValueError as error:
        if policy["require_allowed_adapter_entrypoint"]:
            result.update(stage="adapter_command")
            result["failures"].append(failure("adapter_command", str(error)))
            return complete_with_receipt(result, expected_session, policy)
        raise
    launch_policies = check_implementation_launch_readiness.load_policies()

    consumption = consumption_runner(
        source_checkout,
        proposal,
        proposal_sha256,
        workspace,
        worktree_receipt,
        worktree_receipt_sha256,
        approval_receipt,
        approval_receipt_sha256,
        preflight,
        preflight_sha256,
        authorization_receipt,
        authorization_receipt_sha256,
        launch_policies,
        readiness_runner,
    )
    result["consumption"] = consumption
    result["authorization_consumed"] = consumption.get("consumed") is True
    if policy["require_consumed_authorization"] and not result["authorization_consumed"]:
        result.update(stage="authorization_consumption")
        result["failures"].append(
            failure("authorization_consumption", "Session-start authorization was not consumed.")
        )
        return complete_with_receipt(result, expected_session, policy)

    marker = Path(consumption["consumption_marker"])
    marker_sha256 = consumption["consumption_marker_sha256"]
    launch = launch_readiness_runner(
        source_checkout,
        proposal,
        proposal_sha256,
        workspace,
        worktree_receipt,
        worktree_receipt_sha256,
        approval_receipt,
        approval_receipt_sha256,
        preflight,
        preflight_sha256,
        authorization_receipt,
        authorization_receipt_sha256,
        marker,
        marker_sha256,
        launch_policies,
        readiness_runner,
    )
    result["launch_readiness"] = launch
    result["launch_ready"] = launch.get("launch_ready") is True
    if policy["require_launch_ready"] and not result["launch_ready"]:
        result.update(stage="launch_readiness")
        result["failures"].append(
            failure("launch_readiness", "Launch readiness did not pass.")
        )
        return cleanup_then_complete(
            result,
            expected_session,
            source_checkout,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            cleanup_receipt_output,
            cleanup_runner,
            cleanup_validator,
            policy,
        )

    expected_session = expected_session_from_launch(
        launch,
        preflight_sha256,
        authorization_receipt_sha256,
    )
    result.update(
        issue=expected_session["issue"],
        risk=expected_session["risk"],
        base_commit=expected_session["base_commit"],
        workspace=expected_session["workspace"],
        runner_id=expected_session["runner_id"],
    )
    session_bytes = canonical_bytes(expected_session)
    write_exclusive(outputs["expected_session"], session_bytes)
    result["artifacts"]["expected_session"] = {
        "path": str(outputs["expected_session"]),
        "sha256": validate_implementation_result.sha256_bytes(session_bytes),
    }

    execution = adapter_runner(
        normalized_adapter_command,
        workspace,
        parent_environment,
        isolated_process.load_policy(),
        policy["adapter_timeout_seconds"],
    )
    result["adapter_executed"] = True
    result_validation = validate_implementation_result.validate_execution(
        execution,
        expected_session,
        validate_implementation_result.load_policy(),
        diff_policy.load_policy(validate_implementation_patch.DIFF_POLICY_PATH),
    )
    result["implementation_result_validation"] = result_validation
    result["implementation_result_valid"] = result_validation["valid"] is True
    result["implementation_candidate_ready"] = (
        result_validation["implementation_candidate_ready"] is True
    )
    if policy["require_valid_implementation_result"] and not result["implementation_result_valid"]:
        result.update(stage="implementation_result")
        result["failures"].append(
            failure("implementation_result", "Captured implementation result is invalid.")
        )
        return cleanup_then_complete(
            result,
            expected_session,
            source_checkout,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            cleanup_receipt_output,
            cleanup_runner,
            cleanup_validator,
            policy,
        )

    write_exclusive(outputs["result"], execution["stdout"])
    result["result_written"] = True
    result["artifacts"]["result"] = {
        "path": str(outputs["result"]),
        "sha256": validate_implementation_result.sha256_bytes(execution["stdout"]),
    }
    if (
        policy["require_candidate_ready_result_for_patch"]
        and not result["implementation_candidate_ready"]
    ):
        result.update(stage="implementation_result")
        result["failures"].append(
            failure("implementation_candidate", "Implementation result is not candidate-ready.")
        )
        return cleanup_then_complete(
            result,
            expected_session,
            source_checkout,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            cleanup_receipt_output,
            cleanup_runner,
            cleanup_validator,
            policy,
        )

    patch_validation = patch_validator(
        source_checkout,
        execution,
        expected_session,
        outputs["patch"],
        outputs["patch_receipt"],
        validate_implementation_patch.load_policy(),
    )
    result["patch_validation"] = patch_validation
    result["patch_post_validation_complete"] = (
        patch_validation["post_validation_complete"] is True
    )
    result["patch_candidate_ready"] = patch_validation["patch_candidate_ready"] is True
    if patch_validation.get("receipt_written"):
        result["artifacts"]["patch"] = {
            "path": str(outputs["patch"]),
            "sha256": sha256_file(outputs["patch"]),
        }
        result["artifacts"]["patch_receipt"] = {
            "path": str(outputs["patch_receipt"]),
            "sha256": patch_validation["receipt_sha256"],
        }
    if (
        policy["require_candidate_ready_patch_for_quality_gate"]
        and not result["patch_candidate_ready"]
    ):
        result.update(stage="implementation_patch")
        result["failures"].append(
            failure("patch_candidate", "Implementation patch is not candidate-ready.")
        )
        return cleanup_then_complete(
            result,
            expected_session,
            source_checkout,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            cleanup_receipt_output,
            cleanup_runner,
            cleanup_validator,
            policy,
        )

    quality_gate = quality_gate_executor(
        source_checkout,
        outputs["result"],
        outputs["expected_session"],
        outputs["patch"],
        outputs["patch_receipt"],
        patch_validation["receipt_sha256"],
        outputs["quality_gate_receipt"],
        gradle_user_home,
        run_implementation_quality_gate.load_policy(),
        parent_environment=parent_environment,
    )
    result["quality_gate"] = quality_gate
    result["quality_gate_executed"] = quality_gate["execution_attempted"] is True
    result["quality_gate_passed"] = quality_gate["quality_gate_passed"] is True
    if quality_gate.get("receipt_written"):
        qg_sha = quality_gate["receipt_sha256"]
        result["artifacts"]["quality_gate_receipt"] = {
            "path": str(outputs["quality_gate_receipt"]),
            "sha256": qg_sha,
        }
        qg_validation = validate_implementation_quality_gate.validate(
            source_checkout,
            outputs["result"],
            outputs["expected_session"],
            outputs["patch"],
            outputs["patch_receipt"],
            patch_validation["receipt_sha256"],
            outputs["quality_gate_receipt"],
            qg_sha,
            gradle_user_home,
            validate_implementation_quality_gate.load_policy(),
        )
        result["quality_gate_validation"] = qg_validation
        result["quality_gate_receipt_valid"] = qg_validation["valid"] is True
    if not result["quality_gate_passed"]:
        result.update(stage="quality_gate")
        result["failures"].append(
            failure("quality_gate", "Implementation quality gate did not pass.")
        )
        return cleanup_then_complete(
            result,
            expected_session,
            source_checkout,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            cleanup_receipt_output,
            cleanup_runner,
            cleanup_validator,
            policy,
        )
    if not result["quality_gate_receipt_valid"]:
        result.update(stage="quality_gate_validation")
        result["failures"].append(
            failure("quality_gate_receipt", "Quality-gate receipt did not validate.")
        )
        return cleanup_then_complete(
            result,
            expected_session,
            source_checkout,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            cleanup_receipt_output,
            cleanup_runner,
            cleanup_validator,
            policy,
        )

    if cleanup_receipt_output is not None and policy["allow_success_cleanup"]:
        cleanup = cleanup_runner(
            source_checkout,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            cleanup_receipt_output,
            str(workspace),
            cleanup_disposable_worktree.load_policy(),
        )
        result["cleanup"] = cleanup
        result["cleanup_performed"] = cleanup.get("cleaned") is True
        result["cleanup_required"] = not result["cleanup_performed"]
        if cleanup.get("cleaned") is not True:
            result.update(stage="cleanup")
            result["failures"].append(
                failure("cleanup", "Disposable worktree cleanup did not complete.")
            )
            return complete_with_receipt(result, expected_session, policy)
        cleanup_validation = cleanup_validator(
            source_checkout,
            workspace,
            worktree_receipt,
            worktree_receipt_sha256,
            cleanup_receipt_output,
            cleanup["cleanup_receipt_sha256"],
            validate_disposable_worktree_cleanup.load_policy(),
        )
        result["cleanup_validation"] = cleanup_validation
        result["cleanup_receipt_valid"] = cleanup_validation.get("valid") is True
        if not result["cleanup_receipt_valid"]:
            result.update(stage="cleanup_validation")
            result["failures"].append(
                failure("cleanup_validation", "Cleanup receipt did not validate.")
            )
            return complete_with_receipt(result, expected_session, policy)
        result["artifacts"]["cleanup_receipt"] = {
            "path": str(cleanup_receipt_output),
            "sha256": cleanup["cleanup_receipt_sha256"],
        }

    result.update(runner_complete=True, stage="complete")
    return complete_with_receipt(result, expected_session, policy)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--worktree-receipt", type=Path, required=True)
    parser.add_argument("--worktree-receipt-sha256", required=True)
    parser.add_argument("--approval-receipt", type=Path, required=True)
    parser.add_argument("--approval-receipt-sha256", required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--preflight-sha256", required=True)
    parser.add_argument("--authorization-receipt", type=Path, required=True)
    parser.add_argument("--authorization-receipt-sha256", required=True)
    parser.add_argument("--expected-session-output", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    parser.add_argument("--patch-output", type=Path, required=True)
    parser.add_argument("--patch-receipt-output", type=Path, required=True)
    parser.add_argument("--quality-gate-receipt-output", type=Path, required=True)
    parser.add_argument("--final-receipt-output", type=Path, required=True)
    parser.add_argument("--cleanup-receipt-output", type=Path)
    parser.add_argument("--gradle-user-home", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("adapter_command", nargs=argparse.REMAINDER)
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "COMPLETE" if result["runner_complete"] else "BLOCKED"
    lines = [
        f"supervised-implementation-runner: {status} stage={result['stage']}",
        f"final_receipt_written={str(result['final_receipt_written']).lower()}",
        f"quality_gate_passed={str(result['quality_gate_passed']).lower()}",
        "publication_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    command = args.adapter_command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("supervised-implementation-runner: ERROR\n- adapter command is required", file=sys.stderr)
        return 1
    try:
        result = run_supervised(
            args.repo,
            args.proposal,
            args.proposal_sha256,
            args.workspace,
            args.worktree_receipt,
            args.worktree_receipt_sha256,
            args.approval_receipt,
            args.approval_receipt_sha256,
            args.preflight,
            args.preflight_sha256,
            args.authorization_receipt,
            args.authorization_receipt_sha256,
            command,
            args.expected_session_output,
            args.result_output,
            args.patch_output,
            args.patch_receipt_output,
            args.quality_gate_receipt_output,
            args.final_receipt_output,
            args.gradle_user_home,
            load_policy(),
            cleanup_receipt_output=args.cleanup_receipt_output,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"supervised-implementation-runner: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["runner_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
