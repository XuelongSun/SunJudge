from datetime import timedelta
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import Assignment, AssignmentGrade, ClassRoster, CourseMember, GradingResult, MarkdownAsset, MarkdownDocument, Submission, utc_now
from app.services.markdown_documents import image_sources
from app.services.file_validation import FileValidationContext, FileValidationError, validate_submission_file
from test_assignments import _create_class_with_student, _login


@pytest.fixture()
def context(client, tmp_path):
    client.application.config.update(UPLOAD_FOLDER=str(tmp_path), GRADING_QUEUE_ENABLED=False)
    class_id, teacher_id, student_id, outsider_id = _create_class_with_student(client.application)
    _login(client, "teacher1")
    payload = {
        "title": "Report", "code": "r1", "type": "homework", "status": "published", "max_score": 100,
        "file_rules": {"allowed_extensions": [".md"], "max_size_mb": 1, "filename_template": "{student_id}_{assignment_code}{extension}"},
        "submission_requirements": [{"key": "report", "label": "报告", "allowed_extensions": [".md"], "max_size_mb": 1, "filename_template": "{student_id}_{assignment_code}{extension}", "required": True}],
    }
    response = client.post(f"/api/admin/classes/{class_id}/assignments", json=payload)
    assert response.status_code == 201
    return {"class_id": class_id, "assignment_id": response.json["assignment"]["id"], "teacher_id": teacher_id,
            "student_id": student_id, "outsider_id": outsider_id, "payload": payload, "root": tmp_path}


def login(client, name):
    client.post("/api/auth/logout")
    assert _login(client, "Bob" if name == "outsider" else name).status_code == 200


def open_draft(client, context, kind="submission"):
    response = client.post("/api/markdown-documents", json={"class_id": context["class_id"], "assignment_id": context["assignment_id"], "kind": kind, "item_key": "report"})
    assert response.status_code == 200
    return response.json["document"]


def save(client, document, content):
    response = client.put(f"/api/markdown-documents/{document['id']}", json={"content": content, "revision": document["revision"]})
    assert response.status_code == 200, response.json
    return response.json["document"]


def image_bytes():
    stream = BytesIO()
    Image.new("RGB", (4, 3), "red").save(stream, "PNG")
    stream.seek(0)
    return stream


def upload_image(client, document):
    response = client.post(f"/api/markdown-documents/{document['id']}/images", data={"file": (image_bytes(), "实验.png")})
    assert response.status_code == 201, response.json
    return response.json["asset"]


def test_student_draft_confirmation_and_image_version_permissions(client, context):
    login(client, "OS202601-06")
    document = open_draft(client, context)
    assert open_draft(client, context)["id"] == document["id"]
    asset = upload_image(client, document)
    content = f"# 报告 ✅\n\n![实验]({asset['url']})\n\n**分析**"
    document = save(client, document, content)
    rows = client.get(f"/api/classes/{context['class_id']}/assignments").json["assignments"]
    assert rows[0]["markdown_drafts"]["report"]["pending_changes"]
    with client.application.app_context():
        assert Submission.query.count() == 0
    assert client.get(asset["url"]).status_code == 200
    login(client, "teacher1")
    assert client.get(asset["url"]).status_code == 404
    assert client.get(f"/api/markdown-documents/{document['id']}").status_code == 403
    login(client, "OS202601-06")
    response = client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission")
    assert response.status_code == 200, response.json
    first = response.json["assignment"]["submissions"][0]
    assert first["original_filename"] == "OS202601-06_r1.md"
    assert first["status"] == "submitted"
    with client.application.app_context():
        old_path = context["root"] / db.session.get(Submission, first["id"]).file_path
        assert old_path.read_text(encoding="utf-8") == content
    document = save(client, document, "# 新版本\n不再引用旧图。")
    new_asset = upload_image(client, document)
    login(client, "teacher1")
    assert client.get(asset["url"]).status_code == 200
    assert client.get(new_asset["url"]).status_code == 404
    preview = client.get(f"/api/admin/submissions/{first['id']}/preview")
    assert preview.json["content"] == content
    login(client, "OS202601-06")
    response = client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission")
    assert response.status_code == 200
    assert response.json["assignment"]["submissions"][0]["id"] != first["id"]
    assert old_path.read_text(encoding="utf-8") == content
    login(client, "outsider")
    assert client.get(asset["url"]).status_code == 404
    assert client.get(f"/api/markdown-documents/{document['id']}").status_code == 403
    assert client.post("/api/markdown-documents", json={"class_id": context["class_id"], "assignment_id": context["assignment_id"], "kind": "submission", "item_key": "report"}).status_code == 403


