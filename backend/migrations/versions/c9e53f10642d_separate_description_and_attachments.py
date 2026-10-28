"""Retire main-file flags without changing descriptions or dropping attachments."""
from alembic import op
import sqlalchemy as sa

revision = 'c9e53f10642d'
down_revision = 'b8d42e0f531c'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    metadata = sa.MetaData()
    assignments = sa.Table('assignments', metadata, autoload_with=connection)
    assignment_ids = connection.execute(sa.select(assignments.c.id)).scalars().all()
    for assignment_id in assignment_ids:
        row = connection.execute(sa.select(assignments.c.id, assignments.c.code_templates_json).where(assignments.c.id == assignment_id)).mappings().one()
        files = row['code_templates_json'] or []
        # The old UI auto-selected the first Markdown. It is not reliable evidence
        # that its content should replace the teacher's independent description.
        attachments = [{key: value for key, value in item.items() if key != 'is_main'} for item in files]
        for item in attachments:
            item.setdefault('purpose', '')
        connection.execute(assignments.update().where(assignments.c.id == row['id']).values(code_templates_json=attachments))


def downgrade():
    # Keep independent descriptions and all attachments; there is no lost schema to rebuild.
    pass
