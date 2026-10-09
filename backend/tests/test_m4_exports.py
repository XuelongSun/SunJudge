from __future__ import annotations

from datetime import timedelta
from io import BytesIO

from app.extensions import db
from app.models import Assignment, ClassRoster, Course, CourseClass, CourseMember, GradingResult, User, utc_now


def _login(client, username: str, password: str = "secret123"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


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
        db.session.add_all([teacher, student])
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
        roster = ClassRoster(
            class_id=course_class.id,
            student_name="Alice",
            student_no="06",
            student_number="32300000006",
            source_class="CS2601",
            student_id="OS202601-06",
            matched_user_id=student.id,
            registration_status=ClassRoster.STATUS_REGISTERED,
        )
        db.session.add_all([roster, CourseMember(course_id=course.id, class_id=course_class.id, user_id=student.id, role=User.ROLE_STUDENT)])
        db.session.commit()
        return course_class.id


def _manual_assignment_payload():
    now = utc_now()
    return {
        "title": "Manual Homework",
        "code": "hw4",
        "type": Assignment.TYPE_HOMEWORK,
        "description": "Write a report.",
        "description_format": "markdown",
        "deadline": (now + timedelta(days=3)).isoformat(),
        "max_score": 100,
        "status": Assignment.STATUS_PUBLISHED,
        "submission_requirements": [
            {
                "key": "report",
                "label": "实验报告",
                "allowed_extensions": [".md"],
                "max_size_mb": 1,
                "filename_template": "{student_id}_{assignment_code}{extension}",
                "required": True,
            }
        ],
        "program_evaluations": [],
        "ai_evaluations": [],
    }


def test_m4_teacher_grade_analysis_csv_scoremanager_and_student_summary(client):
    class_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=_manual_assignment_payload()).get_json()["assignment"][
        "id"
    ]
    with client.application.app_context():
        assignment = db.session.get(Assignment, assignment_id)
        assignment.published_at = utc_now() - timedelta(days=2)
        db.session.commit()

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    upload = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"item_key": "report", "file": (BytesIO(b"# report\n"), "OS202601-06_hw4.md")},
        content_type="multipart/form-data",
    )
    submission_id = upload.get_json()["submission"]["id"]
    assert client.post(f"/api/assignments/{assignment_id}/confirm-submission").status_code == 200

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    publish = client.patch(
        f"/api/admin/submissions/{submission_id}/grade",
        json={"final_score": 92, "feedback": "Good.", "teacher_comment": "Well done.", "status": GradingResult.STATUS_PUBLISHED},
    )
    assert publish.status_code == 200

    gradebook = client.get(f"/api/admin/assignments/{assignment_id}/grades")
    assert gradebook.status_code == 200
    analysis = gradebook.get_json()["analysis"]
    assert analysis["expected_count"] == 1
    assert analysis["submitted_count"] == 1
    assert analysis["pending_submission_count"] == 0
    assert analysis["expired_count"] == 0
    assert analysis["published_count"] == 1
    assert analysis["reviewed_count"] == 0
    assert analysis["pending_grading_count"] == 0
    assert analysis["average_score"] == 92
    assert analysis["average_submit_days_after_publish"] is not None
    assert analysis["average_submit_days_before_deadline"] is not None
    assert analysis["publish_to_deadline_days"] == 5

    csv_response = client.get(f"/api/admin/assignments/{assignment_id}/grades.csv")
    assert csv_response.status_code == 200
    csv_text = csv_response.data.decode("utf-8-sig")
    assert "Alice" in csv_text
    assert "Well done." in csv_text

    commands = client.get(f"/api/admin/assignments/{assignment_id}/scoremanager-commands?field=homework").get_json()["export"]
    assert commands["commands"] == "rd 06 homework 92"
    assert commands["exported_count"] == 1

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    classes = client.get("/api/classes/my").get_json()["classes"]
    assert classes[0]["published_assignment_count"] == 1
    assert classes[0]["completed_assignment_count"] == 1
    assert classes[0]["published_grade_count"] == 1
    assert classes[0]["average_score"] == 92


def test_m4_scoremanager_export_blocks_invalid_student_ids(client):
    class_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=_manual_assignment_payload()).get_json()["assignment"][
        "id"
    ]
    with client.application.app_context():
        roster = ClassRoster.query.filter_by(class_id=class_id).first()
        roster.student_id = "OS202601"
        db.session.commit()

    response = client.get(f"/api/admin/assignments/{assignment_id}/scoremanager-commands?field=homework")
    assert response.status_code == 400
    assert response.get_json()["invalid_students"][0]["student_id"] == "OS202601"

def test_teacher_completion_separates_expired_and_pending_students(client):
    class_id = _create_class_with_student(client.application)
    _login(client, 'teacher1')
    payload = _manual_assignment_payload()
    assignment_id = client.post(f'/api/admin/classes/{class_id}/assignments', json=payload).json['assignment']['id']
    def analysis():
        return client.get(f'/api/admin/assignments/{assignment_id}/submissions').json['analysis']
    assert analysis()['pending_submission_count'] == 1
    with client.application.app_context():
        assignment = db.session.get(Assignment, assignment_id)
        assignment.deadline = utc_now() - timedelta(days=1)
        # An unregistered roster student also counts as expired after deadline.
        db.session.add(ClassRoster(class_id=class_id, student_no='07', student_id='OS202601-07', student_name='Bob'))
        db.session.commit()
    expired = analysis()
    assert expired['expected_count'] == 2
    assert expired['submitted_count'] == 0
    assert expired['expired_count'] == 2
    assert expired['pending_submission_count'] == 0
    assert expired['average_score'] is None  # Teacher average does not include expired zero.
    with client.application.app_context():
        assignment = db.session.get(Assignment, assignment_id)
        assignment.allow_late = True
        db.session.commit()
    late = analysis()
    assert late['expired_count'] == 0
    assert late['pending_submission_count'] == 2
    assert late['submitted_count'] + late['expired_count'] + late['pending_submission_count'] == late['expected_count']
