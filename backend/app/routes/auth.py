from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..models import AccountRecovery, ClassRoster, CourseClass, CourseMember, User, utc_now
from ..services.account_recovery import (
    code_digest, consume_code, email_enabled, issue_code, normalize_email,
    queue_code, recovery_account_query, recovery_display_name,
)
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


def _recovery_payload() -> dict:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _recovery_identity(payload: dict) -> tuple[str, str] | None:
    role, identifier = payload.get("role"), payload.get("identifier")
    if role not in (User.ROLE_STUDENT, User.ROLE_TEACHER, User.ROLE_ADMIN) or not isinstance(identifier, str):
        return None
    identifier = identifier.strip()
    return (role, identifier) if 0 < len(identifier) <= 80 else None


@auth_bp.get("/recovery/email")
@login_required
def recovery_email():
    recovery = db.session.get(AccountRecovery, current_user.id)
    response = jsonify(email=recovery.email if recovery else None, enabled=email_enabled())
    response.headers["Cache-Control"] = "private, no-store"
    return response


@auth_bp.post("/recovery/email/request")
@login_required
def request_recovery_email():
    if not email_enabled():
        return jsonify(message="站点尚未启用邮件服务。"), HTTPStatus.SERVICE_UNAVAILABLE
    payload = _recovery_payload()
    email, password = normalize_email(payload.get("email")), payload.get("password")
    if not email:
        return jsonify(message="请输入有效邮箱。"), HTTPStatus.BAD_REQUEST
    if not isinstance(password, str) or not 6 <= len(password) <= 1024 or not current_user.check_password(password):
        return jsonify(message="当前密码错误。"), HTTPStatus.FORBIDDEN
    user_id = current_user.id
    # Serialize with password resets before issuing a new binding code.
    locked = db.session.execute(update(User).where(
        User.id == user_id, User.password_hash == current_user.password_hash,
    ).values(password_hash=User.password_hash)).rowcount
    if locked != 1:
        db.session.rollback()
        return jsonify(message="请重新登录。"), HTTPStatus.UNAUTHORIZED
    recovery = db.session.get(AccountRecovery, user_id)
    if not recovery:
        recovery = AccountRecovery(user_id=user_id)
        db.session.add(recovery)
        db.session.flush()
    code = issue_code(recovery, email, binding=True)
    if not code:
        return jsonify(message="请间隔一分钟再发送验证码。"), HTTPStatus.TOO_MANY_REQUESTS
    if not queue_code(email, code, binding=True, recipient_name=recovery_display_name(current_user)):
        return jsonify(message="邮件发送繁忙，请稍后重试。"), HTTPStatus.SERVICE_UNAVAILABLE
    return jsonify(message="验证邮件已安排发送，请检查收件箱。"), HTTPStatus.ACCEPTED


@auth_bp.post("/recovery/email/confirm")
@login_required
def confirm_recovery_email():
    payload = _recovery_payload()
    email, digest = normalize_email(payload.get("email")), code_digest(payload.get("code"))
    if not email or not digest:
        return jsonify(message="邮箱或验证码无效。"), HTTPStatus.BAD_REQUEST
    try:
        if not consume_code(current_user.id, email, digest, binding=True):
            db.session.commit()
            return jsonify(message="验证码无效、已过期或尝试次数已用完，请重新获取。"), HTTPStatus.BAD_REQUEST
        changed = db.session.execute(update(AccountRecovery).where(
            AccountRecovery.user_id == current_user.id, AccountRecovery.pending_email == email,
        ).values(
            email=email, pending_email=None, binding_digest=None, binding_expires_at=None,
            binding_attempts=0, reset_digest=None, reset_expires_at=None, reset_attempts=0,
        ).execution_options(synchronize_session=False)).rowcount
        if changed != 1:
            db.session.rollback()
            return jsonify(message="验证码无效或已过期。"), HTTPStatus.BAD_REQUEST
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(message="该邮箱已绑定其他账号。"), HTTPStatus.CONFLICT
    return jsonify(email=email, message="找回邮箱已验证。")


@auth_bp.post("/recovery/password/request")
def request_password_reset():
    if not email_enabled():
        return jsonify(message="站点尚未启用邮件服务。"), HTTPStatus.SERVICE_UNAVAILABLE
    payload = _recovery_payload()
    email = normalize_email(payload.get("email"))
    if not email:
        return jsonify(message="请输入有效邮箱。"), HTTPStatus.BAD_REQUEST
    identity = _recovery_identity(payload)
    if not identity:
        return jsonify(message="请选择账号类型，并填写教师/管理员用户名或学生真实姓名。"), HTTPStatus.BAD_REQUEST
    recovery = recovery_account_query(email, *identity).first()
    if recovery:
        code = issue_code(recovery, email, binding=False)
        if code:
            user = db.session.get(User, recovery.user_id)
            queue_code(email, code, binding=False, recipient_name=recovery_display_name(user))
    return jsonify(message="如果账号信息与已绑定邮箱匹配，你将收到密码重置邮件。"), HTTPStatus.ACCEPTED


@auth_bp.post("/recovery/password/confirm")
def confirm_password_reset():
    payload = _recovery_payload()
    email = normalize_email(payload.get("email"))
    digest = code_digest(payload.get("code"))
    password = payload.get("password")
    if not isinstance(password, str) or not 6 <= len(password) <= 1024:
        return jsonify(message="新密码长度须为 6 至 1024 个字符。"), HTTPStatus.BAD_REQUEST
    invalid = {"message": "账号信息或验证码无效、已过期或尝试次数已用完，请重新获取。"}
    identity = _recovery_identity(payload)
    if not email or not digest or not identity:
        return jsonify(invalid), HTTPStatus.BAD_REQUEST
    recovery = recovery_account_query(email, *identity).first()
    if not recovery:
        return jsonify(invalid), HTTPStatus.BAD_REQUEST
    user_id = recovery.user_id
    if not consume_code(user_id, email, digest, binding=False):
        db.session.commit()
        return jsonify(invalid), HTTPStatus.BAD_REQUEST
    db.session.execute(update(User).where(User.id == user_id).values(password_hash=generate_password_hash(password)))
    now = utc_now()
    db.session.execute(update(AccountRecovery).where(AccountRecovery.user_id == user_id).values(
        reset_digest=None, reset_expires_at=None, reset_attempts=0, password_reset_at=now,
        pending_email=None, binding_digest=None, binding_expires_at=None, binding_attempts=0,
    ).execution_options(synchronize_session=False))
    db.session.commit()
    return jsonify(message="密码已重置，请用新密码登录。")
