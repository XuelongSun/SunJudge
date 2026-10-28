from sqlalchemy import inspect, text, Table, MetaData
from sqlalchemy.schema import CreateTable
import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models import Assignment, AssignmentRead, CourseClass, Submission, utc_now
from test_assignments import _create_class_with_student


def test_teacher_library_migration_preserves_and_backfills_old_assets(tmp_path):
    class MigrationConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'library.sqlite'}"
    app = create_app(MigrationConfig)
    runner = app.test_cli_runner()
    result = runner.invoke(args=['db', 'upgrade', 'c8b4e2d1f690'])
    assert result.exit_code == 0, result.output
    class_id, teacher_id, student_id, _ = _create_class_with_student(app)
    with app.app_context():
        from app.models import MarkdownDocument
        teacher_doc = MarkdownDocument(owner_id=teacher_id, class_id=class_id, kind='description', content='旧说明')
        student_doc = MarkdownDocument(owner_id=student_id, class_id=class_id, kind='submission', content='旧报告')
        db.session.add_all([teacher_doc, student_doc])
        db.session.flush()
        for doc, key in [(teacher_doc, 'a' * 32), (student_doc, 'b' * 32)]:
            db.session.execute(text('''INSERT INTO markdown_assets
                (id, document_id, original_filename, file_path, mime_type, file_size, created_at)
                VALUES (:id, :document_id, 'old.png', 'unchanged/old.png', 'image/png', 100, CURRENT_TIMESTAMP)'''),
                {'id': key, 'document_id': doc.id})
        db.session.commit()
    result = runner.invoke(args=['db', 'upgrade'])
    assert result.exit_code == 0, result.output
    with app.app_context():
        from app.models import MarkdownAsset
        teacher_image = db.session.get(MarkdownAsset, 'a' * 32)
        assert teacher_image.teacher_id == teacher_id
        assert teacher_image.file_path == 'unchanged/old.png'
        student_image = db.session.get(MarkdownAsset, 'b' * 32)
        assert student_image.teacher_id is None
        assert student_image.student_user_id == student_id
        assert teacher_image.student_user_id is None
        assert next(col for col in inspect(db.engine).get_columns('markdown_assets') if col['name'] == 'document_id')['nullable']
        db.session.remove()
        db.engine.dispose()


def test_removing_legacy_main_flags_preserves_description_draft_and_all_attachments(tmp_path):
    class MigrationConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'materials.sqlite'}"
    app = create_app(MigrationConfig)
    runner = app.test_cli_runner()
    result = runner.invoke(args=['db', 'upgrade', 'b8d42e0f531c'])
    assert result.exit_code == 0, result.output
    class_id, teacher_id, _, _ = _create_class_with_student(app)
    with app.app_context():
        from app.models import MarkdownDocument
        assignment = Assignment(class_id=class_id, course_id=db.session.get(CourseClass, class_id).course_id,
                                title='Old materials', code='old', description='原主说明', description_format='markdown',
                                code_templates_json=[
                                    {'id': 'main', 'filename': 'main.md', 'content': '\ufeff# 主正文', 'file_size': 12, 'is_main': True},
                                    {'id': 'extra', 'filename': 'notes.md', 'content': '# 附件', 'file_size': 8, 'is_main': False}])
        db.session.add(assignment)
        db.session.flush()
        assignment_id = assignment.id
        document = MarkdownDocument(assignment_id=assignment_id, owner_id=teacher_id, class_id=class_id,
                                    kind='description', content='尚未发布的说明草稿', revision=3)
        db.session.add(document)
        db.session.commit()
        document_id = document.id
    result = runner.invoke(args=['db', 'upgrade'])
    assert result.exit_code == 0, result.output
    with app.app_context():
        db.session.expire_all()
        assignment = db.session.get(Assignment, assignment_id)
        assert assignment.description == '原主说明' and assignment.description_format == 'markdown'
        assert assignment.code_templates_json == [
            {'id': 'main', 'filename': 'main.md', 'content': '\ufeff# 主正文', 'file_size': 12, 'purpose': ''},
            {'id': 'extra', 'filename': 'notes.md', 'content': '# 附件', 'file_size': 8, 'purpose': ''}]
        document = db.session.get(MarkdownDocument, document_id)
        assert document.content == '尚未发布的说明草稿' and document.revision == 3
        db.session.remove()
        db.engine.dispose()


