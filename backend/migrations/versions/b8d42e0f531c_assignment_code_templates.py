"""Store small Python starter files with assignment configuration."""
from alembic import op
import sqlalchemy as sa

revision = 'b8d42e0f531c'
down_revision = 'a7c31d9e420b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('assignments') as batch:
        batch.add_column(sa.Column('code_templates_json', sa.JSON(), nullable=True))
    op.execute("UPDATE assignments SET code_templates_json = '[]' WHERE code_templates_json IS NULL")
    with op.batch_alter_table('assignments') as batch:
        batch.alter_column('code_templates_json', existing_type=sa.JSON(), nullable=False)


def downgrade():
    with op.batch_alter_table('assignments') as batch:
        batch.drop_column('code_templates_json')
