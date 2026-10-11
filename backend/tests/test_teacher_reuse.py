from datetime import UTC, datetime

from app.extensions import db
from app.models import Assignment, AssignmentGrade, ClassRoster, Course, CourseClass, CourseMember, GradingResult, MarkdownAsset, Submission, User
from app.services.feedback_report import report_date
from app.services.markdown_documents import unused_image_assets
from test_assignments import _create_class_with_student, _login
from test_markdown_documents import context, image_bytes, login, open_draft, save, upload_image
from test_roster_import import exported_roster


def target_class(client):
    response = client.post('/api/admin/classes', json={"class": {"alias": "NEXT27"}})
    assert response.status_code == 201
    return response.json['class']['id']


def test_copy_configuration_shares_images_but_never_copies_student_work(client, context):
    document = open_draft(client, context, 'description')
    image = upload_image(client, document)
    text = f"![共享]({image['url']})"
    document = save(client, document, text)
    response = client.patch(f"/api/admin/assignments/{context['assignment_id']}", json={
        "description": text, "markdown_document_id": document['id']})
    assert response.status_code == 200
    source = response.json['assignment']
    target_id = target_class(client)
    with client.application.app_context():
        db.session.add(Submission(assignment_id=context['assignment_id'], student_user_id=context['student_id'],
                                  original_filename='report.md', file_path='fixture.md', file_size=1))
        db.session.add(AssignmentGrade(assignment_id=context['assignment_id'], student_user_id=context['student_id'],
                                     final_score=99, status=GradingResult.STATUS_PUBLISHED))
        db.session.commit()
    response = client.post(f"/api/admin/assignments/{context['assignment_id']}/copy", json={'class_id': target_id})
    assert response.status_code == 201, response.json
    copied = response.json['assignment']
    assert copied['description'] == text and copied['status'] == 'draft' and copied['published_at'] is None
    for field in ('title', 'type', 'description_format', 'deadline', 'allow_late', 'late_policy', 'max_score',
                  'file_rules', 'submission_requirements', 'rubric', 'rubric_format', 'program_evaluations', 'ai_evaluations'):
        assert copied[field] == source[field]
    assert copied['submission_count'] == copied['feedback_count'] == 0
    with client.application.app_context():
        assert MarkdownAsset.query.count() == 1
        assert Submission.query.filter_by(assignment_id=copied['id']).count() == 0
        assert AssignmentGrade.query.filter_by(assignment_id=copied['id']).count() == 0
        target = db.session.get(CourseClass, target_id)
        db.session.add(CourseMember(class_id=target_id, course_id=target.course_id, user_id=context['outsider_id'], role='student'))
        db.session.commit()
    login(client, 'outsider')
    assert client.get(image['url']).status_code == 404
    login(client, 'teacher1')
    assert client.delete(f"/api/teacher/images/{image['id']}").status_code == 409
    assert client.post(f"/api/admin/assignments/{copied['id']}/publish").status_code == 200
    assert client.delete(f"/api/admin/assignments/{context['assignment_id']}").status_code == 200
    login(client, 'outsider')
    assert client.get(image['url']).status_code == 200
    login(client, 'OS202601-06')
    assert client.get(image['url']).status_code == 404  # source is gone; target is another class


def test_copy_rejects_foreign_classes_same_class_duplicates_and_students(client, context):
    target_id = target_class(client)
    url = f"/api/admin/assignments/{context['assignment_id']}/copy"
    assert client.post(url, json=['invalid']).status_code == 400
    assert client.post(url, json={'class_id': context['class_id']}).status_code == 400
    assert client.post(url, json={'class_id': target_id}).status_code == 201
    assert client.post(url, json={'class_id': target_id}).status_code == 409
    assert client.post(url, json={'class_id': target_id, 'code': 'r2'}).status_code == 201
    assert client.post(url, json={'class_id': target_id, 'code': '../bad'}).status_code == 400
    with client.application.app_context():
        teacher = User(username='teacher2', role='teacher', teacher_status='approved')
        teacher.set_password('secret123')
        db.session.add(teacher)
        db.session.flush()
        course = Course(name='Other', code='OTHER', semester='2027', teacher_id=teacher.id)
        db.session.add(course)
        db.session.flush()
        other = CourseClass(name='Other', alias='OTHER27', invite_code='OTHER27', course_id=course.id)
        db.session.add(other)
        db.session.commit()
        foreign_id = other.id
    assert client.post(url, json={'class_id': foreign_id}).status_code == 404
    login(client, 'teacher2')
    assert client.post(url, json={'class_id': foreign_id}).status_code == 404
    login(client, 'OS202601-06')
    assert client.post(url, json={'class_id': target_id}).status_code == 403


