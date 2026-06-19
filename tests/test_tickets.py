import importlib
import sys
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.dependencies import get_db
from app.main import app

DATABASE_MODULES = (
    "app.models.ticket",
    "app.database.database",
)


def clear_database_modules() -> None:
    for module_name in DATABASE_MODULES:
        sys.modules.pop(module_name, None)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    clear_database_modules()

    database_module = importlib.import_module("app.database.database")
    importlib.import_module("app.models.ticket")

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        class_=Session,
    )
    database_module.Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session]:
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        database_module.Base.metadata.drop_all(bind=engine)
        clear_database_modules()


def test_create_ticket(client: TestClient) -> None:
    response = client.post(
        "/tickets",
        json={
            "title": "Cannot log in",
            "description": "Password reset link is not working.",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Cannot log in"
    assert data["description"] == "Password reset link is not working."
    assert data["status"] == "new"
    assert data["category"] is None
    assert data["priority"] is None
    assert data["summary"] is None
    assert data["suggested_reply"] is None
    assert data["created_at"]
    assert data["updated_at"]


def test_list_tickets(client: TestClient) -> None:
    client.post(
        "/tickets",
        json={"title": "First ticket", "description": "First description"},
    )
    client.post(
        "/tickets",
        json={"title": "Second ticket", "description": "Second description"},
    )

    response = client.get("/tickets")

    assert response.status_code == 200
    data = response.json()
    assert [ticket["title"] for ticket in data] == [
        "First ticket",
        "Second ticket",
    ]


def test_get_ticket_by_id(client: TestClient) -> None:
    create_response = client.post(
        "/tickets",
        json={
            "title": "Billing question",
            "description": "I need a copy of my invoice.",
        },
    )
    ticket_id = create_response.json()["id"]

    response = client.get(f"/tickets/{ticket_id}")

    assert response.status_code == 200
    assert response.json()["title"] == "Billing question"


def test_get_ticket_returns_404_for_missing_ticket(client: TestClient) -> None:
    response = client.get("/tickets/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket not found"}


def create_ticket_for_analysis(
    client: TestClient,
    title: str,
    description: str,
) -> int:
    response = client.post(
        "/tickets",
        json={"title": title, "description": description},
    )
    return int(response.json()["id"])


@pytest.mark.parametrize(
    ("title", "description", "expected_category"),
    [
        ("Login problem", "My password reset link is expired.", "authentication"),
        ("Invoice question", "I need help with billing.", "billing"),
        ("App crash", "The app fails with an error.", "technical"),
        ("Feature idea", "It would be nice to export tickets.", "general"),
    ],
)
def test_analyze_ticket_categories(
    client: TestClient,
    title: str,
    description: str,
    expected_category: str,
) -> None:
    ticket_id = create_ticket_for_analysis(
        client=client,
        title=title,
        description=description,
    )

    response = client.post(f"/tickets/{ticket_id}/analyze")

    assert response.status_code == 200
    assert response.json()["category"] == expected_category


@pytest.mark.parametrize(
    ("title", "description", "expected_priority"),
    [
        ("Critical outage", "The service is down.", "high"),
        ("Need help", "Please help with this problem.", "medium"),
        ("Question", "I want to update my profile.", "low"),
    ],
)
def test_analyze_ticket_priorities(
    client: TestClient,
    title: str,
    description: str,
    expected_priority: str,
) -> None:
    ticket_id = create_ticket_for_analysis(
        client=client,
        title=title,
        description=description,
    )

    response = client.post(f"/tickets/{ticket_id}/analyze")

    assert response.status_code == 200
    assert response.json()["priority"] == expected_priority


def test_analyze_ticket_returns_404_for_missing_ticket(client: TestClient) -> None:
    response = client.post("/tickets/999/analyze")

    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket not found"}


def test_analyze_ticket_updates_ticket_fields(client: TestClient) -> None:
    ticket_id = create_ticket_for_analysis(
        client=client,
        title="Payment failed",
        description="Please help, my invoice payment failed.",
    )

    analyze_response = client.post(f"/tickets/{ticket_id}/analyze")
    get_response = client.get(f"/tickets/{ticket_id}")

    assert analyze_response.status_code == 200
    analyzed_ticket = analyze_response.json()
    saved_ticket = get_response.json()
    assert analyzed_ticket["category"] == "billing"
    assert analyzed_ticket["priority"] == "medium"
    assert analyzed_ticket["summary"] == (
        "Payment failed: Please help, my invoice payment failed."
    )
    assert analyzed_ticket["suggested_reply"] == (
        "Thanks for contacting support. We classified this as a medium priority "
        "billing issue and will review it shortly."
    )
    assert saved_ticket["category"] == analyzed_ticket["category"]
    assert saved_ticket["priority"] == analyzed_ticket["priority"]
    assert saved_ticket["summary"] == analyzed_ticket["summary"]
    assert saved_ticket["suggested_reply"] == analyzed_ticket["suggested_reply"]
