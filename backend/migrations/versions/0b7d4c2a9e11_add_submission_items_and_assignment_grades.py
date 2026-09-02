"""add submission items and assignment grades

Revision ID: 0b7d4c2a9e11
Revises: f2a7c9e5d4b3
Create Date: 2026-08-17 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "0b7d4c2a9e11"
down_revision = "f2a7c9e5d4b3"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assignments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("submission_requirements_json", sa.JSON(), nullable=True))

    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("submission_item_key", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("submission_item_label", sa.String(length=120), nullable=True))

    op.execute(
        """
        UPDATE assignments
        SET submission_requirements_json = json_array(
            json_object(
                'key', 'main',
                'label', '提交文件',
                'allowed_extensions', json_extract(file_rules_json, '$.allowed_extensions'),
                'max_size_mb', json_extract(file_rules_json, '$.max_size_mb'),
                'filename_template', json_extract(file_rules_json, '$.filename_template'),
                'required', 1
            )
        )
        WHERE submission_requirements_json IS NULL
        """
    )
    op.execute("UPDATE submissions SET submission_item_key = 'main' WHERE submission_item_key IS NULL")
    op.execute("UPDATE submissions SET submission_item_label = '提交文件' WHERE submission_item_label IS NULL")

    op.create_table(
        "assignment_grades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("student_user_id", sa.Integer(), nullable=False),
        sa.Column("auto_score", sa.Float(), nullable=True),
        sa.Column("llm_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("teacher_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("llm_details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["student_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", "student_user_id", name="uq_assignment_grades_assignment_student"),
    )


def downgrade():
    op.drop_table("assignment_grades")
    with op.batch_alter_table("submissions", schema=None) as batch_op:
        batch_op.drop_column("submission_item_label")
        batch_op.drop_column("submission_item_key")
    with op.batch_alter_table("assignments", schema=None) as batch_op:
        batch_op.drop_column("submission_requirements_json")
