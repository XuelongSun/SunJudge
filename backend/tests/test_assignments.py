from __future__ import annotations

from io import BytesIO

from app.extensions import db
from app.models import Assignment, ClassRoster, Course, CourseClass, CourseMember, Submission, User


def _create_class_with_student(app):
    with app.app_context():
        teacher = User(username="teacher1", role=User.ROLE_TEACHER, teacher_status=User.TEACHER_STATUS_APPROVED)
        teacher.set_password("secret123")
        student = User(
            username="OS202601-06",
            role=User.ROLE_STUDENT,
            student_name="Alice",
            student_id="OS202601-06",
            student_no="06",
            student_number="32300000006",
        )
        student.set_password("secret123")
        outsider = User(username="outsider", role=User.ROLE_STUDENT, student_name="Bob", student_id="DS202601-01")
        outsider.set_password("secret123")
        db.session.add_all([teacher, student, outsider])
        db.session.flush()
        course = Course(name="Operating Systems", code="OS", semester="2026", teacher_id=teacher.id)
        db.session.add(course)
        db.session.flush()
        course_class = CourseClass(
            course_id=course.id,
            name="OS teaching 1",
            alias="OS202601",
            invite_code="OS202601",
            invite_enabled=True,
        )
        db.session.add(course_class)
        db.session.flush()
        db.session.add(
            ClassRoster(
                class_id=course_class.id,
                student_name="Alice",
                student_no="06",
                student_number="32300000006",
                source_class="CS2601",
                student_id="OS202601-06",
                matched_user_id=student.id,
                registration_status=ClassRoster.STATUS_REGISTERED,
            )
        )
        db.session.add(
            CourseMember(course_id=course.id, class_id=course_class.id, user_id=student.id, role=User.ROLE_STUDENT)
        )
        db.session.commit()
        return course_class.id, teacher.id, student.id, outsider.id


def _login(client, username: str, password: str = "secret123"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _confirm_assignment(client, assignment_id: int):
    return client.post(f"/api/assignments/{assignment_id}/confirm-submission")


def _assignment_payload(status: str = Assignment.STATUS_DRAFT):
    return {
        "title": "Homework 1",
        "code": "hw1",
        "type": Assignment.TYPE_HOMEWORK,
        "description": "Write a short **report**.",
        "description_format": "markdown",
        "max_score": 100,
        "status": status,
        "file_rules": {
            "allowed_extensions": [".md", ".zip", ".jpg", ".png"],
            "max_size_mb": 1,
            "filename_template": "{student_id}_{assignment_code}{extension}",
        },
        "program_evaluations": [
            {
                "name": "case 1",
                "args": "--mode sample 2",
                "expected_output": "3",
                "score_percent": 30,
                "timeout_seconds": 2,
            }
        ],
        "ai_evaluations": [
            {
                "name": "report quality",
                "input": "Read the submitted report.",
                "grading_criteria": "Explain clarity and completeness.",
                "score_percent": 20,
            }
        ],
    }


def test_teacher_can_save_draft_and_publish_assignment(client):
    class_id, *_ = _create_class_with_student(client.application)
    _login(client, "teacher1")

    response = client.post(f"/api/admin/classes/{class_id}/assignments", json=_assignment_payload())
    assert response.status_code == 201
    assignment = response.get_json()["assignment"]
    assert assignment["status"] == Assignment.STATUS_DRAFT
    assert assignment["type"] == Assignment.TYPE_HOMEWORK
    assert assignment["description_format"] == "markdown"
    assert assignment["file_rules"]["allowed_extensions"] == [".md", ".zip", ".jpg", ".png"]
    assert assignment["program_evaluations"][0]["cases"][0]["expected_output"] == "3"
    assert assignment["program_evaluations"][0]["cases"][0]["args"] == "--mode sample 2"
    assert assignment["ai_evaluations"][0]["criteria_items"][0]["content"] == "Explain clarity and completeness."

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    response = client.get(f"/api/classes/{class_id}/assignments")
    assert response.status_code == 200
    assert response.get_json()["assignments"] == []

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    response = client.post(f"/api/admin/assignments/{assignment['id']}/publish")
    assert response.status_code == 200
    assert response.get_json()["assignment"]["status"] == Assignment.STATUS_PUBLISHED

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    response = client.get(f"/api/classes/{class_id}/assignments")
    assert response.status_code == 200
    assert response.get_json()["assignments"][0]["code"] == "hw1"

    response = client.get("/api/classes/my")
    assert response.status_code == 200
    assert response.get_json()["classes"][0]["pending_assignment_count"] == 1


def test_student_assignment_payload_hides_ai_evaluations(client):
    class_id, *_ = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment = client.post(
        f"/api/admin/classes/{class_id}/assignments",
        json=_assignment_payload(Assignment.STATUS_PUBLISHED),
    ).get_json()["assignment"]
    assert assignment["ai_evaluations"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    response = client.get(f"/api/classes/{class_id}/assignments")
    assert response.status_code == 200
    student_assignment = response.get_json()["assignments"][0]
    assert student_assignment["ai_evaluations"] == []


def test_teacher_can_delete_assignment(client):
    class_id, *_ = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(
        f"/api/admin/classes/{class_id}/assignments",
        json=_assignment_payload(Assignment.STATUS_PUBLISHED),
    ).get_json()["assignment"]["id"]

    response = client.delete(f"/api/admin/assignments/{assignment_id}")
    assert response.status_code == 200

    response = client.get(f"/api/admin/classes/{class_id}/assignments")
    assert response.status_code == 200
    assert response.get_json()["assignments"] == []

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    response = client.get(f"/api/classes/{class_id}/assignments")
    assert response.status_code == 200
    assert response.get_json()["assignments"] == []


def test_student_submission_requires_extension_and_filename_rules(client):
    class_id, *_ = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(
        f"/api/admin/classes/{class_id}/assignments",
        json=_assignment_payload(Assignment.STATUS_PUBLISHED),
    ).get_json()["assignment"]["id"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    bad_extension = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"print('wrong')"), "OS202601-06_hw1.py")},
        content_type="multipart/form-data",
    )
    assert bad_extension.status_code == 201
    rejected_confirm = _confirm_assignment(client, assignment_id)
    assert rejected_confirm.status_code == 400
    assert "extension" in " ".join(rejected_confirm.get_json()["details"]).lower()

    bad_name = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"# report"), "Alice_hw1.md")},
        content_type="multipart/form-data",
    )
    assert bad_name.status_code == 400
    assert "OS202601-06_hw1.md" in " ".join(bad_name.get_json()["details"])

    response = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"# report"), "OS202601-06_hw1.md")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    submission = response.get_json()["submission"]
    assert submission["status"] == Submission.STATUS_UPLOADED
    assert submission["validation_result"]["ok"] is True


