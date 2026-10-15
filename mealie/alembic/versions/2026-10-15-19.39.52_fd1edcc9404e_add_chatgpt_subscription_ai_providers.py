"""add chatgpt subscription ai providers

Revision ID: fd1edcc9404e
Revises: 7065e077f1ed
Create Date: 2026-10-15 19:39:52

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "fd1edcc9404e"
down_revision: str | None = "7065e077f1ed"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    with op.batch_alter_table("ai_providers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("provider_type", sa.String(), nullable=False, server_default="openai"))
        batch_op.add_column(sa.Column("chatgpt_credential", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("ai_providers", schema=None) as batch_op:
        batch_op.drop_column("chatgpt_credential")
        batch_op.drop_column("provider_type")