def test_teacher_unsaved_images_bind_on_assignment_save_and_are_class_private(client, context):
    response = client.post("/api/markdown-documents", json={"class_id": context["class_id"], "kind": "description"})
    document = response.json["document"]
    asset = upload_image(client, document)
    content = f"![说明]({asset['url']})"
    document = save(client, document, content)
    restored = client.post("/api/markdown-documents", json={"class_id": context["class_id"], "kind": "description"}).json["document"]
    assert restored["id"] == document["id"] and restored["content"] == content
    payload = {**context["payload"], "code": "r2", "status": "draft", "description": content, "markdown_document_id": document["id"]}
    response = client.post(f"/api/admin/classes/{context['class_id']}/assignments", json=payload)
    assert response.status_code == 201, response.json
    assignment_id = response.json["assignment"]["id"]
    login(client, "OS202601-06")
    assert client.get(asset["url"]).status_code == 404
    login(client, "teacher1")
    assert client.post(f"/api/admin/assignments/{assignment_id}/publish").status_code == 200
    login(client, "OS202601-06")
    response = client.get(asset["url"])
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    login(client, "outsider")
    assert client.get(asset["url"]).status_code == 404


def test_revision_conflicts_and_cross_document_image_references_are_rejected(client, context):
    login(client, "OS202601-06")
    original = open_draft(client, context)
    document = save(client, original, "当前草稿")
    response = client.put(f"/api/markdown-documents/{document['id']}", json={"content": "旧窗口", "revision": original["revision"]})
    assert response.status_code == 409
    assert client.get(f"/api/markdown-documents/{document['id']}").json["document"]["content"] == "当前草稿"
    # A class member still cannot reference a different student's draft assets.
    asset = upload_image(client, document)
    with client.application.app_context():
        db.session.add(CourseMember(course_id=db.session.get(Assignment, context["assignment_id"]).course_id, class_id=context["class_id"], user_id=context["outsider_id"], role="student"))
        db.session.add(ClassRoster(class_id=context["class_id"], matched_user_id=context["outsider_id"], student_name="Bob", student_id="OS202601-07", student_no="07", student_number="32300000007"))
        db.session.commit()
    login(client, "outsider")
    assert client.get(asset["url"]).status_code == 404
    other_document = open_draft(client, context)
    save(client, other_document, f"![他人的图]({asset['url']})")
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 400
    with client.application.app_context():
        assert Submission.query.count() == 0


@pytest.mark.parametrize("content", ["![图](images/local.png)", "![图](https://example.com/a.png)", "![图](/api/assets/" + "f" * 32 + "/content)", "\n "])
def test_missing_images_and_empty_markdown_do_not_create_submission(client, context, content):
    login(client, "OS202601-06")
    document = open_draft(client, context)
    save(client, document, content)
    response = client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission")
    assert response.status_code == 400
    with client.application.app_context():
        assert Submission.query.count() == 0
        assert db.session.get(MarkdownDocument, document["id"]).submitted_revision == 0
    assert list(context["root"].rglob("*.md")) == []


def test_image_validation_and_document_limits(client, context):
    login(client, "OS202601-06")
    document = open_draft(client, context)
    for filename, content in [("bad.png", b"not a png"), ("x.svg", b"<svg/>"), ("huge.png", b"x" * (5 * 1024 * 1024 + 1))]:
        response = client.post(f"/api/markdown-documents/{document['id']}/images", data={"file": (BytesIO(content), filename)})
        assert response.status_code == 400
    response = client.put(f"/api/markdown-documents/{document['id']}", json={"content": "x" * (1024 * 1024 + 1), "revision": 0})
    assert response.status_code == 400
    with client.application.app_context():
        assert MarkdownAsset.query.count() == 0
    assert list(context["root"].rglob("*.png")) == []


