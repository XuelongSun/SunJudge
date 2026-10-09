from __future__ import annotations

from ..extensions import db
from ..models import Assignment, AssignmentGrade, GradingResult, JudgeRun, Submission
from .judge import run_python_judge
from .llm_grading import grade_markdown_with_llm


CONFIRMED_SUBMISSION_STATUSES = {Submission.STATUS_SUBMITTED, Submission.STATUS_LATE}


def run_auto_grading_for_submission(submission: Submission) -> AssignmentGrade:
    return run_auto_grading_for_student(submission.assignment, submission.student_user_id)


def run_auto_grading_for_student(assignment: Assignment, student_user_id: int) -> AssignmentGrade:
    grade = AssignmentGrade.query.filter_by(assignment_id=assignment.id, student_user_id=student_user_id).first()
    if not grade:
        grade = AssignmentGrade(assignment_id=assignment.id, student_user_id=student_user_id)

    program_score = 0.0
    ai_score = 0.0
    feedback_parts: list[str] = []
    llm_details: dict[str, object] = {"modules": []}
    evaluated_keys: set[str] = set()

    required_keys = {item["key"] for item in (assignment.submission_requirements_json or assignment.to_dict()["submission_requirements"]) if item.get("required", True)}
    program_modules = {key: value for key, value in _group_modules_by_input_file(assignment.program_evaluations_json or [], default_key="main").items() if key in required_keys}
    for item_key, modules in program_modules.items():
        evaluated_keys.add(item_key)
        submission = _latest_confirmed_submission_for(assignment, student_user_id, item_key)
        if not submission:
            feedback_parts.append(f"Program judge skipped for {item_key}: confirmed file has not been submitted.")
            continue
        judge_run = run_python_judge(submission, _program_cases_from_modules(modules))
        db.session.add(judge_run)
        program_score += judge_run.score
        feedback_parts.append(_judge_feedback(judge_run))

    ai_modules = {key: value for key, value in _group_modules_by_input_file(assignment.ai_evaluations_json or [], default_key="main").items() if key in required_keys}
    for item_key, modules in ai_modules.items():
        evaluated_keys.add(item_key)
        submission = _latest_confirmed_submission_for(assignment, student_user_id, item_key)
        if not submission:
            llm_details["modules"].append({"input_file_key": item_key, "status": "missing_submission", "message": "Confirmed file has not been submitted."})
            feedback_parts.append(f"AI grading skipped for {item_key}: confirmed file has not been submitted.")
            continue
        if not submission.original_filename.lower().endswith(".md"):
            llm_details["modules"].append({"input_file_key": item_key, "status": "skipped", "message": "AI grading expects a .md file."})
            feedback_parts.append(f"AI grading skipped for {item_key}: input file is not markdown.")
            continue
        ai_report = grade_markdown_with_llm(assignment, submission.student, submission.original_filename, submission.file_path, modules)
        llm_details["modules"].extend(ai_report.get("modules") if isinstance(ai_report.get("modules"), list) else [])
        ai_score += float(ai_report.get("score") or 0)
        feedback_parts.append(f"AI grading for {item_key}: {ai_report.get('message') or ai_report.get('status') or 'completed'}. Score {float(ai_report.get('score') or 0):.2f}.")

    manual_keys = [
        str(item.get("key"))
        for item in assignment.submission_requirements_json or []
        if item.get("required", True) and str(item.get("key")) and str(item.get("key")) not in evaluated_keys
    ]
    if manual_keys:
        feedback_parts.append(f"Manual review required for: {', '.join(manual_keys)}.")

    auto_score = round(program_score + ai_score, 2)
    grade.auto_score = auto_score if feedback_parts else None
    grade.llm_score = round(ai_score, 2) if ai_modules else None
    grade.feedback = "\n".join(part for part in feedback_parts if part)
    grade.status = GradingResult.STATUS_PENDING if manual_keys else (GradingResult.STATUS_AUTO_GRADED if feedback_parts else GradingResult.STATUS_PENDING)
    if manual_keys:
        llm_details["manual_file_keys"] = manual_keys
    grade.llm_details_json = llm_details if (llm_details.get("modules") or manual_keys) else None
    db.session.add(grade)
    _sync_latest_submission_grading_result(assignment, student_user_id, grade)
    return grade


def _latest_confirmed_submission_for(assignment: Assignment, student_user_id: int, submission_item_key: str | None = None) -> Submission | None:
    query = Submission.query.filter(
        Submission.assignment_id == assignment.id,
        Submission.student_user_id == student_user_id,
        Submission.status.in_(CONFIRMED_SUBMISSION_STATUSES),
    )
    if submission_item_key is not None:
        query = query.filter(Submission.submission_item_key == submission_item_key)
    return query.order_by(Submission.submitted_at.desc(), Submission.id.desc()).first()


def _group_modules_by_input_file(modules: list[dict[str, object]], default_key: str) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for module in modules:
        item_key = str(module.get("input_file_key") or module.get("file_key") or default_key).strip() or default_key
        grouped.setdefault(item_key, []).append(module)
    return grouped


def _program_cases_from_modules(modules: list[dict[str, object]]) -> list[dict[str, object]]:
    cases: list[dict[str, object]] = []
    for module in modules:
        module_cases = module.get("cases")
        if isinstance(module_cases, list) and module_cases:
            for index, case in enumerate(module_cases, start=1):
                if isinstance(case, dict):
                    cases.append({"name": f"{module.get('name') or 'Program'} / {case.get('name') or f'case {index}'}", **case})
        else:
            cases.append(module)
    return cases


def _sync_latest_submission_grading_result(assignment: Assignment, student_user_id: int, grade: AssignmentGrade) -> None:
    latest = _latest_confirmed_submission_for(assignment, student_user_id)
    if not latest:
        return
    result = latest.grading_result or GradingResult(submission_id=latest.id)
    result.auto_score = grade.auto_score
    result.llm_score = grade.llm_score
    result.final_score = grade.final_score
    result.feedback = grade.feedback
    result.teacher_comment = grade.teacher_comment
    result.reviewed_by = grade.reviewed_by
    result.status = grade.status
    result.llm_details_json = grade.llm_details_json
    db.session.add(result)


def _judge_feedback(judge_run: JudgeRun) -> str:
    details = judge_run.details_json or {}
    if judge_run.status == JudgeRun.STATUS_SKIPPED:
        return str(details.get("message") or "Program judge skipped.")
    cases = details.get("cases") if isinstance(details.get("cases"), list) else []
    accepted = len([case for case in cases if case.get("status") == JudgeRun.STATUS_ACCEPTED])
    return f"Program judge: {accepted}/{len(cases)} cases accepted, score {judge_run.score}."
