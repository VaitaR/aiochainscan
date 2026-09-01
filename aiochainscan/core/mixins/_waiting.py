"""Deadline-bounded polling loop shared by the ``wait_for_*`` helpers.

The wait helpers are pure client-layer composition: they never open HTTP
paths of their own, they re-issue existing ``Method`` calls through
``ChainscanClient.call`` until a final outcome arrives. This module owns the
timing side of that contract:

- deadlines use the monotonic event-loop clock (``loop.time()``), never
  wall-clock ``time.time()``;
- every sleep is capped at the remaining budget, so a ``poll_interval``
  larger than ``timeout`` still observes the deadline;
- transient-vs-fatal classification lives in the caller's probe — anything
  the probe raises propagates unchanged.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from ...exceptions import ChainscanWaitTimeoutError

# One polling attempt: performs the underlying call, classifies the outcome
# and returns ``(final, state)`` — ``final`` carries the value to return in
# ``state``; anything else keeps polling with ``state`` as the last observer.
Probe = Callable[[], Awaitable[tuple[bool, Any]]]


async def poll_until_final(
    probe: Probe,
    *,
    what: str,
    timeout: float,
    poll_interval: float,
) -> Any:
    """Poll ``probe`` until it reports a final outcome or ``timeout`` elapses.

    Args:
        probe: Async callable performing one attempt and returning an
            ``(final, state)`` classification of its outcome.
        what: Human-readable description of the awaited condition (used in
            the timeout error).
        timeout: Total wait budget in seconds. At least one attempt is always
            made; ``0`` means "try once, then give up".
        poll_interval: Delay between attempts in seconds, capped at the
            remaining budget.

    Returns:
        The ``state`` of the first final probe outcome.

    Raises:
        ValueError: If ``timeout`` or ``poll_interval`` is negative.
        ChainscanWaitTimeoutError: If no final outcome arrives within
            ``timeout`` seconds; ``last_state`` carries the last observation.
    """
    if timeout < 0:
        raise ValueError(f'timeout must be >= 0, got {timeout!r}')
    if poll_interval < 0:
        raise ValueError(f'poll_interval must be >= 0, got {poll_interval!r}')

    loop = asyncio.get_running_loop()
    started = loop.time()
    deadline = started + timeout
    while True:
        final, state = await probe()
        if final:
            return state
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise ChainscanWaitTimeoutError(
                what=what,
                waited=max(loop.time() - started, 0.0),
                last_state=state,
            )
        await asyncio.sleep(min(poll_interval, remaining))
