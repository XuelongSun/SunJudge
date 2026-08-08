from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models import AuditLog, ClassRoster, Course, CourseClass, User
from ..services.accounts import StudentIdError, validate_student_id
from ..services.roster_import import RosterImportError, parse_roster_workbook
from .permissions import roles_required


admin_bp = Blueprint("admin", __name__)


def _class_query_for_current_user():
    query = CourseClass.query.join(Course)
    if current_user.role == User.ROLE_TEACHER:
        query = query.filter(Course.teacher_id == current_user.id)
    return query


def _get_managed_class_or_404(class_id: int) -> CourseClass | None:
    return _class_query_for_current_user().filter(CourseClass.id == class_id).first()


def _normalize_student_no(value: str) -> str:
    value = value.strip()
    if value.startswith("0") and value.isdigit():
        return value.zfill(2)
    if value.isdigit():
        return value.zfill(2)
    return value


def _student_id_for_class(course_class: CourseClass, student_no_or_id: str) -> str:
    value = _normalize_student_no(student_no_or_id)
    if value.startswith(f"{course_class.alias}-"):
        prefix, student_no = value.split("-", 1)
        return f"{prefix}-{_normalize_student_no(student_no)}"
    return f"{course_class.alias}-{value}"


@admin_bp.post("/classes")
@login_required
@roles_required(User.ROLE_TEACHER)
def create_class_with_roster():
    payload = request.get_json(silent=True) or {}
    class_payload = payload.get("class") or {}
    course_payload = payload.get("course") or {}
    roster_payload = payload.get("roster") or []

    class_alias = (class_payload.get("alias") or payload.get("alias") or "").strip()
    class_name = (class_payload.get("name") or f"教学班 {class_alias}").strip()
    course_name = (course_payload.get("name") or "待导入").strip()
    course_code = (course_payload.get("code") or f"pending-{class_alias}").strip()
    semester = (course_payload.get("semester") or "待导入").strip()
    invite_code = class_alias

    if not class_alias:
        return jsonify({"message": "教学班别名不能为空。"}), HTTPStatus.BAD_REQUEST
    if not isinstance(roster_payload, list):
        return jsonify({"message": "班级名单必须是数组。"}), HTTPStatus.BAD_REQUEST
    if CourseClass.query.filter_by(invite_code=invite_code).first():
        return jsonify({"message": "教学班别名已存在。"}), HTTPStatus.CONFLICT

    course = Course(name=course_name, code=course_code, semester=semester, teacher_id=current_user.id)
    db.session.add(course)
    db.session.flush()
    if CourseClass.query.filter_by(course_id=course.id, alias=class_alias).first():
        db.session.rollback()
        return jsonify({"message": "该课程下的教学班别名已存在。"}), HTTPStatus.CONFLICT

    course_class = CourseClass(
        course_id=course.id,
        name=class_name,
        alias=class_alias,
        invite_code=invite_code,
        invite_enabled=bool(class_payload.get("invite_enabled", True)),
    )
    db.session.add(course_class)
    db.session.flush()

    roster_entries: list[ClassRoster] = []
    seen_student_ids: set[str] = set()
    for row in roster_payload:
        student_name = (row.get("student_name") or "").strip()
        student_no = (row.get("student_no") or row.get("no") or row.get("student_id") or "").strip()
        student_no = _normalize_student_no(student_no)
        student_number = (row.get("student_number") or "").strip() or None
        source_class = (row.get("source_class") or "").strip() or None
        student_id = _student_id_for_class(course_class, student_no)
        if not student_name or not student_no:
            db.session.rollback()
            return jsonify({"message": "名单中的学生姓名和序号 No. 都不能为空。"}), HTTPStatus.BAD_REQUEST
        if student_id in seen_student_ids:
            db.session.rollback()
            return jsonify({"message": f"名单中存在重复学生编号：{student_id}。"}), HTTPStatus.BAD_REQUEST
        seen_student_ids.add(student_id)
        roster_entry = ClassRoster(
            class_id=course_class.id,
            student_name=student_name,
            student_no=student_no,
            student_number=student_number,
            source_class=source_class,
            student_id=student_id,
        )
        roster_entries.append(roster_entry)
        db.session.add(roster_entry)

    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="class_roster_created",
            target_type="class",
            target_id=course_class.id,
            payload_json={"course_id": course.id, "roster_count": len(roster_entries)},
        )
    )
    db.session.commit()
    return jsonify({"class": course_class.to_admin_dict(), "roster_count": len(roster_entries)}), HTTPStatus.CREATED


