from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
from typing import Any

from flask import current_app

from ..models import JudgeRun, Submission


DEFAULT_DOCKER_IMAGE = "python:3.11-slim"
TIMEOUT_RETURN_CODES = {124, 137, -9, -15}


def run_python_judge(submission: Submission, cases: list[dict[str, Any]] | None = None) -> JudgeRun:
    assignment = submission.assignment
    cases = cases if cases is not None else assignment.program_evaluations_json or []
    if not cases:
        return JudgeRun(
            submission_id=submission.id,
            status=JudgeRun.STATUS_SKIPPED,
            score=0,
            details_json={"message": "No program evaluation modules configured.", "cases": []},
        )

    extension = Path(submission.original_filename).suffix.lower()
    if extension != ".py":
        return JudgeRun(
            submission_id=submission.id,
            status=JudgeRun.STATUS_SKIPPED,
            score=0,
            details_json={"message": "Program judge only runs for .py submissions.", "cases": []},
        )

    source_path = Path(current_app.config["UPLOAD_FOLDER"]) / submission.file_path
    if not source_path.exists():
        return JudgeRun(
            submission_id=submission.id,
            status=JudgeRun.STATUS_ERROR,
            score=0,
            details_json={"message": "Submitted source file was not found.", "cases": []},
        )

    image_error = _ensure_docker_image()
    if image_error:
        return JudgeRun(
            submission_id=submission.id,
            status=JudgeRun.STATUS_ERROR,
            score=0,
            details_json={"message": image_error, "cases": [], "runner": "docker"},
        )

    total_score = 0.0
    case_results: list[dict[str, Any]] = []
    status_rank = {
        JudgeRun.STATUS_ACCEPTED: 1,
        JudgeRun.STATUS_WRONG_ANSWER: 2,
        JudgeRun.STATUS_RUNTIME_ERROR: 3,
        JudgeRun.STATUS_TIME_LIMIT_EXCEEDED: 4,
        JudgeRun.STATUS_ERROR: 5,
    }
    overall_status = JudgeRun.STATUS_ACCEPTED

    for index, case in enumerate(cases, start=1):
        timeout = _positive_float(case.get("timeout_seconds"), default=2.0)
        score_percent = _positive_float(case.get("score_percent"), default=0.0)
        args = _case_args_text(case.get("args", case.get("argv", "")))
        result = _run_case_in_docker(source_path, str(case.get("expected_output") or ""), timeout, args)
        case_score = assignment.max_score * score_percent / 100 if result["status"] == JudgeRun.STATUS_ACCEPTED else 0.0
        total_score += case_score
        result.update(
            {
                "name": str(case.get("name") or f"case {index}"),
                "score": round(case_score, 2),
                "score_percent": score_percent,
                "timeout_seconds": timeout,
                "args": args,
                "is_hidden": bool(case.get("is_hidden", False)),
            }
        )
        case_results.append(result)
        if status_rank[result["status"]] > status_rank[overall_status]:
            overall_status = result["status"]

    return JudgeRun(
        submission_id=submission.id,
        status=overall_status,
        score=round(total_score, 2),
        details_json={"cases": case_results, "max_score": assignment.max_score, "runner": "docker"},
    )


