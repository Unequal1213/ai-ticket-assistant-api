import asyncio
from collections.abc import Callable
from datetime import UTC, date, datetime

from app.ai.exceptions import DailyQuotaExceededError


class DailyRequestQuota:
    """Process-local counter for accepted external analysis operations."""

    def __init__(
        self,
        limit: int,
        *,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._limit = limit
        self._today = today or (lambda: datetime.now(UTC).date())
        self._date = self._today()
        self._count = 0
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return self._count

    async def consume(self) -> None:
        async with self._lock:
            current_date = self._today()
            if current_date != self._date:
                self._date = current_date
                self._count = 0
            if self._count >= self._limit:
                raise DailyQuotaExceededError
            self._count += 1
