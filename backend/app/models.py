from __future__ import annotations

from datetime import UTC, datetime

from flask_login import UserMixin
from sqlalchemy import func, inspect
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utc_now() -> datetime:
    return datetime.now(UTC)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    ROLE_STUDENT = "student"
    ROLE_TEACHER = "teacher"
    ROLE_ADMIN = "admin"

    TEACHER_STATUS_NONE = "none"
    TEACHER_STATUS_PENDING = "pending"
    TEACHER_STATUS_APPROVED = "approved"
    TEACHER_STATUS_REJECTED = "rejected"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_STUDENT)
    student_id = db.Column(db.String(80), unique=True, nullable=True)
    student_name = db.Column(db.String(80), nullable=True)
    student_no = db.Column(db.String(40), nullable=True)
    student_number = db.Column(db.String(80), nullable=True)
    teacher_status = db.Column(db.String(20), nullable=False, default=TEACHER_STATUS_NONE)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_teacher_approved(self) -> bool:
        return self.role == self.ROLE_TEACHER and self.teacher_status == self.TEACHER_STATUS_APPROVED

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "student_id": self.student_id,
            "student_name": self.student_name,
            "student_no": self.student_no,
            "student_number": self.student_number,
            "teacher_status": self.teacher_status,
            "created_at": self.created_at.isoformat(),
        }


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    code = db.Column(db.String(80), nullable=False)
    semester = db.Column(db.String(80), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    teacher = db.relationship("User", backref="teaching_courses")


class CourseClass(db.Model):
    __tablename__ = "classes"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    alias = db.Column(db.String(80), nullable=False)
    invite_code = db.Column(db.String(40), unique=True, nullable=False)
    invite_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    course = db.relationship("Course", backref="classes")

    __table_args__ = (
        db.UniqueConstraint("course_id", "name", name="uq_classes_course_name"),
        db.UniqueConstraint("course_id", "alias", name="uq_classes_course_alias"),
    )

    def to_public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "alias": self.alias,
            "course": {
                "id": self.course.id,
                "name": self.course.name,
                "code": self.course.code,
                "semester": self.course.semester,
                "teacher_id": self.course.teacher_id,
                "teacher_name": self.course.teacher.username if self.course.teacher else None,
            },
        }

    def to_admin_dict(self) -> dict[str, object]:
        data = self.to_public_dict()
        data.update(
            {
                "invite_code": self.invite_code,
                "invite_enabled": self.invite_enabled,
                "roster_count": len(self.roster_entries),
                "assignment_count": assignment_count_for_class(self.id),
            }
        )
        return data


class ClassRoster(db.Model):
    __tablename__ = "class_rosters"

    STATUS_IMPORTED = "imported"
    STATUS_REGISTERED = "registered"

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    student_name = db.Column(db.String(80), nullable=False)
    student_no = db.Column(db.String(40), nullable=True)
    student_number = db.Column(db.String(80), nullable=True)
    source_class = db.Column(db.String(80), nullable=True)
    student_id = db.Column(db.String(80), nullable=False)
    matched_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    registration_status = db.Column(db.String(20), nullable=False, default=STATUS_IMPORTED)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    course_class = db.relationship("CourseClass", backref="roster_entries")
    matched_user = db.relationship("User", foreign_keys=[matched_user_id], backref="matched_roster_entries")

    __table_args__ = (db.UniqueConstraint("class_id", "student_id", name="uq_class_rosters_class_student_id"),)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "class_id": self.class_id,
            "student_name": self.student_name,
            "student_no": self.student_no,
            "student_number": self.student_number,
            "source_class": self.source_class,
            "student_id": self.student_id,
            "matched_user_id": self.matched_user_id,
            "registration_status": self.registration_status,
            "created_at": self.created_at.isoformat(),
        }


class CourseMember(db.Model):
    __tablename__ = "course_members"

    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    course = db.relationship("Course", backref="members")
    course_class = db.relationship("CourseClass", backref="members")
    user = db.relationship("User", backref="course_memberships")


