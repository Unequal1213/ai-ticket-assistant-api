import importlib
import sys

import pytest

DATABASE_MODULES = (
    "app.models.ticket",
    "app.database.database",
)


def clear_database_modules() -> None:
    for module_name in DATABASE_MODULES:
        sys.modules.pop(module_name, None)


def test_database_module_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    clear_database_modules()

    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            importlib.import_module("app.database.database")
    finally:
        clear_database_modules()


def test_ticket_model_defines_expected_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://localhost:5432/test_database",
    )
    clear_database_modules()

    try:
        ticket_module = importlib.import_module("app.models.ticket")
        columns = set(ticket_module.Ticket.__table__.columns.keys())

        assert columns == {
            "id",
            "title",
            "description",
            "status",
            "category",
            "priority",
            "summary",
            "suggested_reply",
            "created_at",
            "updated_at",
        }
        assert ticket_module.Ticket.__table__.c.created_at.type.timezone is True
        assert ticket_module.Ticket.__table__.c.updated_at.type.timezone is True
    finally:
        clear_database_modules()
