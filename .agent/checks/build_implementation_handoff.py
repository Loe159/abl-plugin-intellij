#!/usr/bin/env python3
"""Build a deterministic non-authorizing handoff for supervised implementation."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import apply_stage_output
import build_stage_context
import check_stage_readiness
import diff_policy
import validate_artifacts
import validate_plan_approval


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_DIR = REPO_ROOT / ".agent" / "policies"


def load_handoff_policy(
    path: Path,
    artifact_contract: dict[str, Any],
    readiness_policy: dict[str, Any],
) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "version",
        "purpose",
        "mode",
        "max_bundle_bytes",
        "require_external_run",
        "require_external_output",
        "require_output_outside_run",
        "require_clean_worktree",
        "require_repo_head_match",
        "require_approved_plan",
        "require_valid_plan_approval",
        "readiness_stage",
        "content_artifacts",
    }
    if set(policy) != required:
        raise ValueError("Implementation-handoff policy fields do not match the contract")
    if (
        not isinstance(policy["version"], int)
        or isinstance(policy["version"], bool)
        or policy["version"] != 2
    ):
        raise ValueError(f"Unsupported implementation-handoff policy version: {policy['version']}")
    if policy["purpose"] != "implementation_handoff" or policy["mode"] != "handoff-only":
        raise ValueError("purpose and mode must match the non-authorizing handoff contract")
    if (
        not isinstance(policy["max_bundle_bytes"], int)
        or isinstance(policy["max_bundle_bytes"], bool)
        or policy["max_bundle_bytes"] < 1
    ):
        raise ValueError("max_bundle_bytes must be a positive integer")
    for field in (
        "require_external_run",
        "require_external_output",
        "require_output_outside_run",
        "require_clean_worktree",
        "require_repo_head_match",
        "require_approved_plan",
        "require_valid_plan_approval",
    ):
        if policy[field] is not True:
            raise ValueError(f"{field} must explicitly be true during the pilot")
    if (
        policy["readiness_stage"] != "implement"
        or policy["readiness_stage"] not in readiness_policy["stages"]
    ):
        raise ValueError("readiness_stage must be implement")
    artifacts = policy["content_artifacts"]
    if (
        artifacts != ["task.md", "research.md", "plan.md"]
        or any(name not in artifact_contract["artifacts"] for name in artifacts)
    ):
        raise ValueError("content_artifacts must be exactly task.md, research.md, and plan.md")
    return policy


def load_policies() -> dict[str, Any]:
    artifact = validate_artifacts.load_contract(POLICY_DIR / "artifact-contract.json")
    readiness = check_stage_readiness.load_readiness_policy(
        POLICY_DIR / "stage-readiness.json",
        artifact,
    )
    return {
        "artifact": artifact,
        "readiness": readiness,
        "diff": diff_policy.load_policy(POLICY_DIR / "diff-policy.json"),
        "plan_approval": validate_plan_approval.load_policies(),
        "handoff": load_handoff_policy(
            POLICY_DIR / "implementation-handoff.json",
            artifact,
            readiness,
        ),
    }


def failure(rule: str, message: str, **details: Any) -> dict[str, Any]:
    return {"rule": rule, "message": message, **details}


def artifact_record(name: str, path: Path, include_content: bool) -> dict[str, Any]:
    content = path.read_bytes()
    artifact = validate_artifacts.parse_artifact(path)
    record: dict[str, Any] = {
        "name": name,
        "status": artifact.frontmatter["status"],
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }
    if include_content:
        record["content"] = content.decode("utf-8")
    return record


def base_result() -> dict[str, Any]:
    return {
        "produced": False,
        "authorized": False,
        "agent_invocation_authorized": False,
        "implementation_authorized": False,
        "repository_mutation_authorized": False,
        "network_authorized": False,
        "publication_authorized": False,
        "issue": None,
        "risk": None,
        "base_commit": None,
        "run_snapshot_sha256": None,
        "plan_approval_receipt_sha256": None,
        "failures": [],
    }


def repository_status(repo_root: Path) -> bytes:
    return diff_policy.run_git_with_environment(
        repo_root,
        {"GIT_OPTIONAL_LOCKS": "0"},
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )


def build_handoff(
    repo: Path,
    run: Path,
    output: Path,
    plan_approval_receipt: Path,
    plan_approval_receipt_sha256: str,
    policies: dict[str, Any],
) -> dict[str, Any]:
    result = base_result()
    if run.is_symlink():
        raise ValueError("Run directory symbolic links are not allowed")
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    run = run.resolve()
    output = output.resolve()
    plan_approval_receipt = plan_approval_receipt.resolve()
    result["plan_approval_receipt_sha256"] = plan_approval_receipt_sha256
    if not run.is_dir():
        raise ValueError("Run artifact directory does not exist")
    if policies["handoff"]["require_external_run"] and build_stage_context.is_within(run, repo_root):
        raise ValueError("Run artifact directory must be outside the Git checkout")
    if (
        policies["handoff"]["require_external_output"]
        and build_stage_context.is_within(output, repo_root)
    ):
        raise ValueError("Implementation handoff output must be outside the Git checkout")
    if policies["handoff"]["require_output_outside_run"] and build_stage_context.is_within(
        output,
        run,
    ):
        raise ValueError("Implementation handoff output must be outside the run directory")
    if output.exists():
        raise ValueError("Implementation handoff output already exists")
    if "\n" in str(plan_approval_receipt) or "\r" in str(plan_approval_receipt):
        raise ValueError("Plan-approval receipt path must not contain line breaks")

    artifact_names = list(policies["artifact"]["artifacts"])
    if any((run / name).is_symlink() for name in artifact_names):
        raise ValueError("Run artifact symbolic links are not allowed")
    contract = validate_artifacts.validate_directory(run, policies["artifact"], False)
    if not contract["valid"]:
        result["failures"].append(
            failure("run_contract", "Run does not satisfy the artifact contract.")
        )
        return result
    artifacts = {name: validate_artifacts.parse_artifact(run / name) for name in artifact_names}
    task = artifacts["task.md"]
    result.update(
        issue=int(task.frontmatter["issue"]),
        risk=task.frontmatter["risk"],
        base_commit=task.frontmatter["base_commit"],
        run_snapshot_sha256=apply_stage_output.run_snapshot_sha256(run, artifact_names),
    )

    readiness = check_stage_readiness.check_readiness(
        run,
        policies["handoff"]["readiness_stage"],
        policies["artifact"],
        policies["readiness"],
    )
    if not readiness["ready"]:
        result["failures"].append(
            failure("implementation_readiness", "Implementation prerequisites are not ready.")
        )
        result["failures"].extend(readiness["failures"])
    if (
        policies["handoff"]["require_approved_plan"]
        and artifacts["plan.md"].frontmatter["status"] != "approved"
    ):
        result["failures"].append(
            failure(
                "approved_plan",
                "Implementation handoff requires an approved plan for every risk route.",
            )
        )
    try:
        plan_approval = validate_plan_approval.validate(
            repo_root,
            run,
            plan_approval_receipt,
            plan_approval_receipt_sha256,
            policies["plan_approval"],
        )
    except ValueError as error:
        plan_approval = {
            "valid": False,
            "failures": [failure("plan_approval_receipt", str(error))],
        }
    if policies["handoff"]["require_valid_plan_approval"] and not plan_approval["valid"]:
        result["failures"].append(
            failure(
                "plan_approval_receipt",
                "Implementation handoff requires a valid plan-approval receipt.",
            )
        )
        result["failures"].extend(plan_approval["failures"])

    head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    if policies["handoff"]["require_repo_head_match"] and head != result["base_commit"]:
        result["failures"].append(
            failure("repo_head_match", "Repository HEAD differs from the run base commit.")
        )
    status = repository_status(repo_root)
    if policies["handoff"]["require_clean_worktree"] and status:
        result["failures"].append(
            failure("clean_worktree", "Repository worktree must be clean.")
        )
    if result["failures"]:
        return result

    manifest = [artifact_record(name, run / name, False) for name in artifact_names]
    content_records = [
        artifact_record(name, run / name, True)
        for name in policies["handoff"]["content_artifacts"]
    ]
    detections = build_stage_context.detect_secrets(
        [
            build_stage_context.content_record(name, (run / name).read_text(encoding="utf-8-sig"))
            for name in artifact_names
        ],
        policies["diff"],
    )
    if detections:
        result["failures"].append(
            failure(
                "high_confidence_secret",
                "Run artifact contains a high-confidence secret signature.",
                detections=detections,
            )
        )
        return result
    refreshed_snapshot = apply_stage_output.run_snapshot_sha256(run, artifact_names)
    refreshed_head = diff_policy.run_git(repo_root, "rev-parse", "HEAD").decode("ascii").strip()
    refreshed_status = repository_status(repo_root)
    if (
        refreshed_snapshot != result["run_snapshot_sha256"]
        or refreshed_head != head
        or refreshed_status != status
    ):
        result["failures"].append(
            failure("state_changed", "Run or repository state changed while building the handoff.")
        )
        return result

    bundle = {
        "handoff_version": policies["handoff"]["version"],
        "purpose": policies["handoff"]["purpose"],
        "mode": policies["handoff"]["mode"],
        "authorized": False,
        "agent_invocation_authorized": False,
        "implementation_authorized": False,
        "repository_mutation_authorized": False,
        "network_authorized": False,
        "publication_authorized": False,
        "issue": result["issue"],
        "risk": result["risk"],
        "base_commit": result["base_commit"],
        "repo_head": head,
        "run_snapshot_sha256": result["run_snapshot_sha256"],
        "plan_approval_receipt_sha256": plan_approval_receipt_sha256,
        "run_manifest": manifest,
        "artifacts": content_records,
    }
    bundle_bytes = (json.dumps(bundle, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(bundle_bytes) > policies["handoff"]["max_bundle_bytes"]:
        result["failures"].append(
            failure(
                "max_bundle_bytes",
                "Implementation handoff exceeds the configured byte limit.",
                actual=len(bundle_bytes),
                limit=policies["handoff"]["max_bundle_bytes"],
            )
        )
        return result
    build_stage_context.write_atomic(output, bundle_bytes)
    result.update(
        produced=True,
        output=str(output),
        sha256=hashlib.sha256(bundle_bytes).hexdigest(),
        size_bytes=len(bundle_bytes),
        content_artifacts=policies["handoff"]["content_artifacts"],
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan-approval-receipt", type=Path, required=True)
    parser.add_argument("--plan-approval-receipt-sha256", required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "PRODUCED" if result["produced"] else "NOT_PRODUCED"
    lines = [
        f"implementation-handoff: {status} issue={result['issue'] or 'unknown'}",
        "authorized=false",
        "implementation_authorized=false",
    ]
    for item in result["failures"]:
        lines.append(f"- {item['rule']}: {item['message']}")
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = build_handoff(
            args.repo,
            args.run,
            args.output,
            args.plan_approval_receipt,
            args.plan_approval_receipt_sha256,
            load_policies(),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"implementation-handoff: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["produced"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