class Assignment(db.Model):
    __tablename__ = "assignments"

    TYPE_HOMEWORK = "homework"
    TYPE_LAB_REPORT = "lab_report"
    # Backward-compatible aliases for pre-refinement code paths and stale imports.
    TYPE_PROGRAMMING = TYPE_HOMEWORK
    TYPE_REPORT = TYPE_HOMEWORK
    TYPE_MIXED = TYPE_HOMEWORK

    FORMAT_TEXT = "text"
    FORMAT_MARKDOWN = "markdown"

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    code = db.Column(db.String(80), nullable=False)
    type = db.Column(db.String(30), nullable=False, default=TYPE_HOMEWORK)
    description = db.Column(db.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=True)
    description_format = db.Column(db.String(20), nullable=False, default=FORMAT_TEXT)
    deadline = db.Column(db.DateTime, nullable=True)
    allow_late = db.Column(db.Boolean, nullable=False, default=False)
    late_policy = db.Column(db.String(255), nullable=True)
    max_score = db.Column(db.Float, nullable=False, default=100)
    file_rules_json = db.Column(db.JSON, nullable=False, default=dict)
    submission_requirements_json = db.Column(db.JSON, nullable=False, default=list)
    rubric_json = db.Column(db.JSON, nullable=True)
    rubric_format = db.Column(db.String(20), nullable=False, default=FORMAT_TEXT)
    program_evaluations_json = db.Column(db.JSON, nullable=False, default=list)
    ai_evaluations_json = db.Column(db.JSON, nullable=False, default=list)
    status = db.Column(db.String(20), nullable=False, default=STATUS_DRAFT)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    published_at = db.Column(db.DateTime, nullable=True)

    course = db.relationship("Course", backref="assignments")
    course_class = db.relationship("CourseClass", backref="assignments")

    __table_args__ = (db.UniqueConstraint("class_id", "code", name="uq_assignments_class_code"),)

    def to_dict(self, include_counts: bool = False, student_user_id: int | None = None) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "course_id": self.course_id,
            "class_id": self.class_id,
            "title": self.title,
            "code": self.code,
            "type": self.type,
            "description": self.description,
            "description_format": self.description_format,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "allow_late": self.allow_late,
            "late_policy": self.late_policy,
            "max_score": self.max_score,
            "file_rules": self.file_rules_json or {},
            "submission_requirements": self.submission_requirements_json or _legacy_submission_requirements(self.file_rules_json),
            "rubric": self.rubric_json or {},
            "rubric_format": self.rubric_format,
            "program_evaluations": self.program_evaluations_json or [],
            "ai_evaluations": self.ai_evaluations_json or [],
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }
        if include_counts:
            expected_count = ClassRoster.query.filter_by(class_id=self.class_id).count()
            required_keys = {
                str(item.get("key"))
                for item in self.submission_requirements_json or _legacy_submission_requirements(self.file_rules_json)
                if item.get("required", True)
            }
            submitted_user_ids = _completed_student_user_ids(self.id, required_keys)
            feedback_count = AssignmentGrade.query.filter_by(assignment_id=self.id, status=GradingResult.STATUS_PUBLISHED).count()
            data["expected_submission_count"] = expected_count
            data["submission_count"] = len(submitted_user_ids)
            data["feedback_count"] = feedback_count
            data["latest_submission_count"] = len(self.submissions)
        from .services.assignment_weights import effective_requirements
        data["submission_requirements"] = effective_requirements(data["submission_requirements"], self.program_evaluations_json or [], self.ai_evaluations_json or [])
        if student_user_id is not None:
            markdown_keys = {item["key"] for item in data["submission_requirements"] if ".md" in item["allowed_extensions"]}
            data["markdown_drafts"] = {
                document.item_key: document.summary()
                for document in MarkdownDocument.query.filter_by(
                    assignment_id=self.id, owner_id=student_user_id, kind="submission"
                ).all()
                if document.item_key in markdown_keys
            }
            data["ai_evaluations"] = []
            latest = self.latest_submission_for(student_user_id)
            data["submission"] = latest.to_dict() if latest else None
            data["submissions"] = [submission.to_dict() for submission in self.latest_submissions_for(student_user_id)]
            assignment_grade = AssignmentGrade.query.filter_by(assignment_id=self.id, student_user_id=student_user_id).first()
            data["assignment_grade"] = assignment_grade.to_public_dict() if assignment_grade else None
            from .services.student_assignment_state import student_deadline_state
            data.update(student_deadline_state(self, student_user_id, assignment_grade, data["submission_requirements"]))
            read = AssignmentRead.query.filter_by(assignment_id=self.id, student_user_id=student_user_id).first()
            data["read_at"] = read.read_at.isoformat() if read else None
        return data

    def latest_submission_for(self, student_user_id: int, submission_item_key: str | None = None) -> "Submission | None":
        query = Submission.query.filter_by(assignment_id=self.id, student_user_id=student_user_id)
        if submission_item_key is not None:
            query = query.filter(Submission.submission_item_key == submission_item_key)
        return query.order_by(Submission.submitted_at.desc(), Submission.id.desc()).first()

    def latest_submissions_for(self, student_user_id: int) -> list["Submission"]:
        submissions: list[Submission] = []
        for requirement in self.submission_requirements_json or _legacy_submission_requirements(self.file_rules_json):
            item_key = str(requirement.get("key") or "")
            latest = self.latest_submission_for(student_user_id, item_key)
            if latest:
                submissions.append(latest)
        return submissions


