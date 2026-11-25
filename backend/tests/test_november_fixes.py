from datetime import UTC, datetime, timedelta
from io import BytesIO

from app.extensions import db
from app.models import Assignment, AssignmentGrade, CourseMember, MarkdownAsset, utc_now
from test_markdown_documents import context, login, open_draft, save, upload_image


def test_read_only_student_work_survives_deadline_and_feedback(client, context):
    assignment_id = context["assignment_id"]
    url = f"/api/assignments/{assignment_id}"
    list_url = f"/api/classes/{context['class_id']}/assignments"
    login(client, "OS202601-06")
    document = open_draft(client, context)
    asset = upload_image(client, document)
    original = f"# 已确认报告\n![配图]({asset['url']})"
    document = save(client, document, original)
    confirmed = client.post(f"{url}/confirm-submission").json["assignment"]["saved_files"][0]
    raw_upload = b'# Uploaded\r\n\r\n<tag>\r\n'
    result = client.post(f"{url}/submissions", data={"item_key": "report", "file": (BytesIO(raw_upload), "OS202601-06_r1.md")})
    assert result.status_code == 201
    upload_id = result.json["submission"]["id"]
    document = client.get(f"/api/markdown-documents/{document['id']}").json["document"]
    save(client, document, "# 尚未确认的在线草稿")
    assignment = db.session.get(Assignment, assignment_id)
    assignment.deadline = utc_now() - timedelta(days=1)
    db.session.commit()
    preview_url = f"{url}/submissions/{confirmed['id']}/preview"
    assert client.get(preview_url).json["content"] == original
    assert client.post(f"{url}/confirm-submission").status_code == 403
    grade = AssignmentGrade.query.filter_by(assignment_id=assignment_id, student_user_id=context["student_id"]).one()
    grade.status = "published"
    db.session.commit()

    files = client.get(list_url).json["assignments"][0]["saved_files"]
    assert {file["id"]: file["status"] for file in files} == {confirmed["id"]: "submitted", upload_id: "uploaded"}
    response = client.get(preview_url)
    assert response.status_code == 200 and response.json["content"] == original
    assert response.headers["Cache-Control"] == "private, no-store"
    assert client.get(asset["url"]).status_code == 200
    assert client.get(f"{url}/submissions/{upload_id}/preview").json["content"] == raw_upload.decode()
    assert client.get(f"{url}/submissions/{upload_id}/download").data == raw_upload
    assert client.get(f"/api/markdown-documents/{document['id']}").json["document"]["content"] == "# 尚未确认的在线草稿"
    assert client.post(f"{url}/confirm-submission").status_code == 403

    login(client, "outsider")
    assert client.get(preview_url).status_code == 404
    db.session.add(CourseMember(course_id=assignment.course_id, class_id=assignment.class_id,
                                user_id=context["outsider_id"], role="student"))
    db.session.commit()
    assert client.get(preview_url).status_code == 404
    login(client, "OS202601-06")
    assert client.get(f"/api/assignments/{assignment_id + 1}/submissions/{upload_id}/download").status_code == 404
    assignment.status = "draft"
    db.session.commit()
    assert client.get(preview_url).status_code == 404


def test_deadline_has_explicit_utc_and_submission_gate_uses_same_instant(client, context, monkeypatch):
    url = f"/api/admin/assignments/{context['assignment_id']}"
    response = client.patch(url, json={'deadline': '2030-11-05T22:00:00+08:00', 'require_resubmission': False})
    assert response.status_code == 200
    value = response.json['assignment']['deadline']
    assert datetime.fromisoformat(value) == datetime(2030, 11, 5, 14, tzinfo=UTC)
    assert value.endswith('+00:00')
    assert client.patch(url, json={'deadline': '2030-11-05T22:00:00', 'require_resubmission': False}).status_code == 400
    login(client, 'OS202601-06')
    monkeypatch.setattr('app.services.markdown_documents.utc_now', lambda: datetime(2030, 11, 5, 13, 59, tzinfo=UTC))
    document = open_draft(client, context)
    save(client, document, '# Before deadline')
    monkeypatch.setattr('app.services.markdown_documents.utc_now', lambda: datetime(2030, 11, 5, 14, 1, tzinfo=UTC))
    response = client.put(f"/api/markdown-documents/{document['id']}", json={'content': '# Late', 'revision': 1})
    assert response.status_code == 403


def test_reviewed_image_can_be_retired_to_private_placeholder(client, context):
    login(client, 'OS202601-06')
    document = open_draft(client, context)
    asset = upload_image(client, document)
    document = save(client, document, f"# Report\n![图]({asset['url']})")
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 200
    assert client.delete(f"/api/student/images/{asset['id']}").status_code == 409
    grade = AssignmentGrade.query.filter_by(assignment_id=context['assignment_id'], student_user_id=context['student_id']).one()
    grade.status, grade.final_score = 'reviewed', 80
    db.session.commit()
    assert client.get('/api/student/images').json['assets'][0]['reviewed_only']
    login(client, 'teacher1')
    other = client.post(f"/api/admin/classes/{context['class_id']}/assignments", json={**context['payload'], 'code': 'another'}).json['assignment']['id']
    login(client, 'OS202601-06')
    other_document = open_draft(client, {**context, 'assignment_id': other})
    other_document = save(client, other_document, f"![shared]({asset['url']})")
    # A reviewed report must not authorize deleting an image still used by new work.
    assert client.delete(f"/api/student/images/{asset['id']}").status_code == 409
    save(client, other_document, '# No image')
    assert client.delete(f"/api/student/images/{asset['id']}").status_code == 200
    assert client.get('/api/student/images').json['assets'] == []
    image = db.session.get(MarkdownAsset, asset['id'])
    assert image.deleted_at and image.file_size == 0
    assert not (context['root'] / image.file_path).exists()
    assert client.get(asset['url']).mimetype == 'image/svg+xml'
    # Unchanged draft references remain valid after retirement.
    save(client, document, document['content'] + '\nText')
    login(client, 'teacher1')
    assert client.get(asset['url']).status_code == 200
    login(client, 'outsider')
    assert client.get(asset['url']).status_code == 404
