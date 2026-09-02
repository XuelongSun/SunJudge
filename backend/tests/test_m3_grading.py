from __future__ import annotations

from io import BytesIO

from app.extensions import db
from app.models import Assignment, ClassRoster, Course, CourseClass, CourseMember, GradingResult, JudgeRun, TeacherLLMConfig, User
from app.services import judge, llm_grading


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
        db.session.add_all(
            [
                ClassRoster(
                    class_id=course_class.id,
                    student_name="Alice",
                    student_no="06",
                    student_number="32300000006",
                    source_class="CS2601",
                    student_id="OS202601-06",
                    matched_user_id=student.id,
                    registration_status=ClassRoster.STATUS_REGISTERED,
                ),
                CourseMember(course_id=course.id, class_id=course_class.id, user_id=student.id, role=User.ROLE_STUDENT),
            ]
        )
        db.session.commit()
        return course_class.id


def _login(client, username: str, password: str = "secret123"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _confirm_assignment(client, assignment_id: int):
    return client.post(f"/api/assignments/{assignment_id}/confirm-submission")


def _program_assignment_payload():
    return {
        "title": "Python Judge",
        "code": "py1",
        "type": Assignment.TYPE_HOMEWORK,
        "max_score": 100,
        "status": Assignment.STATUS_PUBLISHED,
        "file_rules": {
            "allowed_extensions": [".py"],
            "max_size_mb": 1,
            "filename_template": "{student_id}_{assignment_code}{extension}",
        },
        "rubric": {"text": "Pass the tests."},
        "program_evaluations": [
            {
                "name": "sample",
                "args": "1 2",
                "expected_output": "3\n",
                "score_percent": 60,
                "timeout_seconds": 2,
            }
        ],
        "ai_evaluations": [],
    }


def test_python_submission_creates_judge_run_and_auto_grade(client, monkeypatch):
    def fake_run_case(_source_path, expected_output, _timeout, args=""):
        return {
            "status": JudgeRun.STATUS_ACCEPTED,
            "expected_output": expected_output,
            "stdout": expected_output,
            "stderr": "",
            "returncode": 0,
        }

    monkeypatch.setattr(judge, "_ensure_docker_image", lambda: None)
    monkeypatch.setattr(judge, "_run_case_in_docker", fake_run_case)
    class_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=_program_assignment_payload()).get_json()[
        "assignment"
    ]["id"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    response = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"import sys\na, b = map(int, sys.argv[1:3])\nprint(a + b)\n"), "OS202601-06_py1.py")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    submission = response.get_json()["submission"]
    assert submission["status"] == "uploaded"
    assert submission["latest_judge_run"] is None

    confirm = _confirm_assignment(client, assignment_id)
    assert confirm.status_code == 200
    assert confirm.get_json()["queue_status"] == "inline"
    confirmed_submission = confirm.get_json()["assignment"]["submissions"][0]
    assert confirmed_submission["latest_judge_run"]["status"] == JudgeRun.STATUS_ACCEPTED
    assert confirmed_submission["latest_judge_run"]["score"] == 60
    assert confirm.get_json()["assignment_grade"]["auto_score"] is None
    assert confirm.get_json()["assignment_grade"]["status"] == GradingResult.STATUS_AUTO_GRADED

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    teacher_row = client.get(f"/api/admin/assignments/{assignment_id}/submissions").get_json()["submissions"][0]
    assert teacher_row["assignment_grade"]["auto_score"] == 60


def test_run_case_in_docker_passes_argv(client, monkeypatch, tmp_path):
    source_path = tmp_path / "solution.py"
    source_path.write_text("print('ok')\n", encoding="utf-8")
    captured: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = "ok\n"
        stderr = ""

    def fake_subprocess_run(command, **kwargs):
        captured["command"] = command
        captured["stdin"] = kwargs.get("stdin")
        captured["input"] = kwargs.get("input")
        return Completed()

    monkeypatch.setattr(judge.subprocess, "run", fake_subprocess_run)
    with client.application.app_context():
        result = judge._run_case_in_docker(source_path, "ok\n", 2, '--limit 3 "two words"')

    assert result["status"] == JudgeRun.STATUS_ACCEPTED
    assert captured["stdin"] is None
    assert captured["input"] is None
    assert captured["command"][-4:] == ["solution.py", "--limit", "3", "two words"]


