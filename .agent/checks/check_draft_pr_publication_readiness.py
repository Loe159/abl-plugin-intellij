#!/usr/bin/env python3
"""Check local draft-PR publication readiness without publishing."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import diff_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "draft-pr-publication-readiness.json"
FALSE_FIELDS = (
    "authorized",
    "repository_mutation_authorized",
    "network_authorized",
    "publication_authorized",
    "draft_pr_created",
    "branch_pushed",
    "external_service_written",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "draft_pr_publication_readiness_check",
    "mode": "local-preflight-only",
    "required_missing_controls": [
        "explicit_publication_request",
        "authenticated_remote_repository",
        "policy_allowed_candidate_patch",
        "validated_quality_gate_receipt",
        "exact_branch_push_result",
        "draft_pr_creation_result",
    ],
    "bindings": [
        ".agent/checks/check_draft_pr_publication_readiness.py",
        ".agent/policies/draft-pr-publication-readiness.json",
        "docs/agent-guides/draft-pr-publication-readiness.md",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Draft-PR publication readiness policy does not match")
    return policy


def git_status(repo: Path) -> bytes:
    return diff_policy.run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")


def binding_records(repo: Path, paths: list[str]) -> list[dict[str, Any]]:
    records = []
    for name in paths:
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Publication-readiness binding must be a regular file: {name}")
        content = path.read_bytes()
        records.append(
            {
                "name": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    return records


def check_readiness(repo: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    before = git_status(repo_root)
    bindings = binding_records(repo_root, policy["bindings"])
    after = git_status(repo_root)
    if after != before:
        raise ValueError("Repository state changed during publication readiness check")

    missing_controls = list(policy["required_missing_controls"])
    return {
        "readiness_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        "publication_ready": False,
        **{field: False for field in FALSE_FIELDS},
        "missing_controls": missing_controls,
        "repo_unchanged": True,
        "bindings": bindings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "READY" if result["publication_ready"] else "NOT_READY"
    lines = [
        f"draft-pr-publication-readiness: {status}",
        "publication_authorized=false",
        "repository_mutation_authorized=false",
        "network_authorized=false",
    ]
    lines.extend(f"- missing: {item}" for item in result["missing_controls"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = check_readiness(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"draft-pr-publication-readiness: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["publication_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
