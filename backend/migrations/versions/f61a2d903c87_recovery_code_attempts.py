"""Bound verification attempts for short recovery codes."""
from alembic import op
import sqlalchemy as sa


revision = "f61a2d903c87"
down_revision = "e5205c637aa"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("account_recoveries") as batch:
        batch.add_column(sa.Column("binding_attempts", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("reset_attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("account_recoveries") as batch:
        batch.drop_column("reset_attempts")
        batch.drop_column("binding_attempts")