def test_teacher_can_review_score_and_comment(client, monkeypatch):
    monkeypatch.setattr(judge, "_ensure_docker_image", lambda: None)
    monkeypatch.setattr(
        judge,
        "_run_case_in_docker",
        lambda _source_path, expected_output, _timeout, args="": {
            "status": JudgeRun.STATUS_ACCEPTED,
            "expected_output": expected_output,
            "stdout": expected_output,
            "stderr": "",
            "returncode": 0,
        },
    )
    class_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=_program_assignment_payload()).get_json()[
        "assignment"
    ]["id"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    submission_id = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"print(3)\n"), "OS202601-06_py1.py")},
        content_type="multipart/form-data",
    ).get_json()["submission"]["id"]
    assert _confirm_assignment(client, assignment_id).status_code == 200

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    response = client.patch(
        f"/api/admin/submissions/{submission_id}/grade",
        json={
            "final_score": 88,
            "feedback": "Good solution.",
            "teacher_comment": "Remember to explain your idea.",
            "reason": "Manual review",
            "status": "reviewed",
        },
    )

    assert response.status_code == 200
    grading = response.get_json()["grading_result"]
    assert grading["final_score"] == 88
    assert grading["teacher_comment"] == "Remember to explain your idea."
    assert grading["status"] == GradingResult.STATUS_REVIEWED


def test_teacher_can_download_submission_and_view_full_hidden_case_report(client, monkeypatch):
    def fake_run_case(_source_path, expected_output, _timeout, args=""):
        return {
            "status": JudgeRun.STATUS_WRONG_ANSWER,
            "expected_output": expected_output,
            "stdout": "4\n",
            "stderr": "",
            "diff": {"line": 1, "expected": "3", "actual": "4"},
            "returncode": 0,
        }

    monkeypatch.setattr(judge, "_ensure_docker_image", lambda: None)
    monkeypatch.setattr(judge, "_run_case_in_docker", fake_run_case)
    class_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    payload = _program_assignment_payload()
    payload["program_evaluations"] = [
        {
            "name": "hidden sample",
            "input_file_key": "main",
            "cases": [
                {
                    "name": "hidden case",
                    "args": '--limit 3 "two words"',
                    "expected_output": "3\n",
                    "score_percent": 60,
                    "timeout_seconds": 2,
                    "is_hidden": True,
                }
            ],
        }
    ]
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=payload).get_json()["assignment"]["id"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    student_response = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"print(4)\n"), "OS202601-06_py1.py")},
        content_type="multipart/form-data",
    )
    submission = student_response.get_json()["submission"]
    confirm = _confirm_assignment(client, assignment_id)
    assert confirm.status_code == 200
    confirmed_submission = confirm.get_json()["assignment"]["submissions"][0]
    student_case = confirmed_submission["latest_judge_run"]["details"]["cases"][0]
    assert student_case["args"] is None
    assert student_case["expected_output"] is None

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    rows_response = client.get(f"/api/admin/assignments/{assignment_id}/submissions")
    row = rows_response.get_json()["submissions"][0]
    teacher_case = row["submission"]["latest_judge_run"]["details"]["cases"][0]
    assert teacher_case["args"] == '--limit 3 "two words"'
    assert teacher_case["expected_output"] == "3\n"
    assert teacher_case["diff"]["actual"] == "4"

    download_response = client.get(f"/api/admin/submissions/{submission['id']}/download")
    assert download_response.status_code == 200
    assert b"print(4)" in download_response.data
    assert "OS202601-06_py1.py" in download_response.headers["Content-Disposition"]


