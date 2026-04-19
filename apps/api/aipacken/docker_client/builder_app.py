"""Builder service — sole owner of the Docker socket.

Exposes a narrow HTTP API that api/worker services call to build and run
training + serving containers. By isolating socket access to this single
service we limit the blast radius of any compromise of api or worker.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

app = FastAPI(title="AIpacken Builder", version="0.1.0")


class HealthResponse(BaseModel):
    status: str


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


# Endpoints below are intentionally stubs for the foundation commit.
# Implementation (build, run, stop, logs, events) lands in the next commit.


class BuildRequest(BaseModel):
    context_uri: str
    tag: str


@app.post("/build", status_code=501)
async def build(_req: BuildRequest) -> dict[str, str]:
    return {"error": "not_implemented", "detail": "builder.build arrives in the next commit"}


class RunRequest(BaseModel):
    image: str
    cmd: list[str] | None = None
    env: dict[str, str] | None = None
    memory_bytes: int | None = None
    nano_cpus: int | None = None


@app.post("/run", status_code=501)
async def run(_req: RunRequest) -> dict[str, str]:
    return {"error": "not_implemented", "detail": "builder.run arrives in the next commit"}
