"""add grocery restock items (the household's "Out of" list)

Revision ID: cef5a4007416
Revises: fd1edcc9404e
Create Date: 2026-10-15 23:10:00

"""

import sqlalchemy as sa
from alembic import op

import mealie.db.migration_types

# revision identifiers, used by Alembic.
revision = "cef5a4007416"
down_revision: str | None = "fd1edcc9404e"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    op.create_table(
        "grocery_restock_items",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("group_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("household_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("food_id", mealie.db.migration_types.GUID(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("store", sa.String(), nullable=True),
        sa.Column("note", sa.String(), nullable=False),
        sa.Column("added_by", sa.String(), nullable=False),
        sa.Column("shopping_list_item_id", mealie.db.migration_types.GUID(), nullable=True),
        sa.Column("week_start", sa.Date(), nullable=True),
        sa.Column("bought_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["food_id"],
            ["ingredient_foods.id"],
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("grocery_restock_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_grocery_restock_items_bought_at"), ["bought_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_grocery_restock_items_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_grocery_restock_items_food_id"), ["food_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_grocery_restock_items_group_id"), ["group_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_grocery_restock_items_household_id"), ["household_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_grocery_restock_items_shopping_list_item_id"), ["shopping_list_item_id"], unique=False
        )


def downgrade():
    with op.batch_alter_table("grocery_restock_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_grocery_restock_items_shopping_list_item_id"))
        batch_op.drop_index(batch_op.f("ix_grocery_restock_items_household_id"))
        batch_op.drop_index(batch_op.f("ix_grocery_restock_items_group_id"))
        batch_op.drop_index(batch_op.f("ix_grocery_restock_items_food_id"))
        batch_op.drop_index(batch_op.f("ix_grocery_restock_items_created_at"))
        batch_op.drop_index(batch_op.f("ix_grocery_restock_items_bought_at"))

    op.drop_table("grocery_restock_items")
