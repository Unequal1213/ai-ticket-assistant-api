from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas.ticket import TicketCreate, TicketUpdate

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


def list_tickets(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> list[Ticket]:
    from app.models.ticket import Ticket

    sort_columns = {
        "created_at": Ticket.created_at,
        "updated_at": Ticket.updated_at,
        "title": Ticket.title,
        "status": Ticket.status,
        "category": Ticket.category,
        "priority": Ticket.priority,
    }
    sort_column = sort_columns[sort_by]
    sort_direction = sort_order.lower()
    order_by = sort_column.asc() if sort_direction == "asc" else sort_column.desc()
    secondary_order = Ticket.id.asc() if sort_direction == "asc" else Ticket.id.desc()

    statement = select(Ticket)
    if status is not None:
        statement = statement.where(Ticket.status == status)
    if category is not None:
        statement = statement.where(Ticket.category == category)
    if priority is not None:
        statement = statement.where(Ticket.priority == priority)

    statement = (
        statement.order_by(order_by, secondary_order).offset(offset).limit(limit)
    )

    return list(db.scalars(statement).all())


def get_ticket(db: Session, ticket_id: int) -> Ticket | None:
    from app.models.ticket import Ticket

    return db.get(Ticket, ticket_id)


def update_ticket(
    db: Session,
    ticket_id: int,
    ticket_data: TicketUpdate,
) -> Ticket | None:
    ticket = get_ticket(db=db, ticket_id=ticket_id)
    if ticket is None:
        return None

    update_data = ticket_data.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(ticket, field_name, value)

    db.commit()
    db.refresh(ticket)
    return ticket


def delete_ticket(db: Session, ticket_id: int) -> bool:
    ticket = get_ticket(db=db, ticket_id=ticket_id)
    if ticket is None:
        return False

    db.delete(ticket)
    db.commit()
    return True
