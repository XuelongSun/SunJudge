from __future__ import annotations

from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
import re
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import desc

from ..extensions import db
from ..models import Assignment, AuditLog, ClassRoster, Course, CourseClass, CourseMember, Submission, User, utc_now
from ..services.accounts import StudentIdError, short_student_no
from ..services.file_validation import (
    FileValidationContext,
    FileValidationError,
    normalize_file_rules,
    validate_submission_file,
)
from .permissions import roles_required


assignments_bp = Blueprint("assignments", __name__)


ASSIGNMENT_TYPES = {Assignment.TYPE_HOMEWORK, Assignment.TYPE_LAB_REPORT}
ASSIGNMENT_STATUSES = {Assignment.STATUS_DRAFT, Assignment.STATUS_PUBLISHED}
TEXT_FORMATS = {Assignment.FORMAT_TEXT, Assignment.FORMAT_MARKDOWN}
CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")


def _class_query_for_current_user():
    query = CourseClass.query.join(Course)
    if current_user.role == User.ROLE_TEACHER:
        query = query.filter(Course.teacher_id == current_user.id)
    return query


def _get_managed_class_or_404(class_id: int) -> CourseClass | None:
    return _class_query_for_current_user().filter(CourseClass.id == class_id).first()


def _get_managed_assignment_or_404(assignment_id: int) -> Assignment | None:
    query = Assignment.query.join(CourseClass, Assignment.class_id == CourseClass.id).join(Course)
    if current_user.role == User.ROLE_TEACHER:
        query = query.filter(Course.teacher_id == current_user.id)
    return query.filter(Assignment.id == assignment_id).first()


def _get_student_class_or_404(class_id: int) -> CourseClass | None:
    return (
        CourseClass.query.join(CourseMember, CourseMember.class_id == CourseClass.id)
        .filter(
            CourseClass.id == class_id,
            CourseMember.user_id == current_user.id,
            CourseMember.role == User.ROLE_STUDENT,
        )
        .first()
    )


def _get_student_assignment_or_404(assignment_id: int) -> Assignment | None:
    return (
        Assignment.query.join(CourseMember, CourseMember.class_id == Assignment.class_id)
        .filter(
            Assignment.id == assignment_id,
            Assignment.status == Assignment.STATUS_PUBLISHED,
            CourseMember.user_id == current_user.id,
            CourseMember.role == User.ROLE_STUDENT,
        )
        .first()
    )


@assignments_bp.get("/admin/classes/<int:class_id>/assignments")
@login_required
@roles_required(User.ROLE_TEACHER, User.ROLE_ADMIN)
def list_managed_assignments(class_id: int):
    course_class = _get_managed_class_or_404(class_id)
    if not course_class:
        return jsonify({"message": "Teaching class not found or not manageable."}), HTTPStatus.NOT_FOUND
    assignments = (
        Assignment.query.filter_by(class_id=course_class.id)
        .order_by(desc(Assignment.updated_at), desc(Assignment.id))
        .all()
    )
    return jsonify(
        {
            "class": course_class.to_admin_dict(),
            "assignments": [assignment.to_dict(include_counts=True) for assignment in assignments],
        }
    )


@assignments_bp.post("/admin/classes/<int:class_id>/assignments")
@login_required
@roles_required(User.ROLE_TEACHER)
def create_assignment(class_id: int):
    course_class = _get_managed_class_or_404(class_id)
    if not course_class:
        return jsonify({"message": "Teaching class not found or not manageable."}), HTTPStatus.NOT_FOUND
    payload = request.get_json(silent=True) or {}
    assignment, error = _apply_assignment_payload(Assignment(course_id=course_class.course_id, class_id=course_class.id), payload)
    if error:
        return jsonify({"message": error}), HTTPStatus.BAD_REQUEST
    if Assignment.query.filter_by(class_id=course_class.id, code=assignment.code).first():
        return jsonify({"message": "Assignment code already exists in this teaching class."}), HTTPStatus.CONFLICT
    if assignment.status == Assignment.STATUS_PUBLISHED and not assignment.published_at:
        assignment.published_at = utc_now()
    db.session.add(assignment)
    db.session.flush()
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="assignment_created",
            target_type="assignment",
            target_id=assignment.id,
            payload_json={"class_id": class_id, "status": assignment.status},
        )
    )
    db.session.commit()
    return jsonify({"assignment": assignment.to_dict(include_counts=True)}), HTTPStatus.CREATED


