import csv
from copy import deepcopy
from datetime import timedelta
from io import StringIO, BytesIO

import pytest

from app.extensions import db
from app.models import Assignment, AssignmentGrade, AssignmentStudentOverride, ClassRoster, GradingResult, MarkdownAsset, Submission, User, utc_now
from test_markdown_documents import context, image_bytes, login, open_draft, save


@pytest.mark.parametrize('editor', [False, True])
def test_student_library_30mb_limit_applies_to_both_upload_paths(client, context, editor):
    login(client, 'OS202601-06')
    document = open_draft(client, context)
    with client.application.app_context():
        db.session.add(MarkdownAsset(id='a' * 32, student_user_id=context['student_id'], original_filename='large.png',
            file_path='fixture.png', mime_type='image/png', file_size=30 * 1024 * 1024))
        db.session.commit()
    url = f"/api/markdown-documents/{document['id']}/images" if editor else '/api/student/images'
    response = client.post(url, data={'file': (image_bytes(), 'new.png')})
    assert response.status_code == 400 and '30 MB' in response.json['message']
    # Reducing a quota never deletes existing images. Teacher quota stays independent.
    assert len(client.get('/api/student/images').json['assets']) == 1
    login(client, 'teacher1')
    assert client.post('/api/teacher/images', data={'file': (image_bytes(), 'teacher.png')}).status_code == 201


def test_export_factor_rounding_csv_columns_and_cli(client, context):
    with client.application.app_context():
        db.session.add(AssignmentGrade(assignment_id=context['assignment_id'], student_user_id=context['student_id'],
            final_score=92.35, status=GradingResult.STATUS_REVIEWED))
        db.session.commit()
    base = f"/api/admin/assignments/{context['assignment_id']}"
    response = client.get(base + '/grades.csv?score_factor=0.1')
    assert response.status_code == 200
    row = next(csv.DictReader(StringIO(response.data.decode('utf-8-sig'))))
    assert row['原始成绩'] == '92.35' and row['比例因子'] == '0.1' and row['最终成绩'] == '9.24'
    for command_type, expected in [('regular', 'rd 06 homework 9.24'), ('lab', 'lab rd 06 homework 9.24')]:
        result = client.get(base + f'/scoremanager-commands?score_factor=0.1&field=homework&command_type={command_type}')
        assert result.status_code == 200 and result.json['export']['commands'] == expected
    assert client.get(base + '/scoremanager-commands?score_factor=0').json['export']['lines'] == ['rd 06 homework 0.00']
    for value in ['nan', 'inf', '-1', 'abc', '1001']:
        for endpoint in ['/grades.csv', '/scoremanager-commands']:
            assert client.get(base + endpoint + '?score_factor=' + value).status_code == 400
    with client.application.app_context():
        assert AssignmentGrade.query.one().final_score == 92.35


def confirmed_report(client, context):
    login(client, 'OS202601-06')
    save(client, open_draft(client, context), '# 原始报告')
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 200
    login(client, 'teacher1')
    with client.application.app_context():
        submission = Submission.query.one()
        identity = (submission.id, submission.file_path, submission.submitted_at)
    assert client.patch(f'/api/admin/submissions/{identity[0]}/grade', json={'final_score': 90, 'status': 'published'}).status_code == 200
    return identity


def test_republish_without_resubmit_preserves_files_grades_counts_even_when_keys_change(client, context):
    identity = confirmed_report(client, context)
    payload = deepcopy(context['payload'])
    payload['submission_requirements'][0]['key'] = 'new_report'
    payload.update(require_resubmission=False, description='修改说明', deadline=(utc_now() + timedelta(days=5)).isoformat())
    response = client.patch(f"/api/admin/assignments/{context['assignment_id']}", json=payload)
    assert response.status_code == 200, response.json
    assert response.json['assignment']['submission_count'] == 1
    rows = client.get(f"/api/admin/assignments/{context['assignment_id']}/submissions").json
    assert rows['submissions'][0]['student_state'] == 'submitted'
    assert rows['analysis']['submitted_count'] == rows['analysis']['published_count'] == 1
    with client.application.app_context():
        submission = Submission.query.one()
        assert (submission.id, submission.file_path, submission.submitted_at) == identity
        assert submission.status == 'submitted'
        assert AssignmentGrade.query.one().final_score == 90
    login(client, 'OS202601-06')
    assignment = client.get(f"/api/classes/{context['class_id']}/assignments").json['assignments'][0]
    assert assignment['submission_complete'] and assignment['submission_preserved']
    assert assignment['submissions'][0]['id'] == identity[0]
    assert client.get('/api/classes/my').json['classes'][0]['completed_assignment_count'] == 1


def test_republish_requiring_resubmit_keeps_draft_and_uploads_but_clears_grades(client, context):
    identity = confirmed_report(client, context)
    response = client.patch(f"/api/admin/assignments/{context['assignment_id']}", json={'require_resubmission': True, 'description': '新要求'})
    assert response.status_code == 200
    with client.application.app_context():
        submission = Submission.query.one()
        assert submission.id == identity[0] and submission.status == 'uploaded'
        assert AssignmentGrade.query.count() == 0
    login(client, 'OS202601-06')
    data = client.get(f"/api/classes/{context['class_id']}/assignments").json['assignments'][0]
    assert not data['submission_complete'] and data['markdown_drafts']['report']['pending_changes']
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 200


