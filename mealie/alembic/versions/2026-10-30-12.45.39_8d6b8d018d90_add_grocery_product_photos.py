"""add grocery product photos

Revision ID: 8d6b8d018d90
Revises: ac86da08ee79
Create Date: 2026-10-30 12:45:39.887476

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "8d6b8d018d90"
down_revision: str | None = "ac86da08ee79"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    with op.batch_alter_table("grocery_products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("photo", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("photo_source", sa.String(), nullable=True))


def downgrade():
    with op.batch_alter_table("grocery_products", schema=None) as batch_op:
        batch_op.drop_column("photo_source")
        batch_op.drop_column("photo")
