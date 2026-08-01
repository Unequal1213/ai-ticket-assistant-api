import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

DATABASE_MODULES = (
    "app.models.ticket",
    "app.database.database",
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def clear_database_modules() -> None:
    for module_name in DATABASE_MODULES:
        sys.modules.pop(module_name, None)


def isolated_import_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    environment.pop("SYNTHETIC_DOTENV_SENTINEL", None)
    environment["AI_PROVIDER"] = "deterministic"
    environment["PYTHONPATH"] = str(PROJECT_ROOT)
    return environment


def test_application_import_does_not_load_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "SYNTHETIC_DOTENV_SENTINEL=must_not_load\n"
        "DATABASE_URL=sqlite+pysqlite:///must-not-load.db\n",
        encoding="utf-8",
    )
    script = """
import os
import app.main

assert "SYNTHETIC_DOTENV_SENTINEL" not in os.environ
try:
    import app.database.database
except RuntimeError as exc:
    assert "DATABASE_URL" in str(exc)
else:
    raise AssertionError("database import unexpectedly loaded the local .env")
assert "SYNTHETIC_DOTENV_SENTINEL" not in os.environ
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=isolated_import_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_database_import_uses_explicit_environment(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "SYNTHETIC_DOTENV_SENTINEL=must_not_load\n"
        "DATABASE_URL=sqlite+pysqlite:///must-not-load.db\n",
        encoding="utf-8",
    )
    explicit_url = "sqlite+pysqlite:///:memory:"
    environment = isolated_import_environment()
    environment["DATABASE_URL"] = explicit_url
    script = f"""
import os
from app.database.database import DATABASE_URL

assert DATABASE_URL == {explicit_url!r}
assert "SYNTHETIC_DOTENV_SENTINEL" not in os.environ
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


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
            "confidence",
            "reasoning_tags",
            "analysis_status",
            "provider_requested",
            "provider_used",
            "model_requested",
            "model_used",
            "prompt_version",
            "fallback_used",
            "input_char_count",
            "input_tokens",
            "output_tokens",
            "provider_attempts",
            "repair_attempts",
            "latency_ms",
            "error_category",
            "provider_request_id",
            "analyzed_at",
            "created_at",
            "updated_at",
        }
        assert ticket_module.Ticket.__table__.c.created_at.type.timezone is True
        assert ticket_module.Ticket.__table__.c.updated_at.type.timezone is True
    finally:
        clear_database_modules()
