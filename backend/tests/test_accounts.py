from __future__ import annotations

import pytest

from app.services.accounts import StudentIdError, short_student_no, validate_student_id


def test_validate_student_id_accepts_class_and_number():
    validate_student_id("OS2026-32")
    assert short_student_no("OS2026-32") == "32"


@pytest.mark.parametrize("student_id", ["", "OS2026", "OS2026-", "-32", "OS 2026-32", "A-B-C"])
def test_validate_student_id_rejects_invalid_values(student_id):
    with pytest.raises(StudentIdError):
        validate_student_id(student_id)

