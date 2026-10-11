from pathlib import Path

from app.extensions import db
from app.models import Assignment, ClassRoster, Course, CourseClass, CourseMember, MarkdownAsset, User
from test_markdown_documents import context, image_bytes, login, open_draft, save, upload_image


def test_student_library_upload_delete_and_role_isolation(client, context):
    assert client.get('/api/student/images').status_code == 403
    login(client, 'OS202601-06')
    response = client.post('/api/student/images', data={'file': (image_bytes(), 'personal.png')})
    assert response.status_code == 201
    image = response.json['asset']
    assert client.get('/api/student/images').json['assets'][0]['id'] == image['id']
    assert client.get(image['url']).status_code == 200
    assert client.get('/api/teacher/images').status_code == 403
    login(client, 'outsider')
    assert client.get('/api/student/images').json['assets'] == []
    assert client.get(image['url']).status_code == 404
    assert client.delete(f"/api/student/images/{image['id']}").status_code == 404
    login(client, 'teacher1')
    assert client.get(image['url']).status_code == 404
    assert client.delete(f"/api/student/images/{image['id']}").status_code == 403
    login(client, 'OS202601-06')
    assert client.delete(f"/api/student/images/{image['id']}").status_code == 200
    assert client.get(image['url']).status_code == 404
    assert list(context['root'].rglob('*.png')) == []


def test_student_reuses_image_across_teachers_but_only_submitted_snapshots_grant_access(client, context):
    with client.application.app_context():
        teacher = User(username='teacher2', role='teacher', teacher_status='approved')
        teacher.set_password('secret123')
        db.session.add(teacher)
        db.session.flush()
        course = Course(name='Next', code='NEXT', semester='2027', teacher_id=teacher.id)
        db.session.add(course)
        db.session.flush()
        course_class = CourseClass(course_id=course.id, name='Next', alias='NEXT27', invite_code='NEXT27')
        db.session.add(course_class)
        db.session.flush()
        db.session.add(CourseMember(class_id=course_class.id, course_id=course.id, user_id=context['student_id'], role='student'))
        db.session.add(ClassRoster(class_id=course_class.id, student_id='NEXT27-01', student_no='01', student_name='Alice', matched_user_id=context['student_id']))
        assignment = Assignment(class_id=course_class.id, course_id=course.id, title='Next report', code='next',
                                status='published', file_rules_json=context['payload']['file_rules'],
                                submission_requirements_json=context['payload']['submission_requirements'])
        db.session.add(assignment)
        db.session.commit()
        next_context = {**context, 'class_id': course_class.id, 'assignment_id': assignment.id}
    login(client, 'OS202601-06')
    document = open_draft(client, context)
    image = upload_image(client, document)
    assert client.get('/api/student/images').json['assets'][0]['id'] == image['id']
    document = save(client, document, f"![复用]({image['url']})")
    login(client, 'teacher1')
    assert client.get(image['url']).status_code == 404
    login(client, 'OS202601-06')
    assert client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission").status_code == 200
    login(client, 'teacher1')
    assert client.get(image['url']).status_code == 200
    login(client, 'teacher2')
    assert client.get(image['url']).status_code == 404
    login(client, 'OS202601-06')
    next_document = save(client, open_draft(client, next_context), document['content'])
    assert client.delete(f"/api/student/images/{image['id']}").status_code == 409
    login(client, 'teacher2')
    assert client.get(image['url']).status_code == 404
    login(client, 'OS202601-06')
    response = client.post(f"/api/assignments/{next_context['assignment_id']}/confirm-submission")
    assert response.status_code == 200, response.json
    assert response.json['assignment']['submissions'][0]['original_filename'] == 'NEXT27-01_next.md'
    save(client, document, '无图片的新草稿')
    save(client, next_document, '也无图片')
    assert client.delete(f"/api/student/images/{image['id']}").status_code == 409  # immutable old snapshots
    login(client, 'teacher2')
    assert client.get(image['url']).status_code == 200
    login(client, 'outsider')
    assert client.get(image['url']).status_code == 404
    with client.application.app_context():
        assert MarkdownAsset.query.count() == 1
    assert len(list(context['root'].rglob('*.png'))) == 1


def test_student_library_upload_validation_and_total_quota(client, context):
    login(client, 'OS202601-06')
    from io import BytesIO
    assert client.post('/api/student/images', data={'file': (BytesIO(b'bad'), 'bad.png')}).status_code == 400
    with client.application.app_context():
        for index in range(1000):
            db.session.add(MarkdownAsset(id=f'{index:032x}', student_user_id=context['student_id'],
                                        original_filename='quota.png', file_path='quota.png', mime_type='image/png', file_size=1))
        db.session.commit()
    response = client.post('/api/student/images', data={'file': (image_bytes(), 'over.png')})
    assert response.status_code == 400 and '上限' in response.json['message']


def test_local_markdown_upload_records_library_references_without_opening_editor(client, context):
    from io import BytesIO
    foreign = client.post('/api/teacher/images', data={'file': (image_bytes(), 'foreign.png')}).json['asset']
    login(client, 'OS202601-06')
    image = client.post('/api/student/images', data={'file': (image_bytes(), 'local.png')}).json['asset']
    content = f"![本地图]({image['url']})".encode('utf-8')
    url = f"/api/assignments/{context['assignment_id']}"
    forged = f"![不可冒用]({foreign['url']})".encode('utf-8')
    assert client.post(url + '/submissions', data={'item_key': 'report', 'file': (BytesIO(forged), 'OS202601-06_r1.md')}).status_code == 201
    assert client.post(url + '/confirm-submission').status_code == 400
    assert client.post(url + '/submissions', data={'item_key': 'report', 'file': (BytesIO(content), 'OS202601-06_r1.md')}).status_code == 201
    assert client.post(url + '/confirm-submission').status_code == 200
    assert client.delete(f"/api/student/images/{image['id']}").status_code == 409
    login(client, 'teacher1')
    assert client.get(image['url']).status_code == 200


def test_student_reused_report_image_count_limit(client, context):
    login(client, 'OS202601-06')
    document = open_draft(client, context)
    with client.application.app_context():
        path = Path(context['root']) / 'fixture.png'
        path.write_bytes(image_bytes().read())
        ids = [f'{index:032x}' for index in range(51)]
        for key in ids:
            db.session.add(MarkdownAsset(id=key, student_user_id=context['student_id'], original_filename='fixture.png',
                                        file_path='fixture.png', mime_type='image/png', file_size=path.stat().st_size))
        db.session.commit()
    save(client, document, '\n'.join(f'![图](/api/assets/{key}/content)' for key in ids))
    response = client.post(f"/api/assignments/{context['assignment_id']}/confirm-submission")
    assert response.status_code == 400 and '50' in response.json['message']