class Submission(db.Model):
    __tablename__ = "submissions"

    STATUS_UPLOADED = "uploaded"
    STATUS_SUBMITTED = "submitted"
    STATUS_LATE = "late"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    student_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    original_filename = db.Column(db.String(255), nullable=False)
    submission_item_key = db.Column(db.String(80), nullable=False, default="main")
    submission_item_label = db.Column(db.String(120), nullable=True)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_SUBMITTED)
    validation_result_json = db.Column(db.JSON, nullable=False, default=dict)

    assignment = db.relationship("Assignment", backref="submissions")
    student = db.relationship("User", backref="submissions")

    def to_dict(self, include_private: bool = False) -> dict[str, object]:
        grading_result = (self.grading_result.to_dict() if include_private else self.grading_result.to_public_dict()) if self.grading_result else None
        latest_judge_run = (
            JudgeRun.query.filter_by(submission_id=self.id).order_by(JudgeRun.created_at.desc(), JudgeRun.id.desc()).first()
        )
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "student_user_id": self.student_user_id,
            "student": self.student.to_dict() if self.student else None,
            "submitted_at": self.submitted_at.isoformat(),
            "original_filename": self.original_filename,
            "submission_item_key": self.submission_item_key,
            "submission_item_label": self.submission_item_label,
            "file_size": self.file_size,
            "status": self.status,
            "validation_result": self.validation_result_json or {},
            "grading_result": grading_result,
            "latest_judge_run": latest_judge_run.to_dict(include_private=include_private) if latest_judge_run else None,
        }


class AssignmentRead(db.Model):
    __tablename__ = "assignment_reads"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    student_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    read_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    assignment = db.relationship("Assignment", backref="assignment_reads")
    student = db.relationship("User", foreign_keys=[student_user_id], backref="assignment_reads")

    __table_args__ = (db.UniqueConstraint("assignment_id", "student_user_id", name="uq_assignment_reads_assignment_student"),)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "student_user_id": self.student_user_id,
            "read_at": self.read_at.isoformat(),
        }


