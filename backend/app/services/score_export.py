from __future__ import annotations

import csv
from collections import defaultdict
from datetime import UTC, datetime
from io import StringIO
import re
from typing import Any

from ..models import Assignment, AssignmentGrade, ClassRoster, GradingResult, Submission
from .accounts import StudentIdError, short_student_no


FINAL_GRADE_STATUSES = {GradingResult.STATUS_REVIEWED, GradingResult.STATUS_PUBLISHED}
SCORE_FIELD_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]{0,40}$")


def build_assignment_gradebook(assignment: Assignment) -> dict[str, Any]:
    roster = ClassRoster.query.filter_by(class_id=assignment.class_id).order_by(ClassRoster.student_no.asc()).all()
    rows = [_build_grade_row(assignment, entry) for entry in roster]
    return {"summary": _summarize_rows(assignment, rows), "rows": rows}


def build_assignment_grade_csv(assignment: Assignment) -> str:
    gradebook = build_assignment_gradebook(assignment)
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "No.",
            "姓名",
            "学号",
            "学生信息班级",
            "学生编号",
            "提交状态",
            "提交时间",
            "发布后提交天数",
            "截止前提交天数",
            "批改状态",
            "最终分",
            "自动分",
            "AI建议分",
            "教师评语",
        ]
    )
    for row in gradebook["rows"]:
        roster = row["roster"]
        grade = row["assignment_grade"] or {}
        writer.writerow(
            [
                roster.get("student_no") or "",
                roster.get("student_name") or "",
                roster.get("student_number") or "",
                roster.get("source_class") or "",
                roster.get("student_id") or "",
                row["student_state"],
                row["submitted_at"] or "",
                _format_optional_number(row["submit_days_after_publish"]),
                _format_optional_number(row["submit_days_before_deadline"]),
                row["grade_status"],
                _format_optional_number(grade.get("final_score")),
                _format_optional_number(grade.get("auto_score")),
                _format_optional_number(grade.get("llm_score")),
                grade.get("teacher_comment") or "",
            ]
        )
    return "\ufeff" + output.getvalue()


