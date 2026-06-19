from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.dependencies import get_db
from app.schemas.ticket import TicketCreate, TicketResponse
from app.services import ticket_service

if TYPE_CHECKING:
    from app.models.ticket import Ticket

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]


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
def list_tickets(db: DbSession) -> list[Ticket]:
    return ticket_service.list_tickets(db=db)


@router.get("/tickets/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: int, db: DbSession) -> Ticket:
    ticket = ticket_service.get_ticket(db=db, ticket_id=ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )
    return ticket