@admin_bp.patch("/classes/<int:class_id>")
@login_required
@roles_required(User.ROLE_TEACHER)
def update_class(class_id: int):
    course_class = _get_managed_class_or_404(class_id)
    if not course_class:
        return jsonify({"message": "教学班不存在或无权访问。"}), HTTPStatus.NOT_FOUND

    payload = request.get_json(silent=True) or {}
    class_payload = payload.get("class") or {}
    course_payload = payload.get("course") or {}

    class_name = (class_payload.get("name") or "").strip()
    invite_enabled = class_payload.get("invite_enabled")
    course_name = (course_payload.get("name") or "").strip()
    course_code = (course_payload.get("code") or "").strip()
    semester = (course_payload.get("semester") or "").strip()

    if class_name:
        course_class.name = class_name
    if invite_enabled is not None:
        course_class.invite_enabled = bool(invite_enabled)
    if course_name:
        course_class.course.name = course_name
    if course_code:
        course_class.course.code = course_code
    if semester:
        course_class.course.semester = semester

    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="class_course_updated",
            target_type="class",
            target_id=course_class.id,
            payload_json={
                "course_id": course_class.course_id,
                "course_name": course_class.course.name,
                "course_code": course_class.course.code,
                "semester": course_class.course.semester,
            },
        )
    )
    db.session.commit()
    return jsonify({"class": course_class.to_admin_dict()})


@admin_bp.get("/classes")
@login_required
@roles_required(User.ROLE_TEACHER, User.ROLE_ADMIN)
def list_classes():
    classes = _class_query_for_current_user().order_by(CourseClass.created_at.desc()).all()
    return jsonify({"classes": [course_class.to_admin_dict() for course_class in classes]})


@admin_bp.post("/classes/import-excel")
@login_required
@roles_required(User.ROLE_TEACHER)
def import_classes_from_excel():
    roster_file = request.files.get("file")
    if not roster_file:
        return jsonify({"message": "请上传 Excel 学生名单文件。"}), HTTPStatus.BAD_REQUEST
    if not roster_file.filename.lower().endswith((".xlsx", ".xlsm")):
        return jsonify({"message": "学生名单必须是 .xlsx 或 .xlsm 文件。"}), HTTPStatus.BAD_REQUEST

    class_id = request.form.get("class_id")
    if not class_id:
        return jsonify({"message": "请先选择要导入名单的教学班。"}), HTTPStatus.BAD_REQUEST
    try:
        class_id_int = int(class_id)
    except ValueError:
        return jsonify({"message": "教学班 ID 必须是数字。"}), HTTPStatus.BAD_REQUEST
    course_class = _get_managed_class_or_404(class_id_int)
    if not course_class:
        return jsonify({"message": "教学班不存在或无权访问。"}), HTTPStatus.NOT_FOUND

    try:
        imported_roster = parse_roster_workbook(roster_file.stream)
    except RosterImportError as exc:
        return jsonify({"message": str(exc)}), HTTPStatus.BAD_REQUEST

    course = course_class.course
    if imported_roster.course_name:
        course.name = imported_roster.course_name
    if imported_roster.course_code:
        course.code = imported_roster.course_code
    if imported_roster.semester:
        course.semester = imported_roster.semester

    imported_count = 0
    updated_count = 0
    for student in imported_roster.students:
        student_id = _student_id_for_class(course_class, student.student_no)
        existing = ClassRoster.query.filter_by(class_id=course_class.id, student_id=student_id).first()
        if existing:
            existing.student_name = student.student_name
            existing.student_no = student.student_no
            existing.student_number = student.student_number
            existing.source_class = student.source_class
            updated_count += 1
            continue
        db.session.add(
            ClassRoster(
                class_id=course_class.id,
                student_name=student.student_name,
                student_no=student.student_no,
                student_number=student.student_number,
                source_class=student.source_class,
                student_id=student_id,
            )
        )
        imported_count += 1

    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="class_roster_excel_imported",
            target_type="course",
            target_id=course.id,
            payload_json={
                "class_id": course_class.id,
                "imported_count": imported_count,
                "updated_count": updated_count,
            },
        )
    )
    db.session.commit()
    return jsonify(
        {
            "course_id": course.id,
            "class_id": course_class.id,
            "imported_count": imported_count,
            "updated_count": updated_count,
        }
    ), HTTPStatus.CREATED


@admin_bp.get("/classes/<int:class_id>/roster")
@login_required
@roles_required(User.ROLE_TEACHER)
def list_roster(class_id: int):
    course_class = _get_managed_class_or_404(class_id)
    if not course_class:
        return jsonify({"message": "班级不存在或无权访问。"}), HTTPStatus.NOT_FOUND
    roster = ClassRoster.query.filter_by(class_id=course_class.id).order_by(ClassRoster.student_id.asc()).all()
    return jsonify({"class": course_class.to_admin_dict(), "roster": [entry.to_dict() for entry in roster]})


