from datetime import timedelta

import pytest

from app.extensions import db
from app.models import Assignment, AssignmentGrade, CourseClass, GradingResult, Submission, utc_now
from test_assignments import _create_class_with_student, _login


@pytest.mark.parametrize("late,expected_pending,expected_expired,expected_average", [(False, 1, 2, 30), (True, 3, 0, 90)])
def test_student_summary_expiration_scores_and_confirmed_history(client, late, expected_pending, expected_expired, expected_average):
    class_id, _, student_id, _ = _create_class_with_student(client.application)
    with client.application.app_context():
        course_id = db.session.get(CourseClass, class_id).course_id
        now = utc_now()
        assignments = []
        for index in range(6):
            assignment = Assignment(course_id=course_id, class_id=class_id, title=f"Test{index}", code=f"h{index}",
                                    status="published" if index < 5 else "draft", max_score=200 if index == 2 else 100,
                                    published_at=now - timedelta(days=5), deadline=now + timedelta(days=1) if index == 3 else now - timedelta(days=1),
                                    allow_late=late, submission_requirements_json=[{"key": "report", "required": True}])
            db.session.add(assignment)
            assignments.append(assignment)
        db.session.flush()
        # Two expired unconfirmed assignments; one published score; one pending;
        # one confirmed before deadline then uploaded a new draft, still completed.
        for index, status in [(1, "uploaded"), (2, "submitted"), (4, "submitted"), (4, "uploaded")]:
            db.session.add(Submission(assignment_id=assignments[index].id, student_user_id=student_id,
                                      submission_item_key="report", original_filename="report.md", file_path="fixture.md", file_size=1,
                                      status=status, submitted_at=now - timedelta(days=2) if status == "submitted" else now))
        db.session.add(AssignmentGrade(assignment_id=assignments[2].id, student_user_id=student_id, status=GradingResult.STATUS_PUBLISHED, final_score=90))
        db.session.add(AssignmentGrade(assignment_id=assignments[4].id, student_user_id=student_id, status=GradingResult.STATUS_REVIEWED, final_score=70))
        db.session.commit()
    assert _login(client, "OS202601-06").status_code == 200
    summary = client.get('/api/classes/my').json["classes"][0]
    assert summary["published_assignment_count"] == 5
    assert summary["completed_assignment_count"] == 2
    assert summary["pending_assignment_count"] == expected_pending
    assert summary["expired_assignment_count"] == expected_expired
    assert summary["published_grade_count"] == 1
    assert summary["average_score"] == expected_average
    assert summary["average_max_score"] == (133.33 if not late else 200)
    assert summary["score_rate"] == (0.225 if not late else 0.45)
    with client.application.app_context():
        assert AssignmentGrade.query.count() == 2  # Read-only: no persisted expired zero.