def test_library_upload_reuse_permissions_deletion_and_cleanup(client, context):
    response = client.post('/api/teacher/images', data={'file': (image_bytes(), 'library.png')})
    assert response.status_code == 201
    image = response.json['asset']
    assert len(client.get('/api/teacher/images').json['assets']) == 1
    assert client.get(image['url']).status_code == 200
    with client.application.app_context():
        assert image['id'] not in {asset.id for asset in unused_image_assets()}
    document = open_draft(client, context, 'description')
    document = save(client, document, f"![库]({image['url']})")
    assert client.patch(f"/api/admin/assignments/{context['assignment_id']}", json={
        'description': document['content'], 'markdown_document_id': document['id']}).status_code == 200
    assert client.delete(f"/api/teacher/images/{image['id']}").status_code == 409
    login(client, 'OS202601-06')
    assert client.get('/api/teacher/images').status_code == 403
    assert client.post('/api/teacher/images', data={'file': (image_bytes(), 'x.png')}).status_code == 403
    student_doc = save(client, open_draft(client, context), f"![不可冒用]({image['url']})")
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 400
    save(client, student_doc, '报告正文')
    login(client, 'teacher1')
    save(client, document, '删除图片引用')
    assert client.patch(f"/api/admin/assignments/{context['assignment_id']}", json={'description': '无图'}).status_code == 200
    assert client.delete(f"/api/teacher/images/{image['id']}").status_code == 200
    assert client.get(image['url']).status_code == 404
    assert list(context['root'].rglob('*.png')) == []


def test_library_cannot_reference_another_teachers_images(client, context):
    image = client.post('/api/teacher/images', data={'file': (image_bytes(), 'private.png')}).json['asset']
    with client.application.app_context():
        teacher = User(username='other', role='teacher', teacher_status='approved')
        teacher.set_password('secret123')
        db.session.add(teacher)
        db.session.commit()
    login(client, 'other')
    assert client.get('/api/teacher/images').json['assets'] == []
    assert client.get(image['url']).status_code == 404
    assert client.delete(f"/api/teacher/images/{image['id']}").status_code == 404
    other_class = target_class(client)
    response = client.post(f'/api/admin/classes/{other_class}/assignments', json={
        **context['payload'], 'description': f"![越权]({image['url']})"})
    assert response.status_code == 400


