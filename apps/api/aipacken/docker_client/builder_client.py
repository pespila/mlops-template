from __future__ import annotations

from typing import Any

import httpx

from aipacken.config import get_settings


class BuilderClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self._base_url = base_url or get_settings().builder_url
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)

    async def healthz(self) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get("/healthz")
            r.raise_for_status()
            return r.json()

    async def build(
        self, context_tar_b64: str, tag: str, build_args: dict[str, str] | None = None
    ) -> dict[str, Any]:
        payload = {"context_tar_b64": context_tar_b64, "tag": tag, "build_args": build_args or {}}
        async with self._client() as c:
            r = await c.post("/build", json=payload, timeout=None)
            r.raise_for_status()
            return r.json()

    async def run(
        self,
        image: str,
        env: dict[str, str],
        memory_bytes: int,
        nano_cpus: int,
        network: str,
        cmd: list[str] | None = None,
        labels: dict[str, str] | None = None,
        mounts: list[dict[str, Any]] | None = None,
        user: str | None = "10001:10001",
        name: str | None = None,
        hostname: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "image": image,
            "cmd": cmd,
            "env": env,
            "memory_bytes": memory_bytes,
            "nano_cpus": nano_cpus,
            "network": network,
            "labels": labels or {},
            "mounts": mounts or [],
            "user": user,
            "name": name,
            "hostname": hostname,
        }
        async with self._client() as c:
            r = await c.post("/run", json=payload)
            r.raise_for_status()
            return r.json()

    async def logs(self, container_id: str, tail: int = 500) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get(f"/logs/{container_id}", params={"tail": tail})
            r.raise_for_status()
            return r.json()

    async def stop(self, container_id: str, timeout: int = 10) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.post("/stop", json={"container_id": container_id, "timeout": timeout})
            r.raise_for_status()
            return r.json()

    async def wait(self, container_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=None) as c:
            r = await c.get(f"/wait/{container_id}")
            r.raise_for_status()
            return r.json()

    async def stream_logs(self, container_id: str) -> httpx.Response:
        # Caller iterates lines via aiter_lines; kept open until iteration completes.
        client = httpx.AsyncClient(base_url=self._base_url, timeout=None)
        return await client.send(
            client.build_request("GET", f"/logs/{container_id}/stream"), stream=True
        )


def get_builder_client() -> BuilderClient:
    return BuilderClient()
