from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable
import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models import Assignment, AssignmentRead, CourseClass, Submission
from test_assignments import _create_class_with_student


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
        assignment = Assignment(course_id=db.session.get(CourseClass, class_id).course_id, class_id=class_id, title="Legacy", code="legacy", file_rules_json=rules)
        db.session.add(assignment)
        db.session.flush()
        submission = Submission(assignment_id=assignment.id, student_user_id=student_id, original_filename="legacy.md", file_path="legacy.md", file_size=0)
        db.session.add(submission)
        db.session.commit()
        assignment_id, submission_id = assignment.id, submission.id
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
        assert db.session.get(Submission, submission_id).submission_item_key == "main"
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