def test_student_read_status_and_published_feedback_lock_resubmission(client, monkeypatch):
    monkeypatch.setattr(judge, "_ensure_docker_image", lambda: None)
    monkeypatch.setattr(
        judge,
        "_run_case_in_docker",
        lambda _source_path, expected_output, _timeout, args="": {
            "status": JudgeRun.STATUS_ACCEPTED,
            "expected_output": expected_output,
            "stdout": expected_output,
            "stderr": "",
            "returncode": 0,
        },
    )
    class_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=_program_assignment_payload()).get_json()[
        "assignment"
    ]["id"]

    rows = client.get(f"/api/admin/assignments/{assignment_id}/submissions").get_json()["submissions"]
    assert rows[0]["student_state"] == "unread"

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    read_response = client.post(f"/api/assignments/{assignment_id}/read")
    assert read_response.status_code == 200

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    rows = client.get(f"/api/admin/assignments/{assignment_id}/submissions").get_json()["submissions"]
    assert rows[0]["student_state"] == "read"

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    submission_id = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"print(3)\n"), "OS202601-06_py1.py")},
        content_type="multipart/form-data",
    ).get_json()["submission"]["id"]
    assert _confirm_assignment(client, assignment_id).status_code == 200

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    publish_response = client.patch(
        f"/api/admin/submissions/{submission_id}/grade",
        json={
            "file_reviews": [
                {
                    "submission_id": submission_id,
                    "submission_item_key": "main",
                    "submission_item_label": "提交文件",
                    "filename": "OS202601-06_py1.py",
                    "review_kind": "program",
                    "review_status": "confirmed",
                    "score": 92,
                    "comment": "Accepted after review.",
                }
            ],
            "teacher_comment": "Well done.",
            "reason": "Publish feedback",
            "status": "published",
        },
    )
    assert publish_response.status_code == 200
    grading = publish_response.get_json()["assignment_grade"]
    assert grading["final_score"] == 92
    assert grading["status"] == GradingResult.STATUS_PUBLISHED
    assert "# Python Judge 批改反馈" in grading["feedback"]
    assert "| 文件 |" not in grading["feedback"]
    assert "### 提交文件" in grading["feedback"]

    rows_after_save = client.get(f"/api/admin/assignments/{assignment_id}/submissions").get_json()["submissions"]
    saved_reviews = rows_after_save[0]["assignment_grade"]["llm_details"]["file_reviews"]
    assert saved_reviews[0]["score"] == 92
    assert saved_reviews[0]["comment"] == "Accepted after review."
    assert saved_reviews[0]["review_status"] == "confirmed"
    assert rows_after_save[0]["submission"]["grading_result"]["llm_details"]["file_reviews"][0]["comment"] == "Accepted after review."

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    assignments = client.get(f"/api/classes/{class_id}/assignments").get_json()["assignments"]
    assert assignments[0]["assignment_grade"]["final_score"] == 92
    assert assignments[0]["assignment_grade"]["feedback"]
    locked_response = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"print(3)\n"), "OS202601-06_py1.py")},
        content_type="multipart/form-data",
    )
    assert locked_response.status_code == 403


def test_teacher_can_return_submission_for_resubmit(client, monkeypatch):
    monkeypatch.setattr(judge, "_ensure_docker_image", lambda: None)
    monkeypatch.setattr(
        judge,
        "_run_case_in_docker",
        lambda _source_path, expected_output, _timeout, args="": {
            "status": JudgeRun.STATUS_ACCEPTED,
            "expected_output": expected_output,
            "stdout": expected_output,
            "stderr": "",
            "returncode": 0,
        },
    )
    class_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=_program_assignment_payload()).get_json()[
        "assignment"
    ]["id"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    submission_id = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"print(3)\n"), "OS202601-06_py1.py")},
        content_type="multipart/form-data",
    ).get_json()["submission"]["id"]
    assert _confirm_assignment(client, assignment_id).status_code == 200

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    client.patch(
        f"/api/admin/submissions/{submission_id}/grade",
        json={"final_score": 91, "feedback": "Published.", "teacher_comment": "ok", "status": "published"},
    )
    response = client.post(f"/api/admin/submissions/{submission_id}/return")
    assert response.status_code == 200

    rows = client.get(f"/api/admin/assignments/{assignment_id}/submissions").get_json()["submissions"]
    assert rows[0]["state"] == "missing"
    assert rows[0]["assignment_grade"] is None
    assert rows[0]["final_score"] is None

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    assignments = client.get(f"/api/classes/{class_id}/assignments").get_json()["assignments"]
    assert assignments[0]["submissions"] == []
    resubmit = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"print(3)\n"), "OS202601-06_py1.py")},
        content_type="multipart/form-data",
    )
    assert resubmit.status_code == 201


