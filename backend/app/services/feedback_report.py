"""Build the feedback.md layout from authoritative assignment/submission data."""
from datetime import UTC, datetime, timedelta, timezone
import re

from ..models import ClassRoster, Submission


def markdown_text(value: object) -> str:
    text = str(value if value is not None else "").replace("\r", " ").replace("\n", " ")
    return re.sub(r"([\\`*_{}\[\]()#+.!|<>~])", r"\\\1", text)


def markdown_filename(value: object) -> str:
    text = str(value or "-").replace("\r", " ").replace("\n", " ").replace("|", r"\|")
    fence = "`" * (max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    return f"{fence} {text} {fence}"


def report_date(value: datetime | None) -> str:
    if value is None:
        return "未设置"
    # SQLite stores UTC timestamps without timezone information.
    return value.replace(tzinfo=value.tzinfo or UTC).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def build_feedback_report(submission: Submission, file_reviews: list[dict], teacher_comment: str | None, final_score: float) -> str:
    assignment = submission.assignment
    roster = ClassRoster.query.filter_by(class_id=assignment.class_id, matched_user_id=submission.student_user_id).first()
    cell = markdown_text
    info = [
        roster.student_name if roster else submission.student.student_name,
        roster.student_number if roster else "-", assignment.code,
        report_date(submission.submitted_at), report_date(assignment.deadline), final_score,
    ]
    lines = [
        "|姓名|学号|作业代码|提交时间|截止时间|得分|",
        "|--|--|--|--|--|--|", "|" + "|".join(cell(value) for value in info) + "|",
        "", "---", "", "|文件|提交文件|权重|得分/满分|备注|", "|:-:|:-:|:-:|:-:|--|",
    ]
    for index, item in enumerate(file_reviews, start=1):
        lines.append(
            f"|{cell(item.get('submission_item_label') or f'文件 {index}')}"
            f"|{markdown_filename(item.get('filename'))}|{item.get('weight_percent') or 0}%"
            f"|{item.get('score')} / {item.get('max_score') or 0}|{cell(item.get('comment') or '-')}|"
        )
    course = assignment.course
    lines.extend([
        "", "---", "", teacher_comment or "", "", "---", "",
        f"*{cell(course.name)} - {cell(course.teacher.username if course.teacher else '-')} - {report_date(datetime.now(UTC)).split(' ')[0]}*",
    ])
    return "\n".join(lines)
