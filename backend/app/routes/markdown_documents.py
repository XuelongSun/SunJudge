from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import Assignment, CourseClass, MarkdownAsset, MarkdownDocument, User, utc_now
from ..services.file_validation import FileValidationError
from ..services.markdown_documents import asset_path, can_read_asset, create_image, require_document_owner, require_student_editable


markdown_bp = Blueprint("markdown", __name__)


def owned_document(document_id, *, write=False):
    document = db.session.get(MarkdownDocument, document_id)
    if not document:
        abort(404)
    try:
        require_document_owner(document, current_user, write=write)
    except PermissionError as exc:
        abort(403, description=str(exc))
    return document


@markdown_bp.post("/markdown-documents")
@login_required
def open_document():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(message="请求必须是 JSON 对象。"), 400
    class_id, assignment_id = payload.get("class_id"), payload.get("assignment_id")
    if type(class_id) is not int or class_id <= 0 or (assignment_id is not None and (type(assignment_id) is not int or assignment_id <= 0)):
        return jsonify(message="班级和作业 ID 无效。"), 400
    course_class = db.session.get(CourseClass, class_id)
    assignment = db.session.get(Assignment, assignment_id) if assignment_id else None
    if not course_class or (assignment_id and (not assignment or assignment.class_id != class_id)):
        abort(404)
    kind = payload.get("kind")
    item_key = str(payload.get("item_key") or "")
    if kind == "description":
        if current_user.role != User.ROLE_TEACHER or current_user.teacher_status != User.TEACHER_STATUS_APPROVED or course_class.course.teacher_id != current_user.id:
            abort(403)
        item_key = ""
    elif kind == "submission" and assignment:
        try:
            require_student_editable(assignment, current_user)
        except PermissionError as exc:
            return jsonify(message=str(exc)), 403
        requirement = next((item for item in assignment.submission_requirements_json or [] if item["key"] == item_key), None)
        if not requirement or ".md" not in requirement["allowed_extensions"]:
            return jsonify(message="此提交项不支持 Markdown 在线编辑。"), 400
    else:
        return jsonify(message="文档类型无效。"), 400
    document = MarkdownDocument.query.filter_by(assignment_id=assignment_id, owner_id=current_user.id, kind=kind, item_key=item_key).first() if assignment_id else None
    if kind == "description" and not assignment_id:
        document = MarkdownDocument.query.filter_by(assignment_id=None, class_id=class_id, owner_id=current_user.id,
                                                    kind="description", item_key="").order_by(MarkdownDocument.updated_at.desc(), MarkdownDocument.id.desc()).first()
    if not document:
        content = (assignment.description or "") if kind == "description" and assignment else ""
        if kind == "submission":
            latest = assignment.latest_submission_for(current_user.id, item_key)
            if latest and latest.original_filename.lower().endswith(".md"):
                root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
                target = (root / latest.file_path).resolve()
                if target.is_relative_to(root) and target.is_file():
                    content = target.read_text(encoding="utf-8", errors="replace")
        document = MarkdownDocument(owner_id=current_user.id, class_id=class_id, assignment_id=assignment_id,
                                    kind=kind, item_key=item_key, content=content)
        db.session.add(document)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            document = MarkdownDocument.query.filter_by(assignment_id=assignment_id, owner_id=current_user.id, kind=kind, item_key=item_key).first()
            if not document:
                raise
    return jsonify(document=document.to_dict())


@markdown_bp.get("/markdown-documents/<int:document_id>")
@login_required
def get_document(document_id):
    return jsonify(document=owned_document(document_id).to_dict())


@markdown_bp.put("/markdown-documents/<int:document_id>")
@login_required
def save_document(document_id):
    document = owned_document(document_id, write=True)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(message="请求必须是 JSON 对象。"), 400
    content, revision = payload.get("content"), payload.get("revision")
    if not isinstance(content, str) or type(revision) is not int or revision < 0:
        return jsonify(message="正文或草稿版本无效。"), 400
    max_bytes = 1024 * 1024
    if document.kind == "submission":
        requirement = next((item for item in document.assignment.submission_requirements_json or [] if item["key"] == document.item_key), None)
        if not requirement or ".md" not in requirement["allowed_extensions"]:
            return jsonify(message="提交项已变更。"), 400
        max_bytes = min(max_bytes, int(requirement["max_size_mb"] * 1024 * 1024))
    if len(content.encode("utf-8")) > max_bytes or "\x00" in content:
        return jsonify(message="Markdown 超过大小限制或包含无效字符。"), 400
    result = db.session.execute(update(MarkdownDocument).where(
        MarkdownDocument.id == document.id, MarkdownDocument.revision == revision
    ).values(content=content, revision=revision + 1, updated_at=utc_now()))
    if result.rowcount != 1:
        db.session.rollback()
        return jsonify(message="草稿已在其他窗口更新，请保留当前内容并重新打开编辑器。"), 409
    db.session.commit()
    return jsonify(document=db.session.get(MarkdownDocument, document_id).to_dict())


@markdown_bp.post("/markdown-documents/<int:document_id>/images")
@login_required
def upload_image(document_id):
    document = owned_document(document_id, write=True)
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify(message="请选择图片。"), 400
    # Serialize quota checks for the same document, including SQLite writers.
    db.session.execute(update(MarkdownDocument).where(MarkdownDocument.id == document.id).values(updated_at=utc_now()))
    db.session.expire(document, ["assets"])
    try:
        asset = create_image(document, uploaded)
    except FileValidationError as exc:
        db.session.rollback()
        return jsonify(message=str(exc)), 400
    try:
        db.session.commit()
    except Exception:
        asset_path(asset).unlink(missing_ok=True)
        db.session.rollback()
        raise
    return jsonify(asset={"id": asset.id, "url": f"/api/assets/{asset.id}/content", "filename": asset.original_filename}), 201


@markdown_bp.get("/assets/<string:asset_id>/content")
@login_required
def read_image(asset_id):
    asset = db.session.get(MarkdownAsset, asset_id)
    if not asset or not can_read_asset(asset, current_user):
        abort(404)
    target = asset_path(asset)
    if not target.is_file():
        abort(404)
    response = send_file(target, mimetype=asset.mime_type, max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