def test_published_assignment_update_requires_reset_and_reruns_auto_grading(client, monkeypatch):
    monkeypatch.setattr(judge, "_ensure_docker_image", lambda: None)
    monkeypatch.setattr(
        judge,
        "_run_case_in_docker",
        lambda _source_path, expected_output, _timeout, args="": {
            "status": JudgeRun.STATUS_ACCEPTED,
            "expected_output": expected_output,
            "stdout": expected_output,
            "stderr": "",
            "returncode": 0,
        },
    )
    class_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    payload = _program_assignment_payload()
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=payload).get_json()["assignment"]["id"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    submission_id = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"file": (BytesIO(b"print(3)\n"), "OS202601-06_py1.py")},
        content_type="multipart/form-data",
    ).get_json()["submission"]["id"]
    assert _confirm_assignment(client, assignment_id).status_code == 200

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    client.patch(
        f"/api/admin/submissions/{submission_id}/grade",
        json={"final_score": 88, "feedback": "Old feedback.", "teacher_comment": "old", "status": "published"},
    )

    changed_payload = {**payload, "title": "Updated Python Judge"}
    blocked = client.patch(f"/api/admin/assignments/{assignment_id}", json=changed_payload)
    assert blocked.status_code == 409
    assert blocked.get_json()["requires_reset_grading"] is True

    changed_payload["reset_grading"] = True
    response = client.patch(f"/api/admin/assignments/{assignment_id}", json=changed_payload)
    assert response.status_code == 200
    assert response.get_json()["reset_grading"] is True
    assert response.get_json()["rerun_count"] == 1

    rows = client.get(f"/api/admin/assignments/{assignment_id}/submissions").get_json()["submissions"]
    grade = rows[0]["assignment_grade"]
    assert grade["status"] == GradingResult.STATUS_AUTO_GRADED
    assert grade["final_score"] is None
    assert "Old feedback" not in (grade["feedback"] or "")
    assert rows[0]["teacher_state"] == "needs_review"

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    student_assignment = client.get(f"/api/classes/{class_id}/assignments").get_json()["assignments"][0]
    assert student_assignment["assignment_grade"]["final_score"] is None
    assert student_assignment["assignment_grade"]["feedback"] is None
    assert student_assignment["assignment_grade"]["llm_details"] == {}


def test_teacher_submission_overview_returns_program_case_details_for_bound_file(client, monkeypatch):
    def fake_run_case(_source_path, expected_output, _timeout, args=""):
        return {
            "status": JudgeRun.STATUS_WRONG_ANSWER,
            "expected_output": expected_output,
            "stdout": "5\n",
            "stderr": "",
            "diff": {"line": 1, "expected": "3", "actual": "5"},
            "returncode": 0,
        }

    monkeypatch.setattr(judge, "_ensure_docker_image", lambda: None)
    monkeypatch.setattr(judge, "_run_case_in_docker", fake_run_case)
    class_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    payload = {
        "title": "Mixed Assignment",
        "code": "mix1",
        "type": Assignment.TYPE_HOMEWORK,
        "max_score": 100,
        "status": Assignment.STATUS_PUBLISHED,
        "submission_requirements": [
            {
                "key": "code",
                "label": "程序文件",
                "allowed_extensions": [".py"],
                "max_size_mb": 1,
                "filename_template": "{student_id}_{assignment_code}_code{extension}",
                "required": True,
            },
            {
                "key": "report",
                "label": "实验报告",
                "allowed_extensions": [".md"],
                "max_size_mb": 1,
                "filename_template": "{student_id}_{assignment_code}_report{extension}",
                "required": True,
            },
        ],
        "program_evaluations": [
            {
                "name": "code judge",
                "input_file_key": "code",
                "cases": [
                    {
                        "name": "wrong answer case",
                        "args": "1 2",
                        "expected_output": "3\n",
                        "score_percent": 60,
                        "timeout_seconds": 2,
                    }
                ],
            }
        ],
        "ai_evaluations": [],
    }
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=payload).get_json()["assignment"]["id"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    code_response = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"item_key": "code", "file": (BytesIO(b"print(5)\n"), "OS202601-06_mix1_code.py")},
        content_type="multipart/form-data",
    )
    assert code_response.status_code == 201
    report_response = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"item_key": "report", "file": (BytesIO(b"# report\n"), "OS202601-06_mix1_report.md")},
        content_type="multipart/form-data",
    )
    assert report_response.status_code == 201
    assert _confirm_assignment(client, assignment_id).status_code == 200

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    row = client.get(f"/api/admin/assignments/{assignment_id}/submissions").get_json()["submissions"][0]
    submissions_by_key = {submission["submission_item_key"]: submission for submission in row["submissions"]}

    code_submission = submissions_by_key["code"]
    report_submission = submissions_by_key["report"]
    assert code_submission["latest_judge_run"]["status"] == JudgeRun.STATUS_WRONG_ANSWER
    case = code_submission["latest_judge_run"]["details"]["cases"][0]
    assert case["name"] == "wrong answer case"
    assert case["args"] == "1 2"
    assert case["expected_output"] == "3\n"
    assert case["stdout"] == "5\n"
    assert case["diff"] == {"line": 1, "expected": "3", "actual": "5"}
    assert report_submission["latest_judge_run"] is None


