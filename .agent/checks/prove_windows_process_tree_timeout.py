#!/usr/bin/env python3
"""Prove bounded taskkill cleanup for one harmless two-level Windows process tree."""

from __future__ import annotations

import argparse
import ctypes
import json
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / ".agent" / "policies" / "windows-process-tree-timeout-proof.json"
FALSE_FIELDS = (
    "authorized",
    "agent_invocation_authorized",
    "implementation_authorized",
    "runner_selected",
    "session_start_authorized",
)
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
SYNCHRONIZE = 0x00100000

EXPECTED_POLICY: dict[str, Any] = {
    "version": 1,
    "purpose": "windows_taskkill_process_tree_timeout_proof",
    "mode": "fixture-only",
    "required_platform": "Windows",
    "tree_terminator": "taskkill",
    "tree_terminator_arguments": ["/PID", "{root_pid}", "/T", "/F"],
    "discovery_timeout_seconds": 2.0,
    "timeout_seconds": 0.5,
    "cleanup_timeout_seconds": 3.0,
    "max_observed_seconds": 6.0,
    "fixture": {
        "id": "two_level_sleeping_tree",
        "descendant_depth": 2,
        "sleep_seconds": 10,
    },
    "proven_control": "windows_taskkill_two_level_process_tree_timeout_fixture",
    "unproven_controls": [
        "arbitrary_process_tree_timeout",
        "cross_platform_process_tree_timeout",
        "implementation_session_wall_clock_timeout",
        "process_spawn_timeout",
    ],
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if policy != EXPECTED_POLICY:
        raise ValueError("Windows process-tree proof policy does not match the fixture-only contract")
    return policy


def python_command(script: str) -> list[str]:
    return [sys.executable, "-I", "-S", "-B", "-c", script]


def root_script(sleep_seconds: int) -> str:
    grandchild = f"import time; time.sleep({sleep_seconds})"
    child = (
        "import subprocess,sys,time;"
        f"p=subprocess.Popen([sys.executable,'-I','-S','-B','-c',{grandchild!r}],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,"
        "shell=False);"
        "print(p.pid,flush=True);"
        f"time.sleep({sleep_seconds})"
    )
    return (
        "import subprocess,sys,time;"
        f"p=subprocess.Popen([sys.executable,'-I','-S','-B','-c',{child!r}],"
        "stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,"
        "text=True,shell=False);"
        "line=p.stdout.readline().strip();"
        "print(str(p.pid)+' '+line,flush=True);"
        f"time.sleep({sleep_seconds})"
    )


def read_line_with_timeout(stream: Any, timeout: float) -> bytes | None:
    result: queue.Queue[bytes | BaseException] = queue.Queue(maxsize=1)

    def read() -> None:
        try:
            result.put(stream.readline(), block=False)
        except BaseException as error:
            result.put(error, block=False)

    threading.Thread(target=read, daemon=True).start()
    try:
        value = result.get(timeout=timeout)
    except queue.Empty:
        return None
    if isinstance(value, BaseException):
        return None
    return value


class WindowsProcessHandle:
    def __init__(self, pid: int) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint32
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            raise OSError("Unable to open fixture process handle")
        self._kernel32 = kernel32
        self._handle = handle

    def is_running(self) -> bool:
        return self._kernel32.WaitForSingleObject(self._handle, 0) == WAIT_TIMEOUT

    def wait_terminated(self, timeout_seconds: float) -> bool:
        milliseconds = max(1, round(timeout_seconds * 1000))
        return self._kernel32.WaitForSingleObject(self._handle, milliseconds) == WAIT_OBJECT_0

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def taskkill_command(path: str, pid: int, policy: dict[str, Any]) -> list[str]:
    return [
        path,
        *[part.replace("{root_pid}", str(pid)) for part in policy["tree_terminator_arguments"]],
    ]


def base_observation(observation: str) -> dict[str, Any]:
    return {
        "id": "two_level_sleeping_tree",
        "observation": observation,
        "matched": False,
        "timed_out": False,
        "tree_kill_requested": False,
        "tree_kill_returncode": None,
        "root_reaped": False,
        "child_observed_running_before_kill": False,
        "grandchild_observed_running_before_kill": False,
        "child_terminated_after_kill": False,
        "grandchild_terminated_after_kill": False,
        "observed_seconds": None,
        "within_observed_bound": False,
    }


def observe_fixture(
    repo: Path,
    policy: dict[str, Any],
    taskkill_path: str,
    popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    handle_factory: Callable[[int], WindowsProcessHandle] = WindowsProcessHandle,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    root = None
    handles: list[WindowsProcessHandle] = []
    observation = base_observation("spawn_error")
    try:
        root = popen(
            python_command(root_script(policy["fixture"]["sleep_seconds"])),
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        started = clock()
        line = read_line_with_timeout(root.stdout, policy["discovery_timeout_seconds"])
        if line is None:
            observation["observation"] = "descendant_discovery_timeout"
            return observation
        try:
            child_pid, grandchild_pid = [int(part) for part in line.decode("ascii").split()]
        except (UnicodeError, ValueError):
            observation["observation"] = "invalid_descendant_identity"
            return observation
        handles = [handle_factory(child_pid), handle_factory(grandchild_pid)]
        child_running, grandchild_running = [handle.is_running() for handle in handles]
        observation["child_observed_running_before_kill"] = child_running
        observation["grandchild_observed_running_before_kill"] = grandchild_running
        if not child_running or not grandchild_running:
            observation["observation"] = "descendant_not_running"
            return observation
        try:
            root.wait(timeout=policy["timeout_seconds"])
            observation["observation"] = "root_finished_before_timeout"
            return observation
        except subprocess.TimeoutExpired:
            observation["timed_out"] = True
        completed = run(
            taskkill_command(taskkill_path, root.pid, policy),
            cwd=repo,
            check=False,
            capture_output=True,
            timeout=policy["cleanup_timeout_seconds"],
            shell=False,
        )
        observation["tree_kill_requested"] = True
        observation["tree_kill_returncode"] = completed.returncode
        try:
            root.wait(timeout=policy["cleanup_timeout_seconds"])
            observation["root_reaped"] = True
        except subprocess.TimeoutExpired:
            observation["observation"] = "root_cleanup_timeout"
            return observation
        observation["child_terminated_after_kill"] = handles[0].wait_terminated(
            policy["cleanup_timeout_seconds"]
        )
        observation["grandchild_terminated_after_kill"] = handles[1].wait_terminated(
            policy["cleanup_timeout_seconds"]
        )
        elapsed = clock() - started
        observation["observed_seconds"] = round(elapsed, 6)
        observation["within_observed_bound"] = elapsed <= policy["max_observed_seconds"]
        matched = (
            completed.returncode == 0
            and observation["root_reaped"]
            and observation["child_terminated_after_kill"]
            and observation["grandchild_terminated_after_kill"]
            and observation["within_observed_bound"]
        )
        observation["matched"] = matched
        observation["observation"] = "tree_timed_out_and_reaped" if matched else "tree_cleanup_failed"
        return observation
    except (OSError, subprocess.TimeoutExpired):
        observation["observation"] = "fixture_error"
        return observation
    finally:
        if root is not None and root.poll() is None:
            try:
                run(
                    taskkill_command(taskkill_path, root.pid, policy),
                    cwd=repo,
                    check=False,
                    capture_output=True,
                    timeout=policy["cleanup_timeout_seconds"],
                    shell=False,
                )
                root.wait(timeout=policy["cleanup_timeout_seconds"])
            except (OSError, subprocess.TimeoutExpired):
                try:
                    root.kill()
                    root.wait(timeout=policy["cleanup_timeout_seconds"])
                except (OSError, subprocess.TimeoutExpired):
                    pass
        if root is not None and root.stdout is not None:
            root.stdout.close()
        for handle in handles:
            handle.close()


def prove(
    repo: Path,
    policy: dict[str, Any],
    system: str = platform.system(),
    which: Callable[[str], str | None] = shutil.which,
    fixture_runner: Callable[[Path, dict[str, Any], str], dict[str, Any]] = observe_fixture,
) -> dict[str, Any]:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Repository path must be an existing directory")
    taskkill_path = which(policy["tree_terminator"])
    supported = system == policy["required_platform"] and taskkill_path is not None
    observation = (
        fixture_runner(repo, policy, taskkill_path)
        if supported and taskkill_path is not None
        else base_observation("unsupported_environment")
    )
    verified = supported and observation["matched"]
    return {
        "proof_version": policy["version"],
        "purpose": policy["purpose"],
        "mode": policy["mode"],
        **{field: False for field in FALSE_FIELDS},
        "proof_complete": True,
        "scope": {
            "platform": policy["required_platform"],
            "tree_terminator": policy["tree_terminator"],
            "fixture_descendant_depth": policy["fixture"]["descendant_depth"],
            "uses_shell": False,
            "invokes_agent": False,
            "writes_files": False,
        },
        "fixture": observation,
        "control_assessments": [
            {
                "id": policy["proven_control"],
                "assessment": "verified_fixture" if verified else "not_proven",
            },
            *[
                {"id": control, "assessment": "not_proven"}
                for control in policy["unproven_controls"]
            ],
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def format_text(result: dict[str, Any]) -> str:
    assessment = result["control_assessments"][0]["assessment"]
    lines = [
        f"windows-process-tree-timeout-proof: {assessment.upper()}",
        "runner_selected=false",
        "agent_invocation_authorized=false",
        f"- fixture: {result['fixture']['observation']}",
    ]
    lines.extend(
        f"- {item['id']}: {item['assessment']}" for item in result["control_assessments"][1:]
    )
    return "\n".join(lines)


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = prove(args.repo, load_policy())
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        print(f"windows-process-tree-timeout-proof: ERROR\n- {error}", file=sys.stderr)
        return 1
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result["control_assessments"][0]["assessment"] == "verified_fixture" else 2


if __name__ == "__main__":
    raise SystemExit(main())
