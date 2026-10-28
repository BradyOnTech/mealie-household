"""The migration adding per-task AI settings keeps existing providers working exactly as they did"""

import uuid

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests.utils.alembic_reader import ALEMBIC_MIGRATIONS, import_file


def _migration():
    path = next(ALEMBIC_MIGRATIONS.glob("*d7a4e9c1b2f3*.py"))
    return import_file("add_ai_task_settings", path)


def _run(engine: sa.Engine, step: str) -> None:
    migration = _migration()
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(migration, step)()


def _tables_before(engine: sa.Engine) -> None:
    """Just enough of the schema as it was at b3d1c2e4f5a6"""
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE ai_provider_settings (id CHAR(32) PRIMARY KEY, group_id CHAR(32))"))
        conn.execute(
            sa.text(
                "CREATE TABLE ai_providers (id CHAR(32) PRIMARY KEY, settings_id CHAR(32) NOT NULL, name VARCHAR, "
                "provider_type VARCHAR NOT NULL DEFAULT 'openai', api_key VARCHAR NOT NULL, model VARCHAR NOT NULL, "
                "timeout INTEGER NOT NULL)"
            )
        )


def test_upgrade_and_downgrade(tmp_path) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _tables_before(engine)
    settings_id, provider_id = uuid.uuid4().hex, uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO ai_provider_settings VALUES (:id, :id)"), {"id": settings_id})
        conn.execute(
            sa.text("INSERT INTO ai_providers VALUES (:id, :settings, 'Mine', 'chatgpt', '', '', 300)"),
            {"id": provider_id, "settings": settings_id},
        )

    _run(engine, "upgrade")

    inspector = sa.inspect(engine)
    assert "reasoning_effort" in {column["name"] for column in inspector.get_columns("ai_providers")}
    assert {column["name"] for column in inspector.get_columns("ai_task_settings")} >= {
        "settings_id",
        "task",
        "provider_id",
        "model",
        "reasoning_effort",
        "image_provider_id",
        "image_model",
        "image_reasoning_effort",
    }
    with engine.begin() as conn:
        # Nothing chosen: a ChatGPT provider keeps reasoning low, and an API-key one keeps sending none
        assert conn.execute(sa.text("SELECT reasoning_effort, name FROM ai_providers")).one() == (None, "Mine")
        conn.execute(
            sa.text(
                "INSERT INTO ai_task_settings (id, settings_id, task, provider_id) "
                "VALUES (:id, :settings, 'recipe_building', :provider)"
            ),
            {"id": uuid.uuid4().hex, "settings": settings_id, "provider": provider_id},
        )
        # One choice per task
        try:
            conn.execute(
                sa.text(
                    "INSERT INTO ai_task_settings (id, settings_id, task) VALUES (:id, :settings, 'recipe_building')"
                ),
                {"id": uuid.uuid4().hex, "settings": settings_id},
            )
            raise AssertionError("a task was saved twice")
        except sa.exc.IntegrityError:
            pass

    _run(engine, "downgrade")

    inspector = sa.inspect(engine)
    assert "ai_task_settings" not in inspector.get_table_names()
    assert "reasoning_effort" not in {column["name"] for column in inspector.get_columns("ai_providers")}
    with engine.begin() as conn:
        assert conn.execute(sa.text("SELECT name FROM ai_providers")).scalar_one() == "Mine"
    engine.dispose()
