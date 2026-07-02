#!/usr/bin/env python3
"""Draft historical benchmark notes from merged GitHub pull requests."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import assess_golden_set_readiness
import build_stage_context
import diff_policy
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "golden-set-pr-draft.json"
FALSE_FIELDS = assess_golden_set_readiness.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "historical_golden_set_draft_from_merged_prs",
    "mode": "draft-only",
    "repository": "Loe159/abl-plugin-intellij",
    "min_prs": 5,
    "max_prs": 20,
    "max_title_chars": 200,
    "required_missing_controls": [
        "closed_issue_snapshot_corpus",
        "refuse_or_escalate_case",
        "human_normalized_task_corpus",
        "issue_to_reference_equivalence_review",
        "human_golden_set_adoption_decision",
    ],
    "require_external_output": True,
    "require_absent_output": True,
    "bindings": [
        ".agent/checks/draft_pr_golden_set_manifest.py",
        ".agent/policies/golden-set-pr-draft.json",
        ".agent/checks/assess_golden_set_readiness.py",
        ".agent/policies/golden-set-readiness.json",
        "docs/agent-guides/golden-set-readiness.md",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Golden-set PR draft policy does not match")
    return policy


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, separators=(",", ": ")).encode(
        "utf-8"
    ) + b"\n"


def repo_root(repo: Path) -> Path:
    return Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()


def validate_output(repo: Path, output: Path, policy: dict[str, Any]) -> Path:
    root = repo_root(repo)
    if output.is_symlink():
        raise ValueError("Golden-set PR draft output symbolic links are not allowed")
    output = output.resolve()
    if "\n" in str(output) or "\r" in str(output):
        raise ValueError("Golden-set PR draft output path must not contain line breaks")
    if policy["require_external_output"] and build_stage_context.is_within(output, root):
        raise ValueError("Golden-set PR draft output must be outside the Git checkout")
    if policy["require_absent_output"] and output.exists():
        raise ValueError("Golden-set PR draft output already exists")
    if not output.parent.is_dir():
        raise ValueError("Golden-set PR draft output parent must be an existing directory")
    return output


def gh_json(args: list[str]) -> Any:
    completed = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise ValueError("GitHub CLI command failed while drafting PR golden set")
    return json.loads(completed.stdout)


def fetch_merged_prs(repository: str, limit: int) -> list[dict[str, Any]]:
    items = gh_json(
        [
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "merged",
            "--limit",
            str(limit),
            "--json",
            "number",
        ]
    )
    records = []
    for item in items:
        number = item["number"]
        records.append(
            gh_json(
                [
                    "pr",
                    "view",
                    str(number),
                    "--repo",
                    repository,
                    "--json",
                    "number,title,state,mergedAt,url,mergeCommit,headRefName,baseRefName,files",
                ]
            )
        )
    return records


def commit_available(repo: Path, commit: str) -> bool:
    if assess_golden_set_readiness.COMMIT.fullmatch(commit) is None:
        return False
    try:
        object_type = diff_policy.run_git(repo, "cat-file", "-t", commit).decode("ascii").strip()
    except ValueError:
        return False
    return object_type == "commit"


def pr_case(repo: Path, record: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    merge = record.get("mergeCommit")
    oid = merge.get("oid") if isinstance(merge, dict) else None
    files = record.get("files") if isinstance(record.get("files"), list) else []
    paths = [item.get("path") for item in files if isinstance(item, dict) and item.get("path")]
    title = str(record.get("title", ""))[: policy["max_title_chars"]]
    title_sha = assess_golden_set_readiness.sha256_bytes(title.encode("utf-8"))
    snapshot_bytes = canonical_bytes(record)
    return {
        "source_kind": "merged_pull_request",
        "pr": {
            "number": record.get("number"),
            "url": record.get("url"),
            "state": record.get("state"),
            "merged_at": record.get("mergedAt"),
            "title_sha256": title_sha,
            "snapshot_sha256": assess_golden_set_readiness.sha256_bytes(snapshot_bytes),
        },
        "reference": {
            "merge_commit": oid,
            "available_locally": isinstance(oid, str) and commit_available(repo, oid),
        },
        "title": title,
        "head_ref": record.get("headRefName"),
        "base_ref": record.get("baseRefName"),
        "changed_paths": sorted(paths),
        "human_review_required": True,
    }


def build_draft(
    repo: Path,
    output: Path,
    policy: dict[str, Any],
    pr_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = repo_root(repo)
    output = validate_output(root, output, policy)
    records = pr_records if pr_records is not None else fetch_merged_prs(
        policy["repository"],
        policy["max_prs"],
    )
    if len(records) < policy["min_prs"]:
        raise ValueError(
            f"Golden-set PR draft requires at least {policy['min_prs']} merged PR records"
        )
    cases = [pr_case(root, record, policy) for record in records[: policy["max_prs"]]]
    local_reference_count = sum(1 for item in cases if item["reference"]["available_locally"])
    draft = {
        "draft_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "candidate_manifest_valid": False,
        "golden_set_ready": False,
        "not_a_candidate_manifest": True,
        "repository": policy["repository"],
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "merged_pr_count": len(cases),
        "local_reference_count": local_reference_count,
        "missing_controls": list(policy["required_missing_controls"]),
        "cases": cases,
        "bindings": initialize_portable_run.binding_records(policy["bindings"]),
    }
    content = canonical_bytes(draft)
    initialize_portable_run.write_exclusive(output, content)
    return {
        "draft_written": True,
        "draft": str(output),
        "draft_sha256": assess_golden_set_readiness.sha256_bytes(content),
        "draft_size_bytes": len(content),
        "merged_pr_count": len(cases),
        "local_reference_count": local_reference_count,
        "candidate_manifest_valid": False,
        "golden_set_ready": False,
        **{field: False for field in FALSE_FIELDS},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "golden-set-pr-draft: WRITTEN",
            f"merged_pr_count={result['merged_pr_count']}",
            f"local_reference_count={result['local_reference_count']}",
            "candidate_manifest_valid=false",
            "golden_set_ready=false",
        ]
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = build_draft(args.repo, args.output, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"golden-set-pr-draft: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
