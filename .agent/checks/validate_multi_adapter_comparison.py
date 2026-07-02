#!/usr/bin/env python3
"""Validate and summarize local multi-adapter artifacts without invoking adapters."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import diff_policy


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "multi-adapter-comparison.json"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,119}")
COMPARISON_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,119}")
FALSE_FIELDS = (
    "authorized",
    "adapter_invocation_authorized",
    "model_invocation_authorized",
    "network_authorized",
    "repository_mutation_authorized",
    "external_service_written",
    "publication_authorized",
    "comparison_executed",
    "metrics_recorded",
    "winner_selected",
)

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "multi_adapter_comparison",
    "mode": "local-artifact-and-metrics-comparison-only",
    "max_manifest_bytes": 40000,
    "max_artifact_bytes": 20000000,
    "max_metrics_record_bytes": 50000,
    "min_candidates": 2,
    "max_candidates": 12,
    "stages": ["research", "plan", "implement", "review"],
    "artifact_roles": ["stage_output", "complete_patch", "summary", "not_applicable"],
    "metric_table": [
        "outcome.status",
        "final_disposition",
        "regression_status",
        "timing.duration_ms",
        "tokens.input_tokens",
        "tokens.output_tokens",
        "cost.amount_microunits",
        "human_corrections.count",
        "diff.changed_lines",
    ],
    "require_distinct_adapters": True,
    "require_shared_stage": True,
    "require_shared_base_commit": True,
    "require_shared_context_sha256": True,
    "no_winner_selection": True,
    "bindings": [
        ".agent/checks/validate_multi_adapter_comparison.py",
        ".agent/policies/multi-adapter-comparison.json",
        ".agent/checks/record_run_metrics.py",
        ".agent/policies/run-metrics.json",
        "docs/agent-guides/multi-adapter-comparison-readiness.md",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Multi-adapter comparison policy does not match")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def read_bounded_file(path: Path, expected_sha256: str, max_bytes: int, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be an existing regular file")
    content = path.read_bytes()
    if len(content) > max_bytes:
        raise ValueError(f"{label} exceeds the policy byte limit")
    digest = sha256_bytes(content)
    if digest != expected_sha256:
        raise ValueError(f"{label} SHA-256 does not match")
    return content


def read_manifest(path: Path, max_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Manifest must be an existing regular file")
    content = path.read_bytes()
    if len(content) > max_bytes:
        raise ValueError("Manifest exceeds the policy byte limit")
    return content


def resolve_manifest_path(manifest_path: Path, value: Any, label: str) -> Path:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty path string")
    path = Path(value)
    if not path.is_absolute():
        path = manifest_path.parent / path
    return path.resolve()


def require_exact_fields(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields do not match the contract")
    return value


def require_identifier(value: Any, label: str) -> str:
    if type(value) is not str or IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a bounded identifier")
    return value


def require_sha256(value: Any, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a 64-character lowercase SHA-256")
    return value


def metric_value(record: dict[str, Any], dotted: str) -> Any:
    value: Any = record
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def validate_metric_record(
    record: Any,
    candidate: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Metrics record must be a JSON object")
    if (
        record.get("metrics_version") != 1
        or record.get("purpose") != "agentic_run_metrics_record"
        or record.get("mode") != "manual-evidence-recording-only"
    ):
        raise ValueError("Metrics record identity does not match the run-metrics contract")
    for field in (
        "authorized",
        "agent_invocation_authorized",
        "implementation_authorized",
        "repository_mutation_authorized",
        "network_authorized",
        "publication_authorized",
        "runner_selected",
        "session_start_authorized",
    ):
        if record.get(field) is not False:
            raise ValueError(f"Metrics record must keep {field}=false")
    if record.get("issue") != task["issue"]:
        raise ValueError("Metrics record issue does not match the comparison task")
    if record.get("stage") != task["stage"]:
        raise ValueError("Metrics record stage does not match the comparison task")
    if record.get("base_commit") != task["base_commit"]:
        raise ValueError("Metrics record base_commit does not match the comparison task")
    if record.get("adapter") != candidate["adapter"]:
        raise ValueError("Metrics record adapter does not match the candidate")
    if record.get("model") != candidate["model"]:
        raise ValueError("Metrics record model does not match the candidate")
    for field in ("run_id", "timing", "tokens", "cost", "outcome", "human_corrections", "diff"):
        if field not in record:
            raise ValueError(f"Metrics record is missing {field}")
    if type(record["run_id"]) is not str or not record["run_id"]:
        raise ValueError("Metrics record run_id must be present")
    if not isinstance(record["timing"], dict) or type(record["timing"].get("duration_ms")) is not int:
        raise ValueError("Metrics record timing.duration_ms must be an integer")
    if record["timing"]["duration_ms"] < 0:
        raise ValueError("Metrics record timing.duration_ms must be non-negative")
    return record


def validate_manifest(value: Any, policy: dict[str, Any]) -> dict[str, Any]:
    manifest = require_exact_fields(
        value,
        {
            "manifest_version",
            "purpose",
            "mode",
            "comparison_id",
            "task",
            "candidates",
            "manual_interpretation",
        },
        "Manifest",
    )
    if (
        manifest["manifest_version"] != policy["version"]
        or manifest["purpose"] != "multi_adapter_comparison_manifest"
        or manifest["mode"] != policy["mode"]
        or type(manifest["comparison_id"]) is not str
        or COMPARISON_ID.fullmatch(manifest["comparison_id"]) is None
    ):
        raise ValueError("Manifest identity does not match the comparison contract")
    task = require_exact_fields(
        manifest["task"],
        {"id", "issue", "stage", "base_commit", "context_sha256"},
        "task",
    )
    require_identifier(task["id"], "task.id")
    if type(task["issue"]) is not int or task["issue"] < 1:
        raise ValueError("task.issue must be a positive integer")
    if task["stage"] not in policy["stages"]:
        raise ValueError("task.stage is unsupported")
    if type(task["base_commit"]) is not str or COMMIT.fullmatch(task["base_commit"]) is None:
        raise ValueError("task.base_commit must be a 40-character lowercase commit")
    require_sha256(task["context_sha256"], "task.context_sha256")
    manual = require_exact_fields(
        manifest["manual_interpretation"],
        {"required", "winner_selected"},
        "manual_interpretation",
    )
    if manual != {"required": True, "winner_selected": False}:
        raise ValueError("Manual interpretation must remain required with no winner selected")
    candidates = manifest["candidates"]
    if (
        not isinstance(candidates, list)
        or len(candidates) < policy["min_candidates"]
        or len(candidates) > policy["max_candidates"]
    ):
        raise ValueError("Manifest must include a bounded set of comparison candidates")
    seen_ids: set[str] = set()
    adapter_ids: set[str] = set()
    for index, candidate_value in enumerate(candidates):
        candidate = require_exact_fields(
            candidate_value,
            {"candidate_id", "adapter", "model", "artifact", "metrics_record"},
            f"candidate[{index}]",
        )
        candidate_id = require_identifier(candidate["candidate_id"], f"candidate[{index}].candidate_id")
        if candidate_id in seen_ids:
            raise ValueError("Candidate identifiers must be unique")
        seen_ids.add(candidate_id)
        adapter = require_exact_fields(candidate["adapter"], {"id", "version"}, "adapter")
        require_identifier(adapter["id"], "adapter.id")
        require_identifier(adapter["version"], "adapter.version")
        adapter_ids.add(adapter["id"])
        model = require_exact_fields(candidate["model"], {"provider", "id"}, "model")
        require_identifier(model["provider"], "model.provider")
        require_identifier(model["id"], "model.id")
        artifact = require_exact_fields(candidate["artifact"], {"role", "path", "sha256"}, "artifact")
        if artifact["role"] not in policy["artifact_roles"]:
            raise ValueError("artifact.role is unsupported")
        if artifact["role"] == "not_applicable":
            if artifact["path"] is not None or artifact["sha256"] is not None:
                raise ValueError("not_applicable artifacts must use null path and sha256")
        else:
            require_sha256(artifact["sha256"], "artifact.sha256")
        metrics_record = require_exact_fields(
            candidate["metrics_record"],
            {"path", "sha256"},
            "metrics_record",
        )
        require_sha256(metrics_record["sha256"], "metrics_record.sha256")
    if policy["require_distinct_adapters"] and len(adapter_ids) < policy["min_candidates"]:
        raise ValueError("Manifest must compare at least two distinct adapters")
    return manifest


def binding_records(repo: Path, names: list[str]) -> list[dict[str, Any]]:
    records = []
    for name in names:
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Multi-adapter comparison binding must be a regular file: {name}")
        content = path.read_bytes()
        records.append({"name": name, "sha256": sha256_bytes(content), "size_bytes": len(content)})
    return records


def git_status(repo: Path) -> bytes:
    return diff_policy.run_git(repo, "status", "--porcelain=v1", "--untracked-files=all")


def build_comparison(repo: Path, manifest_path: Path, policy: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(
        diff_policy.run_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    ).resolve()
    before = git_status(repo_root)

    manifest_path = manifest_path.resolve()
    manifest_bytes = read_manifest(manifest_path, policy["max_manifest_bytes"])
    manifest = validate_manifest(json.loads(manifest_bytes.decode("utf-8-sig")), policy)
    task = manifest["task"]
    rows = []
    for candidate in manifest["candidates"]:
        artifact = candidate["artifact"]
        artifact_record = {
            "role": artifact["role"],
            "path": artifact["path"],
            "sha256": artifact["sha256"],
            "size_bytes": 0,
        }
        if artifact["role"] != "not_applicable":
            artifact_path = resolve_manifest_path(manifest_path, artifact["path"], "artifact.path")
            artifact_bytes = read_bounded_file(
                artifact_path,
                artifact["sha256"],
                policy["max_artifact_bytes"],
                "Artifact",
            )
            artifact_record["path"] = str(artifact_path)
            artifact_record["size_bytes"] = len(artifact_bytes)

        metrics_path = resolve_manifest_path(
            manifest_path,
            candidate["metrics_record"]["path"],
            "metrics_record.path",
        )
        metrics_bytes = read_bounded_file(
            metrics_path,
            candidate["metrics_record"]["sha256"],
            policy["max_metrics_record_bytes"],
            "Metrics record",
        )
        metrics_record = validate_metric_record(
            json.loads(metrics_bytes.decode("utf-8-sig")),
            candidate,
            task,
        )
        if artifact["role"] == "complete_patch" and metrics_record["diff"].get("sha256") != artifact["sha256"]:
            raise ValueError("complete_patch artifact SHA-256 must match metrics diff.sha256")
        rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "adapter": candidate["adapter"],
                "model": candidate["model"],
                "artifact": artifact_record,
                "metrics_record": {
                    "path": str(metrics_path),
                    "sha256": candidate["metrics_record"]["sha256"],
                    "size_bytes": len(metrics_bytes),
                    "run_id": metrics_record["run_id"],
                },
                "metrics": {
                    "outcome": metrics_record["outcome"],
                    "final_disposition": metrics_record.get("final_disposition"),
                    "regression_status": metrics_record.get("regression_status"),
                    "timing": {"duration_ms": metrics_record["timing"]["duration_ms"]},
                    "tokens": metrics_record["tokens"],
                    "cost": metrics_record["cost"],
                    "human_corrections": metrics_record["human_corrections"],
                    "diff": {
                        "status": metrics_record["diff"].get("status"),
                        "sha256": metrics_record["diff"].get("sha256"),
                        "changed_lines": metrics_record["diff"].get("changed_lines"),
                        "additions": metrics_record["diff"].get("additions"),
                        "deletions": metrics_record["diff"].get("deletions"),
                        "file_count": metrics_record["diff"].get("file_count"),
                    },
                },
                "_raw_record": metrics_record,
            }
        )

    rows.sort(key=lambda row: row["candidate_id"])
    metric_table = [
        {
            "metric": metric,
            "values": [
                {"candidate_id": row["candidate_id"], "value": metric_value(row["_raw_record"], metric)}
                for row in rows
            ],
        }
        for metric in policy["metric_table"]
    ]
    for row in rows:
        del row["_raw_record"]

    bindings = binding_records(repo_root, policy["bindings"])
    after = git_status(repo_root)
    if after != before:
        raise ValueError("Repository state changed during multi-adapter comparison validation")

    return {
        "comparison_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "valid": True,
        "local_comparison_calculated": True,
        "local_artifacts_compared": True,
        "manual_interpretation_required": True,
        "shared_context_declared": True,
        "shared_context_provenance_validated": False,
        "comparison_id": manifest["comparison_id"],
        "task": task,
        "candidate_count": len(rows),
        "candidates": rows,
        "metric_table": metric_table,
        "source_evidence": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "manifest_size_bytes": len(manifest_bytes),
        },
        "policy_bindings": bindings,
        "repo_unchanged": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "multi-adapter-comparison: VALID",
            f"comparison_id={result['comparison_id']}",
            f"candidate_count={result['candidate_count']}",
            "adapter_invocation_authorized=false",
            "model_invocation_authorized=false",
            "winner_selected=false",
        ]
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = build_comparison(args.repo, args.manifest, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"multi-adapter-comparison: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
