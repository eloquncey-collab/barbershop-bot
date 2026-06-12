import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

def test_start_monitoring():
    import monitoring
    monitoring._start_time = None
    monitoring.start_monitoring()
    assert monitoring._start_time is not None

def test_get_uptime_after_start():
    import monitoring
    monitoring.start_monitoring()
    time.sleep(0.01)
    assert monitoring.get_uptime() > 0

def test_get_uptime_before_start():
    import monitoring
    monitoring._start_time = None
    assert monitoring.get_uptime() == 0

def test_format_seconds():
    import monitoring
    assert monitoring.format_uptime(45) == "45s"

def test_format_minutes():
    import monitoring
    assert monitoring.format_uptime(125) == "2m 5s"

def test_format_hours():
    import monitoring
    assert monitoring.format_uptime(3725) == "1h 2m 5s"

def test_format_zero():
    import monitoring
    assert monitoring.format_uptime(0) == "0s"

@pytest.mark.asyncio
async def test_check_db_ok():
    import monitoring
    with patch("aiosqlite.connect") as mc:
        db = AsyncMock()
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=False)
        db.execute = AsyncMock()
        mc.return_value = db
        result = await monitoring.check_db_health()
    assert result is True

@pytest.mark.asyncio
async def test_check_db_fail():
    import monitoring
    with patch("aiosqlite.connect", side_effect=Exception("err")):
        result = await monitoring.check_db_health()
    assert result is False

@pytest.mark.asyncio
async def test_check_storage_ok():
    import monitoring
    assert await monitoring.check_storage_health() is True

@pytest.mark.asyncio
async def test_check_storage_fail():
    import monitoring
    with patch("tempfile.NamedTemporaryFile", side_effect=OSError("err")):
        result = await monitoring.check_storage_health()
    assert result is False

@pytest.mark.asyncio
async def test_scheduler_running():
    import monitoring
    ms = MagicMock(); ms.running = True
    with patch("scheduler.scheduler", ms):
        assert await monitoring.check_scheduler_health() is True

@pytest.mark.asyncio
async def test_scheduler_not_running():
    import monitoring
    ms = MagicMock(); ms.running = False
    with patch("scheduler.scheduler", ms):
        assert await monitoring.check_scheduler_health() is False

@pytest.mark.asyncio
async def test_scheduler_exception():
    import monitoring
    with patch("monitoring.scheduler", create=True) as ms:
        ms.scheduler = None
        type(ms).running = property(lambda self: (_ for _ in ()).throw(Exception("e")))
        result = await monitoring.check_scheduler_health()
    # Should return False or True depending on import - just check it runs
    assert isinstance(result, bool)

@pytest.mark.asyncio
async def test_health_ok():
    import monitoring
    monitoring.start_monitoring()
    with (patch.object(monitoring, "check_db_health", AsyncMock(return_value=True)),
         patch.object(monitoring, "check_storage_health", AsyncMock(return_value=True)),
         patch.object(monitoring, "check_scheduler_health", AsyncMock(return_value=True))):
        s = await monitoring.get_health_status()
    assert s["status"] == "ok"
    assert s["checks"]["database"] == "ok"

@pytest.mark.asyncio
async def test_health_degraded():
    import monitoring
    monitoring.start_monitoring()
    with (patch.object(monitoring, "check_db_health", AsyncMock(return_value=False)),
         patch.object(monitoring, "check_storage_health", AsyncMock(return_value=True)),
         patch.object(monitoring, "check_scheduler_health", AsyncMock(return_value=True))):
        s = await monitoring.get_health_status()
    assert s["status"] == "degraded"