def _run_case_in_docker(source_path: Path, expected_output: str, timeout: float, args: object = "") -> dict[str, Any]:
    try:
        argv = _case_argv(args)
    except ValueError as exc:
        return {
            "status": JudgeRun.STATUS_ERROR,
            "expected_output": expected_output,
            "stdout": "",
            "stderr": f"Invalid run arguments: {exc}",
            "returncode": None,
        }

    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--memory",
        "128m",
        "--pids-limit",
        "64",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "-v",
        f"{source_path.parent}:/work:ro",
        "-w",
        "/work",
        _docker_image(),
        "timeout",
        "--signal=KILL",
        _timeout_arg(timeout),
        "python",
        "-I",
        source_path.name,
        *argv,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_host_watchdog_timeout(timeout),
            check=False,
        )
    except FileNotFoundError:
        return {
            "status": JudgeRun.STATUS_ERROR,
            "expected_output": expected_output,
            "stdout": "",
            "stderr": "Docker is not available. Configure Docker to enable the Python judge.",
            "returncode": None,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": JudgeRun.STATUS_ERROR,
            "expected_output": expected_output,
            "stdout": _limit_text(exc.stdout),
            "stderr": _limit_text(exc.stderr) or "Docker runner exceeded the host watchdog timeout before returning a result.",
            "returncode": None,
        }

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    if completed.returncode in TIMEOUT_RETURN_CODES:
        return {
            "status": JudgeRun.STATUS_TIME_LIMIT_EXCEEDED,
            "expected_output": expected_output,
            "stdout": _limit_text(stdout),
            "stderr": _limit_text(stderr),
            "returncode": completed.returncode,
        }
    if completed.returncode != 0:
        return {
            "status": JudgeRun.STATUS_RUNTIME_ERROR,
            "expected_output": expected_output,
            "stdout": _limit_text(stdout),
            "stderr": _limit_text(stderr),
            "returncode": completed.returncode,
        }
    if _normalize_output(stdout) != _normalize_output(expected_output):
        return {
            "status": JudgeRun.STATUS_WRONG_ANSWER,
            "expected_output": expected_output,
            "stdout": _limit_text(stdout),
            "stderr": _limit_text(stderr),
            "diff": _output_diff(expected_output, stdout),
            "returncode": completed.returncode,
        }
    return {
        "status": JudgeRun.STATUS_ACCEPTED,
        "expected_output": expected_output,
        "stdout": _limit_text(stdout),
        "stderr": _limit_text(stderr),
        "returncode": completed.returncode,
    }


def _ensure_docker_image() -> str | None:
    image = _docker_image()
    try:
        inspected = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    except FileNotFoundError:
        return "Docker is not available. Configure Docker to enable the Python judge."
    if inspected.returncode == 0:
        return None

    try:
        pulled = subprocess.run(
            ["docker", "pull", image],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_docker_prepare_timeout(),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return f"Docker image {image} could not be prepared before the image prepare timeout."
    if pulled.returncode != 0:
        message = _limit_text(pulled.stderr or pulled.stdout)
        return f"Docker image {image} could not be prepared: {message}"
    return None


def _docker_image() -> str:
    return str(current_app.config.get("JUDGE_DOCKER_IMAGE") or DEFAULT_DOCKER_IMAGE)


def _docker_prepare_timeout() -> float:
    return _positive_float(current_app.config.get("JUDGE_DOCKER_PREPARE_TIMEOUT"), default=300.0)


def _host_watchdog_timeout(case_timeout: float) -> float:
    buffer = _positive_float(current_app.config.get("JUDGE_DOCKER_HOST_TIMEOUT_BUFFER"), default=30.0)
    return case_timeout + buffer


def _timeout_arg(timeout: float) -> str:
    return f"{max(timeout, 0.1):.3f}s"


def _case_args_text(value: object) -> str:
    if isinstance(value, list):
        return " ".join(shlex.quote(str(item)) for item in value if str(item))
    return str(value or "").strip()


def _case_argv(value: object) -> list[str]:
    if isinstance(value, list):
        argv = [str(item) for item in value if str(item)]
    else:
        try:
            argv = shlex.split(str(value or ""))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    if len(argv) > 64:
        raise ValueError("at most 64 arguments are allowed")
    if any(len(item) > 200 for item in argv):
        raise ValueError("each argument must be at most 200 characters")
    return argv


def _normalize_output(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n"))


def _output_diff(expected_output: str, stdout: str) -> dict[str, object]:
    expected_lines = _normalize_output(expected_output).split("\n")
    actual_lines = _normalize_output(stdout).split("\n")
    line_count = max(len(expected_lines), len(actual_lines))
    for index in range(line_count):
        expected = expected_lines[index] if index < len(expected_lines) else ""
        actual = actual_lines[index] if index < len(actual_lines) else ""
        if expected != actual:
            return {"line": index + 1, "expected": expected, "actual": actual}
    return {"line": None, "expected": _normalize_output(expected_output), "actual": _normalize_output(stdout)}


def _limit_text(value: object, max_length: int = 4000) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= max_length else f"{text[:max_length]}..."


def _positive_float(value: object, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default
