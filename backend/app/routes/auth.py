from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_

from ..extensions import db
from ..models import ClassRoster, CourseClass, CourseMember, User
from ..services.accounts import StudentIdError, validate_student_id


auth_bp = Blueprint("auth", __name__)


def _normalize_student_no(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        return value.zfill(2)
    return value


def _split_registration_code(code: str) -> tuple[str, str] | None:
    if "-" not in code:
        return None
    alias, raw_no = code.rsplit("-", 1)
    alias = alias.strip()
    raw_no = raw_no.strip()
    if not raw_no.isdigit() or len(raw_no) != 2:
        return None
    student_no = _normalize_student_no(raw_no)
    if not alias or not student_no:
        return None
    return alias, student_no


def _matching_roster_entries(roster_entry: ClassRoster, student_name: str) -> list[ClassRoster]:
    if not roster_entry.student_number:
        return [roster_entry]
    return ClassRoster.query.filter(
        or_(
            ClassRoster.id == roster_entry.id,
            (ClassRoster.student_name == student_name) & (ClassRoster.student_number == roster_entry.student_number),
        )
    ).all()


def _unique_student_username(student_id: str) -> str:
    if not User.query.filter_by(username=student_id).first():
        return student_id
    suffix = 2
    while User.query.filter_by(username=f"{student_id}-{suffix}").first():
        suffix += 1
    return f"{student_id}-{suffix}"


def _bind_student_to_rosters(user: User, roster_entries: list[ClassRoster]) -> None:
    seen_memberships: set[tuple[int, int]] = set()
    for entry in roster_entries:
        if entry.matched_user_id and entry.matched_user_id != user.id:
            raise ValueError("该学生已绑定其他账号。")
        entry.matched_user_id = user.id
        entry.registration_status = ClassRoster.STATUS_REGISTERED
        related_class = entry.course_class
        membership_key = (related_class.course_id, related_class.id)
        if membership_key in seen_memberships:
            continue
        seen_memberships.add(membership_key)
        if not CourseMember.query.filter_by(
            course_id=related_class.course_id,
            class_id=related_class.id,
            user_id=user.id,
        ).first():
            db.session.add(
                CourseMember(
                    course_id=related_class.course_id,
                    class_id=related_class.id,
                    user_id=user.id,
                    role=User.ROLE_STUDENT,
                )
            )


@auth_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    role = payload.get("role") or User.ROLE_STUDENT

    if role not in {User.ROLE_STUDENT, User.ROLE_TEACHER}:
        return jsonify({"message": "只能注册学生账号或申请教师账号。"}), HTTPStatus.BAD_REQUEST
    if len(password) < 6:
        return jsonify({"message": "密码至少需要 6 个字符。"}), HTTPStatus.BAD_REQUEST

    if role == User.ROLE_STUDENT:
        student_id = (payload.get("student_id") or payload.get("invite_code") or "").strip()
        student_name = (payload.get("student_name") or "").strip()
        parsed_code = _split_registration_code(student_id)
        if not parsed_code:
            return jsonify({"message": "邀请码格式应为 教学班别名-两位序号，例如 OS202601-06。"}), HTTPStatus.BAD_REQUEST
        class_alias, student_no = parsed_code
        student_id = f"{class_alias}-{student_no}"
        course_class = CourseClass.query.filter_by(alias=class_alias).first()
        if not course_class or not course_class.invite_enabled:
            return jsonify({"message": "邀请码中的教学班别名不存在或暂未开放注册。"}), HTTPStatus.BAD_REQUEST
        try:
            validate_student_id(student_id)
        except StudentIdError as exc:
            return jsonify({"message": str(exc)}), HTTPStatus.BAD_REQUEST
        if not student_name:
            return jsonify({"message": "真实姓名不能为空。"}), HTTPStatus.BAD_REQUEST
        if not student_id.startswith(f"{course_class.alias}-"):
            return jsonify({"message": f"学生编号必须以所选班级别名 {course_class.alias}- 开头。"}), HTTPStatus.BAD_REQUEST
        if User.query.filter_by(student_id=student_id).first():
            return jsonify({"message": "该邀请码已被注册。"}), HTTPStatus.CONFLICT
        roster_entry = ClassRoster.query.filter_by(class_id=course_class.id, student_no=student_no).first()
        if not roster_entry:
            return jsonify({"message": f"名单中不存在序号 No. {student_no}。"}), HTTPStatus.FORBIDDEN
        if roster_entry.student_name != student_name:
            return jsonify({"message": "真实姓名与名单记录不一致，无法注册。"}), HTTPStatus.FORBIDDEN
        related_roster_entries = _matching_roster_entries(roster_entry, student_name)
        matched_user_ids = {entry.matched_user_id for entry in related_roster_entries if entry.matched_user_id}
        if len(matched_user_ids) > 1:
            return jsonify({"message": "该学生名单已绑定多个账号，请联系教师处理。"}), HTTPStatus.CONFLICT

        user = db.session.get(User, next(iter(matched_user_ids))) if matched_user_ids else None
        if not user and roster_entry.student_number:
            user = User.query.filter_by(
                role=User.ROLE_STUDENT,
                student_name=student_name,
                student_number=roster_entry.student_number,
            ).first()
        if user:
            if not user.check_password(password):
                return jsonify({"message": "该学生已存在，请使用原密码加入班级。"}), HTTPStatus.FORBIDDEN
        else:
            if User.query.filter_by(student_id=student_id).first():
                return jsonify({"message": "该邀请码已被注册。"}), HTTPStatus.CONFLICT
            user = User(
                username=_unique_student_username(student_id),
                role=role,
                student_id=student_id,
                student_name=student_name,
                student_no=roster_entry.student_no,
                student_number=roster_entry.student_number,
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
        try:
            _bind_student_to_rosters(user, related_roster_entries)
        except ValueError as exc:
            return jsonify({"message": str(exc)}), HTTPStatus.CONFLICT
    else:
        if len(username) < 3:
            return jsonify({"message": "用户名至少需要 3 个字符。"}), HTTPStatus.BAD_REQUEST
        if User.query.filter_by(username=username).first():
            return jsonify({"message": "用户名已存在。"}), HTTPStatus.CONFLICT
        user = User(username=username, role=role)
        user.set_password(password)
        user.teacher_status = User.TEACHER_STATUS_PENDING
        db.session.add(user)

    db.session.commit()
    return jsonify({"user": user.to_dict()}), HTTPStatus.CREATED


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    exact_user = User.query.filter(User.username == username, User.role != User.ROLE_STUDENT).first()
    if exact_user:
        user = exact_user if exact_user.check_password(password) else None
    else:
        roster_user_ids = [
            entry.matched_user_id
            for entry in ClassRoster.query.filter_by(student_id=username).all()
            if entry.matched_user_id
        ]
        filters = [
            User.student_id == username,
            (User.role == User.ROLE_STUDENT) & (User.student_name == username),
        ]
        if roster_user_ids:
            filters.append(User.id.in_(roster_user_ids))
        candidates = User.query.filter(or_(*filters)).all()
        matched_users = [candidate for candidate in candidates if candidate.check_password(password)]
        if len(matched_users) > 1:
            return jsonify({"message": "登录名匹配多个账号，请改用学生编号登录。"}), HTTPStatus.CONFLICT
        user = matched_users[0] if matched_users else None

    if not user:
        return jsonify({"message": "用户名或密码错误。"}), HTTPStatus.UNAUTHORIZED
    if user.role == User.ROLE_TEACHER and user.teacher_status != User.TEACHER_STATUS_APPROVED:
        return jsonify({"message": "教师账号尚未通过管理员审批。"}), HTTPStatus.FORBIDDEN

    login_user(user)
    return jsonify({"user": user.to_dict()})


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"message": "已退出登录。"})


@auth_bp.get("/me")
def me():
    if current_user.is_authenticated:
        return jsonify({"user": current_user.to_dict()})
    return jsonify({"user": None})
