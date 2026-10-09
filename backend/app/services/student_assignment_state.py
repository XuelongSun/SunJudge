"""Read-only deadline presentation; never overwrite a teacher's grade."""
from datetime import UTC, datetime

from ..models import AssignmentGrade, GradingResult, Submission


def student_deadline_state(assignment, student_user_id: int, grade: AssignmentGrade | None, requirements: list, now=None) -> dict:
    required = {
        str(item["key"]) for item in requirements
        if item.get("required", True)
    }
    confirmed = Submission.query.filter_by(assignment_id=assignment.id, student_user_id=student_user_id).filter(
        Submission.status.in_({Submission.STATUS_SUBMITTED, Submission.STATUS_LATE})
    ).all()
    # A newer upload/draft must not erase an already confirmed submission.
    completed = required.issubset({item.submission_item_key for item in confirmed}) if required else bool(confirmed)
    deadline = assignment.deadline
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=UTC)
    has_grade = grade is not None and (grade.final_score is not None or grade.status == GradingResult.STATUS_PUBLISHED)
    expired = bool(deadline and current_time > deadline and not assignment.allow_late and not completed and not has_grade)
    score = (grade.final_score or 0) if grade and grade.status == GradingResult.STATUS_PUBLISHED else (0 if expired else None)
    return {"is_expired": expired, "display_score": score}
