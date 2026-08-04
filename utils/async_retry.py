import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar


T = TypeVar("T")


async def retry_empty(
    operation: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    retry_delay: float = 1.0,
    on_retry: Callable[[int, int], None] | None = None,
) -> T | None:
    for attempt in range(1, max_attempts + 1):
        result = await operation()
        if result:
            return result
        if attempt < max_attempts:
            if on_retry:
                on_retry(attempt, max_attempts)
            await asyncio.sleep(retry_delay)
    return None