def test_confirmed_markdown_submission_runs_configured_llm_grading(client, monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _traceback):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"{\\"score\\":36,\\"summary\\":\\"Report is clear.\\",\\"criteria_results\\":[{\\"content\\":\\"clarity\\",\\"weight\\":100,\\"score\\":36,\\"comment\\":\\"clear\\"}]}"}}]}'

    captured = {}

    def fake_urlopen(request, timeout=60):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers.get("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(llm_grading, "urlopen", fake_urlopen)
    class_id = _create_class_with_student(client.application)
    with client.application.app_context():
        teacher = User.query.filter_by(username="teacher1").first()
        config = TeacherLLMConfig(
            teacher_id=teacher.id,
            provider="deepseek",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            encrypted_api_key="deepseek-test-key",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()

    _login(client, "teacher1")
    payload = {
        "title": "AI Report",
        "code": "ai1",
        "type": Assignment.TYPE_HOMEWORK,
        "max_score": 100,
        "status": Assignment.STATUS_PUBLISHED,
        "submission_requirements": [
            {
                "key": "report",
                "label": "实验报告",
                "allowed_extensions": [".md"],
                "max_size_mb": 1,
                "filename_template": "{student_id}_{assignment_code}_report{extension}",
                "required": True,
            }
        ],
        "program_evaluations": [],
        "ai_evaluations": [
            {
                "name": "report quality",
                "input_file_key": "report",
                "input": "Read report quality.",
                "score_percent": 40,
                "criteria_items": [{"content": "clarity", "weight": 100}],
            }
        ],
    }
    assignment_id = client.post(f"/api/admin/classes/{class_id}/assignments", json=payload).get_json()["assignment"]["id"]

    client.post("/api/auth/logout")
    _login(client, "OS202601-06")
    upload = client.post(
        f"/api/assignments/{assignment_id}/submissions",
        data={"item_key": "report", "file": (BytesIO(b"# Report\nGood work.\n"), "OS202601-06_ai1_report.md")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201
    confirm = _confirm_assignment(client, assignment_id)
    assert confirm.status_code == 200
    assert confirm.get_json()["queue_status"] == "inline"
    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert captured["authorization"] == "Bearer deepseek-test-key"

    client.post("/api/auth/logout")
    _login(client, "teacher1")
    row = client.get(f"/api/admin/assignments/{assignment_id}/submissions").get_json()["submissions"][0]
    grade = row["assignment_grade"]
    assert grade["llm_score"] == 36
    assert grade["auto_score"] == 36
    module = grade["llm_details"]["modules"][0]
    assert module["status"] == "completed"
    assert module["score"] == 36
    assert module["criteria_results"][0]["comment"] == "clear"


def test_teacher_llm_config_does_not_echo_api_key(client):
    _create_class_with_student(client.application)
    _login(client, "teacher1")

    response = client.put(
        "/api/admin/llm-config",
        json={
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "api_key": "secret-key",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    config = response.get_json()["config"]
    assert config["has_api_key"] is True
    assert "secret-key" not in str(config)
