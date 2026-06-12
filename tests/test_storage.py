
"""Tests for storage.py - covers all CRUD operations (~85% storage coverage)."""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from helpers import SAMPLE_BOOKING


# ============================================================
# init_db
# ============================================================
class TestInitDb:
    async def test_creates_all_tables(self, db):
        import aiosqlite, config
        async with aiosqlite.connect(config.DB_PATH) as conn:
            cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in await cursor.fetchall()}
        expected = {"bookings", "users", "waitlist", "loyalty", "referrals",
                    "reviews", "settings", "masters", "services", "scheduler_jobs", "slot_locks"}
        assert expected.issubset(tables)

    async def test_wal_mode(self, db):
        import aiosqlite, config
        async with aiosqlite.connect(config.DB_PATH) as conn:
            cursor = await conn.execute("PRAGMA journal_mode")
            mode = (await cursor.fetchone())[0]
        assert mode == "wal"

    async def test_idempotent(self, db):
        """Calling init_db twice must not raise."""
        import storage
        await storage.init_db()


# ============================================================
# users
# ============================================================
class TestUsers:
    async def test_save_and_get_user(self, db):
        import storage
        await storage.save_user(101, phone="+77001234567", username="u1", first_name="Alice")
        user = await storage.get_user(101)
        assert user is not None
        assert user["telegram_id"] == 101
        assert user["phone"] == "+77001234567"
        assert user["first_name"] == "Alice"

    async def test_get_missing_user_returns_none(self, db):
        import storage
        assert await storage.get_user(999) is None

    async def test_save_user_upsert_phone(self, db):
        import storage
        await storage.save_user(101, username="u1", first_name="Alice")
        await storage.save_user(101, phone="+77001234567", username="u1", first_name="Alice")
        user = await storage.get_user(101)
        assert user["phone"] == "+77001234567"

    async def test_save_user_preserves_phone(self, db):
        """Saving without phone must not overwrite existing phone."""
        import storage
        await storage.save_user(101, phone="+77009999999", username="u1", first_name="Bob")
        await storage.save_user(101, username="u1_new", first_name="Bob")
        user = await storage.get_user(101)
        assert user["phone"] == "+77009999999"


