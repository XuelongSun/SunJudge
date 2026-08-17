from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify
from flask_login import current_user, login_required

from ..models import ClassRoster, CourseClass, CourseMember, Submission, User, published_assignment_ids_for_class, table_has_columns


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
        published_assignment_ids = published_assignment_ids_for_class(course_class.id)
        submitted_assignment_ids = set()
        if published_assignment_ids and table_has_columns("submissions", {"assignment_id", "student_user_id"}):
            rows = (
                Submission.query.with_entities(Submission.assignment_id)
                .filter(
                    Submission.student_user_id == current_user.id,
                    Submission.assignment_id.in_(published_assignment_ids),
                )
                .distinct()
                .all()
            )
            submitted_assignment_ids = {int(row[0]) for row in rows}
        data["pending_assignment_count"] = len([item for item in published_assignment_ids if item not in submitted_assignment_ids])
        data["published_assignment_count"] = len(published_assignment_ids)
        result.append(data)
    return jsonify({"classes": result})
