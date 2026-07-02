#!/usr/bin/env python3
"""Assess a historical golden-set candidate manifest without trusting remote state."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import build_stage_context
import diff_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "golden-set-readiness.json"
COMMIT = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
CASE_ID = re.compile(r"issue-[1-9][0-9]*")
UTC_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z")
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "repository_mutation_authorized",
    "network_authorized",
    "publication_authorized",
    "runner_selected",
    "session_start_authorized",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "historical_golden_set_candidate_assessment",
    "mode": "candidate-only",
    "repository": "Loe159/abl-plugin-intellij",
    "min_cases": 5,
    "max_cases": 20,
    "max_manifest_bytes": 100000,
    "max_text_characters": 1000,
    "max_criteria_per_case": 10,
    "max_task_acceptance_criteria_per_case": 10,
    "max_task_constraints_per_case": 10,
    "max_task_out_of_scope_per_case": 10,
    "max_verification_steps_per_case": 10,
    "require_external_manifest": True,
    "require_issue_state": "closed",
    "required_categories": [
        "docs_or_typo",
        "simple_bug",
        "missing_test",
        "local_feature",
        "abl_rssw_research",
        "refuse_or_escalate",
    ],
    "expected_outcomes": ["patch", "refuse_or_escalate"],
    "reference_kinds": ["commit", "decision"],
    "bindings": [
        ".agent/checks/assess_golden_set_readiness.py",
        ".agent/policies/golden-set-readiness.json",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Golden-set readiness policy does not match the pilot contract")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def exact_mapping(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} fields do not match the contract")
    return value


def bounded_text(value: Any, name: str, maximum: int) -> str:
    if type(value) is not str or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} must be a bounded non-empty string")
    return value


def bounded_text_list(
    value: Any,
    name: str,
    maximum_items: int,
    maximum_characters: int,
) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) > maximum_items
        or len(value) != len(set(value))
    ):
        raise ValueError(f"{name} must be a bounded unique non-empty list")
    for index, item in enumerate(value):
        bounded_text(item, f"{name}[{index}]", maximum_characters)
    return value


def bounded_optional_text_list(
    value: Any,
    name: str,
    maximum_items: int,
    maximum_characters: int,
) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > maximum_items
        or len(value) != len(set(value))
    ):
        raise ValueError(f"{name} must be a bounded unique list")
    for index, item in enumerate(value):
        bounded_text(item, f"{name}[{index}]", maximum_characters)
    return value


def parse_utc(value: Any, name: str) -> str:
    if type(value) is not str or UTC_TIMESTAMP.fullmatch(value) is None:
        raise ValueError(f"{name} must be an RFC 3339 UTC timestamp ending in Z")
    parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    if parsed.tzinfo != timezone.utc:
        raise ValueError(f"{name} must use UTC")
    return value


def binding_records(repo: Path, names: list[str]) -> list[dict[str, Any]]:
    records = []
    for name in names:
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Golden-set binding must be an existing regular file: {name}")
        content = path.read_bytes()
        records.append(
            {
                "name": name,
                "sha256": sha256_bytes(content),
                "size_bytes": len(content),
            }
        )
    return records


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def commit_record(repo: Path, commit: str) -> dict[str, Any]:
    if COMMIT.fullmatch(commit) is None:
        raise ValueError("Reference commit must be a full lowercase commit SHA")
    try:
        object_type = diff_policy.run_git(repo, "cat-file", "-t", commit).decode("ascii").strip()
    except ValueError as error:
        raise ValueError(f"Reference commit is not available locally: {commit}") from error
    if object_type != "commit":
        raise ValueError(f"Reference object is not a commit: {commit}")
    ancestor = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={diff_policy.git_safe_directory(repo)}",
            "-C",
            str(repo),
            "merge-base",
            "--is-ancestor",
            commit,
            "HEAD",
        ],
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise ValueError(f"Reference commit is not reachable from HEAD: {commit}")
    parents = (
        diff_policy.run_git(repo, "rev-list", "--parents", "-n", "1", commit)
        .decode("ascii")
        .strip()
        .split()
    )
    if len(parents) < 2:
        raise ValueError(f"Root commits are not accepted as reference patches: {commit}")
    parent = parents[1]
    paths = sorted(
        path
        for path in diff_policy.run_git(
            repo,
            "diff",
            "--name-only",
            "--no-renames",
            parent,
            commit,
            "--",
        )
        .decode("utf-8")
        .splitlines()
        if path
    )
    if not paths:
        raise ValueError(f"Reference commit has no patch against its first parent: {commit}")
    patch = diff_policy.run_git(
        repo,
        "diff",
        "--binary",
        "--full-index",
        "--no-renames",
        parent,
        commit,
        "--",
    )
    return {
        "commit": commit,
        "first_parent": parent,
        "patch_sha256": sha256_bytes(patch),
        "patch_size_bytes": len(patch),
        "paths": paths,
    }


def validate_manifest(value: Any, policy: dict[str, Any]) -> dict[str, Any]:
    manifest = exact_mapping(
        value,
        {
            "manifest_version",
            "purpose",
            "mode",
            "repository",
            "captured_at",
            "cases",
        },
        "Manifest",
    )
    if (
        type(manifest["manifest_version"]) is not int
        or manifest["manifest_version"] != policy["version"]
        or manifest["purpose"] != "historical_golden_set_candidate_manifest"
        or manifest["mode"] != "candidate-data-only"
        or manifest["repository"] != policy["repository"]
    ):
        raise ValueError("Manifest identity does not match the contract")
    parse_utc(manifest["captured_at"], "captured_at")
    cases = manifest["cases"]
    if (
        not isinstance(cases, list)
        or len(cases) < policy["min_cases"]
        or len(cases) > policy["max_cases"]
    ):
        raise ValueError(
            f"Manifest must contain {policy['min_cases']} to {policy['max_cases']} cases"
        )

    ids: set[str] = set()
    issue_numbers: set[int] = set()
    covered_categories: set[str] = set()
    validated_cases = []
    for index, raw_case in enumerate(cases):
        case = exact_mapping(
            raw_case,
            {
            "id",
            "issue",
            "task",
            "categories",
            "expected_outcome",
            "success_criteria",
            "reference",
            },
            f"cases[{index}]",
        )
        if type(case["id"]) is not str or CASE_ID.fullmatch(case["id"]) is None:
            raise ValueError(f"cases[{index}].id is invalid")
        if case["id"] in ids:
            raise ValueError("Case IDs must be unique")
        ids.add(case["id"])
        issue = exact_mapping(
            case["issue"],
            {"number", "url", "state", "title_sha256", "snapshot_sha256"},
            f"cases[{index}].issue",
        )
        if type(issue["number"]) is not int or issue["number"] < 1:
            raise ValueError(f"cases[{index}].issue.number must be positive")
        if issue["number"] in issue_numbers:
            raise ValueError("Issue numbers must be unique")
        issue_numbers.add(issue["number"])
        if case["id"] != f"issue-{issue['number']}":
            raise ValueError(f"cases[{index}].id must match its issue number")
        expected_url = (
            f"https://github.com/{policy['repository']}/issues/{issue['number']}"
        )
        if issue["url"] != expected_url or issue["state"] != policy["require_issue_state"]:
            raise ValueError(f"cases[{index}].issue must declare the exact closed issue")
        for digest_name in ("title_sha256", "snapshot_sha256"):
            if type(issue[digest_name]) is not str or SHA256.fullmatch(
                issue[digest_name]
            ) is None:
                raise ValueError(f"cases[{index}].issue.{digest_name} is invalid")

        task = exact_mapping(
            case["task"],
            {
                "title",
                "goal",
                "background",
                "acceptance_criteria",
                "constraints",
                "out_of_scope",
            },
            f"cases[{index}].task",
        )
        bounded_text(task["title"], f"cases[{index}].task.title", policy["max_text_characters"])
        bounded_text(task["goal"], f"cases[{index}].task.goal", policy["max_text_characters"])
        bounded_text(
            task["background"],
            f"cases[{index}].task.background",
            policy["max_text_characters"],
        )
        bounded_text_list(
            task["acceptance_criteria"],
            f"cases[{index}].task.acceptance_criteria",
            policy["max_task_acceptance_criteria_per_case"],
            policy["max_text_characters"],
        )
        bounded_optional_text_list(
            task["constraints"],
            f"cases[{index}].task.constraints",
            policy["max_task_constraints_per_case"],
            policy["max_text_characters"],
        )
        bounded_optional_text_list(
            task["out_of_scope"],
            f"cases[{index}].task.out_of_scope",
            policy["max_task_out_of_scope_per_case"],
            policy["max_text_characters"],
        )

        categories = bounded_text_list(
            case["categories"],
            f"cases[{index}].categories",
            len(policy["required_categories"]),
            policy["max_text_characters"],
        )
        unknown = sorted(set(categories) - set(policy["required_categories"]))
        if unknown:
            raise ValueError(f"cases[{index}] has unsupported categories: {', '.join(unknown)}")
        covered_categories.update(categories)
        if case["expected_outcome"] not in policy["expected_outcomes"]:
            raise ValueError(f"cases[{index}].expected_outcome is unsupported")
        bounded_text_list(
            case["success_criteria"],
            f"cases[{index}].success_criteria",
            policy["max_criteria_per_case"],
            policy["max_text_characters"],
        )
        reference = exact_mapping(
            case["reference"],
            {"kind", "commit", "verification"},
            f"cases[{index}].reference",
        )
        if reference["kind"] not in policy["reference_kinds"]:
            raise ValueError(f"cases[{index}].reference.kind is unsupported")
        bounded_text_list(
            reference["verification"],
            f"cases[{index}].reference.verification",
            policy["max_verification_steps_per_case"],
            policy["max_text_characters"],
        )
        if case["expected_outcome"] == "patch":
            if reference["kind"] != "commit" or type(reference["commit"]) is not str:
                raise ValueError(f"cases[{index}] patch outcome requires a commit reference")
        else:
            if (
                "refuse_or_escalate" not in categories
                or reference["kind"] != "decision"
                or reference["commit"] is not None
            ):
                raise ValueError(
                    f"cases[{index}] refusal outcome requires a decision reference and category"
                )
        validated_cases.append(case)

    missing_categories = sorted(set(policy["required_categories"]) - covered_categories)
    return {
        "manifest": manifest,
        "cases": validated_cases,
        "covered_categories": sorted(covered_categories),
        "missing_categories": missing_categories,
    }


def assess(repo: Path, manifest_path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Candidate manifest must be an existing regular file")
    manifest_path = manifest_path.resolve()
    if policy["require_external_manifest"] and build_stage_context.is_within(
        manifest_path,
        repo_root,
    ):
        raise ValueError("Candidate manifest must be outside the Git checkout")
    content = manifest_path.read_bytes()
    if len(content) > policy["max_manifest_bytes"]:
        raise ValueError("Candidate manifest exceeds max_manifest_bytes")
    validated = validate_manifest(json.loads(content.decode("utf-8-sig")), policy)

    local_references = []
    reference_failures = []
    case_summaries = []
    for case in validated["cases"]:
        case_summaries.append(
            {
                "id": case["id"],
                "issue_number": case["issue"]["number"],
                "categories": list(case["categories"]),
                "expected_outcome": case["expected_outcome"],
                "task_sha256": sha256_bytes(canonical_json(case["task"])),
                "reference_kind": case["reference"]["kind"],
            }
        )
        if case["reference"]["kind"] != "commit":
            continue
        try:
            record = commit_record(repo_root, case["reference"]["commit"])
        except ValueError as error:
            reference_failures.append({"case": case["id"], "message": str(error)})
        else:
            local_references.append({"case": case["id"], **record})

    coverage_complete = not validated["missing_categories"]
    local_references_verified = not reference_failures
    candidate_manifest_valid = coverage_complete and local_references_verified
    return {
        "assessment_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "candidate_manifest_valid": candidate_manifest_valid,
        "coverage_complete": coverage_complete,
        "local_references_verified": local_references_verified,
        "source_state_authenticated": False,
        "issue_closure_independently_verified": False,
        "issue_reference_equivalence_verified": False,
        "golden_set_ready": False,
        "case_count": len(validated["cases"]),
        "case_summaries": case_summaries,
        "covered_categories": validated["covered_categories"],
        "missing_categories": validated["missing_categories"],
        "local_references": local_references,
        "reference_failures": reference_failures,
        "manifest": {
            "path": str(manifest_path),
            "sha256": sha256_bytes(content),
            "size_bytes": len(content),
            "repository": validated["manifest"]["repository"],
            "captured_at": validated["manifest"]["captured_at"],
        },
        "policy_bindings": binding_records(repo_root, policy["bindings"]),
    }


def format_text(result: dict[str, Any]) -> str:
    status = "CANDIDATE-VALID" if result["candidate_manifest_valid"] else "INCOMPLETE"
    return "\n".join(
        [
            f"golden-set-candidates: {status}",
            f"cases={result['case_count']}",
            f"coverage_complete={str(result['coverage_complete']).lower()}",
            f"local_references_verified={str(result['local_references_verified']).lower()}",
            "source_state_authenticated=false",
            "golden_set_ready=false",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = assess(args.repo, args.manifest, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"golden-set-candidates: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["candidate_manifest_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