def test_student_submission_accepts_zip_and_images(client):
    class_id, *_ = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(
        f"/api/admin/classes/{class_id}/assignments",
        json=_assignment_payload(Assignment.STATUS_PUBLISHED),
    ).get_json()["assignment"]["id"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")

    cases = [
        (b"PK\x03\x04zip-content", "OS202601-06_hw1.zip"),
        (b"\xff\xd8\xff\xe0jpg-content", "OS202601-06_hw1.jpg"),
        (b"\x89PNG\r\n\x1a\npng-content", "OS202601-06_hw1.png"),
    ]
    for content, filename in cases:
        response = client.post(
            f"/api/assignments/{assignment_id}/submissions",
            data={"file": (BytesIO(content), filename)},
            content_type="multipart/form-data",
        )
        assert response.status_code == 201
        assert response.get_json()["submission"]["original_filename"] == filename


def test_submission_requires_class_membership(client):
    class_id, *_ = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(
        f"/api/admin/classes/{class_id}/assignments",
        json=_assignment_payload(Assignment.STATUS_PUBLISHED),
    ).get_json()["assignment"]["id"]

    client.post("/api/auth/logout")
    _login(client, "DS202601-01")
    response = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"# report"), "OS202601-06_hw1.md")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 404


def test_teacher_submission_overview_marks_missing_and_submitted(client):
    class_id, *_ = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(
        f"/api/admin/classes/{class_id}/assignments",
        json=_assignment_payload(Assignment.STATUS_PUBLISHED),
    ).get_json()["assignment"]["id"]

    response = client.get(f"/api/admin/assignments/{assignment_id}/submissions")
    assert response.status_code == 200
    assert response.get_json()["submissions"][0]["state"] == "missing"

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"# report"), "OS202601-06_hw1.md")},
        content_type="multipart/form-data",
    )

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    response = client.get(f"/api/admin/assignments/{assignment_id}/submissions")
    assert response.status_code == 200
    row = response.get_json()["submissions"][0]
    assert row["state"] == "missing"
    assert row["student_state"] == "uploaded"
    assert row["submission"]["original_filename"] == "OS202601-06_hw1.md"

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    assert _confirm_assignment(client, assignment_id).status_code == 200

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    response = client.get(f"/api/admin/assignments/{assignment_id}/submissions")
    assert response.status_code == 200
    row = response.get_json()["submissions"][0]
    assert row["state"] == "submitted"
    assert row["student_state"] == "submitted"