@assignments_bp.patch("/admin/assignments/<int:assignment_id>")
@login_required
@roles_required(User.ROLE_TEACHER)
def update_assignment(assignment_id: int):
    assignment = _get_managed_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found or not manageable."}), HTTPStatus.NOT_FOUND
    payload = request.get_json(silent=True) or {}
    old_status = assignment.status
    old_code = assignment.code
    assignment, error = _apply_assignment_payload(assignment, payload, partial=True)
    if error:
        return jsonify({"message": error}), HTTPStatus.BAD_REQUEST
    if assignment.code != old_code:
        duplicate = Assignment.query.filter(
            Assignment.class_id == assignment.class_id,
            Assignment.code == assignment.code,
            Assignment.id != assignment.id,
        ).first()
        if duplicate:
            return jsonify({"message": "Assignment code already exists in this teaching class."}), HTTPStatus.CONFLICT
    if old_status != Assignment.STATUS_PUBLISHED and assignment.status == Assignment.STATUS_PUBLISHED:
        assignment.published_at = utc_now()
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="assignment_updated",
            target_type="assignment",
            target_id=assignment.id,
            payload_json={"old_status": old_status, "new_status": assignment.status},
        )
    )
    db.session.commit()
    return jsonify({"assignment": assignment.to_dict(include_counts=True)})


@assignments_bp.post("/admin/assignments/<int:assignment_id>/publish")
@login_required
@roles_required(User.ROLE_TEACHER)
def publish_assignment(assignment_id: int):
    assignment = _get_managed_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found or not manageable."}), HTTPStatus.NOT_FOUND
    assignment.status = Assignment.STATUS_PUBLISHED
    assignment.published_at = assignment.published_at or utc_now()
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="assignment_published",
            target_type="assignment",
            target_id=assignment.id,
            payload_json={"class_id": assignment.class_id},
        )
    )
    db.session.commit()
    return jsonify({"assignment": assignment.to_dict(include_counts=True)})


@assignments_bp.get("/admin/assignments/<int:assignment_id>/submissions")
@login_required
@roles_required(User.ROLE_TEACHER, User.ROLE_ADMIN)
def list_assignment_submissions(assignment_id: int):
    assignment = _get_managed_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found or not manageable."}), HTTPStatus.NOT_FOUND
    roster = ClassRoster.query.filter_by(class_id=assignment.class_id).order_by(ClassRoster.student_no.asc()).all()
    rows = []
    for entry in roster:
        latest = None
        if entry.matched_user_id:
            latest = assignment.latest_submission_for(entry.matched_user_id)
        rows.append(
            {
                "roster": entry.to_dict(),
                "submission": latest.to_dict() if latest else None,
                "state": "submitted" if latest else "missing",
            }
        )
    return jsonify({"assignment": assignment.to_dict(include_counts=True), "submissions": rows})


@assignments_bp.get("/classes/<int:class_id>/assignments")
@login_required
@roles_required(User.ROLE_STUDENT)
def list_student_assignments(class_id: int):
    course_class = _get_student_class_or_404(class_id)
    if not course_class:
        return jsonify({"message": "Teaching class not found or not joined."}), HTTPStatus.NOT_FOUND
    assignments = (
        Assignment.query.filter_by(class_id=course_class.id, status=Assignment.STATUS_PUBLISHED)
        .order_by(Assignment.deadline.asc().nullslast(), Assignment.id.desc())
        .all()
    )
    return jsonify(
        {
            "class": course_class.to_public_dict(),
            "assignments": [assignment.to_dict(student_user_id=current_user.id) for assignment in assignments],
        }
    )


