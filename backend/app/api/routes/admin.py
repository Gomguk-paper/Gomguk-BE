import platform
import psutil
from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentAdmin

router = APIRouter()


class CpuInfo(BaseModel):
    percent: float
    cores: int


class MemoryInfo(BaseModel):
    total: int
    available: int
    used: int
    percent: float


class DiskInfo(BaseModel):
    total: int
    used: int
    free: int
    percent: float


class SystemStatsResponse(BaseModel):
    cpu: CpuInfo
    memory: MemoryInfo
    disk: DiskInfo
    os: str
    boot_time: str


@router.get("/system-stats", response_model=SystemStatsResponse)
def get_system_stats(current_admin: CurrentAdmin) -> SystemStatsResponse:
    # CPU (0.1s interval to get accurate utilization)
    cpu_percent = psutil.cpu_percent(interval=0.1)
    cpu_cores = psutil.cpu_count()

    # Memory (RAM)
    mem = psutil.virtual_memory()
    memory_info = MemoryInfo(
        total=mem.total,
        available=mem.available,
        used=mem.used,
        percent=mem.percent,
    )

    # Disk Storage (Root)
    disk = psutil.disk_usage("/")
    disk_info = DiskInfo(
        total=disk.total,
        used=disk.used,
        free=disk.free,
        percent=disk.percent,
    )

    # OS Info
    os_name = f"{platform.system()} {platform.release()} ({platform.machine()})"

    # Server Boot Time
    boot_time_ts = psutil.boot_time()
    boot_time_str = datetime.fromtimestamp(boot_time_ts, tz=timezone.utc).isoformat()

    return SystemStatsResponse(
        cpu=CpuInfo(percent=cpu_percent, cores=cpu_cores),
        memory=memory_info,
        disk=disk_info,
        os=os_name,
        boot_time=boot_time_str,
    )
