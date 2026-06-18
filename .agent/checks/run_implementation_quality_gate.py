#!/usr/bin/env python3
"""Run the exact Gradle quality gate for one validated implementation candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Callable

import build_stage_context
import diff_policy
import generate_complete_patch
import initialize_portable_run
import validate_implementation_patch
import validate_implementation_patch_receipt
import validate_implementation_result


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "implementation-quality-gate.json"
FALSE_FIELDS = validate_implementation_result.FALSE_FIELDS

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "implementation_quality_gate_execution",
    "mode": "controlled-gradle-execution-only",
    "required_platform": "Windows",
    "wrapper": "gradlew.bat",
    "required_distribution_directory": "gradle-8.11.1-bin",
    "commands": [
        {"id": "static_analysis", "tasks": ["ktlintCheck", "detekt"]},
        {"id": "tests", "tasks": ["test"]},
        {"id": "plugin_verification", "tasks": ["verifyPlugin"]},
    ],
    "fixed_arguments": ["--offline", "--no-daemon", "--console=plain"],
    "command_timeout_seconds": 900.0,
    "max_total_seconds": 1800.0,
    "max_captured_output_bytes": 2097152,
    "capture_chunk_bytes": 8192,
    "max_pending_capture_chunks": 8,
    "cleanup_timeout_seconds": 10.0,
    "max_receipt_bytes": 100000,
    "tree_terminator": "taskkill",
    "tree_terminator_arguments": ["/PID", "{root_pid}", "/T", "/F"],
    "allowed_parent_variables": [
        "COMSPEC",
        "JAVA_HOME",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "WINDIR",
    ],
    "fixed_child_environment": {
        "AGENT_QUALITY_GATE_MODE": "isolated",
        "CI": "true",
    },
    "require_valid_patch_receipt": True,
    "require_patch_candidate_ready": True,
    "require_external_gradle_user_home": True,
    "require_cached_wrapper_distribution": True,
    "require_external_receipt": True,
    "require_receipt_outside_workspace": True,
    "require_absent_receipt": True,
    "require_workspace_git_state_unchanged": True,
    "stop_after_first_failure": True,
    "network_requested": False,
    "bindings": [
        ".agent/checks/run_implementation_quality_gate.py",
        ".agent/policies/implementation-quality-gate.json",
        ".agent/checks/validate_implementation_patch_receipt.py",
        ".agent/policies/implementation-patch-post-validation-validation.json",
        "gradlew.bat",
        "gradle/wrapper/gradle-wrapper.properties",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Implementation quality-gate policy does not match")
    return policy


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def child_environment(
    parent: Mapping[str, str],
    policy: dict[str, Any],
) -> dict[str, str]:
    index = {name.upper(): name for name in parent}
    if len(index) != len(parent):
        raise ValueError("Parent environment contains duplicate names")
    environment = {
        name: parent[index[name]]
        for name in policy["allowed_parent_variables"]
        if name in index and isinstance(parent[index[name]], str)
    }
    environment.update(policy["fixed_child_environment"])
    return environment


def taskkill_command(path: str, pid: int, policy: dict[str, Any]) -> list[str]:
    return [
        path,
        *[
            part.replace("{root_pid}", str(pid))
            for part in policy["tree_terminator_arguments"]
        ],
    ]


def exact_gradle_command(
    workspace: Path,
    tasks: Sequence[str],
    environment: Mapping[str, str],
    policy: dict[str, Any],
) -> list[str]:
    wrapper = workspace / policy["wrapper"]
    if wrapper.is_symlink() or not wrapper.is_file():
        raise ValueError("Gradle wrapper must be an existing regular file")
    comspec = environment.get("COMSPEC")
    if not comspec:
        raise ValueError("COMSPEC is required for the Windows Gradle wrapper")
    executable = Path(comspec)
    if not executable.is_absolute() or executable.is_symlink() or not executable.is_file():
        raise ValueError("COMSPEC must identify an absolute regular file")
    return [
        str(executable),
        "/d",
        "/s",
        "/c",
        "call",
        policy["wrapper"],
        *tasks,
        *policy["fixed_arguments"],
    ]


def run_bounded(
    command: Sequence[str],
    cwd: Path,
    environment: Mapping[str, str],
    policy: dict[str, Any],
    timeout_seconds: float,
    taskkill_path: str,
    popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    if not command or any(not isinstance(part, str) or not part for part in command):
        raise ValueError("Quality-gate command is invalid")
    process = popen(
        list(command),
        cwd=cwd,
        env=dict(environment),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        bufsize=0,
    )
    if process.stdout is None or process.stderr is None:
        raise ValueError("Quality-gate process pipes were not created")
    events: queue.Queue[tuple[str, bytes | None]] = queue.Queue(
        maxsize=policy["max_pending_capture_chunks"]
    )
    stopped = threading.Event()

    def pump(name: str, stream: Any) -> None:
        try:
            while not stopped.is_set():
                chunk = stream.read(policy["capture_chunk_bytes"])
                if not chunk:
                    break
                while not stopped.is_set():
                    try:
                        events.put((name, chunk), timeout=0.05)
                        break
                    except queue.Full:
                        continue
        except (OSError, ValueError):
            pass
        finally:
            while not stopped.is_set():
                try:
                    events.put((name, None), timeout=0.05)
                    break
                except queue.Full:
                    continue

    threads = [
        threading.Thread(target=pump, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=pump, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()
    started = clock()
    deadline = started + timeout_seconds
    active = 2
    stdout = bytearray()
    stderr = bytearray()
    timed_out = False
    output_limit_exceeded = False
    while active:
        remaining = deadline - clock()
        if remaining <= 0:
            timed_out = True
            break
        try:
            name, chunk = events.get(timeout=min(remaining, 0.05))
        except queue.Empty:
            continue
        if chunk is None:
            active -= 1
            continue
        if len(stdout) + len(stderr) + len(chunk) > policy["max_captured_output_bytes"]:
            output_limit_exceeded = True
            break
        (stdout if name == "stdout" else stderr).extend(chunk)

    tree_kill_requested = False
    tree_kill_returncode: int | None = None
    direct_kill_requested = False
    returncode: int | None = None
    if timed_out or output_limit_exceeded:
        stopped.set()
        tree_kill_requested = True
        try:
            completed = run(
                taskkill_command(taskkill_path, process.pid, policy),
                cwd=cwd,
                check=False,
                capture_output=True,
                timeout=policy["cleanup_timeout_seconds"],
                shell=False,
            )
            tree_kill_returncode = completed.returncode
        except (OSError, subprocess.TimeoutExpired):
            tree_kill_returncode = None
    try:
        returncode = process.wait(timeout=policy["cleanup_timeout_seconds"])
        root_reaped = True
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
            direct_kill_requested = True
            returncode = process.wait(timeout=policy["cleanup_timeout_seconds"])
            root_reaped = True
        except (OSError, subprocess.TimeoutExpired):
            root_reaped = False
    stopped.set()
    process.stdout.close()
    process.stderr.close()
    for thread in threads:
        thread.join(timeout=policy["cleanup_timeout_seconds"])
    capture_complete = (
        active == 0
        and not timed_out
        and not output_limit_exceeded
        and root_reaped
        and all(not thread.is_alive() for thread in threads)
    )
    duration = round(clock() - started, 6)
    return {
        "completed": (
            root_reaped
            and not timed_out
            and not output_limit_exceeded
            and not direct_kill_requested
        ),
        "timed_out": timed_out,
        "output_limit_exceeded": output_limit_exceeded,
        "tree_kill_requested": tree_kill_requested,
        "tree_kill_returncode": tree_kill_returncode,
        "direct_kill_requested": direct_kill_requested,
        "root_reaped": root_reaped,
        "returncode": returncode,
        "capture_complete": capture_complete,
        "stdout": bytes(stdout) if capture_complete else b"",
        "stderr": bytes(stderr) if capture_complete else b"",
        "captured_stdout_bytes": len(stdout),
        "captured_stderr_bytes": len(stderr),
        "duration_seconds": duration,
    }


def command_record(
    command_id: str,
    tasks: list[str],
    execution: dict[str, Any],
) -> dict[str, Any]:
    stdout = execution.get("stdout", b"")
    stderr = execution.get("stderr", b"")
    passed = (
        execution.get("completed") is True
        and execution.get("capture_complete") is True
        and execution.get("returncode") == 0
    )
    return {
        "id": command_id,
        "tasks": tasks,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "returncode": execution.get("returncode"),
        "timed_out": execution.get("timed_out") is True,
        "output_limit_exceeded": execution.get("output_limit_exceeded") is True,
        "tree_kill_requested": execution.get("tree_kill_requested") is True,
        "tree_kill_returncode": execution.get("tree_kill_returncode"),
        "direct_kill_requested": execution.get("direct_kill_requested") is True,
        "root_reaped": execution.get("root_reaped") is True,
        "capture_complete": execution.get("capture_complete") is True,
        "stdout_bytes": execution.get("captured_stdout_bytes"),
        "stderr_bytes": execution.get("captured_stderr_bytes"),
        "stdout_sha256": sha256_bytes(stdout) if execution.get("capture_complete") else None,
        "stderr_sha256": sha256_bytes(stderr) if execution.get("capture_complete") else None,
        "duration_seconds": execution.get("duration_seconds"),
    }


def validate_receipt_output(
    source_root: Path,
    workspace: Path,
    output: Path,
    policy: dict[str, Any],
) -> Path:
    if output.is_symlink():
        raise ValueError("Quality-gate receipt symbolic links are not allowed")
    output = output.resolve()
    if policy["require_external_receipt"] and build_stage_context.is_within(
        output,
        source_root,
    ):
        raise ValueError("Quality-gate receipt must be outside the source checkout")
    if policy["require_receipt_outside_workspace"] and build_stage_context.is_within(
        output,
        workspace,
    ):
        raise ValueError("Quality-gate receipt must be outside the workspace")
    if policy["require_absent_receipt"] and output.exists():
        raise ValueError("Quality-gate receipt already exists")
    if not output.parent.is_dir():
        raise ValueError("Quality-gate receipt parent must exist")
    return output


def validate_gradle_user_home(
    source_root: Path,
    workspace: Path,
    gradle_user_home: Path,
    policy: dict[str, Any],
) -> Path:
    if gradle_user_home.is_symlink():
        raise ValueError("Gradle user home symbolic links are not allowed")
    gradle_user_home = gradle_user_home.resolve()
    if not gradle_user_home.is_dir():
        raise ValueError("Gradle user home must be an existing directory")
    if "\n" in str(gradle_user_home) or "\r" in str(gradle_user_home):
        raise ValueError("Gradle user home path must not contain line breaks")
    if policy["require_external_gradle_user_home"] and (
        build_stage_context.is_within(gradle_user_home, source_root)
        or build_stage_context.is_within(gradle_user_home, workspace)
    ):
        raise ValueError("Gradle user home must be outside source and workspace")
    if policy["require_cached_wrapper_distribution"]:
        distribution_root = (
            gradle_user_home
            / "wrapper"
            / "dists"
            / policy["required_distribution_directory"]
        )
        candidates = list(
            distribution_root.glob("*/gradle-8.11.1/bin/gradle.bat")
        )
        if not candidates or any(path.is_symlink() for path in candidates):
            raise ValueError("Required Gradle wrapper distribution is not cached")
    return gradle_user_home


def execute(
    source_checkout: Path,
    result_path: Path,
    expected_session_path: Path,
    patch: Path,
    patch_receipt: Path,
    patch_receipt_sha256: str,
    receipt_output: Path,
    gradle_user_home: Path,
    policy: dict[str, Any],
    parent_environment: Mapping[str, str] = os.environ,
    system: str = platform.system(),
    which: Callable[[str], str | None] = shutil.which,
    command_runner: Callable[..., dict[str, Any]] = run_bounded,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    source_root = Path(
        diff_policy.run_git(source_checkout, "rev-parse", "--show-toplevel")
        .decode("utf-8")
        .strip()
    ).resolve()
    expected_session = validate_implementation_result.validate_expected_session(
        json.loads(expected_session_path.read_text(encoding="utf-8-sig"))
    )
    workspace = Path(expected_session["workspace"]).resolve()
    receipt_output = validate_receipt_output(
        source_root,
        workspace,
        receipt_output,
        policy,
    )
    gradle_user_home = validate_gradle_user_home(
        source_root,
        workspace,
        gradle_user_home,
        policy,
    )
    result = {
        "execution_attempted": False,
        "quality_gate_passed": False,
        **{field: False for field in FALSE_FIELDS},
        "receipt_written": False,
        "receipt_sha256": None,
        "receipt_size_bytes": None,
        "patch_validation": None,
        "commands": [],
        "failures": [],
    }
    patch_validation = validate_implementation_patch_receipt.validate(
        source_root,
        result_path,
        expected_session_path,
        patch,
        patch_receipt,
        patch_receipt_sha256,
        validate_implementation_patch_receipt.load_policy(),
    )
    result["patch_validation"] = patch_validation
    if policy["require_valid_patch_receipt"] and not patch_validation["valid"]:
        result["failures"].append(
            {"rule": "patch_receipt", "message": "Patch receipt is not valid."}
        )
        return result
    if (
        policy["require_patch_candidate_ready"]
        and not patch_validation["patch_candidate_ready"]
    ):
        result["failures"].append(
            {"rule": "patch_candidate", "message": "Patch is not candidate-ready."}
        )
        return result
    if system != policy["required_platform"]:
        raise ValueError("Quality-gate execution requires Windows")
    taskkill_path = which(policy["tree_terminator"])
    if taskkill_path is None:
        raise ValueError("Quality-gate tree terminator is unavailable")
    environment = child_environment(parent_environment, policy)
    environment["GRADLE_USER_HOME"] = str(gradle_user_home)
    before = generate_complete_patch.repository_snapshot(workspace)
    input_bytes = {
        "result": result_path.read_bytes(),
        "expected_session": expected_session_path.read_bytes(),
        "patch": patch.read_bytes(),
        "patch_receipt": patch_receipt.read_bytes(),
    }
    bindings = initialize_portable_run.binding_records(policy["bindings"])
    started = clock()
    records: list[dict[str, Any]] = []
    result["execution_attempted"] = True
    for command in policy["commands"]:
        remaining = policy["max_total_seconds"] - (clock() - started)
        if remaining <= 0:
            records.append(
                {
                    "id": command["id"],
                    "tasks": command["tasks"],
                    "status": "not_run",
                    "passed": False,
                    "reason": "total_timeout",
                }
            )
            break
        execution = command_runner(
            exact_gradle_command(workspace, command["tasks"], environment, policy),
            workspace,
            environment,
            policy,
            min(policy["command_timeout_seconds"], remaining),
            taskkill_path,
        )
        record = command_record(command["id"], command["tasks"], execution)
        records.append(record)
        if not record["passed"] and policy["stop_after_first_failure"]:
            break
    executed_ids = {record["id"] for record in records}
    records.extend(
        {
            "id": command["id"],
            "tasks": command["tasks"],
            "status": "not_run",
            "passed": False,
            "reason": "previous_failure",
        }
        for command in policy["commands"]
        if command["id"] not in executed_ids
    )
    if (
        policy["require_workspace_git_state_unchanged"]
        and generate_complete_patch.repository_snapshot(workspace) != before
    ):
        raise ValueError("Implementation workspace Git state changed during quality gate")
    refreshed_inputs = {
        "result": result_path.read_bytes(),
        "expected_session": expected_session_path.read_bytes(),
        "patch": patch.read_bytes(),
        "patch_receipt": patch_receipt.read_bytes(),
    }
    refreshed_bindings = initialize_portable_run.binding_records(policy["bindings"])
    if refreshed_inputs != input_bytes or refreshed_bindings != bindings:
        raise ValueError("Quality-gate inputs or trusted bindings changed during execution")
    if (
        policy["require_workspace_git_state_unchanged"]
        and generate_complete_patch.repository_snapshot(workspace) != before
    ):
        raise ValueError("Implementation workspace Git state changed before receipt write")
    passed = all(record["status"] == "passed" for record in records)
    receipt_value = {
        "quality_gate_receipt_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "execution_attempted": True,
        "quality_gate_passed": passed,
        "network_requested": policy["network_requested"],
        "identity": {
            field: expected_session[field]
            for field in sorted(validate_implementation_result.SESSION_FIELDS)
        },
        "patch_receipt_sha256": patch_receipt_sha256,
        "patch_sha256": sha256_bytes(input_bytes["patch"]),
        "gradle_user_home": str(gradle_user_home),
        "commands": records,
        "workspace_git_state_unchanged": True,
        "bindings": bindings,
    }
    receipt_bytes = validate_implementation_patch.canonical_bytes(receipt_value)
    if len(receipt_bytes) > policy["max_receipt_bytes"]:
        raise ValueError("Quality-gate receipt exceeds byte limit")
    try:
        validate_implementation_patch.write_exclusive(receipt_output, receipt_bytes)
    except Exception:
        receipt_output.unlink(missing_ok=True)
        raise
    result.update(
        quality_gate_passed=passed,
        commands=records,
        receipt_written=True,
        receipt_sha256=sha256_bytes(receipt_bytes),
        receipt_size_bytes=len(receipt_bytes),
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--expected-session", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--patch-receipt", type=Path, required=True)
    parser.add_argument("--patch-receipt-sha256", required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--gradle-user-home", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    status = "PASSED" if result["quality_gate_passed"] else "FAILED"
    lines = [
        f"implementation-quality-gate: {status}",
        f"execution_attempted={str(result['execution_attempted']).lower()}",
        f"receipt_written={str(result['receipt_written']).lower()}",
        "publication_authorized=false",
    ]
    lines.extend(
        f"- {record['id']}: {record['status']}" for record in result["commands"]
    )
    lines.extend(f"- {item['rule']}: {item['message']}" for item in result["failures"])
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = execute(
            args.repo,
            args.result,
            args.expected_session,
            args.patch,
            args.patch_receipt,
            args.patch_receipt_sha256,
            args.receipt_output,
            args.gradle_user_home,
            load_policy(),
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
        ValueError,
    ) as error:
        print(f"implementation-quality-gate: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["quality_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
