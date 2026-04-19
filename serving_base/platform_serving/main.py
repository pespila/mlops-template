"""Serving container FastAPI app.

On startup the container reads MODEL_URI (an MLflow model URI) and loads the
model via mlflow.pyfunc. The Pydantic input/output schemas are derived from
signature metadata captured at training time.

Full implementation lands in the next commit — this file provides /healthz and
a stub /predict so the base image builds and the Traefik label routing works
end-to-end.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from platform_serving import __version__

app = FastAPI(title="AIpacken Serving", version=__version__)


class HealthResponse(BaseModel):
    status: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@app.get("/ready", response_model=HealthResponse)
async def ready() -> HealthResponse:
    # Real readiness check (run a tiny inference against a cached sample) lands next commit.
    return HealthResponse(status="ok", version=__version__)


@app.post("/predict", status_code=501)
async def predict(_body: dict) -> dict[str, str]:
    return {"error": "not_implemented", "detail": "serving.predict arrives in the next commit"}
