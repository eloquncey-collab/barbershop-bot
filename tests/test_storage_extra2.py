import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.helpers import SAMPLE_BOOKING


class TestStorageStatsFunctions:
    """Lines 587-588, 831-872: storage stat functions."""

    async def test_get_bookings_by_date_range(self, db):
        import storage
        await storage.init_db()
        await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.get_bookings_by_date_range("2020-01-01", "2030-12-31")
        assert isinstance(result, list)

    async def test_get_stats_by_master(self, db):
        import storage
        await storage.init_db()
        result = await storage.get_stats_by_master()
        assert isinstance(result, list)

    async def test_get_stats_by_day(self, db):
        import storage
        await storage.init_db()
        result = await storage.get_stats_by_day()
        assert isinstance(result, list)

    async def test_get_stats_by_service(self, db):
        import storage
        await storage.init_db()
        result = await storage.get_stats_by_service()
        assert isinstance(result, list)

    async def test_get_master_stats(self, db):
        import storage
        await storage.init_db()
        await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.get_master_stats("Alibek")
        assert "total" in result

    async def test_get_service_stats(self, db):
        import storage
        await storage.init_db()
        result = await storage.get_service_stats("Haircut")
        assert "total" in result


class TestSaveMaster:
    """Line 925: save_master (sqlite branch)."""

    async def test_save_master_new(self, db):
        import storage
        await storage.init_db()
        await storage.save_master("TestMaster", "3 years", "fades")
        masters = await storage.get_all_masters()
        assert "TestMaster" in masters

    async def test_save_master_upsert(self, db):
        import storage
        await storage.init_db()
        await storage.save_master("TestMaster", "3 years", "fades")
        await storage.save_master("TestMaster", "5 years", "cuts")
        masters = await storage.get_all_masters()
        assert masters["TestMaster"]["experience"] == "5 years"


class TestSlotLockCleanup:
    """Lines 1168-1182: cleanup functions."""

    async def test_cleanup_slot_locks_on_startup(self, db):
        import storage
        await storage.init_db()
        await storage.create_slot_lock("2026-12-01", "10:00", "Alibek")
        await storage.cleanup_slot_locks_on_startup()
        locked = await storage.get_locked_slots("2026-12-01", "Alibek")
        assert len(locked) == 0

    async def test_cleanup_expired_slot_locks(self, db):
        import storage
        await storage.init_db()
        from datetime import datetime, timedelta
        past = (datetime.now() - timedelta(hours=2)).isoformat()
        # Insert directly with past expiry
        import db as db_module
        async with db_module.acquire() as conn:
            from tz_utils import get_now
            import config
            now = get_now(config.TIMEZONE).isoformat()
            await conn.execute(
                "INSERT OR IGNORE INTO slot_locks (date, time, master, locked_at, expires_at) VALUES (?,?,?,?,?)",
                "2026-01-01", "10:00", "OldMaster", now, past
            )
            await conn.commit()
        deleted = await storage.cleanup_expired_slot_locks()
        assert deleted >= 1


class TestMasterTelegramId:
    """Lines 1156-1157, 1203-1204: master telegram ID management."""

    async def test_set_and_get_master_telegram_id(self, db):
        import storage
        await storage.init_db()
        await storage.set_master_telegram_id("Alibek", 12345)
        result = await storage.get_master_telegram_id("Alibek")
        assert result == 12345

    async def test_get_master_telegram_id_none(self, db):
        import storage
        await storage.init_db()
        result = await storage.get_master_telegram_id("NonExistent")
        assert result is None

    async def test_set_master_telegram_id_none(self, db):
        import storage
        await storage.init_db()
        await storage.set_master_telegram_id("Alibek", 12345)
        await storage.set_master_telegram_id("Alibek", None)
        result = await storage.get_master_telegram_id("Alibek")
        assert result is None

    async def test_get_all_master_telegram_ids(self, db):
        import storage
        await storage.init_db()
        await storage.set_master_telegram_id("Alibek", 11111)
        await storage.set_master_telegram_id("Berik", 22222)
        result = await storage.get_all_master_telegram_ids()
        assert result.get("Alibek") == 11111
        assert result.get("Berik") == 22222


class TestSlotLockFailure:
    """Lines 412-413, 1134-1135: slot lock failure is non-fatal."""

    async def test_create_slot_lock_failure_is_non_fatal(self, db):
        import storage
        await storage.init_db()
        # Patch the upsert to fail — should only log a warning, not raise
        with patch("storage._db") as mock_db:
            mock_conn = AsyncMock()
            mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_conn.__aexit__ = AsyncMock(return_value=False)
            mock_conn.upsert = AsyncMock(side_effect=Exception("db fail"))
            mock_db.acquire.return_value = mock_conn
            # Should not raise
            await storage.create_slot_lock("2026-12-01", "10:00", "Alibek")
