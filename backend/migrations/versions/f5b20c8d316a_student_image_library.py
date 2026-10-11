"""Promote student report images to a private reusable library."""
from alembic import op
import sqlalchemy as sa

revision = "f5b20c8d316a"
down_revision = "e3a19b7c204f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("markdown_assets") as batch:
        batch.add_column(sa.Column("student_user_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_markdown_assets_student_user_id", "users", ["student_user_id"], ["id"])
        batch.create_index("ix_markdown_assets_student_user_id", ["student_user_id"])
    op.execute("""UPDATE markdown_assets SET student_user_id = (
        SELECT owner_id FROM markdown_documents WHERE markdown_documents.id = markdown_assets.document_id
        AND markdown_documents.kind = 'submission') WHERE teacher_id IS NULL""")


def downgrade():
    # Restoring document-only permissions would break cross-document image references.
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM markdown_assets WHERE student_user_id IS NOT NULL")).scalar():
        raise RuntimeError("Student library assets must be migrated back to document scope before downgrading.")
    with op.batch_alter_table("markdown_assets") as batch:
        batch.drop_index("ix_markdown_assets_student_user_id")
        batch.drop_constraint("fk_markdown_assets_student_user_id", type_="foreignkey")
        batch.drop_column("student_user_id")
