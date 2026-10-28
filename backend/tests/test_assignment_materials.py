import pytest

from app.extensions import db
from app.models import Assignment, CourseClass, CourseMember
from app.services.code_templates import normalize_code_templates
from app.services.file_validation import FileValidationError
from app.services.llm_grading import _build_prompt
from test_code_templates import attach, upload
from test_markdown_documents import context, image_bytes, login


def test_markdown_files_are_attachments_with_editable_purpose_and_four_file_limit():
    files = [{'filename': 'starter.py', 'content': '# TODO', 'purpose': '  代码框架  '},
             {'filename': 'README.md', 'content': '# 附件说明'},
             {'filename': 'notes.md', 'content': '# 补充资料'}]
    result = normalize_code_templates(files)
    assert all('is_main' not in item for item in result)
    assert result[0]['purpose'] == '代码框架'
    files.append({'filename': 'extra.py', 'content': '# TODO'})
    assert len(normalize_code_templates(files)) == 4
    with pytest.raises(FileValidationError):
        normalize_code_templates(files + [{'filename': 'five.md', 'content': '# Too many'}])


@pytest.mark.parametrize('files', [
    [{'filename': 'starter.py', 'content': '# TODO', 'is_main': True}],
    [{'filename': 'main.md', 'content': '# TODO', 'is_main': 'true'}],
    [{'filename': 'a.md', 'content': '# A', 'is_main': True}, {'filename': 'b.md', 'content': '# B', 'is_main': True}],
])
def test_invalid_main_flags_are_rejected(files):
    with pytest.raises(FileValidationError):
        normalize_code_templates(files)


def test_markdown_and_python_preview_preserve_permissions_and_metadata(client, context):
    main = upload(client, '# 作业要求\n[代码](starter.py)'.encode(), 'README.md')
    assert main.status_code == 200
    py = upload(client).json['template']
    extra = upload(client, b'# Extra notes', 'notes.md').json['template']
    data = attach(client, context, [py, main.json['template'], extra])
    files = data['code_templates']
    assert all('is_main' not in item for item in files)
    assert all('content' not in item for item in files)
    main_file = next(item for item in files if item['filename'] == 'README.md')
    with client.application.app_context():
        assignment = db.session.get(Assignment, context['assignment_id'])
        assert assignment.effective_description == (assignment.description or '')
        assert '作业要求' not in _build_prompt(assignment, None, 'report.md', 'student report', {}, 100, [])
    source = client.get(main_file['preview_url'])
    assert source.status_code == 200 and source.json['template']['content'].startswith('# 作业要求')
    assert source.headers['Cache-Control'] == 'private, no-store'
    downloaded = client.get(main_file['url'])
    assert downloaded.data == '# 作业要求\n[代码](starter.py)'.encode()
    assert downloaded.mimetype == 'text/markdown'
    base = f"/api/admin/assignments/{context['assignment_id']}"
    assert client.patch(base, json={'status': 'draft', 'require_resubmission': False}).status_code == 200
    login(client, 'OS202601-06')
    assert client.get(main_file['preview_url']).status_code == 404
    login(client, 'teacher1')
    assert client.post(base + '/publish').status_code == 200
    login(client, 'OS202601-06')
    for file in files:
        response = client.get(file['preview_url'])
        assert response.status_code == 200
        assert response.json['template']['filename'] == file['filename']
    login(client, 'outsider')
    assert client.get(main_file['preview_url']).status_code == 404
    login(client, 'teacher1')
    attach(client, context, [py])
    assert client.get(main_file['preview_url']).status_code == 404


def test_markdown_material_image_references_authorize_students_and_protect_deletion_and_copy(client, context):
    image = client.post('/api/teacher/images', data={'file': (image_bytes(), 'figure.png')}).json['asset']
    content = f"# 实验\n![配图]({image['url']})"
    main = upload(client, content.encode(), 'main.md').json['template']
    attach(client, context, [main])
    assert client.delete(f"/api/teacher/images/{image['id']}").status_code == 409
    login(client, 'OS202601-06')
    assert client.get(image['url']).status_code == 200
    login(client, 'outsider')
    assert client.get(image['url']).status_code == 404
    login(client, 'teacher1')
    target_id = client.post('/api/admin/classes', json={'class': {'alias': 'MATERIAL28'}}).json['class']['id']
    copied = client.post(f"/api/admin/assignments/{context['assignment_id']}/copy", json={'class_id': target_id})
    assignment_id = copied.json['assignment']['id']
    assert 'is_main' not in copied.json['assignment']['code_templates'][0]
    with client.application.app_context():
        target = db.session.get(CourseClass, target_id)
        db.session.add(CourseMember(class_id=target_id, course_id=target.course_id, user_id=context['outsider_id'], role='student'))
        db.session.commit()
    attach(client, context, [])
    assert client.delete(f"/api/teacher/images/{image['id']}").status_code == 409
    login(client, 'outsider')
    assert client.get(image['url']).status_code == 404  # target is still a draft
    login(client, 'teacher1')
    assert client.post(f'/api/admin/assignments/{assignment_id}/publish').status_code == 200
    login(client, 'outsider')
    assert client.get(image['url']).status_code == 200
    login(client, 'teacher1')
    assert client.patch(f'/api/admin/assignments/{assignment_id}', json={'code_templates': [], 'require_resubmission': False}).status_code == 200
    assert client.delete(f"/api/teacher/images/{image['id']}").status_code == 200


def test_markdown_materials_cannot_bypass_image_ownership_or_upload_requirements(client, context):
    login(client, 'outsider')
    foreign = client.post('/api/student/images', data={'file': (image_bytes(), 'private.png')}).json['asset']
    login(client, 'teacher1')
    for source in [foreign['url'], './local.png', 'https://example.com/external.png']:
        response = client.patch(f"/api/admin/assignments/{context['assignment_id']}", json={
            'code_templates': [{'filename': 'main.md', 'content': f'![image]({source})'}], 'require_resubmission': False})
        assert response.status_code == 400
    with client.application.app_context():
        assert db.session.get(Assignment, context['assignment_id']).code_templates_json == []


@pytest.mark.parametrize('purpose', [None, 12, 'x' * 121, 'two\nlines'])
def test_invalid_attachment_purposes_are_rejected(client, context, purpose):
    response = client.patch(f"/api/admin/assignments/{context['assignment_id']}", json={
        'code_templates': [{'filename': 'notes.md', 'content': '# Note', 'purpose': purpose}],
        'require_resubmission': False})
    assert response.status_code == 400


def test_renaming_and_purpose_persist_without_changing_main_description(client, context):
    base = f"/api/admin/assignments/{context['assignment_id']}"
    assert client.patch(base, json={'description': '# 独立主说明', 'require_resubmission': False}).status_code == 200
    original = attach(client, context, [upload(client).json['template']])['code_templates'][0]
    source = client.get(base + '/code-templates').json['templates'][0]
    source.update(filename='实验框架.py', purpose='待补全的代码')
    updated = attach(client, context, [source])
    file = updated['code_templates'][0]
    assert file['filename'] == '实验框架.py' and file['purpose'] == '待补全的代码'
    assert updated['description'] == '# 独立主说明'
    assert file['id'] != original['id']
    assert client.get(original['url']).status_code == 404
    assert client.get(file['url']).status_code == 200
    login(client, 'OS202601-06')
    rows = client.get(f"/api/classes/{context['class_id']}/assignments").json['assignments']
    row = next(item for item in rows if item['id'] == context['assignment_id'])
    assert row['description'] == '# 独立主说明'
    assert row['code_templates'][0]['purpose'] == '待补全的代码'
