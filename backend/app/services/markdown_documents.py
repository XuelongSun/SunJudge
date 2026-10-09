from __future__ import annotations

from datetime import UTC, timedelta
from io import BytesIO
from pathlib import Path
import re
from uuid import uuid4
import warnings

from flask import current_app
from markdown_it import MarkdownIt
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from ..extensions import db
from ..models import Assignment, AssignmentGrade, ClassRoster, CourseClass, CourseMember, GradingResult, MarkdownAsset, MarkdownDocument, Submission, User, utc_now
from .accounts import short_student_no
from .file_validation import FileValidationContext, FileValidationError, render_filename_template, validate_submission_file


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_IMAGE_BYTES = 50 * 1024 * 1024
ASSET_URL = re.compile(r"^/api/assets/([0-9a-f]{32})/content$")


def member_of(class_id: int, user_id: int) -> bool:
    return CourseMember.query.filter_by(class_id=class_id, user_id=user_id, role=User.ROLE_STUDENT).first() is not None


def require_student_editable(assignment: Assignment, user: User):
    if user.role != User.ROLE_STUDENT or assignment.status != Assignment.STATUS_PUBLISHED or not member_of(assignment.class_id, user.id):
        raise PermissionError("无权编辑此作业。")
    if not ClassRoster.query.filter_by(class_id=assignment.class_id, matched_user_id=user.id).first():
        raise PermissionError("学生未绑定当前班级名单。")
    deadline = assignment.deadline
    if deadline and utc_now() > deadline.replace(tzinfo=deadline.tzinfo or UTC) and not assignment.allow_late:
        raise PermissionError("作业已截止，不能编辑或提交。")
    if AssignmentGrade.query.filter_by(assignment_id=assignment.id, student_user_id=user.id, status=GradingResult.STATUS_PUBLISHED).first():
        raise PermissionError("反馈已发布，不能编辑或重新提交。")


def require_document_owner(document: MarkdownDocument, user: User, *, write=False):
    if document.owner_id != user.id:
        raise PermissionError("无权访问此草稿。")
    course_class = db.session.get(CourseClass, document.class_id)
    if document.kind == "description":
        if user.role != User.ROLE_TEACHER or user.teacher_status != User.TEACHER_STATUS_APPROVED or not course_class or course_class.course.teacher_id != user.id:
            raise PermissionError("无权编辑此作业说明。")
    else:
        if not document.assignment or not member_of(document.class_id, user.id):
            raise PermissionError("无权访问此作业。")
        if write:
            require_student_editable(document.assignment, user)


def image_sources(content: str) -> list[str]:
    sources = []
    def visit(tokens):
        for token in tokens:
            if token.type == "image":
                sources.append(token.attrGet("src") or "")
            if token.children:
                visit(token.children)
    visit(MarkdownIt("commonmark", {"html": False}).parse(content))
    return sources


def validate_document_images(document: MarkdownDocument, content: str) -> list[str]:
    ids = []
    for source in image_sources(content):
        match = ASSET_URL.fullmatch(source)
        asset = db.session.get(MarkdownAsset, match[1]) if match else None
        if not asset or asset.document_id != document.id or not asset_path(asset).is_file():
            raise FileValidationError("图片未上传、已丢失或不属于当前文档，请使用“插入图片”重新上传。")
        ids.append(asset.id)
    return sorted(set(ids))


def asset_path(asset: MarkdownAsset) -> Path:
    root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    target = (root / asset.file_path).resolve()
    if not target.is_relative_to(root):
        raise FileValidationError("图片存储路径无效。")
    return target


