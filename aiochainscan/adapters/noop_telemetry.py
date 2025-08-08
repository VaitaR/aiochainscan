from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.ports.telemetry import Telemetry


class NoopTelemetry(Telemetry):
    async def record_event(self, name: str, attributes: Mapping[str, Any] | None = None) -> None:  # noqa: D401
        return

    async def record_error(
        self, name: str, error: BaseException, attributes: Mapping[str, Any] | None = None
    ) -> None:  # noqa: D401
        return
