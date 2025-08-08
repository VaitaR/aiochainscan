from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.ports.telemetry import Telemetry


class StructlogTelemetry(Telemetry):
    """Telemetry adapter that logs via structlog when available.

    Falls back to the standard logging module if structlog is not installed.
    """

    def __init__(self) -> None:
        try:
            import structlog

            self._logger = structlog.get_logger('aiochainscan')
            self._use_structlog = True
        except Exception:
            import logging

            self._logger = logging.getLogger('aiochainscan')
            self._use_structlog = False

    async def record_event(self, name: str, attributes: Mapping[str, Any] | None = None) -> None:
        attrs = dict(attributes or {})
        if self._use_structlog:
            # structlog encourages key/value logs
            self._logger.info(name, **attrs)
        else:
            # Fallback: structured payload via extra
            self._logger.info('%s', name, extra={'attributes': attrs})

    async def record_error(
        self, name: str, error: BaseException, attributes: Mapping[str, Any] | None = None
    ) -> None:
        attrs = dict(attributes or {})
        attrs['error_type'] = type(error).__name__
        attrs['error_message'] = str(error)
        if self._use_structlog:
            self._logger.error(name, **attrs)
        else:
            self._logger.error('%s', name, extra={'attributes': attrs})
