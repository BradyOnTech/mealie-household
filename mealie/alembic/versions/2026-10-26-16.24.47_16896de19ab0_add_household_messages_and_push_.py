"""add household messages, read markers and push subscriptions

Revision ID: 16896de19ab0
Revises: cef5a4007416
Create Date: 2026-10-26 16:24:47.914397

"""

import sqlalchemy as sa
from alembic import op

import mealie.db.migration_types

# revision identifiers, used by Alembic.
revision = "16896de19ab0"
down_revision: str | None = "cef5a4007416"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade():
    op.create_table(
        "household_message_reads",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("user_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("last_read_at", mealie.db.migration_types.NaiveDateTime(), nullable=False),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("household_message_reads", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_household_message_reads_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_household_message_reads_user_id"), ["user_id"], unique=True)

    op.create_table(
        "household_messages",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("group_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("household_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("user_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["groups.id"],
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("household_messages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_household_messages_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_household_messages_group_id"), ["group_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_household_messages_household_id"), ["household_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_household_messages_user_id"), ["user_id"], unique=False)

    op.create_table(
        "user_push_subscriptions",
        sa.Column("id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("user_id", mealie.db.migration_types.GUID(), nullable=False),
        sa.Column("endpoint", sa.String(), nullable=False),
        sa.Column("p256dh", sa.String(), nullable=False),
        sa.Column("auth", sa.String(), nullable=False),
        sa.Column("user_agent", sa.String(), nullable=False),
        sa.Column("created_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.Column("update_at", mealie.db.migration_types.NaiveDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    with op.batch_alter_table("user_push_subscriptions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_user_push_subscriptions_created_at"), ["created_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_user_push_subscriptions_user_id"), ["user_id"], unique=False)


def downgrade():
    with op.batch_alter_table("user_push_subscriptions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_user_push_subscriptions_user_id"))
        batch_op.drop_index(batch_op.f("ix_user_push_subscriptions_created_at"))

    op.drop_table("user_push_subscriptions")
    with op.batch_alter_table("household_messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_household_messages_user_id"))
        batch_op.drop_index(batch_op.f("ix_household_messages_household_id"))
        batch_op.drop_index(batch_op.f("ix_household_messages_group_id"))
        batch_op.drop_index(batch_op.f("ix_household_messages_created_at"))

    op.drop_table("household_messages")
    with op.batch_alter_table("household_message_reads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_household_message_reads_user_id"))
        batch_op.drop_index(batch_op.f("ix_household_message_reads_created_at"))

    op.drop_table("household_message_reads")
