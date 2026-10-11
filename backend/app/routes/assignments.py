from __future__ import annotations

from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
import re
import math
import shlex
from uuid import uuid4
from copy import deepcopy

from flask import Blueprint, Response, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import desc

from ..extensions import db
from ..models import (
    Assignment,
    AssignmentGrade,
    AssignmentRead,
    AuditLog,
    ClassRoster,
    Course,
    CourseClass,
    CourseMember,
    GradingResult,
    JudgeRun,
    MarkdownDocument,
    Submission,
    TeacherLLMConfig,
    User,
    utc_now,
)
from ..services.accounts import StudentIdError, short_student_no
from ..services.file_validation import (
    FileValidationContext,
    FileValidationError,
    normalize_file_rules,
    normalize_submission_requirements,
    validate_saved_submission_file,
    validate_submission_file,
)
from ..services.feedback_report import build_feedback_report
from ..services.markdown_documents import bind_description_document, prepare_student_drafts, validate_document_images
from ..services.grading_queue import enqueue_auto_grading
from ..services.secrets import encrypt_api_key
from ..services.score_export import build_assignment_grade_csv, build_assignment_gradebook, build_scoremanager_export
from ..services.assignment_weights import validate_weights, validate_review_weights
from ..services.student_assignment_state import student_deadline_state
from .permissions import roles_required


assignments_bp = Blueprint("assignments", __name__)


ASSIGNMENT_TYPES = {Assignment.TYPE_HOMEWORK, Assignment.TYPE_LAB_REPORT}
ASSIGNMENT_STATUSES = {Assignment.STATUS_DRAFT, Assignment.STATUS_PUBLISHED}
TEXT_FORMATS = {Assignment.FORMAT_MARKDOWN}
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
    try:
        bind_description_document(assignment, payload, current_user)
    except (FileValidationError, PermissionError) as exc:
        db.session.rollback()
        return jsonify(message=str(exc)), 403 if isinstance(exc, PermissionError) else 400
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


@assignments_bp.post("/admin/assignments/<int:assignment_id>/copy")
@login_required
@roles_required(User.ROLE_TEACHER)
def copy_assignment(assignment_id: int):
    source = _get_managed_assignment_or_404(assignment_id)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(message="请求必须是 JSON 对象。"), 400
    target_id = payload.get("class_id")
    target = _get_managed_class_or_404(target_id) if type(target_id) is int else None
    if not source or not target:
        return jsonify(message="作业或目标教学班不存在或无权访问。"), 404
    if current_user.teacher_status != User.TEACHER_STATUS_APPROVED:
        return jsonify(message="教师账号尚未审批。"), 403
    if target.id == source.class_id:
        return jsonify(message="请选择另一个教学班。"), 400
    code = str(payload.get("code") or source.code).strip()
    if not CODE_PATTERN.fullmatch(code):
        return jsonify(message="作业代码格式无效。"), 400
    if Assignment.query.filter_by(class_id=target.id, code=code).first():
        return jsonify(message="目标班级已有相同代码，请修改迁移后的作业代码。"), 409
    fields = ("title", "type", "description", "description_format", "deadline", "allow_late", "late_policy",
              "max_score", "file_rules_json", "submission_requirements_json", "rubric_json", "rubric_format",
              "program_evaluations_json", "ai_evaluations_json")
    assignment = Assignment(course_id=target.course_id, class_id=target.id, code=code,
                            status=Assignment.STATUS_DRAFT, **{key: deepcopy(getattr(source, key)) for key in fields})
    db.session.add(assignment)
    db.session.flush()
    document = MarkdownDocument(owner_id=current_user.id, class_id=target.id, assignment_id=assignment.id,
                                kind="description", item_key="", content=assignment.description or "")
    db.session.add(document)
    try:
        validate_document_images(document, document.content)
    except FileValidationError as exc:
        db.session.rollback()
        return jsonify(message=str(exc)), 400
    db.session.add(AuditLog(actor_id=current_user.id, action="assignment_copied", target_type="assignment",
                           target_id=assignment.id, payload_json={"source_id": source.id, "class_id": target.id}))
    db.session.commit()
    return jsonify(assignment=assignment.to_dict(include_counts=True)), 201


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
    was_published = old_status == Assignment.STATUS_PUBLISHED
    reset_grading = bool(payload.get("reset_grading") or payload.get("reset_grades"))
    needs_reset_confirmation = was_published and _assignment_has_grading_artifacts(assignment) and not reset_grading
    if needs_reset_confirmation:
        return (
            jsonify(
                {
                    "message": "Published assignment updates require reset_grading=true because existing grading results will be cleared.",
                    "requires_reset_grading": True,
                }
            ),
            HTTPStatus.CONFLICT,
        )

    assignment, error = _apply_assignment_payload(assignment, payload, partial=True)
    if error:
        return jsonify({"message": error}), HTTPStatus.BAD_REQUEST
    try:
        bind_description_document(assignment, payload, current_user)
    except (FileValidationError, PermissionError) as exc:
        db.session.rollback()
        return jsonify(message=str(exc)), 403 if isinstance(exc, PermissionError) else 400
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

    cleanup = None
    rerun_count = 0
    if was_published and reset_grading:
        cleanup = _clear_assignment_student_work(assignment, delete_submissions=False, delete_files=False)
        db.session.flush()
        rerun_count = _enqueue_auto_grading_for_assignment(assignment, reason="assignment_reset")

    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="assignment_updated",
            target_type="assignment",
            target_id=assignment.id,
            payload_json={"old_status": old_status, "new_status": assignment.status, "reset_grading": reset_grading, "cleanup": cleanup, "rerun_count": rerun_count},
        )
    )
    db.session.commit()
    return jsonify({"assignment": assignment.to_dict(include_counts=True), "reset_grading": bool(cleanup), "rerun_count": rerun_count})


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