# ============================================================
# bookings
# ============================================================
class TestSaveBooking:
    async def test_save_booking_returns_id(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        assert bid is not None
        assert len(bid) == 12

    async def test_saved_booking_is_active(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        bookings = await storage.get_user_bookings(SAMPLE_BOOKING["telegram_id"])
        assert any(b["id"] == bid for b in bookings)

    async def test_duplicate_slot_returns_none(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.save_booking(SAMPLE_BOOKING)
        assert result is None

    async def test_different_master_same_slot_allowed(self, db):
        import storage
        booking2 = {**SAMPLE_BOOKING, "master": "Damir"}
        await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.save_booking(booking2)
        assert result is not None

    async def test_same_master_different_time_allowed(self, db):
        import storage
        booking2 = {**SAMPLE_BOOKING, "time": "10:30"}
        await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.save_booking(booking2)
        assert result is not None

    async def test_cancelled_slot_can_be_rebooked(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.cancel_booking(bid, telegram_id=SAMPLE_BOOKING["telegram_id"])
        result = await storage.save_booking(SAMPLE_BOOKING)
        assert result is not None


class TestCancelBooking:
    async def test_cancel_own_booking(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.cancel_booking(bid, telegram_id=111)
        assert result is not None
        assert result["status"] == "active"  # returns old status

    async def test_cancel_wrong_user_returns_none(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.cancel_booking(bid, telegram_id=999)
        assert result is None

    async def test_cancel_releases_slot_lock(self, db):
        import storage, aiosqlite, config
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.create_slot_lock(SAMPLE_BOOKING["date"], SAMPLE_BOOKING["time"], SAMPLE_BOOKING["master"])
        await storage.cancel_booking(bid, telegram_id=111)
        async with aiosqlite.connect(config.DB_PATH) as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM slot_locks")
            count = (await cursor.fetchone())[0]
        assert count == 0

    async def test_cancel_nonexistent_returns_none(self, db):
        import storage
        result = await storage.cancel_booking("nonexistent_id", telegram_id=111)
        assert result is None

    async def test_cancel_already_cancelled_returns_none(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.cancel_booking(bid, telegram_id=111)
        result = await storage.cancel_booking(bid, telegram_id=111)
        assert result is None


class TestCompleteBooking:
    async def test_complete_active_booking(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.complete_booking(bid)
        assert result is not None

    async def test_complete_nonexistent_returns_none(self, db):
        import storage
        result = await storage.complete_booking("nope")
        assert result is None


class TestGetBookedSlots:
    async def test_booked_slot_returned(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        slots = await storage.get_booked_slots(SAMPLE_BOOKING["date"], SAMPLE_BOOKING["master"])
        times = [s["time"] for s in slots]
        assert SAMPLE_BOOKING["time"] in times

    async def test_cancelled_slot_not_returned(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.cancel_booking(bid, telegram_id=111)
        slots = await storage.get_booked_slots(SAMPLE_BOOKING["date"], SAMPLE_BOOKING["master"])
        assert len(slots) == 0


# ============================================================
# has_active_booking
# ============================================================
class TestHasActiveBooking:
    async def test_false_when_no_bookings(self, db):
        import storage
        assert await storage.has_active_booking(111) is False

    async def test_true_at_max_bookings(self, db):
        import storage
        for t in ["10:00", "11:00", "12:00"]:
            await storage.save_booking({**SAMPLE_BOOKING, "time": t})
        assert await storage.has_active_booking(111) is True

    async def test_false_below_max(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        assert await storage.has_active_booking(111) is False


# ============================================================
# slot_locks
# ============================================================
class TestSlotLocks:
    async def test_create_and_release(self, db):
        import storage, aiosqlite, config
        await storage.create_slot_lock("2026-12-01", "10:00", "Alibek")
        async with aiosqlite.connect(config.DB_PATH) as conn:
            c = await conn.execute("SELECT COUNT(*) FROM slot_locks")
            assert (await c.fetchone())[0] == 1
        await storage.release_slot_lock("2026-12-01", "10:00", "Alibek")
        async with aiosqlite.connect(config.DB_PATH) as conn:
            c = await conn.execute("SELECT COUNT(*) FROM slot_locks")
            assert (await c.fetchone())[0] == 0

    async def test_cleanup_expired(self, db):
        import storage, aiosqlite, config
        from datetime import datetime, timedelta
        # Insert an already-expired lock manually
        past = (datetime.now() - timedelta(minutes=10)).isoformat()
        async with aiosqlite.connect(config.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO slot_locks VALUES (?,?,?,?,?)",
                ("2026-12-01", "10:00", "Alibek", past, past)
            )
            await conn.commit()
        deleted = await storage.cleanup_expired_slot_locks()
        assert deleted >= 1

    async def test_cleanup_keeps_active_lock(self, db):
        import storage
        await storage.create_slot_lock("2026-12-01", "10:00", "Alibek", ttl_minutes=5)
        deleted = await storage.cleanup_expired_slot_locks()
        assert deleted == 0

    async def test_startup_cleanup_clears_all(self, db):
        import storage, aiosqlite, config
        await storage.create_slot_lock("2026-12-01", "10:00", "Alibek")
        await storage.cleanup_slot_locks_on_startup()
        async with aiosqlite.connect(config.DB_PATH) as conn:
            c = await conn.execute("SELECT COUNT(*) FROM slot_locks")
            assert (await c.fetchone())[0] == 0


# ============================================================
# waitlist
# ============================================================
class TestWaitlist:
    async def test_add_and_get(self, db):
        import storage
        await storage.add_to_waitlist(111, "Ivan", "Alibek", "Haircut", "2026-12-01", "10:00")
        entries = await storage.get_waitlist_for_slot("2026-12-01", "10:00", "Alibek")
        assert len(entries) == 1
        assert entries[0]["telegram_id"] == 111

    async def test_update_status(self, db):
        import storage
        await storage.add_to_waitlist(111, "Ivan", "Alibek", "Haircut", "2026-12-01", "10:00")
        entries = await storage.get_waitlist_for_slot("2026-12-01", "10:00", "Alibek")
        await storage.update_waitlist_status(entries[0]["id"], "offered")
        entries2 = await storage.get_waitlist_for_slot("2026-12-01", "10:00", "Alibek")
        # offered status should not appear (query filters waiting)
        assert len(entries2) == 0

    async def test_different_slot_not_returned(self, db):
        import storage
        await storage.add_to_waitlist(111, "Ivan", "Alibek", "Haircut", "2026-12-01", "10:00")
        entries = await storage.get_waitlist_for_slot("2026-12-01", "11:00", "Alibek")
        assert len(entries) == 0

    async def test_user_waitlist_count(self, db):
        import storage
        await storage.add_to_waitlist(111, "Ivan", "Alibek", "Haircut", "2026-12-01", "10:00")
        await storage.add_to_waitlist(111, "Ivan", "Alibek", "Haircut", "2026-12-01", "11:00")
        count = await storage.get_user_waitlist_count(111)
        assert count == 2


# ============================================================
# loyalty
# ============================================================
class TestLoyalty:
    async def test_first_visit_creates_record(self, db):
        import storage
        visits = await storage.update_loyalty(111, "Ivan")
        assert visits == 1

    async def test_subsequent_visits_increment(self, db):
        import storage
        await storage.update_loyalty(111, "Ivan")
        await storage.update_loyalty(111, "Ivan")
        visits = await storage.update_loyalty(111, "Ivan")
        assert visits == 3

    async def test_get_loyalty(self, db):
        import storage
        await storage.update_loyalty(111, "Ivan")
        data = await storage.get_loyalty(111)
        assert data is not None
        assert data["visits"] == 1

    async def test_get_loyalty_missing_returns_none(self, db):
        import storage
        assert await storage.get_loyalty(999) is None

    async def test_add_bonus(self, db):
        import storage
        await storage.update_loyalty(111, "Ivan")
        ok = await storage.add_bonus(111, 100)
        assert ok is True
        data = await storage.get_loyalty(111)
        assert data["bonuses"] == 100

    async def test_add_bonus_missing_user_returns_false(self, db):
        import storage
        ok = await storage.add_bonus(999, 100)
        assert ok is False


# ============================================================
# referrals
# ============================================================
class TestReferrals:
    async def test_add_referral(self, db):
        import storage
        ok = await storage.add_referral(111, 222)
        assert ok is True

    async def test_prevent_self_referral(self, db):
        import storage
        ok = await storage.add_referral(111, 111)
        assert ok is False

    async def test_prevent_duplicate_referral(self, db):
        import storage
        await storage.add_referral(111, 222)
        ok = await storage.add_referral(111, 222)
        assert ok is False


# ============================================================
# reviews
# ============================================================
class TestReviews:
    async def test_review_rejected_for_active_booking(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        ok = await storage.save_review(bid, 111, 5, "Great!")
        assert ok is False  # booking not completed

    async def test_review_saved_for_completed_booking(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.complete_booking(bid)
        ok = await storage.save_review(bid, 111, 5, "Great!")
        assert ok is True

    async def test_review_no_duplicate(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.complete_booking(bid)
        await storage.save_review(bid, 111, 5, "Great!")
        ok = await storage.save_review(bid, 111, 4, "Good")
        assert ok is False


# ============================================================
# stats
# ============================================================
class TestStats:
    async def test_empty_stats(self, db):
        import storage
        stats = await storage.get_stats()
        assert stats["total"] == 0
        assert stats["revenue"] == 0

    async def test_stats_after_booking(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        stats = await storage.get_stats()
        assert stats["total"] == 1
        assert stats["active"] == 1

    async def test_revenue_from_completed(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.complete_booking(bid)
        stats = await storage.get_stats()
        assert stats["completed"] == 1
        assert stats["revenue"] == 3000

    async def test_stats_by_master(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        by_master = await storage.get_stats_by_master()
        assert any(m["master"] == "Alibek" for m in by_master)

    async def test_stats_by_service(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        by_service = await storage.get_stats_by_service()
        assert any(s["service"] == "Haircut" for s in by_service)


# ============================================================
# settings / masters / services
# ============================================================
class TestSettings:
    async def test_save_and_get(self, db):
        import storage
        await storage.save_settings("address", "Test St 1")
        val = await storage.get_settings("address")
        assert val == "Test St 1"

    async def test_get_missing_returns_none(self, db):
        import storage
        assert await storage.get_settings("nonexistent") is None

    async def test_get_all_settings(self, db):
        import storage
        await storage.save_settings("k1", "v1")
        await storage.save_settings("k2", "v2")
        all_s = await storage.get_all_settings()
        assert all_s["k1"] == "v1"
        assert all_s["k2"] == "v2"


class TestMasters:
    async def test_save_and_get_masters(self, db):
        import storage
        await storage.save_master("Alibek", "5 years", "fades")
        masters = await storage.get_all_masters()
        assert "Alibek" in masters
        assert masters["Alibek"]["experience"] == "5 years"

    async def test_remove_master(self, db):
        import storage
        await storage.save_master("Alibek", "5 years", "fades")
        await storage.remove_master("Alibek")
        masters = await storage.get_all_masters()
        assert "Alibek" not in masters


class TestServices:
    async def test_save_and_get_services(self, db):
        import storage
        await storage.save_service("Haircut", 3000)
        services = await storage.get_all_services()
        assert "Haircut" in services
        assert services["Haircut"] == 3000

    async def test_remove_service(self, db):
        import storage
        await storage.save_service("Haircut", 3000)
        await storage.remove_service("Haircut")
        services = await storage.get_all_services()
        assert "Haircut" not in services


# ============================================================
# scheduler jobs
# ============================================================
class TestSchedulerJobs:
    async def test_save_and_get_jobs(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.save_scheduler_job("job1", "2026-12-01T09:00", "reminder_24h", bid)
        jobs = await storage.get_all_scheduler_jobs()
        assert any(j["id"] == "job1" for j in jobs)

    async def test_remove_job(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.save_scheduler_job("job1", "2026-12-01T09:00", "reminder_24h", bid)
        await storage.remove_scheduler_job("job1")
        jobs = await storage.get_all_scheduler_jobs()
        assert not any(j["id"] == "job1" for j in jobs)


# ============================================================
# admin helpers
# ============================================================
class TestAdminHelpers:
    async def test_admin_cancel_booking(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.admin_cancel_booking(bid)
        assert result is not None
        assert result["id"] == bid

    async def test_admin_cancel_nonexistent(self, db):
        import storage
        result = await storage.admin_cancel_booking("nope")
        assert result is None

    async def test_admin_complete_booking(self, db):
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        result = await storage.admin_complete_booking(bid)
        assert result is not None

    async def test_export_bookings_csv(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        rows = await storage.export_bookings_csv()
        assert len(rows) == 1
        assert rows[0]["master"] == "Alibek"

    async def test_get_upcoming_bookings(self, db):
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        bookings = await storage.get_upcoming_bookings()
        # future date - should appear
        assert len(bookings) >= 1
