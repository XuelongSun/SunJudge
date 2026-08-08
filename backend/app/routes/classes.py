from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from ..models import ClassRoster, CourseClass, CourseMember, User


classes_bp = Blueprint("classes", __name__)


@classes_bp.get("/public")
def list_public_classes():
    classes = (
        CourseClass.query.filter_by(invite_enabled=True)
        .join(CourseClass.course)
        .order_by(CourseClass.name.asc())
        .all()
    )
    return jsonify({"classes": [course_class.to_public_dict() for course_class in classes]})


@classes_bp.get("/my")
@login_required
def list_my_classes():
    if current_user.role != User.ROLE_STUDENT:
        return jsonify({"message": "只有学生账号可以查看自己的班级。"}), HTTPStatus.FORBIDDEN

    classes = (
        CourseClass.query.join(CourseMember, CourseMember.class_id == CourseClass.id)
        .filter(CourseMember.user_id == current_user.id, CourseMember.role == User.ROLE_STUDENT)
        .order_by(CourseClass.created_at.desc())
        .all()
    )
    result = []
    for course_class in classes:
        data = course_class.to_public_dict()
        roster_entry = ClassRoster.query.filter_by(class_id=course_class.id, matched_user_id=current_user.id).first()
        data["student"] = {
            "student_id": roster_entry.student_id if roster_entry else current_user.student_id,
            "student_no": roster_entry.student_no if roster_entry else current_user.student_no,
            "student_number": roster_entry.student_number if roster_entry else current_user.student_number,
            "student_name": roster_entry.student_name if roster_entry else current_user.student_name,
            "registration_status": roster_entry.registration_status if roster_entry else None,
        }
        result.append(data)
    return jsonify({"classes": result})
