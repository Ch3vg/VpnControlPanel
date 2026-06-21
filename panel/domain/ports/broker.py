from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class PublishedTask:
    task_id: str


@dataclass(frozen=True, slots=True)
class TaskStatus:
    task_id: str
    status: str
    retries: int
    max_retries: int


@dataclass(frozen=True, slots=True)
class PulledTask:
    task_id: str
    task_type: str
    payload: dict[str, Any]
    lock_ttl_seconds: int


class BrokerPort(Protocol):
    async def publish_task(
        self,
        task_type: str,
        payload: dict[str, Any],
        *,
        delay_seconds: int = 0,
        max_retries: int | None = None,
    ) -> PublishedTask: ...

    async def get_status(self, task_id: str) -> TaskStatus: ...

    async def pull(
        self,
        worker_id: str,
        task_types: list[str],
        *,
        timeout: int | None = None,
    ) -> PulledTask | None: ...

    async def heartbeat(self, task_id: str, worker_id: str) -> None: ...

    async def ack(self, task_id: str, worker_id: str) -> None: ...

    async def nack(self, task_id: str, worker_id: str, reason: str = "") -> None: ...

    async def close(self) -> None: ...
