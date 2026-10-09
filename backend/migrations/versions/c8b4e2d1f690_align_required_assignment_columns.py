"""Align four required columns with the ORM after backfilling legacy NULLs."""
from alembic import op
import sqlalchemy as sa

revision = "c8b4e2d1f690"
down_revision = "61a02c8e9f33"
branch_labels = None
depends_on = None


def upgrade():
    # Keep the original assignment's naming and file rules for legacy single-file work.
    op.execute("""
        UPDATE assignments
        SET submission_requirements_json = json_array(json_object(
            'key', 'main', 'label', '提交文件',
            'allowed_extensions', json_extract(file_rules_json, '$.allowed_extensions'),
            'max_size_mb', json_extract(file_rules_json, '$.max_size_mb'),
            'filename_template', json_extract(file_rules_json, '$.filename_template'),
            'required', 1
        ))
        WHERE submission_requirements_json IS NULL
    """)
    assignments = sa.table("assignments", sa.column("program_evaluations_json", sa.JSON()), sa.column("ai_evaluations_json", sa.JSON()))
    for name in ("program_evaluations_json", "ai_evaluations_json"):
        op.execute(assignments.update().where(assignments.c[name].is_(None)).values({name: []}))
    op.execute("UPDATE submissions SET submission_item_key = 'main' WHERE submission_item_key IS NULL")
    with op.batch_alter_table("assignments") as batch:
        for name in ("submission_requirements_json", "program_evaluations_json", "ai_evaluations_json"):
            batch.alter_column(name, existing_type=sa.JSON(), existing_nullable=True, nullable=False)
    with op.batch_alter_table("submissions") as batch:
        batch.alter_column("submission_item_key", existing_type=sa.String(80), existing_nullable=True, nullable=False)
    # Some legacy SQLite databases have the right UNIQUE columns but no name.
    # Normalize the constraint rather than accepting a permanent db-check diff.
    columns = ["assignment_id", "student_user_id"]
    expected = "uq_assignment_reads_assignment_student"
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("assignment_reads")
    matching = [item for item in constraints if item["column_names"] == columns]
    if not any(item["name"] == expected for item in matching):
        convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
        with op.batch_alter_table("assignment_reads", naming_convention=convention) as batch:
            for item in matching:
                batch.drop_constraint(item["name"] or "uq_assignment_reads_assignment_id", type_="unique")
            batch.create_unique_constraint(expected, columns)


def downgrade():
    with op.batch_alter_table("submissions") as batch:
        batch.alter_column("submission_item_key", existing_type=sa.String(80), existing_nullable=False, nullable=True)
    with op.batch_alter_table("assignments") as batch:
        for name in ("submission_requirements_json", "program_evaluations_json", "ai_evaluations_json"):
            batch.alter_column(name, existing_type=sa.JSON(), existing_nullable=False, nullable=True)
