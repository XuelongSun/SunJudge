"""Class summary uses confirmed submissions and visible grades, including expired zeros."""
from ..models import Assignment, AssignmentGrade, GradingResult, Submission, table_has_columns
from .student_assignment_state import student_deadline_state


def student_class_summary(assignment_ids: list[int], student_id: int) -> dict:
    assignments = Assignment.query.filter(Assignment.id.in_(assignment_ids)).all() if assignment_ids else []
    completed = set()
    expired = set()
    scores = []
    maxima = []
    published_count = 0
    grades = {}
    if assignments and table_has_columns("assignment_grades", {"assignment_id", "student_user_id", "status", "final_score"}):
        grades = {grade.assignment_id: grade for grade in AssignmentGrade.query.filter(
            AssignmentGrade.assignment_id.in_(assignment_ids), AssignmentGrade.student_user_id == student_id).all()}
    has_submissions = table_has_columns("submissions", {"assignment_id", "student_user_id", "submission_item_key", "status"})
    confirmed = {}
    if assignments and has_submissions:
        for assignment_id, key in Submission.query.with_entities(Submission.assignment_id, Submission.submission_item_key).filter(
                Submission.assignment_id.in_(assignment_ids), Submission.student_user_id == student_id,
                Submission.status.in_({Submission.STATUS_SUBMITTED, Submission.STATUS_LATE})).distinct().all():
            confirmed.setdefault(assignment_id, set()).add(key)
    for assignment in assignments:
        requirements = assignment.to_dict()["submission_requirements"]
        required = {item["key"] for item in requirements if item.get("required", True)}
        submitted_keys = confirmed.get(assignment.id, set())
        is_complete = required.issubset(submitted_keys) if required else bool(submitted_keys)
        if is_complete:
            completed.add(assignment.id)
        grade = grades.get(assignment.id)
        state = student_deadline_state(assignment, student_id, grade, requirements) if has_submissions else {"is_expired": False, "display_score": None}
        if state["is_expired"]:
            expired.add(assignment.id)
        if grade and grade.status == GradingResult.STATUS_PUBLISHED:
            published_count += 1
        if state["display_score"] is not None:
            scores.append(float(state["display_score"]))
            maxima.append(float(assignment.max_score))
    return {
        "pending_assignment_count": len(set(assignment_ids) - completed - expired),
        "published_assignment_count": len(assignments), "completed_assignment_count": len(completed),
        "expired_assignment_count": len(expired), "published_grade_count": published_count,
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
        "average_max_score": round(sum(maxima) / len(maxima), 2) if maxima else None,
        "score_rate": sum(scores) / sum(maxima) if sum(maxima) > 0 else None,
    }
