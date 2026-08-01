import random


def exponential_backoff_seconds(
    retry_number: int,
    *,
    base_seconds: float = 0.25,
    maximum_seconds: float = 4.0,
) -> float:
    """Return bounded exponential backoff with full jitter."""

    upper_bound = min(maximum_seconds, base_seconds * (2**retry_number))
    return random.uniform(0.0, upper_bound)