def test_targeted_makeup_all_paths_and_deadline_based_metrics(client, context):
    base = f"/api/assignments/{context['assignment_id']}"
    with client.application.app_context():
        deadline = utc_now() - timedelta(days=1)
        assignment = db.session.get(Assignment, context['assignment_id'])
        assignment.deadline, assignment.published_at = deadline, deadline - timedelta(days=2)
        roster_id = ClassRoster.query.filter_by(class_id=context['class_id']).one().id
        db.session.commit()
    permission = f"/api/admin/assignments/{context['assignment_id']}/students/{roster_id}/makeup"
    login(client, 'OS202601-06')
    upload = lambda: client.post(base + '/submissions', data={'item_key': 'report', 'file': (BytesIO(b'# local'), 'OS202601-06_r1.md')})
    assert upload().status_code == 403
    assert client.post(base + '/confirm-submission').status_code == 403
    assert client.patch(permission, json={'allowed': True}).status_code == 403
    login(client, 'teacher1')
    assert client.patch(permission, json={'allowed': 'true'}).status_code == 400
    assert client.patch(permission, json={'allowed': True}).status_code == 200
    assert client.patch(permission, json={'allowed': False}).status_code == 200
    login(client, 'OS202601-06')
    assert upload().status_code == 403
    login(client, 'teacher1')
    assert client.patch(permission, json={'allowed': True}).status_code == 200
    login(client, 'outsider')
    assert upload().status_code == 404
    login(client, 'OS202601-06')
    data = client.get(f"/api/classes/{context['class_id']}/assignments").json['assignments'][0]
    assert data['makeup_allowed'] and not data['is_expired']
    assert upload().status_code == 201
    save(client, open_draft(client, context), '# 补交报告')
    assert client.post(base + '/confirm-submission').status_code == 200
    with client.application.app_context():
        submission = db.session.get(Assignment, context['assignment_id']).latest_submission_for(context['student_id'])
        assert submission.is_makeup and submission.effective_submitted_at == deadline.replace(tzinfo=None)
        assert submission.submitted_at > submission.effective_submitted_at
        assert not AssignmentStudentOverride.query.one().makeup_allowed
    login(client, 'teacher1')
    rows = client.get(f"/api/admin/assignments/{context['assignment_id']}/submissions").json
    assert rows['analysis']['submitted_count'] == 1
    assert rows['analysis']['average_submit_days_before_deadline'] == 0
    assert rows['analysis']['average_submit_days_after_publish'] == 2
    assert rows['submissions'][0]['submission']['is_makeup']
    assert '(补交)' in client.get(f"/api/admin/assignments/{context['assignment_id']}/grades.csv").data.decode('utf-8-sig')


def test_makeup_rejects_before_deadline_and_foreign_roster(client, context):
    with client.application.app_context():
        assignment = db.session.get(Assignment, context['assignment_id'])
        assignment.deadline = utc_now() + timedelta(days=1)
        roster_id = ClassRoster.query.filter_by(class_id=context['class_id']).one().id
        db.session.commit()
    url = f"/api/admin/assignments/{context['assignment_id']}/students/{roster_id}/makeup"
    assert client.patch(url, json={'allowed': True}).status_code == 400
    assert client.patch(url.replace(f'/{roster_id}/makeup', '/99999/makeup'), json={'allowed': True}).status_code == 400


def test_scaled_grouping_uses_rounded_scores_for_theory_and_lab(client, context):
    with client.application.app_context():
        db.session.add(ClassRoster(class_id=context['class_id'], student_no='07', student_id='OS202601-07', student_name='Bob', matched_user_id=context['outsider_id']))
        for student_id, score in [(context['student_id'], 92.35), (context['outsider_id'], 92.36)]:
            db.session.add(AssignmentGrade(assignment_id=context['assignment_id'], student_user_id=student_id, final_score=score, status='reviewed'))
        db.session.commit()
    for kind, expected in [('regular', 'brd 06,07 homework 9.24'), ('lab', 'lab brd 06,07 homework 9.24')]:
        result = client.get(f"/api/admin/assignments/{context['assignment_id']}/scoremanager-commands?score_factor=0.1&field=homework&command_type={kind}&group_same_score=true")
        assert result.json['export']['commands'] == expected


@pytest.mark.parametrize('resubmit', [False, True])
def test_save_draft_then_publish_uses_explicit_resubmission_choice(client, context, resubmit):
    confirmed_report(client, context)
    base = f"/api/admin/assignments/{context['assignment_id']}"
    response = client.patch(base, json={'status': 'draft', 'deadline': (utc_now() + timedelta(days=5)).isoformat(), 'require_resubmission': False})
    assert response.status_code == 200
    with client.application.app_context():
        assert AssignmentGrade.query.one().status == 'published'
        published_at = db.session.get(Assignment, context['assignment_id']).published_at
    response = client.post(base + '/publish', json={'require_resubmission': resubmit})
    assert response.status_code == 200
    assert response.json['assignment']['submission_count'] == (0 if resubmit else 1)
    with client.application.app_context():
        assert db.session.get(Assignment, context['assignment_id']).published_at == published_at
        assert AssignmentGrade.query.count() == (0 if resubmit else 1)


def test_makeup_permission_ownership_and_completed_submission_protection(client, context):
    confirmed_report(client, context)
    with client.application.app_context():
        assignment = db.session.get(Assignment, context['assignment_id'])
        assignment.deadline = utc_now() - timedelta(days=1)
        roster_id = ClassRoster.query.filter_by(class_id=context['class_id']).one().id
        other_teacher = User(username='another_teacher', role='teacher', teacher_status='approved')
        other_teacher.set_password('secret123')
        db.session.add(other_teacher)
        db.session.commit()
    url = f"/api/admin/assignments/{context['assignment_id']}/students/{roster_id}/makeup"
    assert client.patch(url, json={'allowed': True}).status_code == 409
    login(client, 'another_teacher')
    assert client.patch(url, json={'allowed': True}).status_code == 404