@pytest.mark.parametrize("unnamed_legacy_constraint", [False, True])
def test_legacy_null_backfill_and_fresh_migration_match_models(tmp_path, unnamed_legacy_constraint):
    class MigrationConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'migration.sqlite'}"

    app = create_app(MigrationConfig)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["db", "upgrade", "61a02c8e9f33"])
    assert result.exit_code == 0, result.output
    class_id, _, student_id, _ = _create_class_with_student(app)
    with app.app_context():
        rules = {"allowed_extensions": [".md"], "max_size_mb": 2, "filename_template": "{student_id}_legacy.md"}
        legacy = Table('assignments', MetaData(), autoload_with=db.engine)
        result = db.session.execute(legacy.insert().values(
            course_id=db.session.get(CourseClass, class_id).course_id, class_id=class_id,
            title='Legacy', code='legacy', type='homework', description_format='markdown', allow_late=False,
            max_score=100, file_rules_json=rules, submission_requirements_json=[], rubric_format='markdown',
            program_evaluations_json=[], ai_evaluations_json=[], status='draft', created_at=utc_now(), updated_at=utc_now()))
        assignment_id = result.lastrowid
        # Write the historical shape without columns introduced by later models.
        result = db.session.execute(text("""INSERT INTO submissions
            (assignment_id, student_user_id, submitted_at, original_filename, file_path, file_size, status, validation_result_json, submission_item_key)
            VALUES (:assignment_id, :student_id, CURRENT_TIMESTAMP, 'legacy.md', 'legacy.md', 0, 'submitted', '{}', 'main')"""),
            {"assignment_id": assignment_id, "student_id": student_id})
        submission_id = result.lastrowid
        db.session.commit()
        db.session.execute(text("UPDATE assignments SET submission_requirements_json=NULL, program_evaluations_json=NULL, ai_evaluations_json=NULL"))
        db.session.execute(text("UPDATE submissions SET submission_item_key=NULL"))
        if unnamed_legacy_constraint:
            # Simulate the historical local SQLite table, without deleting any read rows.
            assert db.session.query(AssignmentRead).count() == 0
            db.session.execute(text("DROP TABLE assignment_reads"))
            ddl = str(CreateTable(AssignmentRead.__table__).compile(dialect=db.engine.dialect))
            ddl = ddl.replace("CONSTRAINT uq_assignment_reads_assignment_student UNIQUE", "UNIQUE")
            db.session.execute(text(ddl))
        db.session.add(AssignmentRead(assignment_id=assignment_id, student_user_id=student_id))
        db.session.commit()
    for args in (["db", "upgrade"], ["db", "check"]):
        result = runner.invoke(args=args)
        assert result.exit_code == 0, result.output
    with app.app_context():
        db.session.expire_all()
        assignment = db.session.get(Assignment, assignment_id)
        assert assignment.submission_requirements_json[0]["filename_template"] == rules["filename_template"]
        assert assignment.submission_requirements_json[0]["allowed_extensions"] == [".md"]
        assert assignment.program_evaluations_json == assignment.ai_evaluations_json == []
        assert assignment.code_templates_json == []
        assert db.session.get(Submission, submission_id).submission_item_key == "main"
        assert db.session.get(Submission, submission_id).is_makeup is False
        assert db.session.get(Submission, submission_id).effective_submitted_at is None
        assert "assignment_student_overrides" in inspect(db.engine).get_table_names()
        assert db.session.query(AssignmentRead).count() == 1
        for table, names in {"assignments": {"submission_requirements_json", "program_evaluations_json", "ai_evaluations_json"}, "submissions": {"submission_item_key"}}.items():
            assert all(not col["nullable"] for col in inspect(db.engine).get_columns(table) if col["name"] in names)
    # Exercise reversal and rebuilding an entirely fresh schema, not just create_all.
    for args in (["db", "downgrade", "base"], ["db", "upgrade"], ["db", "check"]):
        result = runner.invoke(args=args)
        assert result.exit_code == 0, result.output
    with app.app_context():
        db.session.remove()
        db.engine.dispose()