def build_scoremanager_export(
    assignment: Assignment,
    field: str,
    command_type: str = "regular",
    group_same_score: bool = True,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    field = field.strip()
    if not SCORE_FIELD_PATTERN.fullmatch(field):
        return None, [{"student_id": "", "message": "ScoreManager field must use letters, digits, underscores or hyphens."}]
    if command_type not in {"regular", "lab"}:
        return None, [{"student_id": "", "message": "ScoreManager command_type must be regular or lab."}]

    gradebook = build_assignment_gradebook(assignment)
    invalid_students: list[dict[str, str]] = []
    exportable_rows = []
    skipped_rows = []
    for row in gradebook["rows"]:
        roster = row["roster"]
        student_id = str(roster.get("student_id") or "")
        try:
            short_no = short_student_no(student_id)
        except StudentIdError as exc:
            invalid_students.append({"student_id": student_id, "student_name": str(roster.get("student_name") or ""), "message": str(exc)})
            continue

        grade = row["assignment_grade"]
        if not _has_exportable_final_score(grade):
            skipped_rows.append(
                {
                    "student_id": student_id,
                    "student_name": str(roster.get("student_name") or ""),
                    "reason": "missing_reviewed_or_published_final_score",
                }
            )
            continue
        exportable_rows.append({**row, "short_no": short_no, "score_text": _format_score(float(grade["final_score"]))})

    if invalid_students:
        return None, invalid_students

    lines: list[str] = []
    if command_type == "lab":
        lines = [f"lab rd {row['short_no']} {field} {row['score_text']}" for row in exportable_rows]
    elif group_same_score:
        grouped: dict[str, list[str]] = defaultdict(list)
        for row in exportable_rows:
            grouped[str(row["score_text"])].append(str(row["short_no"]))
        for score_text, numbers in grouped.items():
            if len(numbers) == 1:
                lines.append(f"rd {numbers[0]} {field} {score_text}")
            else:
                lines.append(f"brd {','.join(numbers)} {field} {score_text}")
    else:
        lines = [f"rd {row['short_no']} {field} {row['score_text']}" for row in exportable_rows]

    return (
        {
            "field": field,
            "command_type": command_type,
            "group_same_score": group_same_score,
            "commands": "\n".join(lines),
            "lines": lines,
            "exported_count": len(exportable_rows),
            "skipped": skipped_rows,
        },
        [],
    )


def _build_grade_row(assignment: Assignment, roster_entry: ClassRoster) -> dict[str, Any]:
    latest_submissions = []
    if roster_entry.matched_user_id:
        latest_submissions = sorted(
            assignment.latest_submissions_for(roster_entry.matched_user_id),
            key=lambda submission: (submission.submitted_at, submission.id),
        )
    requirements = assignment.submission_requirements_json or []
    required_keys = {str(item.get("key")) for item in requirements if item.get("required", True)}
    submitted_keys = {
        submission.submission_item_key
        for submission in latest_submissions
        if submission.status in {Submission.STATUS_SUBMITTED, Submission.STATUS_LATE}
    }
    uploaded_keys = {submission.submission_item_key for submission in latest_submissions}
    if required_keys and required_keys.issubset(submitted_keys):
        student_state = "submitted"
    elif uploaded_keys:
        student_state = "uploaded"
    else:
        student_state = "missing"

    submitted_at = _completed_submission_time(latest_submissions, required_keys)
    grade = (
        AssignmentGrade.query.filter_by(assignment_id=assignment.id, student_user_id=roster_entry.matched_user_id).first()
        if roster_entry.matched_user_id
        else None
    )
    return {
        "roster": roster_entry.to_dict(),
        "student_user_id": roster_entry.matched_user_id,
        "student_state": student_state,
        "submitted_at": submitted_at.isoformat() if submitted_at else None,
        "submit_days_after_publish": _days_between(assignment.published_at, submitted_at),
        "submit_days_before_deadline": _days_between(submitted_at, assignment.deadline),
        "grade_status": grade.status if grade else GradingResult.STATUS_PENDING,
        "assignment_grade": grade.to_dict() if grade else None,
        "exportable": _has_exportable_final_score(grade.to_dict() if grade else None),
    }


def _summarize_rows(assignment: Assignment, rows: list[dict[str, Any]]) -> dict[str, Any]:
    final_scores = [
        float(row["assignment_grade"]["final_score"])
        for row in rows
        if _has_exportable_final_score(row.get("assignment_grade"))
    ]
    submit_after_publish = [row["submit_days_after_publish"] for row in rows if row["submit_days_after_publish"] is not None]
    submit_before_deadline = [row["submit_days_before_deadline"] for row in rows if row["submit_days_before_deadline"] is not None]
    submitted_count = len([row for row in rows if row["student_state"] == "submitted"])
    published_count = len(
        [
            row
            for row in rows
            if row.get("assignment_grade") and row["assignment_grade"].get("status") == GradingResult.STATUS_PUBLISHED
        ]
    )
    return {
        "expected_count": len(rows),
        "submitted_count": submitted_count,
        "missing_count": max(len(rows) - submitted_count, 0),
        "submitted_rate": _round_optional(submitted_count / len(rows) if rows else None),
        "reviewed_or_published_count": len(final_scores),
        "published_count": published_count,
        "average_score": _average(final_scores),
        "average_submit_days_after_publish": _average(submit_after_publish),
        "average_submit_days_before_deadline": _average(submit_before_deadline),
        "max_score": assignment.max_score,
    }


def _completed_submission_time(submissions: list[Submission], required_keys: set[str]) -> datetime | None:
    confirmed = [
        submission
        for submission in submissions
        if submission.status in {Submission.STATUS_SUBMITTED, Submission.STATUS_LATE}
        and (not required_keys or submission.submission_item_key in required_keys)
    ]
    if not confirmed:
        return None
    return max(_as_utc(submission.submitted_at) for submission in confirmed)


def _has_exportable_final_score(grade: dict[str, Any] | AssignmentGrade | None) -> bool:
    if grade is None:
        return False
    status = grade.status if isinstance(grade, AssignmentGrade) else grade.get("status")
    final_score = grade.final_score if isinstance(grade, AssignmentGrade) else grade.get("final_score")
    return status in FINAL_GRADE_STATUSES and final_score is not None


def _days_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return _round_optional((_as_utc(end) - _as_utc(start)).total_seconds() / 86400)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return _round_optional(sum(values) / len(values))


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _format_optional_number(value: object) -> str:
    if value is None:
        return ""
    try:
        return _format_score(float(value))
    except (TypeError, ValueError):
        return str(value)


def _format_score(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")
