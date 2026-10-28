"""add cookbook imports, the recipes found in each imported cookbook file

Revision ID: b3d1c2e4f5a6
Revises: 16896de19ab0
Create Date: 2026-10-27 12:00:00

"""

import sqlalchemy as sa
from alembic import op

import mealie.db.migration_types

# revision identifiers, used by Alembic.
revision = "b3d1c2e4f5a6"
down_revision: str | None = "16896de19ab0"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    op.create_table(
        "cookbook_imports",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("group_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("unread_pages", sa.String(), nullable=False),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "fingerprint", name="cookbook_imports_group_id_fingerprint_key"),
    )
    with op.batch_alter_table("cookbook_imports", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cookbook_imports_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_cookbook_imports_fingerprint"), ["fingerprint"], unique=False)
        batch_op.create_index(batch_op.f("ix_cookbook_imports_group_id"), ["group_id"], unique=False)

    op.create_table(
        "cookbook_import_recipes",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("cookbook_import_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("first_page", sa.Integer(), nullable=False),
        sa.Column("last_page", sa.Integer(), nullable=False),
        sa.Column("item", sa.Integer(), nullable=False),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["cookbook_import_id"],
            ["cookbook_imports.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cookbook_import_id", "first_page", "item", name="cookbook_import_recipes_location_key"),
    )
    with op.batch_alter_table("cookbook_import_recipes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_cookbook_import_recipes_cookbook_import_id"), ["cookbook_import_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_cookbook_import_recipes_created_at"), ["created_at"], unique=False)


def downgrade():
    with op.batch_alter_table("cookbook_import_recipes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cookbook_import_recipes_created_at"))
        batch_op.drop_index(batch_op.f("ix_cookbook_import_recipes_cookbook_import_id"))

    op.drop_table("cookbook_import_recipes")

    with op.batch_alter_table("cookbook_imports", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cookbook_imports_group_id"))
        batch_op.drop_index(batch_op.f("ix_cookbook_imports_fingerprint"))
        batch_op.drop_index(batch_op.f("ix_cookbook_imports_created_at"))

    op.drop_table("cookbook_imports")
