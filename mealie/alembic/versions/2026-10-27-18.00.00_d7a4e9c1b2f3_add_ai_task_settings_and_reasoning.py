"""add per-task AI settings and provider reasoning effort

Revision ID: d7a4e9c1b2f3
Revises: b3d1c2e4f5a6
Create Date: 2026-10-27 18:00:00

"""

import sqlalchemy as sa
from alembic import op

import mealie.db.migration_types

# revision identifiers, used by Alembic.
revision = "d7a4e9c1b2f3"
down_revision: str | None = "b3d1c2e4f5a6"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    # Nullable with no default: existing providers keep their current behavior (ChatGPT: low, API key: not sent)
    with op.batch_alter_table("ai_providers", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reasoning_effort", sa.String(), nullable=True))

    op.create_table(
        "ai_task_settings",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("settings_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("task", sa.String(), nullable=False),
        sa.Column("provider_id", mealie.db.migration_types.GUID(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("reasoning_effort", sa.String(), nullable=True),
        sa.Column("image_provider_id", mealie.db.migration_types.GUID(), nullable=True),
        sa.Column("image_model", sa.String(), nullable=True),
        sa.Column("image_reasoning_effort", sa.String(), nullable=True),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(["settings_id"], ["ai_provider_settings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["ai_providers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["image_provider_id"], ["ai_providers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("settings_id", "task", name="ai_task_settings_settings_id_task_key"),
    )
    with op.batch_alter_table("ai_task_settings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_ai_task_settings_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_ai_task_settings_settings_id"), ["settings_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_ai_task_settings_provider_id"), ["provider_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_ai_task_settings_image_provider_id"), ["image_provider_id"], unique=False)


def downgrade():
    with op.batch_alter_table("ai_task_settings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ai_task_settings_image_provider_id"))
        batch_op.drop_index(batch_op.f("ix_ai_task_settings_provider_id"))
        batch_op.drop_index(batch_op.f("ix_ai_task_settings_settings_id"))
        batch_op.drop_index(batch_op.f("ix_ai_task_settings_created_at"))
    op.drop_table("ai_task_settings")

    with op.batch_alter_table("ai_providers", schema=None) as batch_op:
        batch_op.drop_column("reasoning_effort")
