from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import BinaryIO

from werkzeug.datastructures import FileStorage

from .accounts import StudentIdError, validate_student_id


SUPPORTED_EXTENSIONS = {".py", ".md", ".zip", ".jpg", ".png"}
TEXT_EXTENSIONS = {".py", ".md"}
SUBMISSION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
SIGNATURES = {
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".jpg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}


class FileValidationError(ValueError):
    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or [message]


@dataclass(frozen=True)
class FileValidationContext:
    student_id: str
    student_no: str
    student_name: str
    assignment_code: str


@dataclass(frozen=True)
class FileValidationResult:
    ok: bool
    filename: str
    expected_filename: str
    extension: str
    size: int
    checks: list[dict[str, object]]

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "filename": self.filename,
            "expected_filename": self.expected_filename,
            "extension": self.extension,
            "size": self.size,
            "checks": self.checks,
        }


def default_file_rules(assignment_type: str) -> dict[str, object]:
    return {
        "allowed_extensions": [".py", ".md", ".zip", ".jpg", ".png"],
        "max_size_mb": 5,
        "filename_template": "{student_id}_{assignment_code}{extension}",
    }


def normalize_file_rules(raw_rules: dict[str, object] | None, assignment_type: str) -> dict[str, object]:
    defaults = default_file_rules(assignment_type)
    rules = {**defaults, **(raw_rules or {})}
    allowed = rules.get("allowed_extensions")
    if isinstance(allowed, str):
        allowed_extensions = [item.strip() for item in allowed.split(",") if item.strip()]
    elif isinstance(allowed, list):
        allowed_extensions = [str(item).strip() for item in allowed if str(item).strip()]
    else:
        allowed_extensions = defaults["allowed_extensions"]

    normalized_extensions = []
    for extension in allowed_extensions:
        extension = extension.lower()
        if not extension.startswith("."):
            extension = f".{extension}"
        if extension not in SUPPORTED_EXTENSIONS:
            raise FileValidationError("Allowed file types are limited to .py, .md, .zip, .jpg and .png.")
        normalized_extensions.append(extension)
    if not normalized_extensions:
        raise FileValidationError("At least one allowed file extension is required.")

    try:
        max_size_mb = float(rules.get("max_size_mb") or defaults["max_size_mb"])
    except (TypeError, ValueError) as exc:
        raise FileValidationError("File size limit must be a number.") from exc
    if max_size_mb <= 0 or max_size_mb > 64:
        raise FileValidationError("File size limit must be between 0 and 64 MB.")

    filename_template = str(rules.get("filename_template") or defaults["filename_template"]).strip()
    if not filename_template:
        raise FileValidationError("Filename template cannot be empty.")

    return {
        "allowed_extensions": normalized_extensions,
        "max_size_mb": max_size_mb,
        "filename_template": filename_template,
    }


def normalize_submission_requirements(raw_requirements: object, assignment_type: str) -> list[dict[str, object]]:
    if raw_requirements in (None, ""):
        return [{"key": "main", "label": "提交文件", **default_file_rules(assignment_type), "required": True}]
    if not isinstance(raw_requirements, list):
        raise FileValidationError("Submission requirements must be a list.")
    if not raw_requirements:
        raise FileValidationError("At least one submission file item is required.")

    normalized: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for index, item in enumerate(raw_requirements, start=1):
        if not isinstance(item, dict):
            raise FileValidationError("Each submission file item must be an object.")
        key = str(item.get("key") or f"file{index}").strip()
        if not SUBMISSION_KEY_PATTERN.fullmatch(key):
            raise FileValidationError("Submission file item key must use 1-40 letters, digits, underscores or hyphens.")
        if key in seen_keys:
            raise FileValidationError(f"Duplicate submission file item key: {key}.")
        seen_keys.add(key)
        label = str(item.get("label") or item.get("name") or key).strip()
        if not label:
            raise FileValidationError("Submission file item label cannot be empty.")
        normalized.append(
            {
                "key": key,
                "label": label,
                **normalize_file_rules(item, assignment_type),
                "required": bool(item.get("required", True)),
            }
        )
    return normalized


