from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import re
from typing import BinaryIO

from openpyxl import load_workbook


REQUIRED_HEADERS = {"序号", "学号", "姓名", "班级"}


@dataclass(frozen=True)
class ImportedStudent:
    student_no: str
    student_number: str
    student_name: str
    source_class: str


@dataclass(frozen=True)
class ImportedRoster:
    course_name: str | None
    course_code: str | None
    semester: str | None
    students: list[ImportedStudent]


class RosterImportError(ValueError):
    pass


def parse_roster_workbook(file: BinaryIO) -> ImportedRoster:
    data = file.read()
    if not data:
        raise RosterImportError("学生名单文件不能为空。")

    workbook = load_workbook(BytesIO(data), data_only=True, read_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    header_row_index: int | None = None
    header_map: dict[str, int] = {}
    metadata_cells: list[str] = []

    for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
        normalized = [_cell_to_text(value) for value in row]
        metadata_cells.extend(value for value in normalized if value)
        found_headers = {value for value in normalized if value in REQUIRED_HEADERS}
        if REQUIRED_HEADERS.issubset(found_headers):
            header_row_index = row_index
            header_map = {value: index for index, value in enumerate(normalized) if value in REQUIRED_HEADERS}
            break

    if header_row_index is None:
        raise RosterImportError("Excel 中未找到包含 学号、姓名、班级 的表头行。")

    students: list[ImportedStudent] = []
    seen_student_nos: set[str] = set()
    for row in sheet.iter_rows(min_row=header_row_index + 1, values_only=True):
        student_no = _cell_to_text(row[header_map["序号"]] if header_map["序号"] < len(row) else None)
        student_number = _cell_to_text(row[header_map["学号"]] if header_map["学号"] < len(row) else None)
        student_name = _cell_to_text(row[header_map["姓名"]] if header_map["姓名"] < len(row) else None)
        source_class = _cell_to_text(row[header_map["班级"]] if header_map["班级"] < len(row) else None)

        if not any([student_no, student_number, student_name, source_class]):
            continue
        if not _is_numeric_student_no(student_no):
            continue
        if not all([student_number, student_name, source_class]):
            raise RosterImportError("Excel 存在序号、学号、姓名或班级为空的学生行。")

        student = ImportedStudent(
            student_no=_normalize_student_no(student_no),
            student_number=student_number,
            student_name=student_name,
            source_class=source_class,
        )
        if student.student_no in seen_student_nos:
            raise RosterImportError(f"Excel 中存在重复序号 No.：{student.student_no}。")
        seen_student_nos.add(student.student_no)
        students.append(student)

    if not students:
        raise RosterImportError("Excel 中未读取到学生名单。")
    return ImportedRoster(
        course_name=_extract_course_name(metadata_cells),
        course_code=_extract_course_code(metadata_cells),
        semester=_extract_semester(metadata_cells),
        students=students,
    )


def _cell_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value)).strip()
    return str(value).strip()


def _is_numeric_student_no(value: str) -> bool:
    return value.isdigit()


def _normalize_student_no(value: str) -> str:
    return value.zfill(2)


def _extract_course_name(cells: list[str]) -> str | None:
    text = "\n".join(cells)
    match = re.search(r"课程名称[:：]\s*([^,，\n]+)", text)
    return match.group(1).strip() if match else None


def _extract_course_code(cells: list[str]) -> str | None:
    text = "\n".join(cells)
    match = re.search(r"课程号[:：]\s*([^,，\n]+)", text)
    return match.group(1).strip() if match else None


def _extract_semester(cells: list[str]) -> str | None:
    text = "\n".join(cells)
    match = re.search(r"学年[:：]\s*([0-9]{4}-[0-9]{4})\s*学期[:：]\s*([0-9]+)", text)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"