def test_deadline_and_published_grade_lock_draft_mutations(client, context):
    login(client, "OS202601-06")
    document = open_draft(client, context)
    with client.application.app_context():
        assignment = db.session.get(Assignment, context["assignment_id"])
        assignment.deadline = utc_now() - timedelta(days=1)
        db.session.commit()
    assert client.put(f"/api/markdown-documents/{document['id']}", json={"content": "late", "revision": 0}).status_code == 403
    assert client.post(f"/api/markdown-documents/{document['id']}/images", data={"file": (image_bytes(), "x.png")}).status_code == 403
    with client.application.app_context():
        db.session.get(Assignment, context["assignment_id"]).allow_late = True
        db.session.add(AssignmentGrade(assignment_id=context["assignment_id"], student_user_id=context["student_id"], status=GradingResult.STATUS_PUBLISHED))
        db.session.commit()
    assert client.put(f"/api/markdown-documents/{document['id']}", json={"content": "published", "revision": 0}).status_code == 403
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 403


def test_failed_other_file_rolls_back_generated_snapshot_and_revision(client, context):
    with client.application.app_context():
        assignment = db.session.get(Assignment, context["assignment_id"])
        assignment.submission_requirements_json = [*assignment.submission_requirements_json, {
            "key": "code", "label": "程序", "allowed_extensions": [".py"], "max_size_mb": 1,
            "filename_template": "{student_id}_{assignment_code}{extension}", "required": True,
        }]
        db.session.commit()
    login(client, "OS202601-06")
    document = save(client, open_draft(client, context), "# 有效报告")
    uploaded = client.post(f"/api/assignments/{context['assignment_id']}/submissions", data={"item_key": "code", "file": (BytesIO(b"\x00"), "OS202601-06_r1.py")})
    assert uploaded.status_code == 201
    response = client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission")
    assert response.status_code == 400
    with client.application.app_context():
        assert Submission.query.count() == 1
        assert db.session.get(MarkdownDocument, document["id"]).submitted_revision == 0
    assert list(context["root"].rglob("*.md")) == []


def test_unused_cleanup_keeps_old_submission_images(client, context):
    login(client, "OS202601-06")
    document = open_draft(client, context)
    used = upload_image(client, document)
    document = save(client, document, f"![保留]({used['url']})")
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 200
    save(client, document, "新草稿，不引用旧图片")
    unused = upload_image(client, document)
    with client.application.app_context():
        for asset in MarkdownAsset.query.all():
            asset.created_at = utc_now() - timedelta(days=8)
        db.session.commit()
    runner = client.application.test_cli_runner()
    result = runner.invoke(args=["cleanup-markdown-assets"])
    assert result.exit_code == 0 and "Unused candidates: 1" in result.output
    assert client.get(unused["url"]).status_code == 200
    result = runner.invoke(args=["cleanup-markdown-assets", "--apply"])
    assert result.exit_code == 0 and "Deleted: 1" in result.output
    assert client.get(unused["url"]).status_code == 404
    assert client.get(used["url"]).status_code == 200


def test_markdown_parser_reads_reference_images_and_ignores_code():
    content = "![图][figure]\n\n[figure]: /api/assets/abc/content\n\n```md\n![示例](images/local.png)\n```"
    assert image_sources(content) == ["/api/assets/abc/content"]


def test_long_chinese_markdown_and_teacher_return_preserve_editable_draft(client, context):
    login(client, "OS202601-06")
    document = save(client, open_draft(client, context), "中文测试" * 10000)
    response = client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission")
    assert response.status_code == 200, response.json
    submission_id = response.json["assignment"]["submissions"][0]["id"]
    login(client, "teacher1")
    assert client.post(f"/api/admin/submissions/{submission_id}/return").status_code == 200
    login(client, "OS202601-06")
    restored = open_draft(client, context)
    assert restored["content"] == document["content"] and restored["pending_changes"]
    response = client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission")
    assert response.status_code == 200


