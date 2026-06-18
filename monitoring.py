import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_start_time = None


def start_monitoring():
    global _start_time
    _start_time = time.time()
    logger.info("Monitoring started")


def get_uptime() -> float:
    if _start_time:
        return time.time() - _start_time
    return 0


async def check_db_health() -> bool:
    """Check if database is accessible."""
    try:
        import db as _db
        async with _db.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        return False


async def check_storage_health() -> bool:
    """HIGH-05 FIX: Actually check the FSM storage (FileStorage or Redis)."""
    try:
        import os
        redis_url = os.getenv("REDIS_URL", "")
        if redis_url:
            # Test Redis connectivity
            import aioredis
            r = await aioredis.from_url(redis_url, socket_connect_timeout=3)
            await r.ping()
            await r.close()
        else:
            # Test FileStorage JSON file is readable/writable
            import config as _cfg
            from pathlib import Path
            fsm_file = Path(_cfg.DB_PATH).parent / "fsm_state.json"
            parent = fsm_file.parent
            parent.mkdir(parents=True, exist_ok=True)
            if fsm_file.exists():
                with open(fsm_file, "r", encoding="utf-8") as f:
                    import json
                    json.load(f)
        return True
    except Exception as e:
        logger.error(f"Storage health check failed: {e}")
        return False


async def check_scheduler_health() -> bool:
    """Check if scheduler is running."""
    try:
        from scheduler import scheduler
        return scheduler.running
    except Exception as e:
        logger.error(f"Scheduler health check failed: {e}")
        return False


async def get_health_status() -> dict:
    """Get comprehensive health status with real checks."""
    uptime = get_uptime()
    db_ok = await check_db_health()
    storage_ok = await check_storage_health()
    scheduler_ok = await check_scheduler_health()
    all_ok = db_ok and storage_ok and scheduler_ok
    return {
        "status": "ok" if all_ok else "degraded",
        "uptime_seconds": round(uptime, 2),
        "uptime_human": format_uptime(uptime),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "database": "ok" if db_ok else "error",
            "storage": "ok" if storage_ok else "error",
            "scheduler": "ok" if scheduler_ok else "error",
        }
    }


def format_uptime(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"
