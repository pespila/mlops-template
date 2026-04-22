"""Builder service — sole owner of the Docker socket.

The api and worker services reach this HTTP surface instead of talking to the
Docker socket directly. Keeping socket access in exactly one service limits the
blast radius of a compromise in the main app containers.
"""

from __future__ import annotations

import base64
import hmac
import io
import json
from typing import Any

import docker
import structlog
from docker.errors import APIError, ImageNotFound, NotFound
from docker.types import Mount
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from aipacken.config import get_settings
from aipacken.services.redis_client import publish

logger = structlog.get_logger(__name__)


def require_internal_token(
    x_internal_token: str | None = Header(default=None, alias="X-Internal-Token"),
) -> None:
    """Reject any request that does not present the shared INTERNAL_HMAC_TOKEN.

    Every builder endpoint mutates or reads Docker state — leaking them to any
    container on the same network is a host-root RCE primitive. The api and
    worker are the only legitimate callers and both already know the token
    (loaded from the shared .env / compose env). Uses constant-time compare
    to defeat timing-based guessing.
    """
    expected = get_settings().internal_hmac_token
    if not x_internal_token or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=401, detail="invalid_or_missing_internal_token")


app = FastAPI(
    title="AIpacken Builder",
    version="0.1.0",
    # /healthz is the compose liveness probe and must stay unauthenticated;
    # everything else is gated by the dependency attached per-route below.
    dependencies=[],
)

_docker_client: docker.DockerClient | None = None


def get_docker() -> docker.DockerClient:
    global _docker_client
    if _docker_client is None:
        _docker_client = docker.from_env()
    return _docker_client


class HealthResponse(BaseModel):
    status: str


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


class BuildRequest(BaseModel):
    context_tar_b64: str
    tag: str
    build_args: dict[str, str] | None = None


class BuildResponse(BaseModel):
    image_id: str
    tag: str


@app.post("/build", response_model=BuildResponse, dependencies=[Depends(require_internal_token)])
async def build(req: BuildRequest) -> BuildResponse:
    try:
        tar_bytes = base64.b64decode(req.context_tar_b64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid_context_tar: {exc}") from exc

    client = get_docker()
    channel = f"build:{req.tag}:logs"

    try:
        image, log_stream = client.images.build(
            fileobj=io.BytesIO(tar_bytes),
            custom_context=True,
            tag=req.tag,
            buildargs=req.build_args or {},
            rm=True,
            forcerm=True,
        )
        for entry in log_stream:
            line = entry.get("stream") or entry.get("error") or json.dumps(entry)
            if line:
                await publish(channel, line.rstrip("\n"))
    except APIError as exc:
        await publish(channel, f"ERROR: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return BuildResponse(image_id=image.id or "", tag=req.tag)


class VolumeMount(BaseModel):
    source: str  # docker volume name
    target: str  # path inside the container
    read_only: bool = False


class RunRequest(BaseModel):
    image: str
    cmd: list[str] | None = None
    env: dict[str, str] = Field(default_factory=dict)
    memory_bytes: int = 2 * 1024 * 1024 * 1024
    nano_cpus: int = 2_000_000_000
    network: str
    labels: dict[str, str] = Field(default_factory=dict)
    mounts: list[VolumeMount] = Field(default_factory=list)
    user: str | None = "10001:10001"
    name: str | None = None
    hostname: str | None = None


class RunResponse(BaseModel):
    container_id: str


@app.post("/run", response_model=RunResponse, dependencies=[Depends(require_internal_token)])
async def run_container(req: RunRequest) -> RunResponse:
    client = get_docker()
    mounts = [
        Mount(target=m.target, source=m.source, type="volume", read_only=m.read_only)
        for m in req.mounts
    ]
    try:
        container = client.containers.run(
            image=req.image,
            command=req.cmd,
            environment=req.env,
            network=req.network,
            labels=req.labels,
            detach=True,
            read_only=True,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            user=req.user,
            pids_limit=512,
            tmpfs={"/tmp": ""},  # noqa: S108 — container-internal tmpfs mount, not host path
            mem_limit=req.memory_bytes,
            nano_cpus=req.nano_cpus,
            mounts=mounts,
            name=req.name,
            hostname=req.hostname,
        )
    except ImageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"image_not_found: {req.image}") from exc
    except APIError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RunResponse(container_id=container.id or "")


class StopRequest(BaseModel):
    container_id: str
    timeout: int = 10


@app.post("/stop", dependencies=[Depends(require_internal_token)])
async def stop_container(req: StopRequest) -> dict[str, Any]:
    client = get_docker()
    try:
        container = client.containers.get(req.container_id)
        container.stop(timeout=req.timeout)
        container.remove(force=True)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="container_not_found") from exc
    except APIError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"stopped": True, "container_id": req.container_id}


