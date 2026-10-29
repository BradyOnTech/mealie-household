"""add grocery product barcodes

Revision ID: ac86da08ee79
Revises: d7a4e9c1b2f3
Create Date: 2026-10-29 15:21:20.793162

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "ac86da08ee79"
down_revision: str | None = "d7a4e9c1b2f3"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    with op.batch_alter_table("grocery_products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("barcode", sa.String(length=14), nullable=True))
        batch_op.create_index(batch_op.f("ix_grocery_products_barcode"), ["barcode"], unique=False)


def downgrade():
    with op.batch_alter_table("grocery_products", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_grocery_products_barcode"))
        batch_op.drop_column("barcode")
