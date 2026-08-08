from __future__ import annotations

from datetime import UTC, datetime

from flask_login import UserMixin
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


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(80), nullable=False)
    target_type = db.Column(db.String(80), nullable=False)
    target_id = db.Column(db.Integer, nullable=True)
    payload_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
