"""Per-student makeup permissions and preserved submission state."""
from alembic import op
import sqlalchemy as sa

revision = "a7c31d9e420b"
down_revision = "f5b20c8d316a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("assignment_student_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("assignments.id"), nullable=False),
        sa.Column("student_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("makeup_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("preserved_submission_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("assignment_id", "student_user_id", name="uq_assignment_student_override"))
    op.create_index("ix_assignment_student_overrides_assignment_id", "assignment_student_overrides", ["assignment_id"])
    with op.batch_alter_table("submissions") as batch:
        batch.add_column(sa.Column("is_makeup", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("effective_submitted_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("submissions") as batch:
        batch.drop_column("effective_submitted_at")
        batch.drop_column("is_makeup")
    op.drop_table("assignment_student_overrides")
