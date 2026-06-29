"""Small, dependency-free retry helper for flaky external calls."""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry_call(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call ``fn`` up to ``attempts`` times, returning its first success.

    Sleeps ``base_delay * attempt_number`` between failures (linear backoff)
    and re-raises the last exception once all attempts are exhausted.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - caller decides how to handle
            last_exc = exc
            if attempt < attempts:
                sleep(base_delay * attempt)
    assert last_exc is not None  # attempts >= 1, so we always tried at least once
    raise last_exc
