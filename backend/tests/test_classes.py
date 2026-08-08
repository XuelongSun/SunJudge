from __future__ import annotations

from app.extensions import db
from app.models import Course, CourseClass, CourseMember, User


def test_public_classes_only_lists_enabled_classes(client):
    with client.application.app_context():
        teacher = User(username="teacher1", role=User.ROLE_TEACHER, teacher_status=User.TEACHER_STATUS_APPROVED)
        teacher.set_password("secret123")
        db.session.add(teacher)
        db.session.flush()
        course = Course(name="Operating Systems", code="OS", semester="2026", teacher_id=teacher.id)
        db.session.add(course)
        db.session.flush()
        db.session.add(CourseClass(course_id=course.id, name="OS teaching 1", alias="OS2026", invite_code="OPEN", invite_enabled=True))
        db.session.add(CourseClass(course_id=course.id, name="OS teaching 2", alias="OS2027", invite_code="CLOSED", invite_enabled=False))
        db.session.commit()

    response = client.get("/api/classes/public")

    assert response.status_code == 200
    classes = response.get_json()["classes"]
    assert [item["alias"] for item in classes] == ["OS2026"]
    assert classes[0]["course"]["teacher_name"] == "teacher1"


def test_student_can_list_own_classes(client):
    with client.application.app_context():
        teacher = User(username="teacher1", role=User.ROLE_TEACHER, teacher_status=User.TEACHER_STATUS_APPROVED)
        teacher.set_password("secret123")
        student = User(username="OS2026-01", role=User.ROLE_STUDENT, student_name="Alice", student_id="OS2026-01")
        student.set_password("secret123")
        db.session.add_all([teacher, student])
        db.session.flush()
        course = Course(name="Operating Systems", code="OS", semester="2026", teacher_id=teacher.id)
        db.session.add(course)
        db.session.flush()
        course_class = CourseClass(course_id=course.id, name="OS teaching 1", alias="OS2026", invite_code="OPEN", invite_enabled=True)
        db.session.add(course_class)
        db.session.flush()
        db.session.add(
            CourseMember(
                course_id=course.id,
                class_id=course_class.id,
                user_id=student.id,
                role=User.ROLE_STUDENT,
            )
        )
        db.session.commit()

    client.post("/api/auth/login", json={"username": "OS2026-01", "password": "secret123"})
    response = client.get("/api/classes/my")

    assert response.status_code == 200
    assert response.get_json()["classes"][0]["alias"] == "OS2026"