@assignments_bp.delete("/admin/assignments/<int:assignment_id>")
@login_required
@roles_required(User.ROLE_TEACHER)
def delete_assignment(assignment_id: int):
    assignment = _get_managed_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found or not manageable."}), HTTPStatus.NOT_FOUND
    class_id = assignment.class_id
    cleanup = _clear_assignment_student_work(assignment, delete_submissions=True, delete_files=True)
    AssignmentRead.query.filter_by(assignment_id=assignment.id).delete(synchronize_session=False)
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="assignment_deleted",
            target_type="assignment",
            target_id=assignment.id,
            payload_json={"class_id": class_id, **cleanup},
        )
    )
    db.session.delete(assignment)
    db.session.commit()
    return jsonify({"message": "Assignment deleted.", "class_id": class_id, "cleanup": cleanup})


@assignments_bp.get("/admin/assignments/<int:assignment_id>/submissions")
@login_required
@roles_required(User.ROLE_TEACHER, User.ROLE_ADMIN)
def list_assignment_submissions(assignment_id: int):
    assignment = _get_managed_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found or not manageable."}), HTTPStatus.NOT_FOUND
    roster = ClassRoster.query.filter_by(class_id=assignment.class_id).order_by(ClassRoster.student_no.asc()).all()
    rows = []
    test_rows = []
    requirements = assignment.submission_requirements_json or []
    for entry in roster:
        latest_submissions = []
        if entry.matched_user_id:
            latest_submissions = assignment.latest_submissions_for(entry.matched_user_id)
            latest_submissions = sorted(latest_submissions, key=lambda submission: (submission.submitted_at, submission.id))
        latest = latest_submissions[0] if latest_submissions else None
        submitted_keys = {submission.submission_item_key for submission in latest_submissions if submission.status in {Submission.STATUS_SUBMITTED, Submission.STATUS_LATE}}
        uploaded_keys = {submission.submission_item_key for submission in latest_submissions}
        required_keys = {str(item.get("key")) for item in requirements if item.get("required", True)}
        assignment_grade = (
            AssignmentGrade.query.filter_by(assignment_id=assignment.id, student_user_id=entry.matched_user_id).first()
            if entry.matched_user_id
            else None
        )
        read = (
            AssignmentRead.query.filter_by(assignment_id=assignment.id, student_user_id=entry.matched_user_id).first()
            if entry.matched_user_id
            else None
        )
        if required_keys and required_keys.issubset(submitted_keys):
            student_state = "submitted"
        elif uploaded_keys:
            student_state = "uploaded"
        else:
            student_state = "read" if read else "unread"
        teacher_state = _teacher_grading_state(assignment_grade, latest_submissions, assignment)
        deadline_state = student_deadline_state(assignment, entry.matched_user_id, assignment_grade, requirements)
        (test_rows if entry.is_test_student else rows).append(
            {
                "roster": entry.to_dict(),
                "submission": latest.to_dict(include_private=True) if latest else None,
                "submissions": [submission.to_dict(include_private=True) for submission in latest_submissions],
                "assignment_grade": assignment_grade.to_dict() if assignment_grade else None,
                "final_score": assignment_grade.final_score if assignment_grade and assignment_grade.final_score is not None else None,
                "state": "submitted" if student_state == "submitted" else "missing",
                "student_state": student_state,
                "teacher_state": teacher_state,
                "is_expired": deadline_state["is_expired"],
                "read_at": read.read_at.isoformat() if read else None,
            }
        )
    gradebook = build_assignment_gradebook(assignment)
    return jsonify({"assignment": assignment.to_dict(include_counts=True), "analysis": gradebook["summary"], "submissions": rows, "test_submissions": test_rows})



@assignments_bp.get("/admin/assignments/<int:assignment_id>/grades")
@login_required
@roles_required(User.ROLE_TEACHER, User.ROLE_ADMIN)
def get_assignment_grades(assignment_id: int):
    assignment = _get_managed_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found or not manageable."}), HTTPStatus.NOT_FOUND
    gradebook = build_assignment_gradebook(assignment)
    return jsonify(
        {
            "assignment": assignment.to_dict(include_counts=True),
            "class": assignment.course_class.to_admin_dict(),
            "analysis": gradebook["summary"],
            "rows": gradebook["rows"],
        }
    )


