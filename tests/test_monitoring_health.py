
"""Tests for updated monitoring.py (HIGH-05)."""
import pytest, sys, pathlib, json, time
from unittest.mock import AsyncMock, patch, MagicMock
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


class TestCheckStorageHealthSqlite:

    async def test_returns_true_no_redis(self):
        import monitoring
        with patch("os.getenv", return_value=""):
            assert await monitoring.check_storage_health() is True

    async def test_returns_true_fsm_file_absent(self, tmp_path, monkeypatch):
        import monitoring, config
        monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "db.db"))
        with patch("os.getenv", return_value=""):
            assert await monitoring.check_storage_health() is True

    async def test_returns_true_valid_json(self, tmp_path, monkeypatch):
        import monitoring, config
        monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "db.db"))
        (tmp_path / "fsm_state.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
        with patch("os.getenv", return_value=""):
            assert await monitoring.check_storage_health() is True

    async def test_returns_false_invalid_json(self, tmp_path, monkeypatch):
        import monitoring, config
        monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "db.db"))
        (tmp_path / "fsm_state.json").write_bytes(b"\xff\xfe corrupted {{{")
        with patch("os.getenv", return_value=""):
            assert await monitoring.check_storage_health() is False


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("aioredis"),
    reason="aioredis not installed"
)
class TestCheckStorageHealthRedis:

    async def test_returns_true_when_ping_ok(self):
        import monitoring
        mock_r = AsyncMock()
        mock_r.ping = AsyncMock(return_value=True)
        mock_r.close = AsyncMock()
        with patch("os.getenv", return_value="redis://localhost:6379/0"), \
             patch("aioredis.from_url", return_value=mock_r):
            assert await monitoring.check_storage_health() is True
        mock_r.ping.assert_called_once()

    async def test_returns_false_when_unreachable(self):
        import monitoring
        with patch("os.getenv", return_value="redis://localhost:6379/0"), \
             patch("aioredis.from_url", side_effect=ConnectionRefusedError()):
            assert await monitoring.check_storage_health() is False

    async def test_returns_false_when_ping_raises(self):
        import monitoring
        mock_r = AsyncMock()
        mock_r.ping = AsyncMock(side_effect=Exception("timeout"))
        mock_r.close = AsyncMock()
        with patch("os.getenv", return_value="redis://localhost:6379/0"), \
             patch("aioredis.from_url", return_value=mock_r):
            assert await monitoring.check_storage_health() is False


class TestCheckDbHealth:

    async def test_true_with_working_db(self, db):
        import monitoring
        assert await monitoring.check_db_health() is True

    async def test_false_when_db_fails(self):
        import monitoring
        import db as _db
        with patch.object(_db, "acquire", side_effect=Exception("down")):
            assert await monitoring.check_db_health() is False


class TestGetHealthStatus:

    async def test_ok_when_all_pass(self, db):
        import monitoring
        monitoring.start_monitoring()
        with patch("monitoring.check_storage_health", return_value=True), \
             patch("monitoring.check_scheduler_health", return_value=True):
            s = await monitoring.get_health_status()
        assert s["status"] == "ok"
        assert all(v == "ok" for v in s["checks"].values())

    async def test_degraded_when_storage_fails(self, db):
        import monitoring
        monitoring.start_monitoring()
        with patch("monitoring.check_storage_health", return_value=False), \
             patch("monitoring.check_scheduler_health", return_value=True):
            s = await monitoring.get_health_status()
        assert s["status"] == "degraded"
        assert s["checks"]["storage"] == "error"

    async def test_timestamp_iso(self, db):
        import monitoring
        from datetime import datetime
        monitoring.start_monitoring()
        with patch("monitoring.check_storage_health", return_value=True), \
             patch("monitoring.check_scheduler_health", return_value=True):
            s = await monitoring.get_health_status()
        datetime.fromisoformat(s["timestamp"])


class TestFormatUptime:
    def test_seconds(self):
        import monitoring
        assert monitoring.format_uptime(45) == "45s"
    def test_minutes(self):
        import monitoring
        assert monitoring.format_uptime(125) == "2m 5s"
    def test_hours(self):
        import monitoring
        assert monitoring.format_uptime(3661) == "1h 1m 1s"
    def test_zero(self):
        import monitoring
        assert monitoring.format_uptime(0) == "0s"
