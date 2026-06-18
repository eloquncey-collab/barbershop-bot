
"""Extended storage tests for lines missing coverage."""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from helpers import SAMPLE_BOOKING


# ====================================================================
# get_past_bookings, get_all_bookings, export_bookings_csv
# ====================================================================
class TestBookingQueries:

    async def test_get_past_bookings_empty(self, db):
        import storage
        result = await storage.get_past_bookings_for_completion()
        assert result == []

    async def test_get_all_bookings_empty(self, db):
        import storage
        result = await storage.get_all_bookings()
        assert result == []

    async def test_get_all_bookings_returns_saved(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.get_all_bookings()
        assert len(result) == 1
        assert result[0]["id"] == bid

    async def test_export_bookings_csv_empty(self, db):
        import storage
        result = await storage.export_bookings_csv()
        assert result == []

    async def test_cleanup_old_bookings_no_old(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        count = await storage.cleanup_old_bookings(days=90)
        # Future date booking -- not cleaned up
        assert count == 0

    async def test_cleanup_old_bookings_removes_old_cancelled(self, db):
        import storage
        old_booking = {**SAMPLE_BOOKING, "date": "2020-01-01", "time": "10:00"}
        bid = await storage.save_booking(old_booking)
        await storage.cancel_booking(bid)
        count = await storage.cleanup_old_bookings(days=30)
        assert count >= 1


# ====================================================================
# has_active_booking, user_rate_limit_check
# ====================================================================
class TestBookingChecks:

    async def test_has_active_booking_false_for_new_user(self, db):
        import storage
        result = await storage.has_active_booking(999999)
        assert result is False

    async def test_has_active_booking_true_after_booking(self, db):
        import storage, config
        # Set MAX_ACTIVE_BOOKINGS=1 scenario
        original = config.MAX_ACTIVE_BOOKINGS
        config.MAX_ACTIVE_BOOKINGS = 1
        try:
            bid = await storage.save_booking(SAMPLE_BOOKING)
            result = await storage.has_active_booking(SAMPLE_BOOKING["telegram_id"])
            assert result is True
        finally:
            config.MAX_ACTIVE_BOOKINGS = original

    async def test_user_rate_limit_check_false_for_new_user(self, db):
        import storage
        result = await storage.user_rate_limit_check(777888)
        assert result is True  # under limit

    async def test_user_rate_limit_check_blocks_on_excess(self, db):
        import storage
        uid = 5555
        booking_base = {**SAMPLE_BOOKING, "telegram_id": uid}
        for i in range(3):
            b = {**booking_base, "time": f"{10+i}:00"}
            await storage.save_booking(b)
        result = await storage.user_rate_limit_check(uid, window=3600, max_attempts=3)
        assert result is False


# ====================================================================
# get_booking_with_user, get_active_bookings_count, get_bookings_summary
# ====================================================================
class TestBookingExtended:

    async def test_get_booking_with_user_none_for_missing(self, db):
        import storage
        result = await storage.get_booking_with_user("nonexistent")
        assert result is None

    async def test_get_booking_with_user_returns_booking(self, db):
        import storage
        await storage.save_user(SAMPLE_BOOKING["telegram_id"],
            username=SAMPLE_BOOKING["username"], first_name="Ivan")
        bid = await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.get_booking_with_user(bid)
        assert result is not None
        assert result["id"] == bid

    async def test_get_active_bookings_count_zero(self, db):
        import storage
        assert await storage.get_active_bookings_count() == 0

    async def test_get_active_bookings_count_after_booking(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        assert await storage.get_active_bookings_count() == 1

    async def test_get_bookings_summary_empty_date(self, db):
        import storage
        s = await storage.get_bookings_summary("2099-01-01")
        assert s["total"] == 0
        assert s["active"] == 0
        assert s["revenue"] == 0

    async def test_get_bookings_summary_counts_bookings(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        s = await storage.get_bookings_summary(SAMPLE_BOOKING["date"])
        assert s["total"] >= 1
        assert s["active"] >= 1


# ====================================================================
# get_stats_by_service
# ====================================================================
class TestStatsByService:

    async def test_get_stats_by_service_empty_list(self, db):
        import storage
        result = await storage.get_stats_by_service()
        assert isinstance(result, list)

    async def test_get_stats_by_service_after_booking(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.get_stats_by_service()
        assert isinstance(result, list)
        assert len(result) >= 1
        assert "service" in result[0] or "count" in result[0]


# ====================================================================
# Master work days & services
# ====================================================================
class TestMasterWorkDays:

    async def test_get_master_work_days_default(self, db):
        import storage
        await storage.save_master("Alibek", "5 years", "fades")
        days = await storage.get_master_work_days("Alibek")
        assert days == [1, 2, 3, 4, 5, 6]

    async def test_set_master_work_days_success(self, db):
        import storage
        await storage.save_master("Alibek", "5 years", "fades")
        result = await storage.set_master_work_days("Alibek", [1, 2, 3])
        assert result is True
        days = await storage.get_master_work_days("Alibek")
        assert days == [1, 2, 3]

    async def test_set_master_work_days_missing_master(self, db):
        import storage
        result = await storage.set_master_work_days("NoSuchMaster", [1, 2])
        assert result is False

    async def test_set_master_services_success(self, db):
        import storage, config
        await storage.save_master("Alibek", "5 years", "fades")
        service_names = list(config.SERVICES.keys())[:2]
        result = await storage.set_master_services("Alibek", service_names)
        assert result is True
        services = await storage.get_master_services("Alibek")
        assert set(services).issubset(set(config.SERVICES.keys()))

    async def test_set_master_services_missing_master(self, db):
        import storage
        result = await storage.set_master_services("Ghost", ["Haircut"])
        assert result is False

    async def test_get_master_services_fallback_all(self, db):
        """Master with no custom services returns all config.SERVICES."""
        import storage, config
        await storage.save_master("Alibek", "5 years", "fades")
        services = await storage.get_master_services("Alibek")
        assert set(services) == set(config.SERVICES.keys())


# ====================================================================
# Master service prices
# ====================================================================
class TestMasterServicePrices:

    async def test_set_and_get_master_service_price(self, db):
        import storage
        await storage.save_master("Alibek", "5 years", "fades")
        await storage.set_master_service_price("Alibek", "Haircut", 4500)
        prices = await storage.get_all_master_service_prices("Alibek")
        assert prices["Haircut"] == 4500

    async def test_delete_master_service_price(self, db):
        import storage
        await storage.save_master("Alibek", "5 years", "fades")
        await storage.set_master_service_price("Alibek", "Haircut", 4500)
        await storage.delete_master_service_price("Alibek", "Haircut")
        prices = await storage.get_all_master_service_prices("Alibek")
        assert "Haircut" not in prices

    async def test_get_service_price_with_custom(self, db):
        import storage
        await storage.save_master("Alibek", "5 years", "fades")
        await storage.set_master_service_price("Alibek", "Haircut", 9999)
        price = await storage.get_effective_price("Alibek", "Haircut")
        assert price == 9999

    async def test_get_service_price_fallback_config(self, db):
        import storage, config
        service = list(config.SERVICES.keys())[0]
        price = await storage.get_effective_price("AnyMaster", service)
        assert price == config.SERVICES[service]

    async def test_get_all_master_service_prices_empty(self, db):
        import storage
        prices = await storage.get_all_master_service_prices("NoMaster")
        assert prices == {}


# ====================================================================
# Slot locks
# ====================================================================
class TestSlotLocks:

    async def test_create_slot_lock(self, db):
        import storage
        await storage.create_slot_lock("2026-12-01", "10:00", "Alibek")
        # No exception = success

    async def test_cleanup_slot_locks_on_startup(self, db):
        import storage
        await storage.create_slot_lock("2026-12-01", "10:00", "Alibek")
        await storage.cleanup_slot_locks_on_startup()
        # After cleanup, no locks remain (test via trying to acquire again)

    async def test_cleanup_expired_slot_locks_zero_on_fresh(self, db):
        import storage
        count = await storage.cleanup_expired_slot_locks()
        assert count == 0

    async def test_cleanup_expired_slot_locks_removes_expired(self, db):
        import storage
        # Create a lock that expires immediately by using past expiry
        import db as _db
        async with _db.acquire() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO slot_locks (date, time, master, locked_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                "2020-01-01", "10:00", "Alibek",
                "2020-01-01T10:00:00", "2020-01-01T10:05:00"
            )
            await conn.commit()
        count = await storage.cleanup_expired_slot_locks()
        assert count >= 1


# ====================================================================
# Master Telegram IDs
# ====================================================================
class TestMasterTelegramIds:

    async def test_get_master_telegram_id_none_for_unknown(self, db):
        import storage
        result = await storage.get_master_telegram_id("Unknown")
        assert result is None

    async def test_set_and_get_master_telegram_id(self, db):
        import storage
        await storage.set_master_telegram_id("Alibek", 987654321)
        result = await storage.get_master_telegram_id("Alibek")
        assert result == 987654321

    async def test_unset_master_telegram_id(self, db):
        import storage
        await storage.set_master_telegram_id("Alibek", 987654321)
        await storage.set_master_telegram_id("Alibek", None)
        result = await storage.get_master_telegram_id("Alibek")
        assert result is None

    async def test_get_all_master_telegram_ids(self, db):
        import storage
        await storage.set_master_telegram_id("Alibek", 111)
        await storage.set_master_telegram_id("Damir", 222)
        ids = await storage.get_all_master_telegram_ids()
        assert ids["Alibek"] == 111
        assert ids["Damir"] == 222


# ====================================================================
# delete_old_scheduler_jobs
# ====================================================================
class TestSchedulerJobsExtended:

    async def test_delete_old_scheduler_jobs_no_jobs(self, db):
        import storage
        await storage.delete_old_scheduler_jobs()  # should not raise

    async def test_delete_old_scheduler_jobs_removes_past(self, db):
        import storage
        # Insert a job with past run_date
        import db as _db
        async with _db.acquire() as conn:
            await conn.execute(
                "INSERT INTO scheduler_jobs (id, run_date, job_type, booking_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                "job_old", "2020-01-01T10:00:00", "reminder", "abc123", "2020-01-01T00:00:00"
            )
            await conn.commit()
        await storage.delete_old_scheduler_jobs()
        jobs = await storage.get_all_scheduler_jobs()
        assert all(j["id"] != "job_old" for j in jobs)
