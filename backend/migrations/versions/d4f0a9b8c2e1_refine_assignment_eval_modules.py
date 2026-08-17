"""refine assignment types and evaluation modules

Revision ID: d4f0a9b8c2e1
Revises: a3c9d2f6e7b1
Create Date: 2026-08-09 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "d4f0a9b8c2e1"
down_revision = "a3c9d2f6e7b1"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assignments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("description_format", sa.String(length=20), nullable=False, server_default="text"))
        batch_op.add_column(sa.Column("rubric_format", sa.String(length=20), nullable=False, server_default="text"))
        batch_op.add_column(sa.Column("program_evaluations_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("ai_evaluations_json", sa.JSON(), nullable=True))

    op.execute("UPDATE assignments SET type = 'homework' WHERE type IN ('programming', 'report', 'mixed')")
    op.execute("UPDATE assignments SET program_evaluations_json = '[]' WHERE program_evaluations_json IS NULL")
    op.execute("UPDATE assignments SET ai_evaluations_json = '[]' WHERE ai_evaluations_json IS NULL")


def downgrade():
    op.execute("UPDATE assignments SET type = 'report' WHERE type IN ('homework', 'lab_report')")
    with op.batch_alter_table("assignments", schema=None) as batch_op:
        batch_op.drop_column("ai_evaluations_json")
        batch_op.drop_column("program_evaluations_json")
        batch_op.drop_column("rubric_format")
        batch_op.drop_column("description_format")
