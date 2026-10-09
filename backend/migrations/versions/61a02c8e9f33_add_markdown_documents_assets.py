"""Add online Markdown drafts and protected image assets."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "61a02c8e9f33"
down_revision = "7c91a2b4e8d0"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "mysql":
        op.alter_column("assignments", "description", existing_type=sa.Text(), type_=mysql.MEDIUMTEXT(), existing_nullable=True)
    op.create_table(
        "markdown_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id"), nullable=False),
        sa.Column("assignment_id", sa.Integer(), sa.ForeignKey("assignments.id"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("item_key", sa.String(40), nullable=False),
        sa.Column("content", sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("submitted_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("assignment_id", "owner_id", "kind", "item_key", name="uq_markdown_document_scope"),
    )
    op.create_table(
        "markdown_assets",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("markdown_documents.id"), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(40), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_markdown_assets_document_id", "markdown_assets", ["document_id"])


def downgrade():
    op.drop_index("ix_markdown_assets_document_id", table_name="markdown_assets")
    op.drop_table("markdown_assets")
    op.drop_table("markdown_documents")
    if op.get_bind().dialect.name == "mysql":
        op.alter_column("assignments", "description", existing_type=mysql.MEDIUMTEXT(), type_=sa.Text(), existing_nullable=True)