class TeacherLLMConfig(db.Model):
    __tablename__ = "teacher_llm_configs"

    PROVIDER_DEEPSEEK = "deepseek"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    provider = db.Column(db.String(40), nullable=False, default=PROVIDER_DEEPSEEK)
    base_url = db.Column(db.String(255), nullable=False)
    model = db.Column(db.String(120), nullable=False)
    encrypted_api_key = db.Column(db.String(500), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    teacher = db.relationship("User", backref="llm_config", uselist=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "teacher_id": self.teacher_id,
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "enabled": self.enabled,
            "has_api_key": bool(self.encrypted_api_key),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

class JudgeRun(db.Model):
    __tablename__ = "judge_runs"

    STATUS_ACCEPTED = "accepted"
    STATUS_WRONG_ANSWER = "wrong_answer"
    STATUS_RUNTIME_ERROR = "runtime_error"
    STATUS_TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    STATUS_SKIPPED = "skipped"
    STATUS_ERROR = "error"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False)
    status = db.Column(db.String(40), nullable=False)
    score = db.Column(db.Float, nullable=False, default=0)
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    submission = db.relationship("Submission", backref="judge_runs")

    def to_dict(self, include_private: bool = False) -> dict[str, object]:
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "status": self.status,
            "score": self.score,
            "details": (self.details_json or {}) if include_private else _masked_judge_details(self.details_json or {}),
            "created_at": self.created_at.isoformat(),
        }


class GradingResult(db.Model):
    __tablename__ = "grading_results"

    STATUS_PENDING = "pending"
    STATUS_AUTO_GRADED = "auto_graded"
    STATUS_REVIEWED = "reviewed"
    STATUS_PUBLISHED = "published"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("submissions.id"), nullable=False, unique=True)
    auto_score = db.Column(db.Float, nullable=True)
    llm_score = db.Column(db.Float, nullable=True)
    final_score = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    teacher_comment = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(30), nullable=False, default=STATUS_PENDING)
    llm_details_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    submission = db.relationship("Submission", backref=db.backref("grading_result", uselist=False))
    reviewer = db.relationship("User", foreign_keys=[reviewed_by], backref="reviewed_grades")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "submission_id": self.submission_id,
            "auto_score": self.auto_score,
            "llm_score": self.llm_score,
            "final_score": self.final_score,
            "feedback": self.feedback,
            "teacher_comment": self.teacher_comment,
            "reviewed_by": self.reviewed_by,
            "status": self.status,
            "llm_details": self.llm_details_json or {},
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_public_dict(self) -> dict[str, object]:
        data = self.to_dict()
        data["llm_score"] = None
        data["llm_details"] = {}
        if self.status != self.STATUS_PUBLISHED:
            data["final_score"] = None
            data["feedback"] = None
            data["teacher_comment"] = None
        return data


class AssignmentGrade(db.Model):
    __tablename__ = "assignment_grades"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    student_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    auto_score = db.Column(db.Float, nullable=True)
    llm_score = db.Column(db.Float, nullable=True)
    final_score = db.Column(db.Float, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    teacher_comment = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(30), nullable=False, default=GradingResult.STATUS_PENDING)
    llm_details_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    assignment = db.relationship("Assignment", backref="assignment_grades")
    student = db.relationship("User", foreign_keys=[student_user_id], backref="assignment_grades")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by], backref="reviewed_assignment_grades")

    __table_args__ = (db.UniqueConstraint("assignment_id", "student_user_id", name="uq_assignment_grades_assignment_student"),)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "student_user_id": self.student_user_id,
            "auto_score": self.auto_score,
            "llm_score": self.llm_score,
            "final_score": self.final_score,
            "feedback": self.feedback,
            "teacher_comment": self.teacher_comment,
            "reviewed_by": self.reviewed_by,
            "status": self.status,
            "llm_details": self.llm_details_json or {},
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_public_dict(self) -> dict[str, object]:
        data = self.to_dict()
        data["llm_score"] = None
        data["llm_details"] = {}
        if self.status != GradingResult.STATUS_PUBLISHED:
            data["auto_score"] = None
            data["final_score"] = None
            data["feedback"] = None
            data["teacher_comment"] = None
        return data


