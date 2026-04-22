from __future__ import annotations

from typing import Any

import httpx

from aipacken.config import get_settings


class BuilderClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.builder_url
        self._timeout = timeout
        # Shared bearer: the builder rejects requests without it. Keeping the
        # header value resolved once at client construction means every
        # request (including the streaming ones) carries it automatically.
        self._auth_headers: dict[str, str] = {"X-Internal-Token": settings.internal_hmac_token}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, headers=self._auth_headers
        )

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
        # timeout=None is deliberate: a training run can legitimately run for
        # hours. The bound on how long this waits is the Arq job_timeout
        # configured in aipacken.jobs.worker.WorkerSettings, which wraps the
        # whole task. S113 is suppressed inline for that reason.
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=None,  # noqa: S113
            headers=self._auth_headers,
        ) as c:
            r = await c.get(f"/wait/{container_id}")
            r.raise_for_status()
            return r.json()

    async def save_image(self, image: str, dest_path: str) -> dict[str, Any]:
        """Ask the builder to ``docker save`` *image* into *dest_path*.

        The destination must live under ``/var/platform-data`` — the shared
        volume both builder and worker have mounted. Returns the size of the
        written tar in bytes.
        """
        payload = {"image": image, "dest_path": dest_path}
        # ``docker save`` on a 3 GB AutoGluon image can take >1 minute over
        # the unix socket. Bounded by the Arq task timeout around the
        # build_package job.
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=None,  # noqa: S113
            headers=self._auth_headers,
        ) as c:
            r = await c.post("/save_image", json=payload)
            r.raise_for_status()
            return r.json()

    async def stream_logs(self, container_id: str) -> httpx.Response:
        # Long-poll log stream kept open for the lifetime of the caller's
        # aiter_lines loop. Caller decides when to disconnect.
        client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=None,  # noqa: S113
            headers=self._auth_headers,
        )
        return await client.send(
            client.build_request("GET", f"/logs/{container_id}/stream"), stream=True
        )


def get_builder_client() -> BuilderClient:
    return BuilderClient()
