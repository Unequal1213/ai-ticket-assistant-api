from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas.ticket import TicketCreate

if TYPE_CHECKING:
    from app.models.ticket import Ticket


def create_ticket(db: Session, ticket_data: TicketCreate) -> Ticket:
    from app.models.ticket import Ticket

    ticket = Ticket(
        title=ticket_data.title,
        description=ticket_data.description,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def list_tickets(db: Session) -> list[Ticket]:
    from app.models.ticket import Ticket

    return list(db.scalars(select(Ticket).order_by(Ticket.id)).all())


def get_ticket(db: Session, ticket_id: int) -> Ticket | None:
    from app.models.ticket import Ticket

    return db.get(Ticket, ticket_id)