@assignments_bp.get("/admin/assignments/<int:assignment_id>/grades.csv")
@login_required
@roles_required(User.ROLE_TEACHER, User.ROLE_ADMIN)
def export_assignment_grades_csv(assignment_id: int):
    assignment = _get_managed_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found or not manageable."}), HTTPStatus.NOT_FOUND
    csv_text = build_assignment_grade_csv(assignment)
    filename = f"{assignment.course_class.alias}_{assignment.code}_grades.csv"
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@assignments_bp.get("/admin/assignments/<int:assignment_id>/scoremanager-commands")
@login_required
@roles_required(User.ROLE_TEACHER, User.ROLE_ADMIN)
def export_assignment_scoremanager_commands(assignment_id: int):
    assignment = _get_managed_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found or not manageable."}), HTTPStatus.NOT_FOUND
    default_field = assignment.code if assignment.type == Assignment.TYPE_LAB_REPORT else "homework"
    field = str(request.args.get("field") or default_field).strip()
    default_command_type = "lab" if assignment.type == Assignment.TYPE_LAB_REPORT else "regular"
    command_type = str(request.args.get("command_type") or request.args.get("type") or default_command_type).strip()
    group_same_score = _truthy_arg(request.args.get("group_same_score"), default=True)
    export, invalid_students = build_scoremanager_export(
        assignment,
        field=field,
        command_type=command_type,
        group_same_score=group_same_score,
    )
    if invalid_students:
        message = (
            invalid_students[0].get("message")
            if invalid_students and not invalid_students[0].get("student_id")
            else "Student IDs must be valid before exporting ScoreManagerCLI commands."
        )
        return (
            jsonify(
                {
                    "message": message,
                    "invalid_students": invalid_students,
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )
    return jsonify({"assignment": assignment.to_dict(include_counts=True), "export": export})


@assignments_bp.get("/admin/llm-config")
@login_required
@roles_required(User.ROLE_TEACHER)
def get_llm_config():
    config = TeacherLLMConfig.query.filter_by(teacher_id=current_user.id).first()
    return jsonify({"config": config.to_dict() if config else None})


@assignments_bp.put("/admin/llm-config")
@login_required
@roles_required(User.ROLE_TEACHER)
def save_llm_config():
    payload = request.get_json(silent=True) or {}
    base_url = str(payload.get("base_url") or "").strip()
    model = str(payload.get("model") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()
    if len(api_key.encode("utf-8")) > 200:
        return jsonify({"message": "API key must be at most 200 UTF-8 bytes."}), HTTPStatus.BAD_REQUEST
    provider = str(payload.get("provider") or TeacherLLMConfig.PROVIDER_DEEPSEEK).strip() or TeacherLLMConfig.PROVIDER_DEEPSEEK
    enabled = bool(payload.get("enabled", True))

    if not base_url:
        return jsonify({"message": "LLM base URL cannot be empty."}), HTTPStatus.BAD_REQUEST
    if not model:
        return jsonify({"message": "LLM model cannot be empty."}), HTTPStatus.BAD_REQUEST

    config = TeacherLLMConfig.query.filter_by(teacher_id=current_user.id).first()
    if not config:
        if not api_key:
            return jsonify({"message": "API key is required when creating LLM config."}), HTTPStatus.BAD_REQUEST
        config = TeacherLLMConfig(teacher_id=current_user.id, encrypted_api_key=encrypt_api_key(api_key))
        db.session.add(config)
    elif api_key:
        config.encrypted_api_key = encrypt_api_key(api_key)

    if not config.encrypted_api_key:
        return jsonify({"message": "API key is required."}), HTTPStatus.BAD_REQUEST
    config.provider = provider
    config.base_url = base_url
    config.model = model
    config.enabled = enabled
    db.session.flush()
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="teacher_llm_config_saved",
            target_type="teacher_llm_config",
            target_id=config.id,
            payload_json={"provider": provider, "base_url": base_url, "model": model, "enabled": enabled},
        )
    )
    db.session.commit()
    return jsonify({"config": config.to_dict()})


@assignments_bp.get("/admin/submissions/<int:submission_id>/preview")
@login_required
@roles_required(User.ROLE_TEACHER, User.ROLE_ADMIN)
def preview_submission_file(submission_id: int):
    submission = _get_managed_submission_or_404(submission_id)
    if not submission:
        return jsonify({"message": "Submission not found or not manageable."}), HTTPStatus.NOT_FOUND
    target, error = _submission_file_path(submission)
    if error:
        return jsonify({"message": error}), HTTPStatus.NOT_FOUND
    extension = Path(submission.original_filename).suffix.lower()
    if extension not in {".py", ".md"}:
        return jsonify(
            {
                "submission": submission.to_dict(include_private=True),
                "previewable": False,
                "content": None,
                "message": "Only .py and .md submissions are previewed inline in M3.",
            }
        )
    content = target.read_text(encoding="utf-8", errors="replace")
    return jsonify({"submission": submission.to_dict(include_private=True), "previewable": True, "content": content})


@assignments_bp.get("/admin/submissions/<int:submission_id>/download")
@login_required
@roles_required(User.ROLE_TEACHER, User.ROLE_ADMIN)
def download_submission_file(submission_id: int):
    submission = _get_managed_submission_or_404(submission_id)
    if not submission:
        return jsonify({"message": "Submission not found or not manageable."}), HTTPStatus.NOT_FOUND
    target, error = _submission_file_path(submission)
    if error:
        return jsonify({"message": error}), HTTPStatus.NOT_FOUND
    return send_file(target, as_attachment=True, download_name=submission.original_filename)


@assignments_bp.post("/admin/submissions/<int:submission_id>/rerun-grading")
@login_required
@roles_required(User.ROLE_TEACHER)
def rerun_submission_grading(submission_id: int):
    submission = _get_managed_submission_or_404(submission_id)
    if not submission:
        return jsonify({"message": "Submission not found or not manageable."}), HTTPStatus.NOT_FOUND
    if submission.status not in {Submission.STATUS_SUBMITTED, Submission.STATUS_LATE}:
        return jsonify({"message": "Student must confirm the submission before grading can run."}), HTTPStatus.BAD_REQUEST
    queue_status = enqueue_auto_grading(current_app._get_current_object(), submission.assignment_id, submission.student_user_id, reason="teacher_rerun")
    grade = AssignmentGrade.query.filter_by(assignment_id=submission.assignment_id, student_user_id=submission.student_user_id).first()
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="submission_auto_grading_queued",
            target_type="submission",
            target_id=submission.id,
            payload_json={"assignment_id": submission.assignment_id, "queue_status": queue_status},
        )
    )
    db.session.commit()
    return jsonify({"submission": submission.to_dict(include_private=True), "assignment_grade": grade.to_dict() if grade else None, "queue_status": queue_status})

@assignments_bp.post("/admin/submissions/<int:submission_id>/return")
@login_required
@roles_required(User.ROLE_TEACHER)
def return_submission_for_resubmit(submission_id: int):
    submission = _get_managed_submission_or_404(submission_id)
    if not submission:
        return jsonify({"message": "Submission not found or not manageable."}), HTTPStatus.NOT_FOUND
    assignment = submission.assignment
    student_user_id = submission.student_user_id
    cleanup = _clear_assignment_student_work(assignment, student_user_id=student_user_id, delete_submissions=True, delete_files=True)
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="assignment_submission_returned",
            target_type="submission",
            target_id=submission_id,
            payload_json={"assignment_id": assignment.id, "student_user_id": student_user_id, **cleanup},
        )
    )
    db.session.commit()
    return jsonify({"message": "Submission returned for resubmission.", "assignment": assignment.to_dict(include_counts=True), "cleanup": cleanup})


