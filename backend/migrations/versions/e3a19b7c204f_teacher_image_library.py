"""Share teacher images across assignment descriptions without copying files."""
from alembic import op
import sqlalchemy as sa

revision = "e3a19b7c204f"
down_revision = "c8b4e2d1f690"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("markdown_assets") as batch:
        batch.alter_column("document_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("teacher_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_markdown_assets_teacher_id", "users", ["teacher_id"], ["id"])
        batch.create_index("ix_markdown_assets_teacher_id", ["teacher_id"])
    # Existing description images automatically become their teacher's library.
    op.execute("""UPDATE markdown_assets SET teacher_id = (
        SELECT owner_id FROM markdown_documents WHERE markdown_documents.id = markdown_assets.document_id
        AND markdown_documents.kind = 'description')""")


def downgrade():
    # Library-only images cannot fit the old schema; never silently discard them.
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM markdown_assets WHERE document_id IS NULL")).scalar():
        raise RuntimeError("Remove library-only images before downgrading.")
    with op.batch_alter_table("markdown_assets") as batch:
        batch.drop_index("ix_markdown_assets_teacher_id")
        batch.drop_constraint("fk_markdown_assets_teacher_id", type_="foreignkey")
        batch.drop_column("teacher_id")
        batch.alter_column("document_id", existing_type=sa.Integer(), nullable=False)
