import sys
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command


def clear_database_modules() -> None:
    for module_name in ("app.models.ticket", "app.database.database"):
        sys.modules.pop(module_name, None)


def run_migration(config: Config, revision: str) -> None:
    clear_database_modules()
    if revision == "downgrade:0001":
        command.downgrade(config, "0001")
    else:
        command.upgrade(config, revision)


def test_migration_upgrade_and_downgrade_preserve_ticket(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "migration-test.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")

    try:
        run_migration(config, "0001")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO tickets "
                    "(title, description, status, created_at, updated_at) "
                    "VALUES ('Synthetic ticket', 'Synthetic description', 'new', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )

        run_migration(config, "head")
        upgraded_columns = {
            column["name"] for column in inspect(engine).get_columns("tickets")
        }
        assert "provider_requested" in upgraded_columns
        assert "reasoning_tags" in upgraded_columns
        assert "model_requested" in upgraded_columns
        assert "model_used" in upgraded_columns
        assert "provider_attempts" in upgraded_columns
        assert "repair_attempts" in upgraded_columns
        assert "model" not in upgraded_columns

        run_migration(config, "downgrade:0001")
        downgraded_columns = {
            column["name"] for column in inspect(engine).get_columns("tickets")
        }
        assert "provider_requested" not in downgraded_columns
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM tickets")) == 1

        run_migration(config, "head")
        assert "analyzed_at" in {
            column["name"] for column in inspect(engine).get_columns("tickets")
        }
        engine.dispose()
    finally:
        clear_database_modules()
