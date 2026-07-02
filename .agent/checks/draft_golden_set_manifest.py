#!/usr/bin/env python3
"""Draft historical golden-set candidate notes from local commits."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import assess_golden_set_readiness
import build_stage_context
import diff_policy
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "golden-set-draft.json"
FALSE_FIELDS = assess_golden_set_readiness.FALSE_FIELDS
SHA1 = re.compile(r"[0-9a-f]{40}")

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "historical_golden_set_draft_from_local_commits",
    "mode": "draft-only",
    "max_commits_scanned": 100,
    "max_candidates": 20,
    "max_subject_chars": 160,
    "required_categories": [
        "docs_or_typo",
        "simple_bug",
        "missing_test",
        "local_feature",
        "abl_rssw_research",
        "refuse_or_escalate",
    ],
    "category_hints": {
        "docs_or_typo": ["doc", "docs", "typo"],
        "simple_bug": ["fix", "bug"],
        "missing_test": ["test"],
        "local_feature": ["feat", "feature"],
        "abl_rssw_research": ["rssw", "proparse", "parser", "abl", "psi"],
    },
    "require_external_output": True,
    "require_absent_output": True,
    "bindings": [
        ".agent/checks/draft_golden_set_manifest.py",
        ".agent/policies/golden-set-draft.json",
        ".agent/checks/assess_golden_set_readiness.py",
        ".agent/policies/golden-set-readiness.json",
        "docs/agent-guides/golden-set-readiness.md",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Golden-set draft policy does not match")
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
        raise ValueError("Golden-set draft output symbolic links are not allowed")
    if "\n" in str(output) or "\r" in str(output):
        raise ValueError("Golden-set draft output path must not contain line breaks")
    output = output.resolve()
    if policy["require_external_output"] and build_stage_context.is_within(output, root):
        raise ValueError("Golden-set draft output must be outside the Git checkout")
    if policy["require_absent_output"] and output.exists():
        raise ValueError("Golden-set draft output already exists")
    if not output.parent.is_dir():
        raise ValueError("Golden-set draft output parent must be an existing directory")
    return output


def commit_subjects(repo: Path, max_count: int) -> list[tuple[str, str]]:
    raw = diff_policy.run_git(
        repo,
        "log",
        f"--max-count={max_count}",
        "--no-merges",
        "--format=%H%x00%s",
    ).decode("utf-8", errors="replace")
    pairs = []
    for line in raw.splitlines():
        if "\0" not in line:
            continue
        commit, subject = line.split("\0", 1)
        if SHA1.fullmatch(commit) is None:
            continue
        pairs.append((commit, subject))
    return pairs


def commit_patch_record(repo: Path, commit: str) -> dict[str, Any] | None:
    try:
        return assess_golden_set_readiness.commit_record(repo, commit)
    except ValueError:
        return None


def category_hints(subject: str, paths: list[str], policy: dict[str, Any]) -> list[str]:
    text = " ".join([subject, *paths]).lower()
    categories = []
    for category, hints in policy["category_hints"].items():
        if any(hint in text for hint in hints):
            categories.append(category)
    return categories


def build_draft(repo: Path, output: Path, policy: dict[str, Any]) -> dict[str, Any]:
    root = repo_root(repo)
    output = validate_output(root, output, policy)
    candidates = []
    covered: set[str] = set()
    for commit, subject in commit_subjects(root, policy["max_commits_scanned"]):
        if len(candidates) >= policy["max_candidates"]:
            break
        patch = commit_patch_record(root, commit)
        if patch is None:
            continue
        subject = subject[: policy["max_subject_chars"]]
        categories = category_hints(subject, patch["paths"], policy)
        covered.update(categories)
        candidates.append(
            {
                "commit": commit,
                "subject": subject,
                "suggested_categories": categories,
                "reference": patch,
                "human_review_required": True,
                "candidate_manifest_fields_still_required": [
                    "closed_github_issue_snapshot",
                    "human_normalized_task",
                    "success_criteria",
                    "issue_to_reference_equivalence_review",
                ],
            }
        )
    missing = sorted(set(policy["required_categories"]) - covered)
    draft = {
        "draft_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "candidate_manifest_valid": False,
        "golden_set_ready": False,
        "not_a_candidate_manifest": True,
        "requires_closed_github_issues": True,
        "requires_human_normalization": True,
        "repository": "Loe159/abl-plugin-intellij",
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "scanned_commit_count": len(commit_subjects(root, policy["max_commits_scanned"])),
        "draft_candidate_count": len(candidates),
        "covered_category_hints": sorted(covered),
        "missing_category_hints": missing,
        "candidates": candidates,
        "bindings": initialize_portable_run.binding_records(policy["bindings"]),
    }
    content = canonical_bytes(draft)
    initialize_portable_run.write_exclusive(output, content)
    return {
        "draft_written": True,
        "draft": str(output),
        "draft_sha256": assess_golden_set_readiness.sha256_bytes(content),
        "draft_size_bytes": len(content),
        "draft_candidate_count": len(candidates),
        "missing_category_hints": missing,
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
            "golden-set-draft: WRITTEN",
            f"draft_candidate_count={result['draft_candidate_count']}",
            "candidate_manifest_valid=false",
            "golden_set_ready=false",
        ]
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = build_draft(args.repo, args.output, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"golden-set-draft: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