def create_image(document: MarkdownDocument, uploaded: FileStorage) -> MarkdownAsset:
    if Path(uploaded.filename or "").suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise FileValidationError("仅支持 PNG、JPEG 图片。")
    raw = uploaded.stream.read(MAX_IMAGE_BYTES + 1)
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise FileValidationError("单张图片必须非空且不超过 5 MB。")
    existing = document.assets
    if len(existing) >= 50 or sum(asset.file_size for asset in existing) + len(raw) > MAX_DOCUMENT_IMAGE_BYTES:
        raise FileValidationError("每份文档最多 50 张图片，总图片大小不超过 50 MB。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format not in {"PNG", "JPEG"} or image.width * image.height > 10_000_000:
                    raise FileValidationError("仅支持 PNG/JPEG，图片像素总数不能超过 1000 万。")
                image.load()
                fmt = image.format
                # Copy pixels into a fresh image: do not preserve EXIF/ICC/text metadata.
                mode = "RGBA" if fmt == "PNG" and "A" in image.getbands() else "RGB"
                pixels = image.convert(mode)
                clean = Image.new(mode, pixels.size)
                clean.paste(pixels)
                output = BytesIO()
                clean.save(output, format=fmt)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise FileValidationError("图片损坏或格式无效。") from exc
    encoded = output.getvalue()
    if len(encoded) > MAX_IMAGE_BYTES or sum(asset.file_size for asset in existing) + len(encoded) > MAX_DOCUMENT_IMAGE_BYTES:
        raise FileValidationError("图片解码后超过大小限制。")
    key = uuid4().hex
    extension = ".png" if fmt == "PNG" else ".jpg"
    asset = MarkdownAsset(id=key, document_id=document.id, original_filename=Path(uploaded.filename).name[:255],
                          file_path=f"markdown-assets/{document.id}/{key}{extension}",
                          mime_type="image/png" if fmt == "PNG" else "image/jpeg", file_size=len(encoded))
    target = asset_path(asset)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(encoded)
    except OSError:
        target.unlink(missing_ok=True)
        raise
    db.session.add(asset)
    return asset


def can_read_asset(asset: MarkdownAsset, user: User) -> bool:
    document = asset.document
    try:
        require_document_owner(document, user)
        return True
    except PermissionError:
        pass
    assignment = document.assignment
    if not assignment:
        return False
    if document.kind == "description":
        # Unused or unsaved draft images are private, even in published assignments.
        if asset.id not in {match[1] for source in image_sources(assignment.description or "") if (match := ASSET_URL.fullmatch(source))}:
            return False
        return assignment.status == Assignment.STATUS_PUBLISHED and user.role == User.ROLE_STUDENT and member_of(assignment.class_id, user.id)
    if user.role != User.ROLE_TEACHER or assignment.course.teacher_id != user.id:
        return False
    return any(
        asset.id in (submission.validation_result_json or {}).get("markdown_asset_ids", [])
        for submission in Submission.query.filter_by(assignment_id=assignment.id, student_user_id=document.owner_id)
        .filter(Submission.status.in_([Submission.STATUS_SUBMITTED, Submission.STATUS_LATE])).all()
    )


def bind_description_document(assignment: Assignment, payload: dict, user: User):
    document_id = payload.get("markdown_document_id")
    if document_id is None:
        return
    document = db.session.get(MarkdownDocument, document_id) if isinstance(document_id, int) else None
    if not document:
        raise FileValidationError("作业说明草稿不存在。")
    require_document_owner(document, user, write=True)
    if document.kind != "description" or document.class_id != assignment.class_id or document.assignment_id not in {None, assignment.id}:
        raise FileValidationError("作业说明草稿归属不匹配。")
    validate_document_images(document, assignment.description or "")
    document.assignment = assignment


def prepare_student_drafts(assignment: Assignment, user: User, requirements: dict, created_paths: list[Path]):
    """Create immutable .md files inside the confirmation transaction."""
    documents = MarkdownDocument.query.filter_by(assignment_id=assignment.id, owner_id=user.id, kind="submission").with_for_update().all()
    roster = ClassRoster.query.filter_by(class_id=assignment.class_id, matched_user_id=user.id).first()
    context = FileValidationContext(roster.student_id, roster.student_no or short_student_no(roster.student_id), roster.student_name, assignment.code, assignment.course_class.alias)
    for document in documents:
        if document.revision <= document.submitted_revision:
            continue
        requirement = requirements.get(document.item_key)
        if not requirement or ".md" not in requirement["allowed_extensions"]:
            # Keep retired drafts for history, but do not submit them as current work.
            continue
        if not document.content.strip():
            raise FileValidationError("Markdown 草稿不能为空，请填写正文后再确认提交。")
        asset_ids = validate_document_images(document, document.content)
        filename = render_filename_template(requirement["filename_template"], context, ".md")
        uploaded = FileStorage(stream=BytesIO(document.content.encode("utf-8")), filename=filename)
        validation = validate_submission_file(uploaded, requirement, context)
        relative = Path(str(assignment.course_id)) / str(assignment.class_id) / str(assignment.id) / f"{uuid4().hex}.md"
        target = Path(current_app.config["UPLOAD_FOLDER"]) / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        created_paths.append(target)
        uploaded.save(target)
        submission = Submission(assignment_id=assignment.id, student_user_id=user.id, original_filename=filename,
                                submission_item_key=document.item_key, submission_item_label=requirement["label"],
                                file_path=str(relative), file_size=validation.size, status=Submission.STATUS_UPLOADED,
                                validation_result_json={**validation.to_dict(), "markdown_asset_ids": asset_ids,
                                                        "markdown_document_id": document.id, "markdown_revision": document.revision})
        db.session.add(submission)
        document.submitted_revision = document.revision
    db.session.flush()


def unused_image_assets(days: int = 7) -> list[MarkdownAsset]:
    """Keep every draft, saved description and historical submission reference."""
    used = set()
    contents = [document.content for document in MarkdownDocument.query.all()]
    contents.extend(assignment.description or "" for assignment in Assignment.query.all())
    for content in contents:
        used.update(match[1] for source in image_sources(content) if (match := ASSET_URL.fullmatch(source)))
    for submission in Submission.query.all():
        used.update((submission.validation_result_json or {}).get("markdown_asset_ids", []))
    cutoff = utc_now() - timedelta(days=max(1, days))
    return [asset for asset in MarkdownAsset.query.filter(MarkdownAsset.created_at < cutoff).all() if asset.id not in used]