@assignments_bp.patch("/admin/submissions/<int:submission_id>/grade")
@login_required
@roles_required(User.ROLE_TEACHER)
def review_submission_grade(submission_id: int):
    submission = _get_managed_submission_or_404(submission_id)
    if not submission:
        return jsonify({"message": "Submission not found or not manageable."}), HTTPStatus.NOT_FOUND
    payload = request.get_json(silent=True) or {}
    result = AssignmentGrade.query.filter_by(assignment_id=submission.assignment_id, student_user_id=submission.student_user_id).first()
    if not result:
        result = AssignmentGrade(assignment_id=submission.assignment_id, student_user_id=submission.student_user_id)
    before = result.to_dict() if result.id else None
    try:
        file_reviews = _normalize_file_reviews(payload.get("file_reviews"))
        file_reviews = validate_review_weights(submission.assignment, file_reviews)
        for review in file_reviews:
            target = db.session.get(Submission, review.get("submission_id"))
            if not target or target.assignment_id != submission.assignment_id or target.student_user_id != submission.student_user_id or target.submission_item_key != review["submission_item_key"]:
                raise ValueError("批改文件不属于当前学生和作业。")
    except ValueError as exc:
        return jsonify({"message": str(exc)}), HTTPStatus.BAD_REQUEST
    try:
        final_score = float(payload.get("final_score", sum(float(item["score"]) for item in file_reviews)))
    except (TypeError, ValueError):
        return jsonify({"message": "Final score must be a number."}), HTTPStatus.BAD_REQUEST
    if file_reviews:
        final_score = round(sum(float(item["score"]) for item in file_reviews), 2)
    if not math.isfinite(final_score) or final_score < 0 or final_score > submission.assignment.max_score:
        return jsonify({"message": f"Final score must be between 0 and {submission.assignment.max_score}."}), HTTPStatus.BAD_REQUEST
    status = str(payload.get("status") or GradingResult.STATUS_REVIEWED).strip()
    if status not in {GradingResult.STATUS_REVIEWED, GradingResult.STATUS_PUBLISHED}:
        return jsonify({"message": "Grade status must be reviewed or published."}), HTTPStatus.BAD_REQUEST

    result.final_score = final_score
    result.teacher_comment = str(payload.get("teacher_comment") or "").strip() or None
    report = str(payload.get("feedback") or "").strip()
    if not report and file_reviews:
        report = build_feedback_report(submission, file_reviews, result.teacher_comment, final_score)
    result.feedback = report or result.feedback or None
    result.reviewed_by = current_user.id
    result.status = status
    details = dict(result.llm_details_json or {})
    details["file_reviews"] = file_reviews
    details["feedback_report_markdown"] = result.feedback
    result.llm_details_json = details or None
    db.session.add(result)
    _sync_submission_grading_result(submission, result)
    db.session.flush()
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="grade_reviewed",
            target_type="assignment_grade",
            target_id=result.id,
            payload_json={
                "before": before,
                "after": result.to_dict(),
                "reason": str(payload.get("reason") or "").strip(),
            },
        )
    )
    db.session.commit()
    return jsonify({"submission": submission.to_dict(include_private=True), "assignment_grade": result.to_dict(), "grading_result": result.to_dict()})


@assignments_bp.get("/classes/<int:class_id>/assignments")
@login_required
@roles_required(User.ROLE_STUDENT)
def list_student_assignments(class_id: int):
    course_class = _get_student_class_or_404(class_id)
    if not course_class:
        return jsonify({"message": "Teaching class not found or not joined."}), HTTPStatus.NOT_FOUND
    assignments = (
        Assignment.query.filter_by(class_id=course_class.id, status=Assignment.STATUS_PUBLISHED)
        # MySQL has no NULLS LAST syntax; sort missing deadlines after dated work.
        .order_by(Assignment.deadline.is_(None), Assignment.deadline.asc(), Assignment.id.desc())
        .all()
    )
    return jsonify(
        {
            "class": course_class.to_public_dict(),
            "assignments": [assignment.to_dict(student_user_id=current_user.id) for assignment in assignments],
        }
    )


@assignments_bp.post("/assignments/<int:assignment_id>/read")
@login_required
@roles_required(User.ROLE_STUDENT)
def mark_assignment_read(assignment_id: int):
    assignment = _get_student_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found, not published, or not accessible."}), HTTPStatus.NOT_FOUND
    read = AssignmentRead.query.filter_by(assignment_id=assignment.id, student_user_id=current_user.id).first()
    if not read:
        read = AssignmentRead(assignment_id=assignment.id, student_user_id=current_user.id)
        db.session.add(read)
        db.session.commit()
    return jsonify({"read": read.to_dict(), "assignment": assignment.to_dict(student_user_id=current_user.id)})


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

    published_grade = AssignmentGrade.query.filter_by(
        assignment_id=assignment.id,
        student_user_id=current_user.id,
        status=GradingResult.STATUS_PUBLISHED,
    ).first()
    if published_grade:
        return jsonify({"message": "Feedback has been published for this assignment; resubmission is no longer allowed."}), HTTPStatus.FORBIDDEN

    roster_entry = ClassRoster.query.filter_by(class_id=assignment.class_id, matched_user_id=current_user.id).first()
    if not roster_entry:
        return jsonify({"message": "Current student is not bound to this teaching class roster."}), HTTPStatus.FORBIDDEN

    item_key = str(request.form.get("item_key") or request.form.get("submission_item_key") or "").strip()
    requirements = assignment.submission_requirements_json or []
    if not item_key and len(requirements) == 1:
        item_key = str(requirements[0].get("key") or "main")
    requirement = _find_submission_requirement(assignment, item_key)
    if not requirement:
        return jsonify({"message": "Submission item not found for this assignment."}), HTTPStatus.BAD_REQUEST

    uploaded_file = request.files.get("file")
    if not uploaded_file:
        return jsonify({"message": "Please upload a .py, .md, .zip, .jpg or .png file."}), HTTPStatus.BAD_REQUEST

    try:
        student_no = roster_entry.student_no or short_student_no(roster_entry.student_id)
        validation = validate_submission_file(
            uploaded_file,
            requirement,
            FileValidationContext(
                student_id=roster_entry.student_id,
                student_no=student_no,
                student_name=roster_entry.student_name,
                assignment_code=assignment.code,
                course_alias=assignment.course_class.alias,
            ),
            check_content=False,
            filename_only=True,
        )
    except (FileValidationError, StudentIdError) as exc:
        details = exc.details if isinstance(exc, FileValidationError) else [str(exc)]
        return jsonify({"message": str(exc), "details": details}), HTTPStatus.BAD_REQUEST

    relative_path = _save_submission_file(uploaded_file, assignment, roster_entry.student_id, validation.extension)
    submission = Submission(
        assignment_id=assignment.id,
        student_user_id=current_user.id,
        original_filename=validation.filename,
        submission_item_key=str(requirement["key"]),
        submission_item_label=str(requirement["label"]),
        file_path=relative_path,
        file_size=validation.size,
        status=Submission.STATUS_UPLOADED,
        validation_result_json=validation.to_dict(),
    )
    db.session.add(submission)
    # An explicit file upload replaces this item's online draft as the next version.
    document = MarkdownDocument.query.filter_by(assignment_id=assignment.id, owner_id=current_user.id,
                                               kind="submission", item_key=item_key).first()
    if document:
        target = Path(current_app.config["UPLOAD_FOLDER"]) / relative_path
        document.content = target.read_text(encoding="utf-8", errors="replace") if validation.extension == ".md" and validation.size <= 1024 * 1024 else ""
        document.revision += 1
        document.submitted_revision = document.revision
        if validation.extension == ".md":
            submission.validation_result_json = {**validation.to_dict(), "markdown_document_id": document.id,
                                                 "markdown_revision": document.revision}
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="assignment_file_uploaded",
            target_type="assignment",
            target_id=assignment.id,
            payload_json={"submission_filename": validation.filename, "submission_item_key": item_key, "class_id": assignment.class_id},
        )
    )
    db.session.commit()
    assignment_grade = AssignmentGrade.query.filter_by(assignment_id=assignment.id, student_user_id=current_user.id).first()
    return jsonify({"submission": submission.to_dict(), "assignment_grade": assignment_grade.to_public_dict() if assignment_grade else None}), HTTPStatus.CREATED


