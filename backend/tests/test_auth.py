from __future__ import annotations

from app.extensions import db
from app.models import ClassRoster, Course, CourseClass, CourseMember, User


def create_rostered_class(app, student_name: str = "Alice", student_id: str = "OS2026-32") -> int:
    student_no = student_id.split("-", 1)[1]
    with app.app_context():
        teacher = User(username=f"teacher-{student_id}", role=User.ROLE_TEACHER, teacher_status=User.TEACHER_STATUS_APPROVED)
        teacher.set_password("secret123")
        db.session.add(teacher)
        db.session.flush()
        course = Course(name="Operating Systems", code="OS", semester="2026", teacher_id=teacher.id)
        db.session.add(course)
        db.session.flush()
        course_class = CourseClass(course_id=course.id, name="Operating Systems 01", alias="OS2026", invite_code="OS2026")
        db.session.add(course_class)
        db.session.flush()
        db.session.add(
            ClassRoster(
                class_id=course_class.id,
                student_name=student_name,
                student_no=student_no,
                student_number=f"long-{student_no}",
                source_class="信计251",
                student_id=student_id,
            )
        )
        db.session.commit()
        return course_class.id


def test_student_can_register_and_login(client):
    create_rostered_class(client.application)
    response = client.post(
        "/api/auth/register",
        json={
            "password": "secret123",
            "role": "student",
            "student_id": "OS2026-32",
            "student_name": "Alice",
        },
    )
    assert response.status_code == 201

    response = client.post("/api/auth/login", json={"username": "OS2026-32", "password": "secret123"})
    assert response.status_code == 200
    assert response.get_json()["user"]["role"] == User.ROLE_STUDENT
    with client.application.app_context():
        roster_entry = ClassRoster.query.filter_by(student_id="OS2026-32").first()
        member = CourseMember.query.filter_by(user_id=response.get_json()["user"]["id"]).first()
        assert roster_entry.registration_status == ClassRoster.STATUS_REGISTERED
        assert roster_entry.matched_user_id == response.get_json()["user"]["id"]
        assert member is not None


def test_student_can_login_by_real_name_or_student_id(client):
    create_rostered_class(client.application)
    response = client.post(
        "/api/auth/register",
        json={
            "password": "secret123",
            "role": "student",
            "student_id": "OS2026-32",
            "student_name": "Alice",
        },
    )
    assert response.status_code == 201

    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"username": "Alice", "password": "secret123"})
    assert response.status_code == 200
    assert response.get_json()["user"]["student_id"] == "OS2026-32"

    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"username": "OS2026-32", "password": "secret123"})
    assert response.status_code == 200
    assert response.get_json()["user"]["student_id"] == "OS2026-32"


def test_student_registration_binds_matching_rosters_by_name_and_number(client):
    create_rostered_class(client.application, student_id="OS2026-32")
    with client.application.app_context():
        teacher = User(username="teacher2", role=User.ROLE_TEACHER, teacher_status=User.TEACHER_STATUS_APPROVED)
        teacher.set_password("secret123")
        db.session.add(teacher)
        db.session.flush()
        course = Course(name="Data Structures", code="DS", semester="2026", teacher_id=teacher.id)
        db.session.add(course)
        db.session.flush()
        course_class = CourseClass(course_id=course.id, name="Data Structures 01", alias="DS2026", invite_code="DS2026")
        db.session.add(course_class)
        db.session.flush()
        db.session.add(
            ClassRoster(
                class_id=course_class.id,
                student_name="Alice",
                student_no="07",
                student_number="long-32",
                source_class="信计251",
                student_id="DS2026-07",
            )
        )
        db.session.commit()

    response = client.post(
        "/api/auth/register",
        json={
            "password": "secret123",
            "role": "student",
            "student_id": "OS2026-32",
            "student_name": "Alice",
        },
    )
    assert response.status_code == 201
    user_id = response.get_json()["user"]["id"]

    with client.application.app_context():
        memberships = CourseMember.query.filter_by(user_id=user_id).all()
        secondary_roster = ClassRoster.query.filter_by(student_id="DS2026-07").first()
        assert len(memberships) == 2
        assert secondary_roster.registration_status == ClassRoster.STATUS_REGISTERED
        assert secondary_roster.matched_user_id == user_id

    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"username": "DS2026-07", "password": "secret123"})
    assert response.status_code == 200
    assert response.get_json()["user"]["student_id"] == "OS2026-32"


