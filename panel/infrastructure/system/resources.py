from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import psutil


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    percent: float
    used_bytes: int | None = None
    total_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class SystemResourcesSnapshot:
    cpu_percent: float
    memory: ResourceSnapshot
    swap: ResourceSnapshot
    disk: ResourceSnapshot
    disk_path: str


def _clamp_percent(value: float) -> float:
    return round(min(max(value, 0.0), 100.0), 1)


def collect_system_resources(disk_path: Path) -> SystemResourcesSnapshot:
    cpu_percent = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage(str(disk_path))

    return SystemResourcesSnapshot(
        cpu_percent=_clamp_percent(cpu_percent),
        memory=ResourceSnapshot(_clamp_percent(memory.percent), memory.used, memory.total),
        swap=ResourceSnapshot(_clamp_percent(swap.percent), swap.used, swap.total),
        disk=ResourceSnapshot(_clamp_percent(disk.percent), disk.used, disk.total),
        disk_path=str(disk_path),
    )


async def get_system_resources(disk_path: Path) -> SystemResourcesSnapshot:
    return await asyncio.to_thread(collect_system_resources, disk_path)
