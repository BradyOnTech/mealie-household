import json
from datetime import date
from uuid import uuid4

from mealie.core.config import get_app_settings
from mealie.db.models._model_base import SqlAlchemyBase
from mealie.db.models._model_utils.datetime import NaiveDateTime
from mealie.services.backups_v2.alchemy_exporter import AlchemyExporter
from tests.utils.alembic_reader import alembic_versions


def test_alchemy_exporter():
    settings = get_app_settings()
    exporter = AlchemyExporter(settings.DB_URL)
    data = exporter.dump()

    assert data["alembic_version"] == alembic_versions()
    assert json.dumps(data, indent=4)  # Make sure data is json-serializable

    exporter.engine.dispose()


def test_every_datetime_column_survives_a_backup():
    """Restores rebuild datetimes by column name, so an unregistered one comes back as a string.

    The failure is silent at backup time and only shows up on restore, so this asserts the two stay
    in step rather than waiting for someone to notice a broken restore.
    """
    datetime_columns = {
        column.name
        for table in SqlAlchemyBase.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, NaiveDateTime)
    }

    unregistered = datetime_columns - AlchemyExporter.look_for_datetime
    assert not unregistered, (
        f"datetime columns missing from AlchemyExporter.look_for_datetime: {sorted(unregistered)}. "
        "Add them, or they will restore as strings."
    )


def test_restore_conversion_preserves_grocery_json() -> None:
    food_id = str(uuid4())
    json_fields = {
        "stores": ["walmart", "aldi"],
        "meal_scales": {"12": 2.0},
        "warnings": ["Review this quantity"],
        "pantry_snapshot": {food_id: {"food_id": food_id, "quantity": 0.4, "enabled": True}},
    }
    data = {"grocery_weeks": [{"week_start": "2026-10-12", "revision": 3, **json_fields}]}
    exporter = AlchemyExporter("sqlite:///:memory:")
    try:
        converted = exporter.convert_types(data)["grocery_weeks"][0]
        assert converted == {"week_start": date(2026, 10, 12), "revision": 3, **json_fields}
        assert json.dumps({key: converted[key] for key in json_fields})
    finally:
        exporter.engine.dispose()
