#!/usr/bin/env python3
"""Validate one captured read-only stage response against its exact context."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import build_stage_context
import diff_policy
import validate_artifacts
import validate_prompts


SHA256 = re.compile(r"[0-9a-f]{64}")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_output_policy(
    path: Path,
    context_policy: dict[str, Any],
    prompt_contract: dict[str, Any],
    artifact_contract: dict[str, Any],
) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required = {"version", "max_response_bytes", "require_external_inputs", "stages"}
    missing = required.difference(policy)
    if missing:
        raise ValueError(f"Stage-output policy is missing fields: {', '.join(sorted(missing))}")
    if (
        not isinstance(policy["version"], int)
        or isinstance(policy["version"], bool)
        or policy["version"] != 1
    ):
        raise ValueError(f"Unsupported stage-output policy version: {policy['version']}")
    if (
        not isinstance(policy["max_response_bytes"], int)
        or isinstance(policy["max_response_bytes"], bool)
        or policy["max_response_bytes"] < 1
    ):
        raise ValueError("max_response_bytes must be a positive integer")
    if policy["require_external_inputs"] is not True:
        raise ValueError("require_external_inputs must explicitly be true during the pilot")
    if not isinstance(policy["stages"], dict) or set(policy["stages"]) != set(context_policy["stages"]):
        raise ValueError("stages must exactly match the stage-context policy")
    prompt_outputs = {
        specification["stage"]: specification["output_artifact"]
        for specification in prompt_contract["prompts"].values()
    }
    for stage, specification in policy["stages"].items():
        if not isinstance(specification, dict) or set(specification) != {
            "artifact",
            "allowed_statuses",
        }:
            raise ValueError(f"{stage} must define exactly artifact and allowed_statuses")
        artifact = specification["artifact"]
        if artifact != prompt_outputs[stage]:
            raise ValueError(f"{stage} artifact must match the portable prompt output")
        allowed = artifact_contract["artifacts"][artifact]["allowed_statuses"]
        statuses = specification["allowed_statuses"]
        if (
            not isinstance(statuses, list)
            or not statuses
            or not all(isinstance(status, str) and status in allowed for status in statuses)
            or len(statuses) != len(set(statuses))
        ):
            raise ValueError(f"{stage} allowed_statuses must be unique contracted statuses")
        if "approved" in statuses:
            raise ValueError(f"{stage} output must never self-approve")
        if "blocked" not in statuses:
            raise ValueError(f"{stage} output must allow blocked status")
    return policy


def validate_record(record: Any, expected_name: str) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if not isinstance(record, dict) or set(record) != {"name", "sha256", "size_bytes", "content"}:
        return [{"rule": "bundle_record", "message": f"Invalid content record: {expected_name}"}]
    if record["name"] != expected_name:
        failures.append({"rule": "bundle_record_name", "message": f"Wrong record name: {expected_name}"})
    if not isinstance(record["content"], str):
        return failures + [{"rule": "bundle_record_content", "message": f"Non-text record: {expected_name}"}]
    content = record["content"].encode("utf-8")
    if record["size_bytes"] != len(content):
        failures.append({"rule": "bundle_record_size", "message": f"Wrong record size: {expected_name}"})
    if record["sha256"] != hashlib.sha256(content).hexdigest():
        failures.append({"rule": "bundle_record_sha256", "message": f"Wrong record digest: {expected_name}"})
    return failures


def validate_bundle(
    bundle: Any,
    expected_digest: str,
    bundle_path: Path,
    context_policy: dict[str, Any],
    prompt_contract: dict[str, Any],
    artifact_contract: dict[str, Any],
    prompts_dir: Path,
) -> tuple[list[dict[str, str]], validate_artifacts.Artifact | None]:
    failures: list[dict[str, str]] = []
    if not SHA256.fullmatch(expected_digest):
        raise ValueError("Expected bundle SHA-256 must be 64 lowercase hexadecimal characters")
    if file_sha256(bundle_path) != expected_digest:
        return [{"rule": "bundle_sha256", "message": "Bundle does not match its expected SHA-256."}], None
    expected_fields = {
        "bundle_version",
        "stage",
        "mode",
        "authorized",
        "issue",
        "risk",
        "base_commit",
        "provenance",
        "prompt",
        "artifacts",
    }
    if not isinstance(bundle, dict) or set(bundle) != expected_fields:
        return [{"rule": "bundle_schema", "message": "Bundle fields do not match the contract."}], None
    stage = bundle["stage"]
    if stage not in context_policy["stages"]:
        return [{"rule": "bundle_stage", "message": "Bundle stage is not contracted."}], None
    if (
        bundle["bundle_version"] != context_policy["version"]
        or bundle["mode"] != "read-only"
        or bundle["authorized"] is not False
    ):
        failures.append({"rule": "bundle_metadata", "message": "Bundle safety metadata does not match."})
    stage_context = context_policy["stages"][stage]
    provenance = bundle["provenance"]
    if stage_context["provenance"] == "validated_task_approval":
        if (
            not isinstance(provenance, dict)
            or set(provenance) != {"kind", "task_approval_receipt_sha256"}
            or provenance["kind"] != "validated_task_approval"
            or type(provenance["task_approval_receipt_sha256"]) is not str
            or not SHA256.fullmatch(provenance["task_approval_receipt_sha256"])
        ):
            failures.append(
                {
                    "rule": "bundle_provenance",
                    "message": "Research bundle approval provenance does not match.",
                }
            )
    elif stage_context["provenance"] == "validated_stage_application":
        if (
            not isinstance(provenance, dict)
            or set(provenance) != {"kind", "stage_application_receipt_sha256"}
            or provenance["kind"] != "validated_stage_application"
            or type(provenance["stage_application_receipt_sha256"]) is not str
            or not SHA256.fullmatch(provenance["stage_application_receipt_sha256"])
        ):
            failures.append(
                {
                    "rule": "bundle_provenance",
                    "message": "Plan bundle research-application provenance does not match.",
                }
            )
    elif stage_context["provenance"] == "local_artifact_contract":
        if provenance != {"kind": "local_artifact_contract"}:
            failures.append(
                {
                    "rule": "bundle_provenance",
                    "message": "Bundle local artifact provenance does not match.",
                }
            )
    elif provenance != {"kind": "none"}:
        failures.append(
            {
                "rule": "bundle_provenance",
                "message": "Bundle unexpectedly declares approval provenance.",
            }
        )
    failures.extend(validate_record(bundle["prompt"], stage_context["prompt"]))
    prompt_path = prompts_dir / stage_context["prompt"]
    if (
        isinstance(bundle["prompt"], dict)
        and isinstance(bundle["prompt"].get("content"), str)
        and bundle["prompt"]["content"] != prompt_path.read_text(encoding="utf-8-sig")
    ):
        failures.append(
            {"rule": "bundle_prompt_content", "message": "Bundle prompt differs from repository prompt."}
        )
    artifacts = bundle["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != len(stage_context["artifacts"]):
        failures.append({"rule": "bundle_artifacts", "message": "Bundle artifact list does not match."})
        return failures, None
    for record, expected_name in zip(artifacts, stage_context["artifacts"], strict=True):
        failures.extend(validate_record(record, expected_name))
    task_record = artifacts[stage_context["artifacts"].index("task.md")]
    if not isinstance(task_record, dict) or not isinstance(task_record.get("content"), str):
        return failures, None
    try:
        task = validate_artifacts.parse_artifact_text("task.md", task_record["content"])
    except ValueError:
        failures.append({"rule": "bundle_task", "message": "Bundle task artifact is invalid."})
        return failures, None
    if (
        task.frontmatter.get("artifact") != artifact_contract["artifacts"]["task.md"]["artifact"]
        or task.frontmatter.get("artifact_version") != str(artifact_contract["version"])
        or task.frontmatter.get("status") != "approved"
        or task.frontmatter.get("issue") != str(bundle["issue"])
        or task.frontmatter.get("risk") != bundle["risk"]
        or task.frontmatter.get("base_commit") != bundle["base_commit"]
    ):
        failures.append({"rule": "bundle_task_metadata", "message": "Bundle metadata does not match task.md."})
    prompt_spec = prompt_contract["prompts"][stage_context["prompt"]]
    if prompt_spec["stage"] != stage:
        failures.append({"rule": "bundle_prompt_stage", "message": "Bundle prompt does not match stage."})
    return failures, task


def validate_output(
    bundle_path: Path,
    expected_bundle_sha256: str,
    response_path: Path,
    repo_root: Path,
    policies: dict[str, Any],
    prompts_dir: Path,
) -> dict[str, Any]:
    if bundle_path.is_symlink() or response_path.is_symlink():
        raise ValueError("Bundle and response symbolic links are not allowed")
    bundle_path = bundle_path.resolve()
    response_path = response_path.resolve()
    repo_root = repo_root.resolve()
    if policies["output"]["require_external_inputs"]:
        if build_stage_context.is_within(bundle_path, repo_root):
            raise ValueError("Bundle must be outside the Git checkout")
        if build_stage_context.is_within(response_path, repo_root):
            raise ValueError("Captured response must be outside the Git checkout")
    if not SHA256.fullmatch(expected_bundle_sha256):
        raise ValueError("Expected bundle SHA-256 must be 64 lowercase hexadecimal characters")
    early_result: dict[str, Any] = {
        "valid": False,
        "accepted": False,
        "authorized": False,
        "stage": None,
        "artifact": None,
        "status": None,
        "failures": [],
    }
    if bundle_path.stat().st_size > policies["context"]["max_bundle_bytes"]:
        early_result["failures"].append(
            {"rule": "max_bundle_bytes", "message": "Bundle exceeds the configured byte limit."}
        )
        return early_result
    if file_sha256(bundle_path) != expected_bundle_sha256:
        early_result["failures"].append(
            {"rule": "bundle_sha256", "message": "Bundle does not match its expected SHA-256."}
        )
        return early_result
    bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
    failures, task = validate_bundle(
        bundle,
        expected_bundle_sha256,
        bundle_path,
        policies["context"],
        policies["prompt"],
        policies["artifact"],
        prompts_dir,
    )
    stage = bundle.get("stage") if isinstance(bundle, dict) else None
    result: dict[str, Any] = {
        "valid": False,
        "accepted": False,
        "authorized": False,
        "stage": stage,
        "artifact": None,
        "status": None,
        "failures": failures,
    }
    if failures or task is None or stage not in policies["output"]["stages"]:
        return result
    response_bytes = response_path.read_bytes()
    if len(response_bytes) > policies["output"]["max_response_bytes"]:
        result["failures"].append(
            {"rule": "max_response_bytes", "message": "Captured response exceeds the byte limit."}
        )
        return result
    try:
        response_text = response_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        result["failures"].append({"rule": "response_utf8", "message": "Captured response is not UTF-8."})
        return result
    detections = build_stage_context.detect_secrets(
        [build_stage_context.content_record("response", response_text)],
        policies["diff"],
    )
    if detections:
        result["failures"].append(
            {
                "rule": "high_confidence_secret",
                "message": "Captured response contains a high-confidence secret signature.",
                "detections": detections,
            }
        )
        return result
    expected_artifact = policies["output"]["stages"][stage]["artifact"]
    try:
        artifact = validate_artifacts.parse_artifact_text(expected_artifact, response_text)
    except ValueError as error:
        result["failures"].append({"rule": "parse_response", "message": str(error)})
        return result
    result["artifact"] = expected_artifact
    result["status"] = artifact.frontmatter.get("status")
    specification = policies["artifact"]["artifacts"][expected_artifact]
    required_frontmatter = set(policies["artifact"]["common_frontmatter"]) | set(
        specification["required_frontmatter"]
    )
    if set(artifact.frontmatter) != required_frontmatter:
        result["failures"].append(
            {"rule": "response_frontmatter", "message": "Response frontmatter does not exactly match."}
        )
    if (
        artifact.frontmatter.get("artifact") != specification["artifact"]
        or artifact.frontmatter.get("artifact_version") != str(policies["artifact"]["version"])
    ):
        result["failures"].append({"rule": "response_identity", "message": "Response artifact identity is invalid."})
    if (
        artifact.frontmatter.get("issue") != task.frontmatter["issue"]
        or artifact.frontmatter.get("base_commit") != task.frontmatter["base_commit"]
    ):
        result["failures"].append({"rule": "response_context", "message": "Response issue or base commit differs."})
    if artifact.frontmatter.get("status") not in policies["output"]["stages"][stage]["allowed_statuses"]:
        result["failures"].append({"rule": "response_status", "message": "Response status is not allowed for stage."})
    for section in specification["required_sections"]:
        if section not in artifact.sections:
            result["failures"].append({"rule": "response_sections", "message": f"Missing section: {section}"})
        elif not artifact.sections[section]:
            result["failures"].append({"rule": "response_sections", "message": f"Empty section: {section}"})
    if set(artifact.sections) != set(specification["required_sections"]):
        result["failures"].append(
            {"rule": "response_sections", "message": "Response contains unexpected sections."}
        )
    if validate_artifacts.PLACEHOLDER.search(artifact.text):
        result["failures"].append({"rule": "response_placeholders", "message": "Response contains placeholders."})
    result["valid"] = not result["failures"]
    result["accepted"] = result["valid"]
    return result


def build_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="Git checkout root")
    parser.add_argument("--bundle", type=Path, required=True, help="External stage-context JSON")
    parser.add_argument("--bundle-sha256", required=True, help="Expected bundle SHA-256")
    parser.add_argument("--response", type=Path, required=True, help="External captured raw response")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--artifact-contract", type=Path, default=repo_root / ".agent/policies/artifact-contract.json")
    parser.add_argument("--prompt-contract", type=Path, default=repo_root / ".agent/policies/prompt-contract.json")
    parser.add_argument("--context-policy", type=Path, default=repo_root / ".agent/policies/stage-context.json")
    parser.add_argument("--output-policy", type=Path, default=repo_root / ".agent/policies/stage-output.json")
    parser.add_argument("--diff-policy", type=Path, default=repo_root / ".agent/policies/diff-policy.json")
    parser.add_argument("--prompts", type=Path, default=repo_root / ".agent/prompts")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "VALID" if result["valid"] else "INVALID"
    lines = [
        f"stage-output: {status} stage={result['stage'] or 'unknown'}",
        f"accepted={str(result['accepted']).lower()}",
        "authorized=false",
    ]
    for failure in result["failures"]:
        lines.append(f"- {failure['rule']}: {failure['message']}")
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        artifact = validate_artifacts.load_contract(args.artifact_contract)
        prompt = validate_prompts.load_prompt_contract(args.prompt_contract, artifact)
        context = build_stage_context.load_context_policy(args.context_policy, prompt, artifact)
        policies = {
            "artifact": artifact,
            "prompt": prompt,
            "context": context,
            "output": load_output_policy(args.output_policy, context, prompt, artifact),
            "diff": diff_policy.load_policy(args.diff_policy),
        }
        result = validate_output(
            args.bundle,
            args.bundle_sha256,
            args.response,
            args.repo,
            policies,
            args.prompts,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"stage-output: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
