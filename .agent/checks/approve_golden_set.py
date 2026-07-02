#!/usr/bin/env python3
"""Adopt one exact historical golden-set candidate manifest by local human receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import assess_golden_set_readiness
import build_stage_context
import diff_policy
import initialize_portable_run


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "golden-set-adoption.json"
FALSE_FIELDS = assess_golden_set_readiness.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "historical_golden_set_adoption",
    "mode": "exact-local-adoption-only",
    "confirmation_prefix": "ADOPT-HISTORICAL-GOLDEN-SET",
    "max_approver_chars": 120,
    "max_receipt_bytes": 250000,
    "require_candidate_manifest_valid": True,
    "require_source_state_authenticated": True,
    "require_issue_closure_independently_verified": True,
    "require_issue_reference_equivalence_reviewed": True,
    "require_external_receipt": True,
    "require_absent_receipt": True,
    "bindings": [
        ".agent/checks/approve_golden_set.py",
        ".agent/policies/golden-set-adoption.json",
        ".agent/checks/assess_golden_set_readiness.py",
        ".agent/policies/golden-set-readiness.json",
        "docs/agent-guides/golden-set-readiness.md",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Golden-set adoption policy does not match")
    return policy


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True, separators=(",", ": ")).encode(
        "utf-8"
    ) + b"\n"


def failure(rule: str, message: str) -> dict[str, str]:
    return {"rule": rule, "message": message}


def validate_approver(value: str, max_chars: int) -> str:
    if not value.strip() or len(value) > max_chars or "\n" in value or "\r" in value:
        raise ValueError("Approver declaration is empty, too long, or multiline")
    return value


def binding_records(policy: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    records = initialize_portable_run.binding_records(policy["bindings"])
    digest = assess_golden_set_readiness.sha256_bytes(
        (json.dumps(records, sort_keys=True) + "\n").encode("utf-8")
    )
    return records, digest


def repo_root(repo: Path) -> Path:
    return Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()


def validate_receipt_path(repo: Path, receipt: Path, policy: dict[str, Any]) -> Path:
    root = repo_root(repo)
    if receipt.is_symlink():
        raise ValueError("Golden-set adoption receipt symbolic links are not allowed")
    if "\n" in str(receipt) or "\r" in str(receipt):
        raise ValueError("Golden-set adoption receipt path must not contain line breaks")
    receipt = receipt.resolve()
    if policy["require_external_receipt"] and build_stage_context.is_within(receipt, root):
        raise ValueError("Golden-set adoption receipt must be outside the Git checkout")
    if policy["require_absent_receipt"] and receipt.exists():
        raise ValueError("Golden-set adoption receipt already exists")
    if not receipt.parent.is_dir():
        raise ValueError("Golden-set adoption receipt parent must be an existing directory")
    return receipt


def base_result(receipt: Path) -> dict[str, Any]:
    return {
        "adoptable": False,
        "golden_set_adopted": False,
        "receipt_written": False,
        "receipt": str(receipt),
        "receipt_sha256": None,
        **{field: False for field in FALSE_FIELDS},
        "candidate_manifest_valid": False,
        "source_state_authenticated": False,
        "issue_closure_independently_verified": False,
        "issue_reference_equivalence_reviewed": False,
        "approver_declaration": None,
        "manifest": None,
        "case_count": 0,
        "case_summaries": [],
        "local_references": [],
        "required_confirmation": None,
        "failures": [],
    }


def assess_adoption(
    repo: Path,
    manifest: Path,
    receipt: Path,
    policy: dict[str, Any],
) -> dict[str, Any]:
    receipt = validate_receipt_path(repo, receipt, policy)
    result = base_result(receipt)
    assessment = assess_golden_set_readiness.assess(
        repo,
        manifest,
        assess_golden_set_readiness.load_policy(),
    )
    result.update(
        candidate_manifest_valid=assessment["candidate_manifest_valid"],
        manifest=assessment["manifest"],
        case_count=assessment["case_count"],
        case_summaries=assessment["case_summaries"],
        local_references=assessment["local_references"],
    )
    if policy["require_candidate_manifest_valid"] and not assessment[
        "candidate_manifest_valid"
    ]:
        result["failures"].append(
            failure("candidate_manifest", "Golden-set adoption requires a valid candidate manifest.")
        )
        result["failures"].extend(assessment["reference_failures"])
    _bindings, bindings_sha256 = binding_records(policy)
    if not result["failures"]:
        result["required_confirmation"] = (
            f"{policy['confirmation_prefix']} "
            f"manifest_sha256={assessment['manifest']['sha256']} "
            f"case_count={assessment['case_count']} "
            f"local_reference_count={len(assessment['local_references'])} "
            f"source_state_authenticated=true "
            f"issue_closure_independently_verified=true "
            f"issue_reference_equivalence_reviewed=true "
            f"golden_set_adoption_bindings_sha256={bindings_sha256} "
            f"receipt={receipt}"
        )
    result["adoptable"] = not result["failures"]
    return result


def receipt_value(
    result: dict[str, Any],
    approver: str,
    confirmation: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    bindings, _bindings_sha256 = binding_records(policy)
    return {
        "golden_set_adoption_receipt_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "golden_set_adopted": True,
        "candidate_manifest_valid": True,
        "source_state_authenticated": True,
        "issue_closure_independently_verified": True,
        "issue_reference_equivalence_reviewed": True,
        "approver_declaration": approver,
        "confirmation_sha256": assess_golden_set_readiness.sha256_bytes(
            confirmation.encode("utf-8")
        ),
        "manifest": result["manifest"],
        "case_count": result["case_count"],
        "case_summaries": result["case_summaries"],
        "local_references": result["local_references"],
        "bindings": bindings,
    }


def adopt(args: argparse.Namespace, policy: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    approver = validate_approver(args.approver, policy["max_approver_chars"])
    if build_stage_context.detect_secrets(
        [build_stage_context.content_record("approver", approver)],
        diff_policy.load_policy(REPO_ROOT / ".agent" / "policies" / "diff-policy.json"),
    ):
        raise ValueError("Approver declaration contains a high-confidence secret signature")
    required_flags = (
        args.source_state_authenticated
        and args.issue_closure_independently_verified
        and args.issue_reference_equivalence_reviewed
    )
    if not required_flags:
        result["failures"].append(
            failure("manual_attestations", "All golden-set adoption attestations are required.")
        )
        result["adoptable"] = False
        return result
    if args.confirm != result["required_confirmation"]:
        result["failures"].append(
            failure("confirmation_mismatch", "Confirmation does not match the exact golden set.")
        )
        result["adoptable"] = False
        return result
    refreshed = assess_adoption(args.repo, args.manifest, args.receipt, policy)
    if not refreshed["adoptable"] or args.confirm != refreshed["required_confirmation"]:
        refreshed["failures"].append(
            failure("state_changed", "Golden-set candidate or adoption controls changed.")
        )
        refreshed["adoptable"] = False
        return refreshed
    value = receipt_value(refreshed, approver, args.confirm, policy)
    content = canonical_bytes(value)
    if len(content) > policy["max_receipt_bytes"]:
        raise ValueError("Golden-set adoption receipt exceeds max_receipt_bytes")
    receipt = Path(refreshed["receipt"])
    initialize_portable_run.write_exclusive(receipt, content)
    refreshed.update(
        adoptable=False,
        golden_set_adopted=True,
        receipt_written=True,
        receipt_sha256=assess_golden_set_readiness.sha256_bytes(content),
        source_state_authenticated=True,
        issue_closure_independently_verified=True,
        issue_reference_equivalence_reviewed=True,
        approver_declaration=approver,
        required_confirmation=None,
    )
    return refreshed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("check", "adopt"):
        sub = subparsers.add_parser(action)
        sub.add_argument("--repo", type=Path, required=True)
        sub.add_argument("--manifest", type=Path, required=True)
        sub.add_argument("--receipt", type=Path, required=True)
        sub.add_argument("--format", choices=("text", "json"), default="json")
        if action == "adopt":
            sub.add_argument("--approver", required=True)
            sub.add_argument("--confirm", required=True)
            sub.add_argument("--source-state-authenticated", action="store_true")
            sub.add_argument("--issue-closure-independently-verified", action="store_true")
            sub.add_argument("--issue-reference-equivalence-reviewed", action="store_true")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "ADOPTED" if result["golden_set_adopted"] else "ADOPTABLE" if result["adoptable"] else "BLOCKED"
    lines = [
        f"golden-set-adoption: {status}",
        f"case_count={result['case_count']}",
        f"receipt_written={str(result['receipt_written']).lower()}",
        "agent_invocation_authorized=false",
    ]
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        policy = load_policy()
        result = assess_adoption(args.repo, args.manifest, args.receipt, policy)
        if args.action == "adopt" and result["adoptable"]:
            result = adopt(args, policy, result)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"golden-set-adoption: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if (result["adoptable"] if args.action == "check" else result["golden_set_adopted"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