def test_student_real_name_login_requires_unambiguous_match(client):
    with client.application.app_context():
        first = User(username="OS2026-01", role=User.ROLE_STUDENT, student_name="Alice", student_id="OS2026-01")
        first.set_password("secret123")
        second = User(username="DS2026-01", role=User.ROLE_STUDENT, student_name="Alice", student_id="DS2026-01")
        second.set_password("secret123")
        db.session.add_all([first, second])
        db.session.commit()

    response = client.post("/api/auth/login", json={"username": "Alice", "password": "secret123"})

    assert response.status_code == 409


def test_student_registration_requires_invite_code(client):
    response = client.post(
        "/api/auth/register",
        json={
            "password": "secret123",
            "role": "student",
            "student_name": "Alice",
        },
    )
    assert response.status_code == 400


def test_student_registration_requires_two_digit_no(client):
    create_rostered_class(client.application, student_id="OS2026-02")
    response = client.post(
        "/api/auth/register",
        json={
            "password": "secret123",
            "role": "student",
            "student_id": "OS2026-2",
            "student_name": "Alice",
        },
    )
    assert response.status_code == 400


def test_student_registration_requires_roster_match(client):
    create_rostered_class(client.application)
    response = client.post(
        "/api/auth/register",
        json={
            "password": "secret123",
            "role": "student",
            "student_id": "OS2026-33",
            "student_name": "Bob",
        },
    )
    assert response.status_code == 403


def test_student_registration_requires_existing_alias(client):
    create_rostered_class(client.application)
    response = client.post(
        "/api/auth/register",
        json={
            "password": "secret123",
            "role": "student",
            "student_id": "OTHER-32",
            "student_name": "Alice",
        },
    )
    assert response.status_code == 400


def test_teacher_must_be_approved_before_login(client, admin):
    response = client.post(
        "/api/auth/register",
        json={"username": "teacher1", "password": "secret123", "role": "teacher"},
    )
    assert response.status_code == 201
    teacher_id = response.get_json()["user"]["id"]

    response = client.post("/api/auth/login", json={"username": "teacher1", "password": "secret123"})
    assert response.status_code == 403

    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200

    response = client.patch(f"/api/admin/teachers/{teacher_id}/status", json={"status": "approved"})
    assert response.status_code == 200

    client.post("/api/auth/logout")
    response = client.post("/api/auth/login", json={"username": "teacher1", "password": "secret123"})
    assert response.status_code == 200
    assert response.get_json()["user"]["teacher_status"] == User.TEACHER_STATUS_APPROVED


def test_only_admin_can_approve_teachers(client):
    create_rostered_class(client.application)
    client.post(
        "/api/auth/register",
        json={
            "password": "secret123",
            "role": "student",
            "student_id": "OS2026-32",
            "student_name": "Alice",
        },
    )
    with client.application.app_context():
        teacher = User(username="teacher1", role=User.ROLE_TEACHER, teacher_status=User.TEACHER_STATUS_PENDING)
        teacher.set_password("secret123")
        db.session.add(teacher)
        db.session.commit()
        teacher_id = teacher.id

    client.post("/api/auth/login", json={"username": "OS2026-32", "password": "secret123"})
    response = client.patch(f"/api/admin/teachers/{teacher_id}/status", json={"status": "approved"})
    assert response.status_code == 403
