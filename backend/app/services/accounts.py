from __future__ import annotations


class StudentIdError(ValueError):
    pass


def validate_student_id(student_id: str) -> None:
    if not student_id:
        raise StudentIdError("学生编号不能为空，格式应为 班级名-编号，例如 OS2026-32。")
    if student_id.count("-") != 1:
        raise StudentIdError("学生编号必须且只能包含一个连字符，格式应为 班级名-编号。")
    class_name, number = student_id.split("-", 1)
    if not class_name or not number:
        raise StudentIdError("学生编号的班级名和编号都不能为空。")
    if any(char.isspace() for char in student_id):
        raise StudentIdError("学生编号不能包含空白字符。")


def short_student_no(student_id: str) -> str:
    validate_student_id(student_id)
    return student_id.rsplit("-", 1)[1]

