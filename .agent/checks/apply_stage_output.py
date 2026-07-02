#!/usr/bin/env python3
"""Check and explicitly apply one validated read-only stage response."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

import build_stage_context
import diff_policy
import initialize_portable_run
import validate_artifacts
import validate_prompts
import validate_stage_output


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / ".agent" / "policies"
PROMPTS_DIR = REPO_ROOT / ".agent" / "prompts"
REVIEWER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._@-]*")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def run_snapshot_sha256(run: Path, artifact_names: list[str]) -> str:
    snapshot = b"".join(
        name.encode("utf-8")
        + b"\0"
        + sha256_bytes((run / name).read_bytes()).encode("ascii")
        + b"\n"
        for name in sorted(artifact_names)
    )
    return sha256_bytes(snapshot)


def load_application_policy(
    path: Path,
    output_policy: dict[str, Any],
    artifact_contract: dict[str, Any],
) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "version",
        "purpose",
        "mode",
        "confirmation_prefix",
        "max_reviewer_chars",
        "max_application_receipt_bytes",
        "require_external_run",
        "require_external_application_receipt",
        "require_application_receipt_outside_run",
        "require_absent_application_receipt",
        "require_clean_worktree",
        "require_repo_head_match",
        "bindings",
        "stages",
    }
    if set(policy) != required:
        raise ValueError("Stage-application policy fields do not match the contract")
    if (
        not isinstance(policy["version"], int)
        or isinstance(policy["version"], bool)
        or policy["version"] != 2
    ):
        raise ValueError(f"Unsupported stage-application policy version: {policy['version']}")
    if policy["purpose"] != "operator_confirmed_stage_application":
        raise ValueError("purpose must match the stage-application contract")
    if policy["mode"] != "exact-local-copy-only":
        raise ValueError("mode must match the stage-application contract")
    if policy["confirmation_prefix"] != "APPLY-VALIDATED-STAGE-OUTPUT":
        raise ValueError("confirmation_prefix must match the pilot contract")
    if (
        not isinstance(policy["max_reviewer_chars"], int)
        or isinstance(policy["max_reviewer_chars"], bool)
        or policy["max_reviewer_chars"] < 1
    ):
        raise ValueError("max_reviewer_chars must be a positive integer")
    if (
        not isinstance(policy["max_application_receipt_bytes"], int)
        or isinstance(policy["max_application_receipt_bytes"], bool)
        or policy["max_application_receipt_bytes"] < 1
    ):
        raise ValueError("max_application_receipt_bytes must be a positive integer")
    for field in (
        "require_external_run",
        "require_external_application_receipt",
        "require_application_receipt_outside_run",
        "require_absent_application_receipt",
        "require_clean_worktree",
        "require_repo_head_match",
    ):
        if policy[field] is not True:
            raise ValueError(f"{field} must explicitly be true during the pilot")
    if (
        not isinstance(policy["bindings"], list)
        or not policy["bindings"]
        or not all(isinstance(name, str) for name in policy["bindings"])
        or len(policy["bindings"]) != len(set(policy["bindings"]))
    ):
        raise ValueError("bindings must be a unique non-empty list")
    if not isinstance(policy["stages"], dict) or set(policy["stages"]) != set(output_policy["stages"]):
        raise ValueError("Application stages must exactly match stage-output policy")
    for stage, specification in policy["stages"].items():
        if not isinstance(specification, dict) or set(specification) != {
            "target_artifact",
            "allowed_current_statuses",
        }:
            raise ValueError(f"{stage} application policy fields do not match")
        target = specification["target_artifact"]
        if target != output_policy["stages"][stage]["artifact"]:
            raise ValueError(f"{stage} target artifact must match stage output")
        statuses = specification["allowed_current_statuses"]
        allowed = artifact_contract["artifacts"][target]["allowed_statuses"]
        if (
            not isinstance(statuses, list)
            or not statuses
            or not all(isinstance(status, str) and status in allowed for status in statuses)
            or len(statuses) != len(set(statuses))
        ):
            raise ValueError(f"{stage} allowed_current_statuses must be unique contracted statuses")
        if "approved" in statuses or "blocked" in statuses:
            raise ValueError(f"{stage} application cannot replace approved or blocked artifacts")
    return policy


def load_policies() -> dict[str, Any]:
    artifact = validate_artifacts.load_contract(POLICY_DIR / "artifact-contract.json")
    prompt = validate_prompts.load_prompt_contract(POLICY_DIR / "prompt-contract.json", artifact)
    context = build_stage_context.load_context_policy(
        POLICY_DIR / "stage-context.json",
        prompt,
        artifact,
    )
    output = validate_stage_output.load_output_policy(
        POLICY_DIR / "stage-output.json",
        context,
        prompt,
        artifact,
    )
    return {
        "artifact": artifact,
        "prompt": prompt,
        "context": context,
        "output": output,
        "diff": diff_policy.load_policy(POLICY_DIR / "diff-policy.json"),
        "application": load_application_policy(
            POLICY_DIR / "stage-application.json",
            output,
            artifact,
        ),
    }


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def base_result() -> dict[str, Any]:
    return {
        "applicable": False,
        "applied": False,
        "run_mutated": False,
        "response_applied": False,
        "copy_confirmed": False,
        "reviewer_declaration": None,
        "authorized": False,
        "stage_authorized": False,
        "publication_authorized": False,
        "stage": None,
        "artifact": None,
        "status": None,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "bundle_sha256": None,
        "run_snapshot_sha256": None,
        "post_run_snapshot_sha256": None,
        "response_sha256": None,
        "replaced_sha256": None,
        "application_bindings_sha256": None,
        "application_receipt": None,
        "application_receipt_sha256": None,
        "application_receipt_size_bytes": None,
        "receipt_written": False,
        "rollback_attempted": False,
        "rollback_succeeded": False,
        "required_confirmation": None,
        "failures": [],
    }


def application_bindings(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["bindings"])
    content = (json.dumps(records, sort_keys=True) + "\n").encode("utf-8")
    return records, sha256_bytes(content)


def snapshot_with_artifact(
    run: Path,
    artifact_names: list[str],
    target_name: str,
    target_bytes: bytes,
) -> str:
    snapshot = b"".join(
        name.encode("utf-8")
        + b"\0"
        + sha256_bytes(
            target_bytes if name == target_name else (run / name).read_bytes()
        ).encode("ascii")
        + b"\n"
        for name in sorted(artifact_names)
    )
    return sha256_bytes(snapshot)


def assess_application(
    repo: Path,
    run: Path,
    bundle_path: Path,
    bundle_sha256: str,
    response_path: Path,
    application_receipt: Path,
    policies: dict[str, Any],
) -> dict[str, Any]:
    result = base_result()
    result["bundle_sha256"] = bundle_sha256
    if run.is_symlink():
        raise ValueError("Run directory symbolic links are not allowed")
    if bundle_path.is_symlink() or response_path.is_symlink():
        raise ValueError("Bundle and response symbolic links are not allowed")
    if application_receipt.is_symlink():
        raise ValueError("Stage-application receipt symbolic links are not allowed")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    run = run.resolve()
    bundle_path = bundle_path.resolve()
    response_path = response_path.resolve()
    application_receipt = application_receipt.resolve()
    if not run.is_dir():
        raise ValueError("Run artifact directory does not exist")
    if policies["application"]["require_external_run"] and build_stage_context.is_within(run, repo_root):
        raise ValueError("Run artifact directory must be outside the Git checkout")
    if "\n" in str(application_receipt) or "\r" in str(application_receipt):
        raise ValueError("Stage-application receipt path must not contain line breaks")
    if policies["application"]["require_external_application_receipt"] and build_stage_context.is_within(
        application_receipt,
        repo_root,
    ):
        raise ValueError("Stage-application receipt must be outside the Git checkout")
    if policies["application"]["require_application_receipt_outside_run"] and build_stage_context.is_within(
        application_receipt,
        run,
    ):
        raise ValueError("Stage-application receipt must be outside the portable run")
    if policies["application"]["require_absent_application_receipt"] and application_receipt.exists():
        raise ValueError("Stage-application receipt already exists")
    if not application_receipt.parent.is_dir():
        raise ValueError("Stage-application receipt parent must be an existing directory")
    if build_stage_context.is_within(bundle_path, run) or build_stage_context.is_within(response_path, run):
        raise ValueError("Bundle and response must be outside the run directory")
    if any((run / name).is_symlink() for name in policies["artifact"]["artifacts"]):
        raise ValueError("Run artifact symbolic links are not allowed")

    run_validation = validate_artifacts.validate_directory(run, policies["artifact"], False)
    if not run_validation["valid"]:
        result["failures"].append(failure("run_contract", "Run does not satisfy the artifact contract."))
        return result
    result["run_snapshot_sha256"] = run_snapshot_sha256(
        run,
        list(policies["artifact"]["artifacts"]),
    )
    output = validate_stage_output.validate_output(
        bundle_path,
        bundle_sha256,
        response_path,
        repo_root,
        policies,
        PROMPTS_DIR,
    )
    result.update(
        stage=output["stage"],
        artifact=output["artifact"],
        status=output["status"],
    )
    if not output["valid"]:
        result["failures"].append(failure("stage_output", "Stage response is not structurally accepted."))
        result["failures"].extend(output["failures"])
        return result

    bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
    result.update(
        issue=bundle["issue"],
        risk=bundle["risk"],
        base_commit=bundle["base_commit"],
        application_receipt=str(application_receipt),
    )
    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    if policies["application"]["require_repo_head_match"] and head != bundle["base_commit"]:
        result["failures"].append(failure("repo_head_match", "Repository HEAD differs from bundle base."))
    status = diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if policies["application"]["require_clean_worktree"] and status:
        result["failures"].append(failure("clean_worktree", "Repository worktree must be clean."))
    for record in bundle["artifacts"]:
        path = run / record["name"]
        if path.is_symlink():
            raise ValueError("Run artifact symbolic links are not allowed")
        if path.read_text(encoding="utf-8-sig") != record["content"]:
            result["failures"].append(
                failure("context_source_changed", f"Run source changed after bundle creation: {record['name']}")
            )

    stage_policy = policies["application"]["stages"][output["stage"]]
    target = run / stage_policy["target_artifact"]
    if target.is_symlink() or not target.is_file():
        raise ValueError("Target artifact must be an existing regular file")
    target_bytes = target.read_bytes()
    target_artifact = validate_artifacts.parse_artifact(target)
    if target_artifact.frontmatter.get("status") not in stage_policy["allowed_current_statuses"]:
        result["failures"].append(
            failure("current_status", "Target artifact status cannot be replaced by this stage.")
        )
    response_bytes = response_path.read_bytes()
    response_digest = sha256_bytes(response_bytes)
    target_digest = sha256_bytes(target_bytes)
    post_snapshot = snapshot_with_artifact(
        run,
        list(policies["artifact"]["artifacts"]),
        stage_policy["target_artifact"],
        response_bytes,
    )
    _bindings, bindings_sha256 = application_bindings(policies["application"])
    result["response_sha256"] = response_digest
    result["replaced_sha256"] = target_digest
    result["post_run_snapshot_sha256"] = post_snapshot
    result["application_bindings_sha256"] = bindings_sha256
    if response_digest == target_digest:
        result["failures"].append(failure("no_change", "Response is byte-identical to the target artifact."))
    confirmation = (
        f"{policies['application']['confirmation_prefix']} "
        f"stage={output['stage']} artifact={output['artifact']} "
        f"bundle_sha256={bundle_sha256} "
        f"run_snapshot_sha256={result['run_snapshot_sha256']} "
        f"post_run_snapshot_sha256={post_snapshot} "
        f"response_sha256={response_digest} replace_sha256={target_digest} "
        f"application_bindings_sha256={bindings_sha256} "
        f"application_receipt={application_receipt}"
    )
    result["required_confirmation"] = confirmation
    result["applicable"] = not result["failures"]
    return result


def validate_reviewer(reviewer: str, maximum: int) -> str:
    if len(reviewer) > maximum or not REVIEWER.fullmatch(reviewer):
        raise ValueError(
            f"Reviewer declaration must be a 1 to {maximum} character identifier "
            "using letters, digits, dot, underscore, at, or hyphen"
        )
    return reviewer


def write_atomic_existing(target: Path, content: bytes) -> None:
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def apply_response(
    args: argparse.Namespace,
    policies: dict[str, Any],
    assessment: dict[str, Any],
) -> dict[str, Any]:
    reviewer = validate_reviewer(args.reviewer, policies["application"]["max_reviewer_chars"])
    if build_stage_context.detect_secrets(
        [build_stage_context.content_record("reviewer", reviewer)],
        policies["diff"],
    ):
        raise ValueError("Reviewer declaration contains a high-confidence secret signature")
    if args.confirm != assessment["required_confirmation"]:
        assessment["failures"].append(
            failure("confirmation_mismatch", "Confirmation does not match the current exact copy operation.")
        )
        assessment["applicable"] = False
        return assessment
    refreshed = assess_application(
        args.repo,
        args.run,
        args.bundle,
        args.bundle_sha256,
        args.response,
        args.application_receipt,
        policies,
    )
    if not refreshed["applicable"] or args.confirm != refreshed["required_confirmation"]:
        refreshed["failures"].append(
            failure("state_changed", "Application state changed after confirmation.")
        )
        refreshed["applicable"] = False
        return refreshed
    target = args.run.resolve() / refreshed["artifact"]
    response_bytes = args.response.resolve().read_bytes()
    application_receipt = args.application_receipt.resolve()
    current_snapshot = run_snapshot_sha256(
        args.run.resolve(),
        list(policies["artifact"]["artifacts"]),
    )
    if (
        current_snapshot != refreshed["run_snapshot_sha256"]
        or sha256_bytes(response_bytes) != refreshed["response_sha256"]
        or sha256_bytes(target.read_bytes()) != refreshed["replaced_sha256"]
    ):
        refreshed["failures"].append(
            failure("state_changed", "Run, response, or target changed immediately before replacement.")
        )
        refreshed["applicable"] = False
        return refreshed
    bindings, _bindings_sha256 = application_bindings(policies["application"])
    receipt_value = {
        "stage_application_receipt_version": policies["application"]["version"],
        "purpose": policies["application"]["purpose"],
        "mode": policies["application"]["mode"],
        "authorized": False,
        "stage_authorized": False,
        "publication_authorized": False,
        "run_mutated": True,
        "response_applied": True,
        "copy_confirmed": True,
        "reviewer_declaration": reviewer,
        "stage": refreshed["stage"],
        "artifact": refreshed["artifact"],
        "status": refreshed["status"],
        "issue": refreshed["issue"],
        "risk": refreshed["risk"],
        "base_commit": refreshed["base_commit"],
        "run": str(args.run.resolve()),
        "application_receipt": str(application_receipt),
        "bundle_sha256": refreshed["bundle_sha256"],
        "pre_application_run_snapshot_sha256": refreshed["run_snapshot_sha256"],
        "post_application_run_snapshot_sha256": refreshed["post_run_snapshot_sha256"],
        "response_sha256": refreshed["response_sha256"],
        "replaced_sha256": refreshed["replaced_sha256"],
        "confirmation_sha256": sha256_bytes(args.confirm.encode("utf-8")),
        "bindings": bindings,
    }
    receipt_bytes = (json.dumps(receipt_value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(receipt_bytes) > policies["application"]["max_application_receipt_bytes"]:
        raise ValueError("Stage-application receipt exceeds max_application_receipt_bytes")
    receipt_written = False
    target_mutated = False
    target_bytes = target.read_bytes()
    try:
        initialize_portable_run.write_exclusive(application_receipt, receipt_bytes)
        receipt_written = True
        write_atomic_existing(target, response_bytes)
        target_mutated = True
        final_validation = validate_artifacts.validate_directory(args.run.resolve(), policies["artifact"], False)
        if not final_validation["valid"]:
            raise ValueError("Run contract unexpectedly failed after atomic artifact replacement")
        if (
            application_receipt.read_bytes() != receipt_bytes
            or run_snapshot_sha256(args.run.resolve(), list(policies["artifact"]["artifacts"]))
            != refreshed["post_run_snapshot_sha256"]
            or sha256_bytes(target.read_bytes()) != refreshed["response_sha256"]
        ):
            raise ValueError("Applied run or stage-application receipt changed during final validation")
    except (OSError, UnicodeError, ValueError) as error:
        refreshed["rollback_attempted"] = receipt_written or target_mutated
        if target_mutated and target.read_bytes() == response_bytes:
            write_atomic_existing(target, target_bytes)
        if receipt_written:
            application_receipt.unlink(missing_ok=True)
        refreshed["rollback_succeeded"] = (
            target.read_bytes() == target_bytes and not application_receipt.exists()
        )
        status = "succeeded" if refreshed["rollback_succeeded"] else "failed"
        raise ValueError(f"Stage application failed; rollback {status}") from error
    refreshed.update(
        applicable=False,
        applied=True,
        run_mutated=True,
        response_applied=True,
        copy_confirmed=True,
        reviewer_declaration=reviewer,
        receipt_written=True,
        application_receipt_sha256=sha256_bytes(receipt_bytes),
        application_receipt_size_bytes=len(receipt_bytes),
        required_confirmation=None,
    )
    return refreshed


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--application-receipt", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    check_parser = subparsers.add_parser("check", help="Validate and print the exact confirmation")
    add_common_arguments(check_parser)
    apply_parser = subparsers.add_parser("apply", help="Revalidate and atomically replace one artifact")
    add_common_arguments(apply_parser)
    apply_parser.add_argument("--reviewer", required=True, help="Unauthenticated operator declaration")
    apply_parser.add_argument("--confirm", required=True, help="Exact confirmation printed by check")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        policies = load_policies()
        result = assess_application(
            args.repo,
            args.run,
            args.bundle,
            args.bundle_sha256,
            args.response,
            args.application_receipt,
            policies,
        )
        if args.action == "apply" and result["applicable"]:
            result = apply_response(args, policies, result)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"stage-application: ERROR\n- {error}", file=sys.stderr)
        return 1
    result["action"] = args.action
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if (result["applicable"] if args.action == "check" else result["applied"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
