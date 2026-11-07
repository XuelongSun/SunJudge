"""Keep authorized placeholders for retired report images."""
from alembic import op
import sqlalchemy as sa

revision = 'd0f64121753e'
down_revision = 'c9e53f10642d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('markdown_assets') as batch:
        batch.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('markdown_assets') as batch:
        batch.drop_column('deleted_at')
