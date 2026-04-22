"""OpenTelemetry bootstrap for the api + worker + builder processes.

Auto-instruments the libraries that carry the real traffic on the 5-hop
pipeline (web -> api -> arq -> builder -> trainer -> serving):

  * FastAPI (api + builder) — request spans with status_code + route.
  * SQLAlchemy — spans per statement, with db.system + db.statement
    attributes.
  * httpx — spans for every outbound HTTP call (builder_client,
    deployments.predict fan-out).
  * Redis — spans for every command, including Arq's enqueue /
    ratelimit counters.

The exporter target is controlled by the standard OTEL_EXPORTER_OTLP_*
env vars (https://opentelemetry.io/docs/specs/otel/protocol/exporter/).
If ``OTEL_SDK_DISABLED=true`` this module silently no-ops, so it is
safe to call unconditionally even when no collector is running.

Not covered yet: the trainer / serving images need the same bootstrap
in their own entry points; this commit only instruments the Python
services inside apps/api.
"""

from __future__ import annotations

import os

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from aipacken.db import engine

logger = structlog.get_logger(__name__)

_INITIALIZED = False


def _is_enabled() -> bool:
    return os.environ.get("OTEL_SDK_DISABLED", "").lower() not in ("true", "1", "yes")


def init_tracing(service_name: str) -> None:
    """Install the global TracerProvider + auto-instrument libraries once.

    Safe to call from multiple entry points (api lifespan + worker
    startup + builder lifespan) — the first call wins; subsequent
    calls are no-ops. OTLP/gRPC exporter uses OTEL_EXPORTER_OTLP_ENDPOINT
    by default, falling back to http://otel-collector:4317 so the compose
    overlay that ships a Collector 'just works'.
    """
    global _INITIALIZED
    if _INITIALIZED or not _is_enabled():
        return

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "aipacken",
            "deployment.environment": os.environ.get("PLATFORM_ENV", "dev"),
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"),
        insecure=True,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()

    _INITIALIZED = True
    logger.info("otel.initialized", service=service_name)


def instrument_fastapi_app(app: object) -> None:
    """Wire FastAPI's middleware after init_tracing() has run."""
    if not _is_enabled():
        return
    FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
