from collections.abc import Callable, Generator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

SessionFactory = Callable[[], Session]


def get_db() -> Generator[Session]:
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_factory() -> SessionFactory:
    """Return the factory without opening a connection or transaction."""

    from app.database.database import SessionLocal

    return SessionLocal


SessionFactoryDependency = Annotated[SessionFactory, Depends(get_session_factory)]
