"""Store verified recovery emails and pending verification codes."""
from alembic import op
import sqlalchemy as sa


revision = "e5205c637aa"
down_revision = "d0f64121753e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_recoveries",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("email", sa.String(254), unique=True),
        sa.Column("pending_email", sa.String(254)),
        sa.Column("binding_digest", sa.String(64)),
        sa.Column("binding_expires_at", sa.DateTime()),
        sa.Column("reset_digest", sa.String(64)),
        sa.Column("reset_expires_at", sa.DateTime()),
        sa.Column("password_reset_at", sa.DateTime()),
    )


def downgrade():
    op.drop_table("account_recoveries")
