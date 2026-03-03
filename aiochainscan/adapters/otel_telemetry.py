"""OpenTelemetry adapter for distributed tracing.

Implements the Telemetry port using OpenTelemetry API. When the OTEL SDK
is configured (e.g., in a FastAPI app), spans are automatically exported
to Jaeger/Datadog/etc. When no SDK is present, the API is a zero-cost noop.

Install with: pip install aiochainscan[otel]

Example integration with FastAPI:
    from aiochainscan import ChainscanClient
    from aiochainscan.adapters.otel_telemetry import OTelTelemetry

    telemetry = OTelTelemetry()
    client = ChainscanClient.from_config(
        'blockscout_v2', 'ethereum',
        telemetry=telemetry,
    )
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiochainscan.ports.telemetry import Telemetry

try:
    from opentelemetry import context, trace
    from opentelemetry.trace import StatusCode

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


class OTelTelemetry(Telemetry):
    """OpenTelemetry adapter that creates spans and records exceptions.

    When the OpenTelemetry SDK is configured, events appear as spans in
    your tracing backend (Jaeger, Datadog, etc.). When no SDK is present,
    this is effectively a noop — the OTel API stubs out all calls.

    The adapter automatically inherits the parent span context, so a
    call chain like:
        HTTP Request → ChainscanClient.get_transactions → Network.request
    shows as a nested waterfall in your tracing UI.
    """

    def __init__(self, tracer_name: str = 'aiochainscan') -> None:
        if _OTEL_AVAILABLE:
            self._tracer = trace.get_tracer(tracer_name)
        else:
            self._tracer = None

    async def record_event(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Record an event as an OTEL span with attributes."""
        if self._tracer is None:
            return

        attrs = {k: _coerce_attr_value(v) for k, v in (attributes or {}).items()}
        with self._tracer.start_as_current_span(
            name,
            attributes=attrs,
            context=context.get_current(),
        ):
            pass  # Span auto-closes on exit

    async def record_error(
        self,
        name: str,
        error: BaseException,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Record an error as a span with exception details."""
        if self._tracer is None:
            return

        attrs = {k: _coerce_attr_value(v) for k, v in (attributes or {}).items()}
        with self._tracer.start_as_current_span(
            name,
            attributes=attrs,
            context=context.get_current(),
        ) as span:
            span.set_status(StatusCode.ERROR, str(error))
            span.record_exception(error)


def _coerce_attr_value(value: Any) -> str | int | float | bool:
    """Coerce attribute values to OTEL-compatible types.

    OpenTelemetry attributes only support str, int, float, bool,
    and sequences thereof. Complex objects are stringified.
    """
    if isinstance(value, str | int | float | bool):
        return value
    return str(value)
