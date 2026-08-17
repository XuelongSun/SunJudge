from __future__ import annotations

from datetime import UTC, datetime

from flask_login import UserMixin
from sqlalchemy import func, inspect
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
    description = db.Column(db.Text, nullable=True)
    description_format = db.Column(db.String(20), nullable=False, default=FORMAT_TEXT)
    deadline = db.Column(db.DateTime, nullable=True)
    allow_late = db.Column(db.Boolean, nullable=False, default=False)
    late_policy = db.Column(db.String(255), nullable=True)
    max_score = db.Column(db.Float, nullable=False, default=100)
    file_rules_json = db.Column(db.JSON, nullable=False, default=dict)
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
            submitted_user_ids = {submission.student_user_id for submission in self.submissions}
            data["submission_count"] = len(submitted_user_ids)
            data["latest_submission_count"] = len(self.submissions)
        if student_user_id is not None:
            latest = self.latest_submission_for(student_user_id)
            data["submission"] = latest.to_dict() if latest else None
        return data

    def latest_submission_for(self, student_user_id: int) -> "Submission | None":
        return (
            Submission.query.filter_by(assignment_id=self.id, student_user_id=student_user_id)
            .order_by(Submission.submitted_at.desc())
            .first()
        )


class Submission(db.Model):
    __tablename__ = "submissions"

    STATUS_SUBMITTED = "submitted"
    STATUS_LATE = "late"

    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignments.id"), nullable=False)
    student_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_SUBMITTED)
    validation_result_json = db.Column(db.JSON, nullable=False, default=dict)

    assignment = db.relationship("Assignment", backref="submissions")
    student = db.relationship("User", backref="submissions")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "assignment_id": self.assignment_id,
            "student_user_id": self.student_user_id,
            "student": self.student.to_dict() if self.student else None,
            "submitted_at": self.submitted_at.isoformat(),
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "status": self.status,
            "validation_result": self.validation_result_json or {},
        }


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