class MarkdownDocument(db.Model):
    __tablename__ = "markdown_documents"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=True)
    kind = db.Column(db.String(20), nullable=False)
    item_key = db.Column(db.String(40), nullable=False, default="")
    content = db.Column(db.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False, default="")
    revision = db.Column(db.Integer, nullable=False, default=0)
    submitted_revision = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    assignment = db.relationship("Assignment", backref="markdown_documents")
    assets = db.relationship("MarkdownAsset", backref="document", cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint("assignment_id", "owner_id", "kind", "item_key", name="uq_markdown_document_scope"),)

    def summary(self):
        return {"id": self.id, "revision": self.revision, "has_content": bool(self.content.strip()),
                "pending_changes": self.revision > self.submitted_revision, "updated_at": self.updated_at.isoformat()}

    def to_dict(self):
        return {**self.summary(), "content": self.content, "kind": self.kind, "item_key": self.item_key}


class MarkdownAsset(db.Model):
    __tablename__ = "markdown_assets"

    id = db.Column(db.String(32), primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey("markdown_documents.id"), nullable=False, index=True)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    mime_type = db.Column(db.String(40), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(80), nullable=False)
    target_type = db.Column(db.String(80), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    payload_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)


def table_has_columns(table_name: str, columns: set[str]) -> bool:
    try:
        inspector = inspect(db.engine)
        if table_name not in inspector.get_table_names():
            return False
        existing = {column["name"] for column in inspector.get_columns(table_name)}
    except SQLAlchemyError:
        return False
    return columns.issubset(existing)


def assignment_count_for_class(class_id: int, published_only: bool = False) -> int:
    if not table_has_columns("assignments", {"id", "class_id", "status"}):
        return 0
    query = db.session.query(func.count(Assignment.id)).filter(Assignment.class_id == class_id)
    if published_only:
        query = query.filter(Assignment.status == Assignment.STATUS_PUBLISHED)
    return int(query.scalar() or 0)


def published_assignment_ids_for_class(class_id: int) -> list[int]:
    if not table_has_columns("assignments", {"id", "class_id", "status"}):
        return []
    rows = (
        db.session.query(Assignment.id)
        .filter(Assignment.class_id == class_id, Assignment.status == Assignment.STATUS_PUBLISHED)
        .all()
    )
    return [int(row[0]) for row in rows]


def _legacy_submission_requirements(file_rules: dict[str, object] | None) -> list[dict[str, object]]:
    return [{"key": "main", "label": "提交文件", **(file_rules or {})}]


def _completed_student_user_ids(assignment_id: int, required_keys: set[str]) -> set[int]:
    if not required_keys:
        return {int(row[0]) for row in db.session.query(Submission.student_user_id).filter(Submission.assignment_id == assignment_id, Submission.status.in_({Submission.STATUS_SUBMITTED, Submission.STATUS_LATE})).distinct().all()}
    rows = (
        db.session.query(Submission.student_user_id, Submission.submission_item_key)
        .filter(Submission.assignment_id == assignment_id, Submission.submission_item_key.in_(required_keys), Submission.status.in_({Submission.STATUS_SUBMITTED, Submission.STATUS_LATE}))
        .all()
    )
    submitted_by_student: dict[int, set[str]] = {}
    for student_user_id, item_key in rows:
        submitted_by_student.setdefault(int(student_user_id), set()).add(str(item_key))
    return {student_user_id for student_user_id, submitted_keys in submitted_by_student.items() if required_keys.issubset(submitted_keys)}


def _masked_judge_details(details: dict[str, object]) -> dict[str, object]:
    masked = dict(details)
    cases = masked.get("cases")
    if not isinstance(cases, list):
        return masked

    masked_cases: list[object] = []
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            masked_cases.append(raw_case)
            continue
        case = dict(raw_case)
        if case.get("is_hidden"):
            case["input"] = None
            case["expected_output"] = None
            case["args"] = None
            case["stdout"] = None
            case["stderr"] = None
            case["diff"] = None
        masked_cases.append(case)
    masked["cases"] = masked_cases
    return masked
