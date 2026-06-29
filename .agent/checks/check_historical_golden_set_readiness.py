#!/usr/bin/env python3
"""Check local historical golden-set readiness without selecting a corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import diff_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "historical-golden-set-readiness.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "network_authorized",
    "repository_mutation_authorized",
    "publication_authorized",
    "source_state_authenticated",
    "issue_closure_independently_verified",
    "issue_reference_equivalence_verified",
    "candidate_manifest_approved",
    "golden_set_ready",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "historical_golden_set_readiness_check",
    "mode": "local-preflight-only",
    "required_missing_controls": [
        "approved_external_issue_snapshot_corpus",
        "external_candidate_manifest",
        "authenticated_closed_issue_states",
        "issue_to_reference_equivalence_review",
        "complete_category_coverage",
        "human_golden_set_adoption_decision",
    ],
    "bindings": [
        ".agent/checks/check_historical_golden_set_readiness.py",
        ".agent/policies/historical-golden-set-readiness.json",
        ".agent/checks/assess_golden_set_readiness.py",
        ".agent/policies/golden-set-readiness.json",
        "docs/agent-guides/golden-set-readiness.md",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Historical golden-set readiness policy does not match")
    return policy


def git_status(repo: Path) -> bytes:
    return diff_policy.run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")


def binding_records(repo: Path, paths: list[str]) -> list[dict[str, Any]]:
    records = []
    for name in paths:
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Golden-set-readiness binding must be a regular file: {name}")
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
        raise ValueError("Repository state changed during golden-set readiness check")

    return {
        "readiness_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        "candidate_manifest_valid": False,
        **{field: False for field in FALSE_FIELDS},
        "missing_controls": list(policy["required_missing_controls"]),
        "repo_unchanged": True,
        "bindings": bindings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "READY" if result["golden_set_ready"] else "NOT_READY"
    lines = [
        f"historical-golden-set-readiness: {status}",
        "source_state_authenticated=false",
        "issue_closure_independently_verified=false",
        "golden_set_ready=false",
    ]
    lines.extend(f"- missing: {item}" for item in result["missing_controls"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = check_readiness(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"historical-golden-set-readiness: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["golden_set_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
