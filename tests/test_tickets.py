import importlib
import sys
from collections.abc import Generator
from typing import Any

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
    app.state.testing_session_local = testing_session_local
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
        del app.state.testing_session_local
        database_module.Base.metadata.drop_all(bind=engine)
        clear_database_modules()


def create_ticket_for_test(
    client: TestClient,
    title: str,
    description: str,
) -> int:
    response = client.post(
        "/tickets",
        json={"title": title, "description": description},
    )
    assert response.status_code == 201
    return int(response.json()["id"])


def update_ticket_fields(ticket_id: int, **fields: Any) -> None:
    ticket_module = importlib.import_module("app.models.ticket")

    session_local = app.state.testing_session_local
    with session_local() as db:
        ticket = db.get(ticket_module.Ticket, ticket_id)
        assert ticket is not None
        for field_name, value in fields.items():
            setattr(ticket, field_name, value)
        db.commit()


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


def test_list_tickets_default_behavior(client: TestClient) -> None:
    create_ticket_for_test(
        client=client,
        title="First ticket",
        description="First description",
    )
    create_ticket_for_test(
        client=client,
        title="Second ticket",
        description="Second description",
    )

    response = client.get("/tickets")

    assert response.status_code == 200
    data = response.json()
    assert [ticket["title"] for ticket in data] == [
        "Second ticket",
        "First ticket",
    ]


def test_list_tickets_limit_and_offset(client: TestClient) -> None:
    for title in ("Alpha", "Bravo", "Charlie"):
        create_ticket_for_test(
            client=client,
            title=title,
            description=f"{title} description",
        )

    response = client.get(
        "/tickets",
        params={
            "sort_by": "title",
            "sort_order": "asc",
            "limit": 1,
            "offset": 1,
        },
    )

    assert response.status_code == 200
    assert [ticket["title"] for ticket in response.json()] == ["Bravo"]


def test_list_tickets_filters_by_status(client: TestClient) -> None:
    open_ticket_id = create_ticket_for_test(
        client=client,
        title="Open ticket",
        description="Open description",
    )
    closed_ticket_id = create_ticket_for_test(
        client=client,
        title="Closed ticket",
        description="Closed description",
    )
    update_ticket_fields(open_ticket_id, status="open")
    update_ticket_fields(closed_ticket_id, status="closed")

    response = client.get("/tickets", params={"status": "closed"})

    assert response.status_code == 200
    assert [ticket["title"] for ticket in response.json()] == ["Closed ticket"]


def test_list_tickets_filters_by_category(client: TestClient) -> None:
    auth_ticket_id = create_ticket_for_test(
        client=client,
        title="Login issue",
        description="Password reset does not work.",
    )
    billing_ticket_id = create_ticket_for_test(
        client=client,
        title="Invoice issue",
        description="Billing details are wrong.",
    )
    client.post(f"/tickets/{auth_ticket_id}/analyze")
    client.post(f"/tickets/{billing_ticket_id}/analyze")

    response = client.get("/tickets", params={"category": "billing"})

    assert response.status_code == 200
    assert [ticket["title"] for ticket in response.json()] == ["Invoice issue"]


def test_list_tickets_filters_by_priority(client: TestClient) -> None:
    high_ticket_id = create_ticket_for_test(
        client=client,
        title="Critical outage",
        description="The service is down.",
    )
    low_ticket_id = create_ticket_for_test(
        client=client,
        title="Question",
        description="I want to update my profile.",
    )
    client.post(f"/tickets/{high_ticket_id}/analyze")
    client.post(f"/tickets/{low_ticket_id}/analyze")

    response = client.get("/tickets", params={"priority": "high"})

    assert response.status_code == 200
    assert [ticket["title"] for ticket in response.json()] == ["Critical outage"]


def test_list_tickets_uses_default_sorting(client: TestClient) -> None:
    create_ticket_for_test(
        client=client,
        title="Older ticket",
        description="Older description",
    )
    create_ticket_for_test(
        client=client,
        title="Newer ticket",
        description="Newer description",
    )

    response = client.get("/tickets")

    assert response.status_code == 200
    assert [ticket["title"] for ticket in response.json()] == [
        "Newer ticket",
        "Older ticket",
    ]


def test_list_tickets_supports_ascending_sorting(client: TestClient) -> None:
    create_ticket_for_test(
        client=client,
        title="Zulu ticket",
        description="Zulu description",
    )
    create_ticket_for_test(
        client=client,
        title="Alpha ticket",
        description="Alpha description",
    )

    response = client.get(
        "/tickets",
        params={"sort_by": "title", "sort_order": "asc"},
    )

    assert response.status_code == 200
    assert [ticket["title"] for ticket in response.json()] == [
        "Alpha ticket",
        "Zulu ticket",
    ]


def test_list_tickets_rejects_invalid_sort_by(client: TestClient) -> None:
    response = client.get("/tickets", params={"sort_by": "id"})

    assert response.status_code == 422


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
    ticket_id = create_ticket_for_test(
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
    ticket_id = create_ticket_for_test(
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
    ticket_id = create_ticket_for_test(
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
