from collections.abc import Generator

from sqlalchemy.orm import Session


def get_db() -> Generator[Session]:
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
