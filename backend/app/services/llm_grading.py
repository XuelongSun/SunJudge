from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from flask import current_app

from ..models import Assignment, TeacherLLMConfig, User


def grade_markdown_with_llm(
    assignment: Assignment,
    student: User | None,
    submission_filename: str,
    relative_file_path: str,
    modules: list[dict[str, object]],
) -> dict[str, object]:
    config = TeacherLLMConfig.query.filter_by(teacher_id=assignment.course.teacher_id, enabled=True).first()
    if not config:
        return {
            "status": "llm_config_missing",
            "message": "Teacher LLM config is missing or disabled.",
            "modules": [_module_waiting(module, "LLM config is missing or disabled.") for module in modules],
            "score": 0.0,
        }

    content, error = _read_submission_text(relative_file_path)
    if error:
        return {
            "status": "file_read_error",
            "message": error,
            "modules": [_module_waiting(module, error) for module in modules],
            "score": 0.0,
        }

    module_reports: list[dict[str, object]] = []
    total_score = 0.0
    for module in modules:
        report = _call_module(config, assignment, student, submission_filename, content, module)
        module_reports.append(report)
        total_score += float(report.get("score") or 0)
    return {
        "status": "completed" if all(report.get("status") == "completed" for report in module_reports) else "partial",
        "message": "AI grading completed." if module_reports else "No AI modules configured.",
        "modules": module_reports,
        "score": round(total_score, 2),
    }


def _call_module(
    config: TeacherLLMConfig,
    assignment: Assignment,
    student: User | None,
    submission_filename: str,
    content: str,
    module: dict[str, object],
) -> dict[str, object]:
    max_score = assignment.max_score * _float(module.get("score_percent"), 0) / 100
    criteria_items = module.get("criteria_items") if isinstance(module.get("criteria_items"), list) else []
    prompt = _build_prompt(assignment, student, submission_filename, content, module, max_score, criteria_items)
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": "You are a careful teaching assistant. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    try:
        response = _post_chat_completion(config, payload)
        parsed = _parse_llm_json(response)
    except Exception as exc:
        return {
            **_module_base(module),
            "status": "error",
            "message": f"LLM grading failed: {exc}",
            "score": 0.0,
            "max_score": round(max_score, 2),
            "criteria_results": [],
        }

    score = max(0.0, min(max_score, _float(parsed.get("score"), 0)))
    return {
        **_module_base(module),
        "status": "completed",
        "message": str(parsed.get("summary") or parsed.get("feedback") or "AI grading completed."),
        "score": round(score, 2),
        "max_score": round(max_score, 2),
        "criteria_results": parsed.get("criteria_results") if isinstance(parsed.get("criteria_results"), list) else [],
        "raw": parsed,
    }


def _post_chat_completion(config: TeacherLLMConfig, payload: dict[str, object]) -> dict[str, object]:
    base_url = config.base_url.rstrip("/") + "/"
    url = urljoin(base_url, "chat/completions")
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.encrypted_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = float(current_app.config.get("LLM_GRADING_TIMEOUT", 60))
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _parse_llm_json(response: dict[str, object]) -> dict[str, object]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM response has no choices.")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM response content is empty.")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("LLM response is not valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM JSON response must be an object.")
    return parsed


def _build_prompt(
    assignment: Assignment,
    student: User | None,
    submission_filename: str,
    content: str,
    module: dict[str, object],
    max_score: float,
    criteria_items: list[object],
) -> str:
    criteria_json = json.dumps(criteria_items, ensure_ascii=False, indent=2)
    return f"""
Grade this student's Markdown submission according to the teacher's AI evaluation module.
Return only one valid JSON object. Do not wrap it in Markdown fences.

Assignment title: {assignment.title}
Assignment code: {assignment.code}
Assignment content:
{assignment.description or ""}

Student: {student.student_name if student else "Unknown"}
Submitted file: {submission_filename}
Evaluation module: {module.get("name") or "AI evaluation"}
Module instruction:
{module.get("input") or ""}
Module maximum score: {round(max_score, 2)}
Criterion items, each with teacher-defined content and weight:
{criteria_json}

Student submission content:
{content[:20000]}

Required JSON schema:
{{
  "score": <number between 0 and the module maximum score>,
  "summary": "<brief scoring suggestion for the teacher>",
  "criteria_results": [
    {{"content": "<criterion content>", "weight": <criterion weight>, "score": <criterion score>, "comment": "<reason>"}}
  ],
  "feedback": "<draft feedback the teacher may reuse or edit>"
}}
""".strip()


def _read_submission_text(relative_file_path: str) -> tuple[str, str | None]:
    path = Path(current_app.config["UPLOAD_FOLDER"]) / relative_file_path
    if not path.exists() or not path.is_file():
        return "", "Submitted markdown file was not found."
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        return "", "Submitted markdown file must be UTF-8 text."


def _module_base(module: dict[str, object]) -> dict[str, object]:
    criteria_items = module.get("criteria_items") if isinstance(module.get("criteria_items"), list) else []
    return {
        "input_file_key": str(module.get("input_file_key") or module.get("file_key") or "main"),
        "name": str(module.get("name") or "AI evaluation"),
        "score_percent": module.get("score_percent"),
        "criteria_items": criteria_items,
        "criteria_weight_total": sum(_float(item.get("weight"), 0) for item in criteria_items if isinstance(item, dict)),
        "input": str(module.get("input") or ""),
    }


def _module_waiting(module: dict[str, object], message: str) -> dict[str, object]:
    return {**_module_base(module), "status": "skipped", "message": message, "score": 0.0}


def _float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default