def test_test_student_separate_review_list_excluded_from_counts_analysis_and_exports(client, context):
    with client.application.app_context():
        roster = ClassRoster.query.filter_by(class_id=context['class_id']).one()
        student = db.session.get(User, context['student_id'])
        roster.student_id = student.student_id = 'OS202601-00'
        roster.student_no = student.student_no = '00'
        db.session.commit()
    url = f"/api/admin/assignments/{context['assignment_id']}/submissions"
    before = client.get(url).json
    assert before['submissions'] == []
    assert len(before['test_submissions']) == 1
    assert before['test_submissions'][0]['roster']['student_no'] == '00'
    assert before['test_submissions'][0]['submission'] is None
    login(client, 'OS202601-00')
    save(client, open_draft(client, context), '测试作业')
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 200
    assert client.get(url).status_code == 403
    login(client, 'teacher1')
    test_row = client.get(url).json['test_submissions'][0]
    submission_id = test_row['submission']['id']
    assert test_row['student_state'] == 'submitted'
    assert test_row['submissions'][0]['id'] == submission_id
    assert client.get(f'/api/admin/submissions/{submission_id}/preview').status_code == 200
    review = client.patch(f'/api/admin/submissions/{submission_id}/grade', json={
        'final_score': 100, 'status': 'published', 'teacher_comment': '测试号反馈'})
    assert review.status_code == 200, review.json
    assignment = client.get(f"/api/admin/classes/{context['class_id']}/assignments").json['assignments'][0]
    assert assignment['submission_count'] == assignment['feedback_count'] == assignment['expected_submission_count'] == 0
    data = client.get(f"/api/admin/assignments/{context['assignment_id']}/submissions").json
    assert data['submissions'] == []
    assert data['test_submissions'][0]['final_score'] == 100
    assert data['test_submissions'][0]['teacher_state'] == 'published'
    assert data['analysis']['expected_count'] == data['analysis']['published_count'] == 0
    assert data['analysis']['average_score'] is None
    assert client.get(f"/api/admin/assignments/{context['assignment_id']}/scoremanager-commands?field=homework").json['export']['exported_count'] == 0
    csv = client.get(f"/api/admin/assignments/{context['assignment_id']}/grades.csv").data.decode('utf-8-sig')
    assert 'OS202601-00' not in csv
    assert client.get(f"/api/admin/classes/{context['class_id']}/roster").json['roster'][0]['student_no'] == '00'
    with client.application.app_context():
        db.session.add(ClassRoster(class_id=context['class_id'], student_no='01',
                                   student_id='OS202601-01', student_name='普通学生'))
        db.session.commit()
    mixed = client.get(url).json
    assert [row['roster']['student_no'] for row in mixed['submissions']] == ['01']
    assert [row['roster']['student_no'] for row in mixed['test_submissions']] == ['00']
    assert mixed['analysis']['expected_count'] == 1
    assert mixed['analysis']['submitted_count'] == mixed['analysis']['published_count'] == 0


def test_deadline_normalized_before_storage_and_feedback(client, context):
    url = f"/api/admin/assignments/{context['assignment_id']}"
    assert client.patch(url, json={'deadline': '2030-10-11T23:59:00+08:00'}).status_code == 200
    with client.application.app_context():
        deadline = db.session.get(Assignment, context['assignment_id']).deadline
        assert deadline.replace(tzinfo=UTC) == datetime(2030, 10, 11, 15, 59, tzinfo=UTC)
        assert report_date(deadline) == '2030-10-11 23:59:00'


def test_roster_preview_append_replace_and_protect_registered(client):
    class_id, _, student_id, _ = _create_class_with_student(client.application)
    _login(client, 'teacher1')
    url = '/api/admin/classes/import-excel'
    def upload(**kwargs):
        return client.post(url, data={'class_id': str(class_id), 'file': (exported_roster(), 'roster.xlsx'), **kwargs})
    assert upload(preview='true').json['student_count'] == 1
    assert len(client.get(f'/api/admin/classes/{class_id}/roster').json['roster']) == 1
    assert upload(mode='append').json['imported_count'] == 1
    with client.application.app_context():
        first = ClassRoster.query.filter_by(class_id=class_id, student_no='01').one()
        first.student_name = '原姓名'
        db.session.add(ClassRoster(class_id=class_id, student_no='02', student_id='OS202601-02', student_name='移除'))
        db.session.commit()
    assert upload(mode='append').json['updated_count'] == 0
    response = upload(mode='replace')
    assert response.status_code == 201 and response.json['removed_count'] == 1
    assert response.json['preserved_registered_count'] == 1
    roster = client.get(f'/api/admin/classes/{class_id}/roster').json['roster']
    assert len(roster) == 2 and next(row for row in roster if row['student_no'] == '01')['student_name'] == '测试学生'
    with client.application.app_context():
        first = ClassRoster.query.filter_by(class_id=class_id, student_no='01').one()
        first.matched_user_id = student_id
        first.student_name = '已注册的不同姓名'
        db.session.commit()
    assert upload(mode='replace').status_code == 409
    assert upload(mode='invalid').status_code == 400
