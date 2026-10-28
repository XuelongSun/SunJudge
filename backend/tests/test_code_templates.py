from copy import deepcopy
from io import BytesIO

import pytest
from flask import g

from app.extensions import db
from app.models import Assignment, Submission, User
from test_markdown_documents import context, login, open_draft, save


def upload(client, content=b'# TODO\nprint("framework")\n', filename='starter.py'):
    return client.post('/api/teacher/code-templates/validate', data={'file': (BytesIO(content), filename)})


def attach(client, context, templates):
    response = client.patch(f"/api/admin/assignments/{context['assignment_id']}", json={
        'code_templates': templates, 'require_resubmission': False})
    assert response.status_code == 200, response.json
    return response.json['assignment']


def test_code_upload_is_staged_and_creates_no_files_or_assignment_changes(client, context):
    # Incomplete Python is useful in a starter; it must not be compiled or run.
    response = upload(client, b'def finish_me(\n')
    assert response.status_code == 200
    template = response.json['template']
    assert template['filename'] == 'starter.py' and template['file_size'] == len(b'def finish_me(\n')
    with client.application.app_context():
        assert db.session.get(Assignment, context['assignment_id']).code_templates_json == []
        assert Submission.query.count() == 0
    assert list(context['root'].rglob('*.py')) == []
    assert client.post('/api/teacher/code-templates/validate').status_code == 400


def test_create_edit_download_and_metadata_only_listing(client, context):
    source = '# 实验框架\n\ndef solve():\n    pass\n'.encode('utf-8')
    template = upload(client, source, '实验框架.py').json['template']
    # The server recomputes IDs and size rather than accepting caller-provided metadata.
    payload = deepcopy(context['payload'])
    payload.update(code='framework', status='draft', code_templates=[{**template, 'id': '../forged', 'file_size': 1}])
    created = client.post(f"/api/admin/classes/{context['class_id']}/assignments", json=payload)
    assert created.status_code == 201, created.json
    assignment = created.json['assignment']
    entry = assignment['code_templates'][0]
    assert entry['id'] == template['id'] and entry['file_size'] == len(source)
    assert 'content' not in entry
    assignment_id = assignment['id']
    edit_url = f'/api/admin/assignments/{assignment_id}/code-templates'
    assert client.get(edit_url).json['templates'][0]['content'].encode('utf-8') == source
    downloaded = client.get(entry['url'])
    assert downloaded.data == source
    assert downloaded.headers['Content-Disposition'].startswith('attachment;')
    assert downloaded.headers['Cache-Control'] == 'private, no-store'
    assert downloaded.headers['X-Content-Type-Options'] == 'nosniff'
    login(client, 'OS202601-06')
    assert client.get(entry['url']).status_code == 404  # not published yet
    assert client.get(edit_url).status_code == 403
    assert upload(client).status_code == 403
    login(client, 'teacher1')
    assert client.post(f'/api/admin/assignments/{assignment_id}/publish').status_code == 200
    login(client, 'OS202601-06')
    rows = client.get(f"/api/classes/{context['class_id']}/assignments").json['assignments']
    listed = next(item for item in rows if item['id'] == assignment_id)
    assert 'content' not in listed['code_templates'][0]
    assert client.get(entry['url']).data == source
    login(client, 'outsider')
    assert client.get(entry['url']).status_code == 404


@pytest.mark.parametrize('content, filename', [
    (b'print(1)', 'starter.txt'), (b'print(1)', 'starter.py.exe'), (b'print(1)', '../starter.py'),
    (b'print(1)', 'C:\\starter.py'), (b'print(1)', '.py'),
    (b'', 'starter.py'), (b'  \n', 'starter.py'), (b'\xef\xbb\xbf', 'starter.py'),
    (b'bad\x00binary', 'starter.py'), (b'\xff\xfe', 'starter.py'),
    (b'x' * (1024 * 1024 + 1), 'starter.py'),
], ids=['text-extension', 'double-extension', 'relative-path', 'windows-path', 'empty-name',
        'empty', 'whitespace', 'bom-only', 'binary', 'encoding', 'oversized'])