@assignments_bp.post("/assignments/<int:assignment_id>/submissions")
@login_required
@roles_required(User.ROLE_STUDENT)
def submit_assignment(assignment_id: int):
    assignment = _get_student_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found, not published, or not accessible."}), HTTPStatus.NOT_FOUND

    now = utc_now()
    if assignment.deadline and now > _as_utc(assignment.deadline) and not assignment.allow_late:
        return jsonify({"message": "Assignment deadline has passed and late submissions are not allowed."}), HTTPStatus.FORBIDDEN

    roster_entry = ClassRoster.query.filter_by(class_id=assignment.class_id, matched_user_id=current_user.id).first()
    if not roster_entry:
        return jsonify({"message": "Current student is not bound to this teaching class roster."}), HTTPStatus.FORBIDDEN

    uploaded_file = request.files.get("file")
    if not uploaded_file:
        return jsonify({"message": "Please upload a .py, .md, .zip, .jpg or .png file."}), HTTPStatus.BAD_REQUEST

    try:
        student_no = roster_entry.student_no or short_student_no(roster_entry.student_id)
        validation = validate_submission_file(
            uploaded_file,
            assignment.file_rules_json or {},
            FileValidationContext(
                student_id=roster_entry.student_id,
                student_no=student_no,
                student_name=roster_entry.student_name,
                assignment_code=assignment.code,
            ),
        )
    except (FileValidationError, StudentIdError) as exc:
        details = exc.details if isinstance(exc, FileValidationError) else [str(exc)]
        return jsonify({"message": str(exc), "details": details}), HTTPStatus.BAD_REQUEST

    relative_path = _save_submission_file(uploaded_file, assignment, roster_entry.student_id, validation.extension)
    submission = Submission(
        assignment_id=assignment.id,
        student_user_id=current_user.id,
        original_filename=validation.filename,
        file_path=relative_path,
        file_size=validation.size,
        status=Submission.STATUS_LATE if assignment.deadline and now > _as_utc(assignment.deadline) else Submission.STATUS_SUBMITTED,
        validation_result_json=validation.to_dict(),
    )
    db.session.add(submission)
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="assignment_submitted",
            target_type="assignment",
            target_id=assignment.id,
            payload_json={"submission_filename": validation.filename, "class_id": assignment.class_id},
        )
    )
    db.session.commit()
    return jsonify({"submission": submission.to_dict()}), HTTPStatus.CREATED