@app.get("/wait/{container_id}", dependencies=[Depends(require_internal_token)])
async def wait_container(container_id: str) -> dict[str, Any]:
    """Block until the container exits and return its exit code.

    Runs synchronously via docker-py `container.wait()`. Use off-thread when
    calling from an async worker (see builder_client.wait).
    """
    client = get_docker()
    try:
        container = client.containers.get(container_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="container_not_found") from exc
    try:
        result = container.wait(timeout=24 * 3600)
    except APIError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "container_id": container_id,
        "exit_code": int(result.get("StatusCode", -1)) if isinstance(result, dict) else -1,
    }


@app.get("/logs/{container_id}", dependencies=[Depends(require_internal_token)])
async def get_logs(container_id: str, tail: int = 500) -> dict[str, Any]:
    """Return the last *tail* lines of a container's stdout/stderr."""
    client = get_docker()
    try:
        container = client.containers.get(container_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="container_not_found") from exc
    raw = container.logs(stdout=True, stderr=True, tail=tail)
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    return {"container_id": container_id, "lines": text.splitlines()}


@app.get("/logs/{container_id}/stream", dependencies=[Depends(require_internal_token)])
async def stream_logs(container_id: str) -> StreamingResponse:
    client = get_docker()
    try:
        container = client.containers.get(container_id)
    except NotFound as exc:
        raise HTTPException(status_code=404, detail="container_not_found") from exc

    def _iter() -> Any:
        for chunk in container.logs(stream=True, follow=True, stdout=True, stderr=True):
            if isinstance(chunk, bytes):
                text = chunk.decode("utf-8", errors="replace")
            else:
                text = str(chunk)
            for line in text.splitlines():
                yield f"data: {line}\n\n"

    return StreamingResponse(_iter(), media_type="text/event-stream")


class SaveImageRequest(BaseModel):
    image: str
    # Absolute path inside the shared platform-data volume where the tar is
    # written. The caller is responsible for picking a path inside
    # ``/var/platform-data`` — the endpoint rejects anything else.
    dest_path: str


class SaveImageResponse(BaseModel):
    image: str
    dest_path: str
    size_bytes: int


@app.post(
    "/save_image", response_model=SaveImageResponse, dependencies=[Depends(require_internal_token)]
)
async def save_image(req: SaveImageRequest) -> SaveImageResponse:
    """Stream ``docker save`` for *image* into *dest_path* on the shared volume.

    Kept on the builder so the api/worker never touch the Docker socket. Path
    must live under ``/var/platform-data`` (the only writable volume shared
    between builder and worker); anything else is rejected.
    """
    import os

    data_root = "/var/platform-data"
    dest = os.path.abspath(req.dest_path)
    if not dest.startswith(data_root + os.sep):
        raise HTTPException(status_code=400, detail=f"dest_path must be under {data_root}")

    client = get_docker()
    try:
        image = client.images.get(req.image)
    except ImageNotFound as exc:
        raise HTTPException(status_code=404, detail=f"image_not_found: {req.image}") from exc

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    total = 0
    try:
        with open(dest, "wb") as fp:
            for chunk in image.save(named=True):
                if not chunk:
                    continue
                fp.write(chunk)
                total += len(chunk)
    except APIError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return SaveImageResponse(image=req.image, dest_path=dest, size_bytes=total)


@app.get("/events/stream", dependencies=[Depends(require_internal_token)])
async def stream_events() -> StreamingResponse:
    client = get_docker()

    def _iter() -> Any:
        for event in client.events(decode=True):
            attrs = event.get("Actor", {}).get("Attributes", {}) if isinstance(event, dict) else {}
            if "platform.run_id" in attrs or "platform.deployment_id" in attrs:
                yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(_iter(), media_type="text/event-stream")