@assignments_bp.post("/assignments/<int:assignment_id>/confirm-submission")
@login_required
@roles_required(User.ROLE_STUDENT)
def confirm_assignment_submission(assignment_id: int):
    assignment = _get_student_assignment_or_404(assignment_id)
    if not assignment:
        return jsonify({"message": "Assignment not found, not published, or not accessible."}), HTTPStatus.NOT_FOUND

    now = utc_now()
    if assignment.deadline and now > _as_utc(assignment.deadline) and not assignment.allow_late:
        return jsonify({"message": "Assignment deadline has passed and late submissions are not allowed."}), HTTPStatus.FORBIDDEN

    published_grade = AssignmentGrade.query.filter_by(
        assignment_id=assignment.id,
        student_user_id=current_user.id,
        status=GradingResult.STATUS_PUBLISHED,
    ).first()
    if published_grade:
        return jsonify({"message": "Feedback has been published for this assignment; confirmation is no longer allowed."}), HTTPStatus.FORBIDDEN

    roster_entry = ClassRoster.query.filter_by(class_id=assignment.class_id, matched_user_id=current_user.id).first()
    if not roster_entry:
        return jsonify({"message": "Current student is not bound to this teaching class roster."}), HTTPStatus.FORBIDDEN

    latest_submissions = assignment.latest_submissions_for(current_user.id)
    latest_by_key = {submission.submission_item_key: submission for submission in latest_submissions}
    requirements_by_key = {str(item.get("key")): item for item in assignment.submission_requirements_json or []}
    required_keys = {key for key, item in requirements_by_key.items() if item.get("required", True)}
    pending_drafts = MarkdownDocument.query.filter_by(assignment_id=assignment.id, owner_id=current_user.id, kind="submission").all()
    draft_keys = {document.item_key for document in pending_drafts if document.revision > document.submitted_revision and document.content.strip()}
    missing_keys = sorted(key for key in required_keys if key not in latest_by_key and key not in draft_keys)
    if missing_keys:
        return jsonify({"message": "Please upload all required files before confirming submission.", "missing_keys": missing_keys}), HTTPStatus.BAD_REQUEST

    created_paths = []
    try:
        prepare_student_drafts(assignment, current_user, requirements_by_key, created_paths)
        latest_submissions = assignment.latest_submissions_for(current_user.id)
        student_no = roster_entry.student_no or short_student_no(roster_entry.student_id)
        validation_context = FileValidationContext(
            student_id=roster_entry.student_id,
            student_no=student_no,
            student_name=roster_entry.student_name,
            assignment_code=assignment.code,
            course_alias=assignment.course_class.alias,
        )
        for submission in latest_submissions:
            requirement = requirements_by_key.get(submission.submission_item_key)
            if not requirement:
                raise FileValidationError("Submission item not found for this assignment.")
            target, error = _submission_file_path(submission)
            if error:
                raise FileValidationError(error)
            validation = validate_saved_submission_file(target, submission.original_filename, requirement, validation_context)
            previous = submission.validation_result_json or {}
            document = None
            if previous.get("markdown_document_id"):
                document = db.session.get(MarkdownDocument, previous["markdown_document_id"])
                if not document or document.assignment_id != assignment.id or document.owner_id != current_user.id or document.item_key != submission.submission_item_key:
                    raise FileValidationError("Markdown 文档归属不匹配。")
            if target.suffix.lower() == ".md":
                # Local .md uploads can reference library images even before opening the editor.
                document = document or MarkdownDocument(owner_id=current_user.id, class_id=assignment.class_id,
                                                        assignment_id=assignment.id, kind="submission", item_key=submission.submission_item_key)
                previous = {**previous, "markdown_asset_ids": validate_document_images(document, target.read_text(encoding="utf-8"))}
            submission.validation_result_json = {**validation.to_dict(), **{key: value for key, value in previous.items() if key.startswith("markdown_")}}
            submission.file_size = validation.size
    except (FileValidationError, StudentIdError) as exc:
        db.session.rollback()
        for target in created_paths:
            target.unlink(missing_ok=True)
        details = exc.details if isinstance(exc, FileValidationError) else [str(exc)]
        return jsonify({"message": str(exc), "details": details}), HTTPStatus.BAD_REQUEST
    except Exception:
        db.session.rollback()
        for target in created_paths:
            target.unlink(missing_ok=True)
        raise

    cleanup = _clear_assignment_student_work(assignment, student_user_id=current_user.id, delete_submissions=False, delete_files=False)
    confirmed_status = Submission.STATUS_LATE if assignment.deadline and now > _as_utc(assignment.deadline) else Submission.STATUS_SUBMITTED
    for submission in latest_submissions:
        submission.status = confirmed_status
        submission.submitted_at = now
        db.session.add(submission)
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="assignment_submission_confirmed",
            target_type="assignment",
            target_id=assignment.id,
            payload_json={"class_id": assignment.class_id, "submission_ids": [submission.id for submission in latest_submissions], **cleanup},
        )
    )
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        for target in created_paths:
            target.unlink(missing_ok=True)
        raise
    queue_status = enqueue_auto_grading(current_app._get_current_object(), assignment.id, current_user.id, reason="student_confirmed")
    assignment_grade = AssignmentGrade.query.filter_by(assignment_id=assignment.id, student_user_id=current_user.id).first()
    return jsonify(
        {
            "assignment": assignment.to_dict(student_user_id=current_user.id),
            "assignment_grade": assignment_grade.to_public_dict() if assignment_grade else None,
            "queue_status": queue_status,
        }
    )