def _apply_assignment_payload(assignment: Assignment, payload: dict[str, object], partial: bool = False) -> tuple[Assignment, str | None]:
    title = str(payload.get("title") or (assignment.title if partial else "")).strip()
    code = str(payload.get("code") or (assignment.code if partial else "")).strip()
    assignment_type = str(payload.get("type") or (assignment.type if partial else Assignment.TYPE_HOMEWORK)).strip()
    status = str(payload.get("status") or (assignment.status if partial else Assignment.STATUS_DRAFT)).strip()
    description_format = str(
        payload.get("description_format") or (assignment.description_format if partial else Assignment.FORMAT_TEXT)
    ).strip()
    rubric_format = str(payload.get("rubric_format") or (assignment.rubric_format if partial else Assignment.FORMAT_TEXT)).strip()

    if not title:
        return assignment, "Assignment title cannot be empty."
    if not CODE_PATTERN.fullmatch(code):
        return assignment, "Assignment code must use 1-40 letters, digits, underscores or hyphens."
    if assignment_type not in ASSIGNMENT_TYPES:
        return assignment, "Assignment type must be homework or lab_report."
    if status not in ASSIGNMENT_STATUSES:
        return assignment, "Assignment status must be draft or published."
    if description_format not in TEXT_FORMATS or rubric_format not in TEXT_FORMATS:
        return assignment, "Text format must be text or markdown."

    try:
        max_score = float(payload.get("max_score", assignment.max_score if partial else 100))
    except (TypeError, ValueError):
        return assignment, "Max score must be a number."
    if max_score <= 0:
        return assignment, "Max score must be greater than 0."

    try:
        file_rules = normalize_file_rules(payload.get("file_rules") or assignment.file_rules_json, assignment_type)
    except FileValidationError as exc:
        return assignment, str(exc)

    assignment.title = title
    assignment.code = code
    assignment.type = assignment_type
    assignment.description = str(payload.get("description", assignment.description or "") or "").strip() or None
    assignment.description_format = description_format
    try:
        assignment.deadline = _parse_datetime(payload.get("deadline")) if "deadline" in payload else assignment.deadline
    except ValueError:
        return assignment, "Deadline must be an ISO datetime string."
    assignment.allow_late = bool(payload.get("allow_late", assignment.allow_late if partial else False))
    assignment.late_policy = str(payload.get("late_policy", assignment.late_policy or "") or "").strip() or None
    assignment.max_score = max_score
    assignment.file_rules_json = file_rules
    assignment.rubric_json = _normalize_rubric(payload.get("rubric", assignment.rubric_json if partial else None))
    assignment.rubric_format = rubric_format
    try:
        assignment.program_evaluations_json = _normalize_evaluations(
            payload.get("program_evaluations", assignment.program_evaluations_json if partial else []),
            "program",
        )
        assignment.ai_evaluations_json = _normalize_evaluations(
            payload.get("ai_evaluations", assignment.ai_evaluations_json if partial else []),
            "ai",
        )
    except ValueError as exc:
        return assignment, str(exc)
    assignment.status = status
    return assignment, None


def _normalize_rubric(raw_rubric: object) -> dict[str, object]:
    if isinstance(raw_rubric, dict):
        return raw_rubric
    return {"text": str(raw_rubric or "").strip()}


def _normalize_evaluations(raw_evaluations: object, evaluation_type: str) -> list[dict[str, object]]:
    if raw_evaluations in (None, ""):
        return []
    if not isinstance(raw_evaluations, list):
        raise ValueError("Evaluation modules must be a list.")

    normalized: list[dict[str, object]] = []
    total_percent = 0.0
    for index, item in enumerate(raw_evaluations, start=1):
        if not isinstance(item, dict):
            raise ValueError("Each evaluation module must be an object.")
        name = str(item.get("name") or f"{'Program' if evaluation_type == 'program' else 'AI'} evaluation {index}").strip()
        try:
            score_percent = float(item.get("score_percent", item.get("score", 0)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Evaluation score percent must be a number.") from exc
        if score_percent <= 0:
            raise ValueError("Evaluation score percent must be greater than 0.")
        total_percent += score_percent
        if total_percent > 100:
            raise ValueError("Total evaluation score percent cannot exceed 100.")

        if evaluation_type == "program":
            normalized.append(
                {
                    "name": name,
                    "input": str(item.get("input") or ""),
                    "expected_output": str(item.get("expected_output") or ""),
                    "score_percent": score_percent,
                    "timeout_seconds": float(item.get("timeout_seconds") or 2),
                    "is_hidden": bool(item.get("is_hidden", False)),
                }
            )
        else:
            normalized.append(
                {
                    "name": name,
                    "input": str(item.get("input") or ""),
                    "grading_criteria": str(item.get("grading_criteria") or item.get("rubric") or ""),
                    "score_percent": score_percent,
                }
            )
    return normalized


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("Deadline must be an ISO datetime string.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _save_submission_file(uploaded_file, assignment: Assignment, student_id: str, extension: str) -> str:
    root = Path(current_app.config["UPLOAD_FOLDER"])
    relative_dir = Path(str(assignment.course_id)) / str(assignment.class_id) / str(assignment.id)
    target_dir = root / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{student_id}_{assignment.code}_{uuid4().hex}{extension}"
    uploaded_file.stream.seek(0)
    uploaded_file.save(target_dir / filename)
    return str(relative_dir / filename)