def test_teacher_cannot_attach_another_users_document(client, context):
    login(client, "OS202601-06")
    document = open_draft(client, context)
    login(client, "teacher1")
    response = client.post(f"/api/admin/classes/{context['class_id']}/assignments", json={**context["payload"], "code": "blocked", "markdown_document_id": document["id"]})
    assert response.status_code == 403
    with client.application.app_context():
        assert Assignment.query.filter_by(code="blocked").count() == 0


@pytest.mark.parametrize("suffix", [b"\x00", b"\xff"])
def test_text_validation_rejects_binary_or_invalid_utf8_after_the_first_chunk(suffix):
    uploaded = FileStorage(stream=BytesIO(b"x" * 65536 + suffix), filename="OS202601-06_r1.md")
    context = FileValidationContext("OS202601-06", "06", "Alice", "r1")
    rules = {"allowed_extensions": [".md"], "max_size_mb": 1, "filename_template": "{student_id}_{assignment_code}{extension}"}
    with pytest.raises(FileValidationError):
        validate_submission_file(uploaded, rules, context)


def test_retired_submission_item_drafts_do_not_block_current_requirements(client, context):
    login(client, "OS202601-06")
    original = save(client, open_draft(client, context), "旧提交项草稿")
    with client.application.app_context():
        assignment = db.session.get(Assignment, context["assignment_id"])
        assignment.submission_requirements_json = [{**assignment.submission_requirements_json[0], "key": "new_report"}]
        db.session.commit()
    response = client.post("/api/markdown-documents", json={"class_id": context["class_id"], "assignment_id": context["assignment_id"], "kind": "submission", "item_key": "new_report"})
    save(client, response.json["document"], "新提交项草稿")
    response = client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission")
    assert response.status_code == 200, response.json
    assert set(response.json["assignment"]["markdown_drafts"]) == {"new_report"}
    assert response.json["assignment"]["submissions"][0]["submission_item_key"] == "new_report"
    assert client.get(f"/api/markdown-documents/{original['id']}").json["document"]["content"] == "旧提交项草稿"


def test_explicit_markdown_file_upload_preserves_managed_image_references(client, context):
    login(client, "OS202601-06")
    document = open_draft(client, context)
    asset = upload_image(client, document)
    content = f"# 从文件上传\n\n![图]({asset['url']})"
    response = client.post(f"/api/assignments/{context['assignment_id']}/submissions", data={
        "item_key": "report", "file": (BytesIO(content.encode()), "OS202601-06_r1.md")
    })
    assert response.status_code == 201
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 200
    login(client, "teacher1")
    assert client.get(asset["url"]).status_code == 200

@pytest.mark.parametrize('online', [False, True])
def test_course_alias_filename_works_for_upload_and_online_snapshot(client, context, online):
    with client.application.app_context():
        assignment = db.session.get(Assignment, context['assignment_id'])
        requirement = dict(assignment.submission_requirements_json[0])
        requirement['filename_template'] = '{course_alias}_{student_no}_{name}_{assignment_code}{extension}'
        assignment.submission_requirements_json = [requirement]
        db.session.commit()
    login(client, 'OS202601-06')
    if online:
        save(client, open_draft(client, context), '# online report')
    else:
        upload = client.post(f"/api/assignments/{context['assignment_id']}/submissions", data={
            'item_key': 'report', 'file': (BytesIO(b'# uploaded report'), 'OS202601_06_Alice_r1.md')})
        assert upload.status_code == 201, upload.json
    response = client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission")
    assert response.status_code == 200, response.json
    with client.application.app_context():
        submission = Submission.query.filter_by(assignment_id=context['assignment_id']).first()
        assert submission.original_filename == 'OS202601_06_Alice_r1.md'
        assert submission.status == 'submitted'