def test_template_upload_rejects_invalid_names_types_encoding_and_size(client, context, content, filename):
    assert upload(client, content, filename).status_code == 400


def test_template_count_duplicates_and_direct_payload_validation(client, context):
    base = f"/api/admin/assignments/{context['assignment_id']}"
    good = {'filename': 'starter.py', 'content': '# TODO'}
    invalid = [None, {}, 'file', [None], [{'filename': '../bad.py', 'content': '# TODO'}],
               [{'filename': '\ud800.py', 'content': '# TODO'}],
               [{'filename': 'starter.py', 'content': None}],
               [{'filename': 'starter.py', 'content': 'x' * (1024 * 1024 + 1)}],
               [good, {**good, 'filename': 'STARTER.PY'}],
               [{'filename': f'file{n}.py', 'content': '# TODO'} for n in range(5)]]
    for index, templates in enumerate(invalid):
        response = client.patch(base, json={'code_templates': templates, 'require_resubmission': False})
        assert response.status_code == 400, (index, response.json)
    assert client.patch(base, json={'code_templates': [good] * 5, 'require_resubmission': False}).status_code == 400
    at_limit = [{'filename': f'file{n}.py', 'content': 'x' * 1024 * 1024} for n in range(4)]
    assert client.patch(base, json={'code_templates': at_limit, 'require_resubmission': False}).status_code == 200
    assert len(client.get(base + '/code-templates').json['templates']) == 4


def test_framework_copy_is_independent_and_source_removal_does_not_break_target(client, context):
    original = attach(client, context, [upload(client).json['template']])
    old_url = original['code_templates'][0]['url']
    target_id = client.post('/api/admin/classes', json={'class': {'alias': 'NEXT28'}}).json['class']['id']
    copied = client.post(f"/api/admin/assignments/{context['assignment_id']}/copy", json={'class_id': target_id})
    assert copied.status_code == 201
    entry = copied.json['assignment']['code_templates'][0]
    assert entry['id'] == original['code_templates'][0]['id'] and entry['url'] != old_url
    attach(client, context, [])
    assert client.get(old_url).status_code == 404
    assert client.get(entry['url']).status_code == 200
    login(client, 'OS202601-06')
    assert client.get(entry['url']).status_code == 404  # another class, still a draft


def test_template_edit_preserves_existing_student_work_and_enforces_teacher_ownership(client, context):
    login(client, 'OS202601-06')
    save(client, open_draft(client, context), '# 已提交报告')
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 200
    login(client, 'teacher1')
    with client.application.app_context():
        submission_id = Submission.query.one().id
        teacher = User(username='other_teacher', role='teacher', teacher_status='approved')
        teacher.set_password('secret123')
        pending = User(username='pending_teacher', role='teacher', teacher_status='pending')
        pending.set_password('secret123')
        db.session.add_all([teacher, pending])
        db.session.commit()
        pending_id = pending.id
    result = attach(client, context, [upload(client).json['template']])
    assert result['submission_count'] == 1
    with client.application.app_context():
        assert Submission.query.one().id == submission_id and Submission.query.one().status == 'submitted'
    url = result['code_templates'][0]['url']
    login(client, 'other_teacher')
    assert client.get(url).status_code == 404
    assert client.get(f"/api/admin/assignments/{context['assignment_id']}/code-templates").status_code == 404
    # Normal login already blocks pending accounts; test defense in depth for an existing session.
    with client.session_transaction() as session:
        session['_user_id'] = str(pending_id)
        session['_fresh'] = True
    # conftest keeps one app context open, so also invalidate its Flask-Login cache.
    g.pop('_login_user', None)
    assert upload(client).status_code == 403
    assert client.get(url).status_code == 403
