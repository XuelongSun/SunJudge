"""add assignment reads

Revision ID: 7c91a2b4e8d0
Revises: 0b7d4c2a9e11
Create Date: 2026-08-18 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "7c91a2b4e8d0"
down_revision = "0b7d4c2a9e11"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "assignment_reads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("student_user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"]),
        sa.ForeignKeyConstraint(["student_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assignment_id", "student_user_id", name="uq_assignment_reads_assignment_student"),
    )


def downgrade():
    op.drop_table("assignment_reads")