def _truthy_arg(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def _assignment_submission_query(assignment: Assignment, student_user_id: int | None = None):
    query = Submission.query.filter_by(assignment_id=assignment.id)
    if student_user_id is not None:
        query = query.filter(Submission.student_user_id == student_user_id)
    return query


def _assignment_has_grading_artifacts(assignment: Assignment) -> bool:
    if AssignmentGrade.query.filter_by(assignment_id=assignment.id).first():
        return True
    if GradingResult.query.join(Submission).filter(Submission.assignment_id == assignment.id).first():
        return True
    if JudgeRun.query.join(Submission).filter(Submission.assignment_id == assignment.id).first():
        return True
    return False


def _clear_assignment_student_work(
    assignment: Assignment,
    student_user_id: int | None = None,
    delete_submissions: bool = False,
    delete_files: bool = False,
) -> dict[str, int]:
    submissions = _assignment_submission_query(assignment, student_user_id).all()
    submission_ids = [submission.id for submission in submissions]
    judge_runs_deleted = 0
    grading_results_deleted = 0
    submissions_deleted = 0
    files_deleted = 0

    if submission_ids:
        judge_runs = JudgeRun.query.filter(JudgeRun.submission_id.in_(submission_ids)).all()
        judge_runs_deleted = len(judge_runs)
        for judge_run in judge_runs:
            db.session.delete(judge_run)
        grading_results = GradingResult.query.filter(GradingResult.submission_id.in_(submission_ids)).all()
        grading_results_deleted = len(grading_results)
        for grading_result in grading_results:
            db.session.delete(grading_result)

    grade_query = AssignmentGrade.query.filter_by(assignment_id=assignment.id)
    if student_user_id is not None:
        grade_query = grade_query.filter(AssignmentGrade.student_user_id == student_user_id)
    assignment_grades = grade_query.all()
    assignment_grades_deleted = len(assignment_grades)
    for grade in assignment_grades:
        db.session.delete(grade)

    if delete_submissions:
        document_query = MarkdownDocument.query.filter_by(assignment_id=assignment.id, kind="submission")
        if student_user_id is not None:
            document_query = document_query.filter_by(owner_id=student_user_id)
        for document in document_query.all():
            # A returned report can be confirmed again without retyping its body.
            document.submitted_revision = -1
        for submission in submissions:
            if delete_files and _delete_submission_file(submission):
                files_deleted += 1
            db.session.delete(submission)
            submissions_deleted += 1

    return {
        "judge_runs_deleted": judge_runs_deleted,
        "grading_results_deleted": grading_results_deleted,
        "assignment_grades_deleted": assignment_grades_deleted,
        "submissions_deleted": submissions_deleted,
        "files_deleted": files_deleted,
    }


def _delete_submission_file(submission: Submission) -> bool:
    target, error = _submission_file_path(submission)
    if error:
        return False
    try:
        target.unlink()
    except OSError:
        return False
    return True


def _enqueue_auto_grading_for_assignment(assignment: Assignment, reason: str) -> int:
    student_user_ids = [
        int(row[0])
        for row in db.session.query(Submission.student_user_id)
        .filter(Submission.assignment_id == assignment.id, Submission.status.in_({Submission.STATUS_SUBMITTED, Submission.STATUS_LATE}))
        .distinct()
        .all()
    ]
    for student_user_id in student_user_ids:
        enqueue_auto_grading(current_app._get_current_object(), assignment.id, student_user_id, reason=reason)
    return len(student_user_ids)


def _get_managed_submission_or_404(submission_id: int) -> Submission | None:
    query = Submission.query.join(Assignment, Submission.assignment_id == Assignment.id).join(Course, Assignment.course_id == Course.id)
    if current_user.role == User.ROLE_TEACHER:
        query = query.filter(Course.teacher_id == current_user.id)
    return query.filter(Submission.id == submission_id).first()


def _submission_file_path(submission: Submission) -> tuple[Path, str | None]:
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (root / submission.file_path).resolve()
    if target != root and root not in target.parents:
        return target, "Submission file path is invalid."
    if not target.exists() or not target.is_file():
        return target, "Submission file was not found."
    return target, None


def _teacher_grading_state(grade: AssignmentGrade | None, submissions: list[Submission], assignment: Assignment) -> str:
    if not submissions:
        return "needs_grading"
    if grade and grade.status == GradingResult.STATUS_PUBLISHED:
        return "published"
    if grade and grade.status == GradingResult.STATUS_REVIEWED:
        return "reviewed"
    if _manual_submission_keys(assignment):
        return "needs_grading"
    if grade and grade.status == GradingResult.STATUS_AUTO_GRADED:
        return "needs_review"
    return "needs_grading"


def _manual_submission_keys(assignment: Assignment) -> set[str]:
    evaluated = {
        str(module.get("input_file_key") or module.get("file_key") or "main")
        for module in (assignment.program_evaluations_json or []) + (assignment.ai_evaluations_json or [])
        if isinstance(module, dict)
    }
    return {
        str(item.get("key"))
        for item in assignment.submission_requirements_json or []
        if item.get("required", True) and str(item.get("key")) and str(item.get("key")) not in evaluated
    }


def _normalize_file_reviews(raw_reviews: object) -> list[dict[str, object]]:
    if raw_reviews in (None, ""):
        return []
    if not isinstance(raw_reviews, list):
        raise ValueError("File reviews must be a list.")
    reviews: list[dict[str, object]] = []
    has_weight = False
    for raw_review in raw_reviews:
        if not isinstance(raw_review, dict):
            raise ValueError("Each file review must be an object.")
        try:
            score = float(raw_review.get("score", 0))
            weight_percent = float(raw_review.get("weight_percent", 0))
            max_score = float(raw_review.get("max_score", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("File review score, weight and max score must be numbers.") from exc
        if not all(math.isfinite(value) for value in [score, weight_percent, max_score]):
            raise ValueError("File review numbers must be finite.")
        if score < 0:
            raise ValueError("File review score cannot be negative.")
        if "weight_percent" in raw_review:
            has_weight = True
            if weight_percent < 0:
                raise ValueError("File review weight cannot be negative.")
            if max_score < 0:
                raise ValueError("File review max score cannot be negative.")
            if max_score and score > max_score:
                raise ValueError("File review score cannot exceed its max score.")
        reviews.append(
            {
                "submission_id": raw_review.get("submission_id"),
                "submission_item_key": str(raw_review.get("submission_item_key") or ""),
                "submission_item_label": str(raw_review.get("submission_item_label") or ""),
                "filename": str(raw_review.get("filename") or ""),
                "review_kind": _normalize_review_kind(raw_review.get("review_kind")),
                "review_status": _normalize_review_status(raw_review.get("review_status")),
                "score": score,
                "weight_percent": weight_percent,
                "max_score": max_score,
                "comment": str(raw_review.get("comment") or "").strip(),
            }
        )
    if has_weight:
        total_weight = sum(float(item.get("weight_percent") or 0) for item in reviews)
        if abs(total_weight - 100) > 0.01:
            raise ValueError("File review weights must sum to 100%.")
    return reviews


def _normalize_review_kind(value: object) -> str:
    kind = str(value or "manual").strip()
    return kind if kind in {"manual", "program", "ai"} else "manual"


def _normalize_review_status(value: object) -> str:
    status = str(value or "pending").strip()
    return status if status in {"pending", "confirmed"} else "pending"


def _sync_submission_grading_result(submission: Submission, grade: AssignmentGrade) -> None:
    result = submission.grading_result or GradingResult(submission_id=submission.id)
    result.auto_score = grade.auto_score
    result.llm_score = grade.llm_score
    result.final_score = grade.final_score
    result.feedback = grade.feedback
    result.teacher_comment = grade.teacher_comment
    result.reviewed_by = grade.reviewed_by
    result.status = grade.status
    result.llm_details_json = dict(grade.llm_details_json or {}) or None
    db.session.add(result)


def _apply_assignment_payload(assignment: Assignment, payload: dict[str, object], partial: bool = False) -> tuple[Assignment, str | None]:
    title = str(payload.get("title") or (assignment.title if partial else "")).strip()
    code = str(payload.get("code") or (assignment.code if partial else "")).strip()
    assignment_type = str(payload.get("type") or (assignment.type if partial else Assignment.TYPE_HOMEWORK)).strip()
    status = str(payload.get("status") or (assignment.status if partial else Assignment.STATUS_DRAFT)).strip()
    description_format = str(payload.get("description_format") or Assignment.FORMAT_MARKDOWN).strip()
    rubric_format = str(payload.get("rubric_format") or Assignment.FORMAT_MARKDOWN).strip()

    if not title:
        return assignment, "Assignment title cannot be empty."
    if not CODE_PATTERN.fullmatch(code):
        return assignment, "Assignment code must use 1-40 letters, digits, underscores or hyphens."
    if assignment_type not in ASSIGNMENT_TYPES:
        return assignment, "Assignment type must be homework or lab_report."
    if status not in ASSIGNMENT_STATUSES:
        return assignment, "Assignment status must be draft or published."
    if description_format not in TEXT_FORMATS or rubric_format not in TEXT_FORMATS:
        return assignment, "Text format must be markdown."

    try:
        max_score = float(payload.get("max_score", assignment.max_score if partial else 100))
    except (TypeError, ValueError):
        return assignment, "Max score must be a number."
    if not math.isfinite(max_score) or max_score <= 0:
        return assignment, "Max score must be greater than 0."

    try:
        file_rules = normalize_file_rules(payload.get("file_rules") or assignment.file_rules_json, assignment_type)
        raw_requirements = payload.get("submission_requirements", assignment.submission_requirements_json if partial else None)
        if raw_requirements in (None, "", []):
            raw_requirements = [{"key": "main", "label": "提交文件", **file_rules, "required": True}]
        submission_requirements = normalize_submission_requirements(
            raw_requirements,
            assignment_type,
        )
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
    assignment.submission_requirements_json = submission_requirements
    assignment.rubric_json = _normalize_rubric(payload.get("rubric", assignment.rubric_json if partial else None))
    assignment.rubric_format = rubric_format
    try:
        requirement_keys = {str(item["key"]) for item in submission_requirements}
        default_input_key = submission_requirements[0]["key"]
        program_evaluations = _normalize_evaluations(
            payload.get("program_evaluations", assignment.program_evaluations_json if partial else []),
            "program",
            requirement_keys,
            str(default_input_key),
        )
        ai_evaluations = _normalize_evaluations(
            payload.get("ai_evaluations", assignment.ai_evaluations_json if partial else []),
            "ai",
            requirement_keys,
            str(default_input_key),
        )
        total_percent = _evaluation_total_percent(program_evaluations, ai_evaluations)
        if total_percent > 100:
            return assignment, "Total evaluation score percent cannot exceed 100."
        validate_weights(submission_requirements, program_evaluations, ai_evaluations)
        assignment.program_evaluations_json = program_evaluations
        assignment.ai_evaluations_json = ai_evaluations
    except ValueError as exc:
        return assignment, str(exc)
    assignment.status = status
    return assignment, None


def _find_submission_requirement(assignment: Assignment, item_key: str) -> dict[str, object] | None:
    for requirement in assignment.submission_requirements_json or []:
        if str(requirement.get("key")) == item_key:
            return requirement
    return None


def _normalize_rubric(raw_rubric: object) -> dict[str, object]:
    if isinstance(raw_rubric, dict):
        return raw_rubric
    return {"text": str(raw_rubric or "").strip()}


def _normalize_evaluations(
    raw_evaluations: object,
    evaluation_type: str,
    requirement_keys: set[str],
    default_input_key: str,
) -> list[dict[str, object]]:
    if raw_evaluations in (None, ""):
        return []
    if not isinstance(raw_evaluations, list):
        raise ValueError("Evaluation modules must be a list.")

    normalized: list[dict[str, object]] = []
    for index, item in enumerate(raw_evaluations, start=1):
        if not isinstance(item, dict):
            raise ValueError("Each evaluation module must be an object.")
        name = str(item.get("name") or f"{'Program' if evaluation_type == 'program' else 'AI'} evaluation {index}").strip()
        input_file_key = str(item.get("input_file_key") or item.get("file_key") or default_input_key).strip()
        if input_file_key not in requirement_keys:
            raise ValueError(f"Evaluation input file must reference an existing submission item: {input_file_key}.")

        if evaluation_type == "program":
            cases = _normalize_program_cases(item, name)
            normalized.append(
                {
                    "name": name,
                    "input_file_key": input_file_key,
                    "score_percent": sum(float(case["score_percent"]) for case in cases),
                    "cases": cases,
                }
            )
        else:
            try:
                score_percent = float(item.get("score_percent", item.get("score", 0)))
            except (TypeError, ValueError) as exc:
                raise ValueError("Evaluation score percent must be a number.") from exc
            if not math.isfinite(score_percent) or score_percent <= 0:
                raise ValueError("Evaluation score percent must be greater than 0.")
            normalized.append(
                {
                    "name": name,
                    "input_file_key": input_file_key,
                    "input": str(item.get("input") or ""),
                    "criteria_items": _normalize_ai_criteria_items(item),
                    "score_percent": score_percent,
                }
            )
    return normalized


def _normalize_ai_criteria_items(module: dict[str, object]) -> list[dict[str, object]]:
    raw_items = module.get("criteria_items")
    if raw_items in (None, ""):
        legacy_text = str(module.get("grading_criteria") or module.get("rubric") or "").strip()
        raw_items = [{"content": legacy_text, "weight": 100}] if legacy_text else []
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("AI evaluation must include at least one grading criterion item.")

    normalized: list[dict[str, object]] = []
    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError("Each AI grading criterion item must be an object.")
        content = str(raw_item.get("content") or raw_item.get("standard") or raw_item.get("criteria") or "").strip()
        if not content:
            raise ValueError("AI grading criterion content cannot be empty.")
        try:
            weight = float(raw_item.get("weight", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("AI grading criterion weight must be a number.") from exc
        if weight <= 0:
            raise ValueError("AI grading criterion weight must be greater than 0.")
        normalized.append({"content": content, "weight": weight, "name": str(raw_item.get("name") or f"criterion {index}").strip()})
    return normalized


def _normalize_program_cases(module: dict[str, object], module_name: str) -> list[dict[str, object]]:
    raw_cases = module.get("cases")
    if raw_cases in (None, ""):
        raw_cases = [
            {
                "name": module_name,
                "args": module.get("args", module.get("argv", module.get("arguments", ""))),
                "expected_output": module.get("expected_output") or "",
                "score_percent": module.get("score_percent", module.get("score", 0)),
                "timeout_seconds": module.get("timeout_seconds") or 2,
                "is_hidden": module.get("is_hidden", False),
            }
        ]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Program evaluation must include at least one test case.")

    normalized: list[dict[str, object]] = []
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise ValueError("Each program test case must be an object.")
        try:
            score_percent = float(raw_case.get("score_percent", raw_case.get("score", 0)))
        except (TypeError, ValueError) as exc:
            raise ValueError("Program test case score percent must be a number.") from exc
        if not math.isfinite(score_percent) or score_percent <= 0:
            raise ValueError("Program test case score percent must be greater than 0.")
        try:
            timeout_seconds = float(raw_case.get("timeout_seconds") or 2)
        except (TypeError, ValueError) as exc:
            raise ValueError("Program test case timeout must be a number.") from exc
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Program test case timeout must be greater than 0.")
        normalized.append(
            {
                "name": str(raw_case.get("name") or f"case {index}").strip(),
                "args": _normalize_program_args(raw_case.get("args", raw_case.get("argv", raw_case.get("arguments", "")))),
                "expected_output": str(raw_case.get("expected_output") or ""),
                "score_percent": score_percent,
                "timeout_seconds": timeout_seconds,
                "is_hidden": bool(raw_case.get("is_hidden", False)),
            }
        )
    return normalized


def _normalize_program_args(raw_args: object) -> str:
    if raw_args in (None, ""):
        return ""
    if isinstance(raw_args, list):
        argv = [str(item) for item in raw_args if str(item)]
        if len(argv) > 64:
            raise ValueError("Program run arguments support at most 64 items.")
        if any(len(item) > 200 for item in argv):
            raise ValueError("Each program run argument must be at most 200 characters.")
        return " ".join(shlex.quote(item) for item in argv)
    args = str(raw_args).strip()
    if len(args) > 1000:
        raise ValueError("Program run arguments must be at most 1000 characters.")
    try:
        argv = shlex.split(args)
    except ValueError as exc:
        raise ValueError(f"Program run arguments are invalid: {exc}") from exc
    if len(argv) > 64:
        raise ValueError("Program run arguments support at most 64 items.")
    if any(len(item) > 200 for item in argv):
        raise ValueError("Each program run argument must be at most 200 characters.")
    return args


def _evaluation_total_percent(program_evaluations: list[dict[str, object]], ai_evaluations: list[dict[str, object]]) -> float:
    program_total = 0.0
    for module in program_evaluations:
        cases = module.get("cases") if isinstance(module.get("cases"), list) else []
        program_total += sum(float(case.get("score_percent") or 0) for case in cases if isinstance(case, dict))
    ai_total = sum(float(item["score_percent"]) for item in ai_evaluations)
    return program_total + ai_total


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("Deadline must be an ISO datetime string.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


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