def validate_submission_file(
    uploaded_file: FileStorage,
    rules: dict[str, object],
    context: FileValidationContext,
    *,
    check_content: bool = True,
    filename_only: bool = False,
) -> FileValidationResult:
    filename = Path(uploaded_file.filename or "").name
    if not filename:
        raise FileValidationError("Please choose a file before submitting.")

    try:
        validate_student_id(context.student_id)
    except StudentIdError as exc:
        raise FileValidationError(str(exc)) from exc

    extension = Path(filename).suffix.lower()
    allowed_extensions = [str(item).lower() for item in rules["allowed_extensions"]]
    expected_filename = render_filename_template(rules["filename_template"], context, extension)
    size = _stream_size(uploaded_file.stream)
    max_size = int(float(rules["max_size_mb"]) * 1024 * 1024)

    if filename_only:
        checks = [
            _check(filename == expected_filename, f"Filename should be {expected_filename}."),
        ]
    else:
        allowed_text = ", ".join(allowed_extensions)
        checks = [
            _check(extension in allowed_extensions, "File extension must be one of: " + allowed_text + "."),
            _check(size > 0, "Submitted file cannot be empty."),
            _check(size <= max_size, "File must not exceed " + str(rules["max_size_mb"]) + " MB."),
            _check(filename == expected_filename, f"Filename should be {expected_filename}."),
        ]
        if check_content:
            checks.extend(_basic_content_checks(uploaded_file.stream, extension))

    failed = [str(check["message"]) for check in checks if not check["ok"]]
    if failed:
        raise FileValidationError("Submission file did not pass validation.", failed)
    return FileValidationResult(
        ok=True,
        filename=filename,
        expected_filename=expected_filename,
        extension=extension,
        size=size,
        checks=checks,
    )


def validate_saved_submission_file(
    file_path: Path,
    original_filename: str,
    rules: dict[str, object],
    context: FileValidationContext,
) -> FileValidationResult:
    filename = Path(original_filename or "").name
    if not filename:
        raise FileValidationError("Submitted file is missing its original filename.")

    try:
        validate_student_id(context.student_id)
    except StudentIdError as exc:
        raise FileValidationError(str(exc)) from exc

    extension = Path(filename).suffix.lower()
    allowed_extensions = [str(item).lower() for item in rules["allowed_extensions"]]
    allowed_text = ", ".join(allowed_extensions)
    expected_filename = render_filename_template(rules["filename_template"], context, extension)
    size = file_path.stat().st_size if file_path.exists() else 0
    max_size = int(float(rules["max_size_mb"]) * 1024 * 1024)
    checks = [
        _check(extension in allowed_extensions, "File extension must be one of: " + allowed_text + "."),
        _check(size > 0, "Submitted file cannot be empty."),
        _check(size <= max_size, "File must not exceed " + str(rules["max_size_mb"]) + " MB."),
        _check(filename == expected_filename, f"Filename should be {expected_filename}."),
    ]
    if file_path.exists():
        with file_path.open("rb") as stream:
            checks.extend(_basic_content_checks(stream, extension))

    failed = [str(check["message"]) for check in checks if not check["ok"]]
    if failed:
        raise FileValidationError("Submission file did not pass validation.", failed)
    return FileValidationResult(
        ok=True,
        filename=filename,
        expected_filename=expected_filename,
        extension=extension,
        size=size,
        checks=checks,
    )


def render_filename_template(template: str, context: FileValidationContext, extension: str) -> str:
    values = {
        "student_id": context.student_id,
        "student_no": context.student_no,
        "assignment_code": context.assignment_code,
        "name": context.student_name,
        "extension": extension,
    }
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{key}}}", value)
    unknown_placeholders = re.findall(r"{[^{}]+}", rendered)
    if unknown_placeholders:
        raise FileValidationError(f"Unknown filename placeholder: {unknown_placeholders[0]}.")
    return rendered


def _stream_size(stream: BinaryIO) -> int:
    current = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(current)
    return size


def _basic_content_checks(stream: BinaryIO, extension: str) -> list[dict[str, object]]:
    current = stream.tell()
    stream.seek(0)
    sample = stream.read(4096)
    stream.seek(current)

    checks: list[dict[str, object]] = []
    if extension in TEXT_EXTENSIONS:
        checks.append(_check(b"\x00" not in sample, "Text submissions must not contain binary null bytes."))
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            checks.append(_check(False, "File content must be valid UTF-8 text."))
        else:
            checks.append(_check(True, "File content is valid UTF-8 text."))
    elif extension in SIGNATURES:
        signatures = SIGNATURES[extension]
        checks.append(_check(any(sample.startswith(signature) for signature in signatures), f"File content must look like a valid {extension} file."))
    return checks


def _check(ok: bool, message: str) -> dict[str, object]:
    return {"ok": ok, "message": message}
