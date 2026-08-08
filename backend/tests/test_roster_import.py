from __future__ import annotations

from pathlib import Path

from app.services.roster_import import parse_roster_workbook


def test_parse_students_xlsx_fixture():
    fixture = Path(__file__).resolve().parents[2] / "students.xlsx"
    with fixture.open("rb") as file:
        roster = parse_roster_workbook(file)

    assert roster.course_name == "计算机组成原理"
    assert roster.course_code == "211530001"
    assert roster.semester == "2025-2026-2"
    assert len(roster.students) == 21
    assert roster.students[0].student_no == "01"
    assert roster.students[0].student_number == "32319500084"
    assert roster.students[0].student_name == "student_name_1"
    assert roster.students[0].source_class == "物联（创）231"
