from __future__ import annotations

from pathlib import Path

from app.extensions import db
from app.models import ClassRoster, CourseClass, User


def login_approved_teacher(client):
    with client.application.app_context():
        teacher = User(username="teacher1", role=User.ROLE_TEACHER, teacher_status=User.TEACHER_STATUS_APPROVED)
        teacher.set_password("secret123")
        db.session.add(teacher)
        db.session.commit()
    client.post("/api/auth/login", json={"username": "teacher1", "password": "secret123"})


def test_teacher_can_create_class_with_roster(client, admin):
    login_approved_teacher(client)

    response = client.post(
        "/api/admin/classes",
        json={
            "class": {"alias": "OS2026"},
            "roster": [
                {
                    "student_name": "Alice",
                    "student_no": "32",
                    "student_number": "32319500084",
                    "source_class": "信计251",
                }
            ],
        },
    )

    assert response.status_code == 201
    assert response.get_json()["roster_count"] == 1
    with client.application.app_context():
        assert CourseClass.query.filter_by(alias="OS2026").first() is not None
        assert ClassRoster.query.filter_by(student_id="OS2026-32").first() is not None


def test_admin_can_view_existing_classes(client, admin):
    login_approved_teacher(client)
    client.post(
        "/api/admin/classes",
        json={"class": {"alias": "OS2026"}, "roster": []},
    )
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})

    response = client.get("/api/admin/classes")

    assert response.status_code == 200
    assert response.get_json()["classes"][0]["alias"] == "OS2026"


def test_teacher_can_import_students_xlsx(client, admin):
    login_approved_teacher(client)

    create_class = client.post(
        "/api/admin/classes",
        json={"class": {"alias": "OS202601"}, "roster": []},
    )
    class_id = create_class.get_json()["class"]["id"]

    fixture = Path(__file__).resolve().parents[2] / "students.xlsx"
    with fixture.open("rb") as file:
        response = client.post(
            "/api/admin/classes/import-excel",
            data={
                "class_id": str(class_id),
                "file": (file, "students.xlsx"),
            },
            content_type="multipart/form-data",
        )

    assert response.status_code == 201
    assert response.get_json()["imported_count"] == 21
    with client.application.app_context():
        course_class = CourseClass.query.filter_by(alias="OS202601").first()
        assert course_class is not None
        assert course_class.invite_code == "OS202601"
        assert course_class.course.name == "计算机组成原理"
        assert course_class.course.code == "211530001"
        roster_entry = ClassRoster.query.filter_by(student_id="OS202601-01").first()
        assert roster_entry is not None
        assert roster_entry.student_no == "01"
        assert roster_entry.student_number == "32319500084"
        assert roster_entry.source_class == "物联（创）231"


def test_teacher_can_crud_roster_entries(client, admin):
    login_approved_teacher(client)
    create_class = client.post(
        "/api/admin/classes",
        json={
            "class": {"alias": "OS2026"},
            "roster": [{"student_name": "Alice", "student_no": "32", "student_number": "32319500084"}],
        },
    )
    class_id = create_class.get_json()["class"]["id"]

    response = client.post(
        f"/api/admin/classes/{class_id}/roster",
        json={"student_name": "Bob", "student_no": "33", "student_number": "32319500085"},
    )
    assert response.status_code == 201
    entry_id = response.get_json()["entry"]["id"]
    assert response.get_json()["entry"]["student_id"] == "OS2026-33"

    response = client.patch(
        f"/api/admin/roster/{entry_id}",
        json={"student_name": "Bobby", "student_no": "34", "student_number": "32319500086"},
    )
    assert response.status_code == 200
    assert response.get_json()["entry"]["student_name"] == "Bobby"
    assert response.get_json()["entry"]["student_id"] == "OS2026-34"

    response = client.get(f"/api/admin/classes/{class_id}/roster")
    assert response.status_code == 200
    assert len(response.get_json()["roster"]) == 2

    response = client.delete(f"/api/admin/roster/{entry_id}")
    assert response.status_code == 200
