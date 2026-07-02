#!/usr/bin/env python3
"""Generate and validate a complete patch after an exact implementation result."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

import build_stage_context
import classify_patch_risk
import diff_policy
import generate_complete_patch
import initialize_portable_run
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = (
    REPO_ROOT
    / ".agent"
    / "policies"
    / "implementation-patch-post-validation.json"
)
DIFF_POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "diff-policy.json"
RISK_POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "risk-rules.json"
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_patch_post_validation",
    "mode": "deterministic-post-validation-only",
    "max_receipt_bytes": 250000,
    "require_external_patch": True,
    "require_external_receipt": True,
    "require_outputs_outside_workspace": True,
    "require_absent_outputs": True,
    "require_distinct_outputs": True,
    "require_candidate_ready_result": True,
    "require_nonempty_patch_for_candidate": True,
    "require_patch_retained_for_candidate": True,
    "require_policy_allowed_for_candidate": True,
    "quality_gate_execution_required": True,
    "bindings": [
        ".agent/checks/validate_implementation_patch.py",
        ".agent/policies/implementation-patch-post-validation.json",
        ".agent/checks/validate_implementation_result.py",
        ".agent/policies/implementation-result-validation.json",
        ".agent/schemas/implementation-result.schema.json",
        ".agent/checks/generate_complete_patch.py",
        ".agent/checks/diff_policy.py",
        ".agent/policies/diff-policy.json",
        ".agent/checks/classify_patch_risk.py",
        ".agent/policies/risk-rules.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation patch post-validation policy does not match")
    return policy


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_output_target(
    target: Path,
    source_checkout: Path,
    workspace: Path,
    require_external: bool,
    policy: dict[str, Any],
    label: str,
) -> Path:
    if target.is_symlink():
        raise ValueError(f"{label} symbolic links are not allowed")
    target = target.resolve()
    if "\n" in str(target) or "\r" in str(target):
        raise ValueError(f"{label} path must not contain line breaks")
    if require_external and build_stage_context.is_within(target, source_checkout):
        raise ValueError(f"{label} must be outside the source checkout")
    if policy["require_outputs_outside_workspace"] and build_stage_context.is_within(
        target,
        workspace,
    ):
        raise ValueError(f"{label} must be outside the implementation workspace")
    if policy["require_absent_outputs"] and target.exists():
        raise ValueError(f"{label} already exists")
    if not target.parent.is_dir():
        raise ValueError(f"{label} parent must exist")
    return target


def validate_output_targets(
    source_checkout: Path,
    workspace: Path,
    patch_output: Path,
    receipt_output: Path,
    policy: dict[str, Any],
) -> tuple[Path, Path]:
    patch = validate_output_target(
        patch_output,
        source_checkout,
        workspace,
        policy["require_external_patch"],
        policy,
        "Patch output",
    )
    receipt = validate_output_target(
        receipt_output,
        source_checkout,
        workspace,
        policy["require_external_receipt"],
        policy,
        "Post-validation receipt",
    )
    if policy["require_distinct_outputs"] and patch == receipt:
        raise ValueError("Patch and receipt outputs must be distinct")
    return patch, receipt


def base_result(patch: Path, receipt: Path) -> dict[str, Any]:
    return {
        "post_validation_complete": False,
        "patch_candidate_ready": False,
        **{field: False for field in FALSE_FIELDS},
        "patch_output": str(patch),
        "receipt_output": str(receipt),
        "receipt_written": False,
        "receipt_sha256": None,
        "receipt_size_bytes": None,
        "result_validation": None,
        "patch": None,
        "risk": None,
        "quality_gate": {
            "required": True,
            "completed": False,
            "passed": False,
        },
        "failures": [],
    }


def compact_patch_record(generated: dict[str, Any]) -> dict[str, Any]:
    artifact = generated["artifact"]
    facts = generated["facts"]
    return {
        "path": artifact["patch"],
        "nonempty": artifact["size_bytes"] > 0 and facts["file_count"] > 0,
        "retained": artifact["retained"],
        "sha256": artifact["sha256"],
        "size_bytes": artifact["size_bytes"],
        "policy_allowed": generated["allowed"],
        "facts": {
            "file_count": facts["file_count"],
            "changed_lines": facts["changed_lines"],
            "paths": facts["paths"],
            "binary_paths": facts["binary_paths"],
            "symlink_paths": facts["symlink_paths"],
            "deleted_paths": facts["deleted_paths"],
            "rename_from_paths": facts["rename_from_paths"],
        },
        "violations": generated["violations"],
        "worktree": generated["worktree"],
    }


def write_exclusive(path: Path, content: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def validate_patch(
    source_checkout: Path,
    execution: dict[str, Any],
    expected_session: dict[str, Any],
    patch_output: Path,
    receipt_output: Path,
    policy: dict[str, Any],
    generator: Callable[..., dict[str, Any]] = generate_complete_patch.generate_and_validate,
    classifier: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] = (
        classify_patch_risk.classify
    ),
) -> dict[str, Any]:
    source_checkout = Path(
        diff_policy.run_git(source_checkout, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip()
    ).resolve()
    expected_session = validate_implementation_result.validate_expected_session(
        expected_session
    )
    workspace = Path(expected_session["workspace"])
    patch_output, receipt_output = validate_output_targets(
        source_checkout,
        workspace,
        patch_output,
        receipt_output,
        policy,
    )
    result = base_result(patch_output, receipt_output)
    result_validation = validate_implementation_result.validate_execution(
        execution,
        expected_session,
        validate_implementation_result.load_policy(),
        diff_policy.load_policy(DIFF_POLICY_PATH),
    )
    result["result_validation"] = result_validation
    if (
        policy["require_candidate_ready_result"]
        and result_validation["implementation_candidate_ready"] is not True
    ):
        result["failures"].append(
            failure(
                "implementation_result",
                "Patch post-validation requires a candidate-ready implementation result.",
            )
        )
        return result

    before = generate_complete_patch.repository_snapshot(workspace)
    generated: dict[str, Any] | None = None
    try:
        generated = generator(
            workspace,
            expected_session["base_commit"],
            patch_output,
            DIFF_POLICY_PATH,
            False,
        )
        risk = classifier(
            generated,
            classify_patch_risk.load_risk_policy(RISK_POLICY_PATH),
        )
        result.update(
            post_validation_complete=True,
            patch=compact_patch_record(generated),
            risk=risk,
        )
        retained = generated["artifact"]["retained"] is True
        allowed = generated["allowed"] is True
        nonempty = result["patch"]["nonempty"] is True
        result["patch_candidate_ready"] = (
            result_validation["implementation_candidate_ready"] is True
            and (
                nonempty
                or not policy["require_nonempty_patch_for_candidate"]
            )
            and (
                retained
                or not policy["require_patch_retained_for_candidate"]
            )
            and (
                allowed
                or not policy["require_policy_allowed_for_candidate"]
            )
        )
        receipt_value = {
            "post_validation_version": policy["version"],
            "purpose": policy["purpose"],
            "mode": policy["mode"],
            **{field: False for field in FALSE_FIELDS},
            "post_validation_complete": True,
            "patch_candidate_ready": result["patch_candidate_ready"],
            "identity": {
                field: expected_session[field]
                for field in sorted(validate_implementation_result.SESSION_FIELDS)
            },
            "implementation_result": {
                "status": result_validation["status"],
                "sha256": result_validation["result_sha256"],
                "size_bytes": result_validation["result_size_bytes"],
                "valid": result_validation["valid"],
                "candidate_ready": result_validation["implementation_candidate_ready"],
            },
            "patch": result["patch"],
            "risk": risk,
            "quality_gate": result["quality_gate"],
            "bindings": initialize_portable_run.binding_records(policy["bindings"]),
        }
        receipt_bytes = canonical_bytes(receipt_value)
        if len(receipt_bytes) > policy["max_receipt_bytes"]:
            raise ValueError("Implementation patch post-validation receipt exceeds byte limit")
        if generate_complete_patch.repository_snapshot(workspace) != before:
            raise ValueError("Implementation workspace changed during post-validation")
        write_exclusive(receipt_output, receipt_bytes)
        result.update(
            receipt_written=True,
            receipt_sha256=validate_implementation_result.sha256_bytes(receipt_bytes),
            receipt_size_bytes=len(receipt_bytes),
        )
        return result
    except Exception:
        receipt_output.unlink(missing_ok=True)
        patch_output.unlink(missing_ok=True)
        raise


def captured_execution(stdout: bytes, stderr: bytes) -> dict[str, Any]:
    return {
        "completed": True,
        "timed_out": False,
        "output_limit_exceeded": False,
        "kill_requested": False,
        "direct_child_reaped": True,
        "returncode": 0,
        "stdout": stdout,
        "stderr": stderr,
        "capture_complete": True,
        "captured_stdout_bytes": len(stdout),
        "captured_stderr_bytes": len(stderr),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--expected-session", type=Path, required=True)
    parser.add_argument("--stderr", type=Path)
    parser.add_argument("--patch-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "COMPLETE" if result["post_validation_complete"] else "BLOCKED"
    lines = [
        f"implementation-patch-post-validation: {status}",
        f"patch_candidate_ready={str(result['patch_candidate_ready']).lower()}",
        f"receipt_written={str(result['receipt_written']).lower()}",
        "publication_authorized=false",
    ]
    if result["risk"]:
        lines.append(
            f"risk={result['risk']['risk']} route={result['risk']['route']}"
        )
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        stdout = args.result.read_bytes()
        stderr = args.stderr.read_bytes() if args.stderr else b""
        expected_session = json.loads(
            args.expected_session.read_text(encoding="utf-8-sig")
        )
        result = validate_patch(
            args.repo,
            captured_execution(stdout, stderr),
            expected_session,
            args.patch_output,
            args.receipt_output,
            load_policy(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-patch-post-validation: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["post_validation_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
