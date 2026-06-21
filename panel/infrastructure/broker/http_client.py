from __future__ import annotations

from typing import Any

import httpx

from panel.config import BrokerClientSettings
from panel.domain.ports.broker import BrokerPort, PublishedTask, PulledTask, TaskStatus


class HttpBrokerClient(BrokerPort):
    def __init__(self, settings: BrokerClientSettings) -> None:
        self._settings = settings
        headers: dict[str, str] = {}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        self._client = httpx.AsyncClient(
            base_url=settings.url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(60.0),
        )

    async def publish_task(
        self,
        task_type: str,
        payload: dict[str, Any],
        *,
        delay_seconds: int = 0,
        max_retries: int | None = None,
    ) -> PublishedTask:
        body: dict[str, Any] = {
            "task_type": task_type,
            "payload": payload,
            "delay_seconds": delay_seconds,
        }
        if max_retries is not None:
            body["max_retries"] = max_retries
        response = await self._client.post("/api/v1/tasks", json=body)
        response.raise_for_status()
        data = response.json()
        return PublishedTask(task_id=data["task_id"])

    async def get_status(self, task_id: str) -> TaskStatus:
        response = await self._client.get(f"/api/v1/tasks/{task_id}/status")
        response.raise_for_status()
        data = response.json()
        return TaskStatus(
            task_id=data["id"],
            status=data["status"],
            retries=data["retries"],
            max_retries=data["max_retries"],
        )

    async def pull(
        self,
        worker_id: str,
        task_types: list[str],
        *,
        timeout: int | None = None,
    ) -> PulledTask | None:
        params: list[tuple[str, str]] = [("worker_id", worker_id)]
        for task_type in task_types:
            params.append(("task_types", task_type))
        if timeout is not None:
            params.append(("timeout", str(timeout)))
        response = await self._client.get("/api/v1/tasks/pull", params=params)
        if response.status_code == 204:
            return None
        response.raise_for_status()
        data = response.json()
        return PulledTask(
            task_id=data["task_id"],
            task_type=data["task_type"],
            payload=data["payload"],
            lock_ttl_seconds=data["lock_ttl_seconds"],
        )

    async def heartbeat(self, task_id: str, worker_id: str) -> None:
        response = await self._client.post(
            f"/api/v1/tasks/{task_id}/heartbeat",
            json={"worker_id": worker_id},
        )
        response.raise_for_status()

    async def ack(self, task_id: str, worker_id: str) -> None:
        response = await self._client.post(
            f"/api/v1/tasks/{task_id}/ack",
            json={"worker_id": worker_id},
        )
        response.raise_for_status()

    async def nack(self, task_id: str, worker_id: str, reason: str = "") -> None:
        response = await self._client.post(
            f"/api/v1/tasks/{task_id}/nack",
            json={"worker_id": worker_id, "reason": reason},
        )
        response.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()