@admin_bp.post("/classes/<int:class_id>/roster")
@login_required
@roles_required(User.ROLE_TEACHER)
def create_roster_entry(class_id: int):
    course_class = _get_managed_class_or_404(class_id)
    if not course_class:
        return jsonify({"message": "班级不存在或无权访问。"}), HTTPStatus.NOT_FOUND

    payload = request.get_json(silent=True) or {}
    student_name = (payload.get("student_name") or "").strip()
    student_no = (payload.get("student_no") or payload.get("no") or payload.get("student_id") or "").strip()
    student_no = _normalize_student_no(student_no)
    student_number = (payload.get("student_number") or "").strip() or None
    source_class = (payload.get("source_class") or "").strip() or None
    if not student_name or not student_no:
        return jsonify({"message": "学生姓名和序号 No. 不能为空。"}), HTTPStatus.BAD_REQUEST
    student_id = _student_id_for_class(course_class, student_no)
    try:
        validate_student_id(student_id)
    except StudentIdError as exc:
        return jsonify({"message": str(exc)}), HTTPStatus.BAD_REQUEST

    if ClassRoster.query.filter_by(class_id=course_class.id, student_id=student_id).first():
        return jsonify({"message": "该学生编号已在班级名单中。"}), HTTPStatus.CONFLICT
    entry = ClassRoster(
        class_id=course_class.id,
        student_name=student_name,
        student_no=student_no,
        student_number=student_number,
        source_class=source_class,
        student_id=student_id,
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({"entry": entry.to_dict()}), HTTPStatus.CREATED


@admin_bp.patch("/roster/<int:entry_id>")
@login_required
@roles_required(User.ROLE_TEACHER)
def update_roster_entry(entry_id: int):
    entry = db.session.get(ClassRoster, entry_id)
    if not entry:
        return jsonify({"message": "名单项不存在。"}), HTTPStatus.NOT_FOUND
    course_class = _get_managed_class_or_404(entry.class_id)
    if not course_class:
        return jsonify({"message": "无权访问该名单项。"}), HTTPStatus.NOT_FOUND
    if entry.matched_user_id:
        return jsonify({"message": "该学生已注册绑定账号，暂不能修改名单项。"}), HTTPStatus.CONFLICT

    payload = request.get_json(silent=True) or {}
    student_name = (payload.get("student_name") or entry.student_name).strip()
    student_no = (payload.get("student_no") or payload.get("no") or payload.get("student_id") or entry.student_no or entry.student_id).strip()
    student_no = _normalize_student_no(student_no)
    student_number = (payload.get("student_number") or entry.student_number or "").strip() or None
    source_class = (payload.get("source_class") or entry.source_class or "").strip() or None
    student_id = _student_id_for_class(course_class, student_no)
    try:
        validate_student_id(student_id)
    except StudentIdError as exc:
        return jsonify({"message": str(exc)}), HTTPStatus.BAD_REQUEST
    duplicate = ClassRoster.query.filter(
        ClassRoster.class_id == course_class.id,
        ClassRoster.student_id == student_id,
        ClassRoster.id != entry.id,
    ).first()
    if duplicate:
        return jsonify({"message": "该学生编号已在班级名单中。"}), HTTPStatus.CONFLICT

    entry.student_name = student_name
    entry.student_no = student_no
    entry.student_number = student_number
    entry.source_class = source_class
    entry.student_id = student_id
    db.session.commit()
    return jsonify({"entry": entry.to_dict()})


@admin_bp.delete("/roster/<int:entry_id>")
@login_required
@roles_required(User.ROLE_TEACHER)
def delete_roster_entry(entry_id: int):
    entry = db.session.get(ClassRoster, entry_id)
    if not entry:
        return jsonify({"message": "名单项不存在。"}), HTTPStatus.NOT_FOUND
    if not _get_managed_class_or_404(entry.class_id):
        return jsonify({"message": "无权访问该名单项。"}), HTTPStatus.NOT_FOUND
    if entry.matched_user_id:
        return jsonify({"message": "该学生已注册绑定账号，暂不能删除名单项。"}), HTTPStatus.CONFLICT

    db.session.delete(entry)
    db.session.commit()
    return jsonify({"message": "名单项已删除。"})


@admin_bp.get("/teachers")
@login_required
@roles_required(User.ROLE_ADMIN)
def list_teachers():
    status = request.args.get("status")
    query = User.query.filter_by(role=User.ROLE_TEACHER).order_by(User.created_at.desc())
    if status and status != "all":
        query = query.filter_by(teacher_status=status)
    return jsonify({"teachers": [teacher.to_dict() for teacher in query.all()]})


@admin_bp.patch("/teachers/<int:teacher_id>/status")
@login_required
@roles_required(User.ROLE_ADMIN)
def update_teacher_status(teacher_id: int):
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in {User.TEACHER_STATUS_APPROVED, User.TEACHER_STATUS_REJECTED}:
        return jsonify({"message": "教师审批状态只能是 approved 或 rejected。"}), HTTPStatus.BAD_REQUEST

    teacher = db.session.get(User, teacher_id)
    if not teacher or teacher.role != User.ROLE_TEACHER:
        return jsonify({"message": "教师账号不存在。"}), HTTPStatus.NOT_FOUND

    old_status = teacher.teacher_status
    teacher.teacher_status = status
    db.session.add(
        AuditLog(
            actor_id=current_user.id,
            action="teacher_status_updated",
            target_type="user",
            target_id=teacher.id,
            payload_json={"old_status": old_status, "new_status": status},
        )
    )
    db.session.commit()
    return jsonify({"teacher": teacher.to_dict()})
