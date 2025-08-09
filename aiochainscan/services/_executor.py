from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable, Mapping
from time import monotonic
from typing import Any

from aiochainscan.ports.rate_limiter import RateLimiter, RetryPolicy
from aiochainscan.ports.telemetry import Telemetry


async def run_with_policies(
    *,
    do_call: Callable[[], Awaitable[Any]],
    telemetry: Telemetry | None,
    telemetry_name: str,
    api_kind: str,
    network: str,
    rate_limiter: RateLimiter | None = None,
    rate_limiter_key: str | None = None,
    retry_policy: RetryPolicy | None = None,
) -> Any:
    """Execute an async call with optional RL/retry and standardized duration/error telemetry.

    - Records `<telemetry_name>.duration` with `duration_ms`.
    - Records `<telemetry_name>.error` on exception, then re-raises.
    """

    if rate_limiter is not None and rate_limiter_key is not None:
        await rate_limiter.acquire(key=rate_limiter_key)

    start = monotonic()
    try:
        if retry_policy is not None:
            return await retry_policy.run(do_call)
        return await do_call()
    except Exception as exc:  # noqa: BLE001
        if telemetry is not None:
            await telemetry.record_error(
                f'{telemetry_name}.error',
                exc,
                {'api_kind': api_kind, 'network': network},
            )
        raise
    finally:
        if telemetry is not None:
            duration_ms = int((monotonic() - start) * 1000)
            await telemetry.record_event(
                f'{telemetry_name}.duration',
                {'api_kind': api_kind, 'network': network, 'duration_ms': duration_ms},
            )


def make_hashed_cache_key(*, prefix: str, payload: Mapping[str, Any], length: int = 24) -> str:
    """Build a deterministic short-hash cache key from an arbitrary payload.

    - JSON-encodes with stable ordering and compact separators
    - SHA-256 digest truncated to ``length`` (default 24 hex chars)
    - Returned format: ``"{prefix}:{short_hash}"``
    """

    payload_str = json.dumps(dict(payload), sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
    return f'{prefix}:{digest[:length]}'
