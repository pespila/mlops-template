"""OpenTelemetry bootstrap — deliberately stubbed out.

Earlier we wired opentelemetry-api / sdk / exporter-otlp /
instrumentation-fastapi / -sqlalchemy / -httpx / -redis with a
BatchSpanProcessor pointed at http://otel-collector:4317. Useful only
when an actual Collector is running; on a local-only single-node
deployment without external observability it's 100+ MB of deps and a
setuptools hack for zero runtime value.

The two entry functions below are kept as explicit no-ops so the three
call sites (main.create_app, jobs/worker.startup, docker_client/builder_app
module load) don't need conditional-import dance — they always succeed,
they just do nothing.

To re-enable: restore the instrumentation imports + BatchSpanProcessor
setup here, add the opentelemetry-* packages back to pyproject.toml,
and stand up a Collector (Grafana Tempo, Jaeger, Honeycomb, etc.). The
call-site code in main.py / worker.py / builder_app.py does not need
to change.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def init_tracing(service_name: str) -> None:
    """No-op placeholder.

    Kept so production code can call this unconditionally regardless of
    whether observability infra is wired up.
    """
    logger.debug("otel.init_tracing.stubbed", service=service_name)


def instrument_fastapi_app(app: object) -> None:
    """No-op placeholder (see init_tracing)."""
    _ = app  # explicitly unused
