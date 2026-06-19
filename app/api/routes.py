from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.schemas.ticket import TicketCreate, TicketResponse, TicketUpdate
from app.services import ticket_service

if TYPE_CHECKING:
    from app.models.ticket import Ticket

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
TicketSortField = Literal[
    "created_at",
    "updated_at",
    "title",
    "status",
    "category",
    "priority",
]
SortOrder = Literal["asc", "desc"]


@router.get("/health")
def read_health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_ticket(ticket_data: TicketCreate, db: DbSession) -> Ticket:
    return ticket_service.create_ticket(db=db, ticket_data=ticket_data)


@router.get("/tickets", response_model=list[TicketResponse])
def list_tickets(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    category: str | None = None,
    priority: str | None = None,
    sort_by: TicketSortField = "created_at",
    sort_order: SortOrder = "desc",
) -> list[Ticket]:
    return ticket_service.list_tickets(
        db=db,
        limit=limit,
        offset=offset,
        status=status_filter,
        category=category,
        priority=priority,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: int, db: DbSession) -> Ticket:
    ticket = ticket_service.get_ticket(db=db, ticket_id=ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return ticket


@router.patch("/tickets/{ticket_id}", response_model=TicketResponse)
def update_ticket(
    ticket_id: int,
    ticket_data: TicketUpdate,
    db: DbSession,
) -> Ticket:
    ticket = ticket_service.update_ticket(
        db=db,
        ticket_id=ticket_id,
        ticket_data=ticket_data,
    )
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return ticket


@router.delete("/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(ticket_id: int, db: DbSession) -> None:
    deleted = ticket_service.delete_ticket(db=db, ticket_id=ticket_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )


@router.post("/tickets/{ticket_id}/analyze", response_model=TicketResponse)
def analyze_ticket(ticket_id: int, db: DbSession) -> Ticket:
    ticket = ticket_service.analyze_existing_ticket(db=db, ticket_id=ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return ticket
