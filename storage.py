import uuid
import db as _db
from datetime import timedelta
import config
import os
import logging
from pathlib import Path
from tz_utils import get_now

logger = logging.getLogger(__name__)


# ======================================================================
# Schema migration helpers
# ======================================================================

async def _migrate_masters_columns(conn) -> None:
    """Add work_days / services columns if absent (both backends)."""
    if _db.is_postgres():
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name=$1",
            "masters"
        )
        existing = {r["column_name"] for r in rows}
    else:
        rows = await conn.fetch("PRAGMA table_info(masters)")
        existing = {r["name"] for r in rows}
        await conn.commit()

    if "work_days" not in existing:
        await conn.execute("ALTER TABLE masters ADD COLUMN work_days TEXT DEFAULT \'1,2,3,4,5,6\'")
    if "services" not in existing:
        await conn.execute("ALTER TABLE masters ADD COLUMN services TEXT DEFAULT \'\'")
    await conn.commit()


async def _migrate_master_prices(conn) -> None:
    """Ensure master_service_prices table exists (idempotent)."""
    if _db.is_postgres():
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS master_service_prices (
                master  TEXT NOT NULL,
                service TEXT NOT NULL,
                price   INTEGER NOT NULL,
                PRIMARY KEY (master, service)
            )
        """)
    else:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS master_service_prices (
                master  TEXT NOT NULL,
                service TEXT NOT NULL,
                price   INTEGER NOT NULL,
                PRIMARY KEY (master, service)
            )
        """)
        await conn.commit()


# ======================================================================
# init_db
# ======================================================================

async def init_db() -> None:
    if _db.is_postgres():
        await _init_pg()
    else:
        await _init_sqlite()


async def _init_pg() -> None:
    async with _db.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id          TEXT PRIMARY KEY,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                name        TEXT NOT NULL,
                telegram_id BIGINT NOT NULL,
                username    TEXT DEFAULT \'\',
                master      TEXT NOT NULL,
                service     TEXT NOT NULL,
                price       INTEGER NOT NULL,
                status      TEXT DEFAULT \'active\',
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_slot "
            "ON bookings(date, time, master) WHERE status=\'active\'"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id BIGINT PRIMARY KEY,
                phone       TEXT,
                username    TEXT,
                first_name  TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id          SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                name        TEXT NOT NULL,
                master      TEXT NOT NULL,
                service     TEXT NOT NULL,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                status      TEXT DEFAULT \'waiting\',
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS loyalty (
                telegram_id BIGINT PRIMARY KEY,
                name        TEXT,
                visits      INTEGER DEFAULT 0,
                bonuses     INTEGER DEFAULT 0,
                ref_code    TEXT UNIQUE,
                updated_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id          SERIAL PRIMARY KEY,
                referrer_id BIGINT NOT NULL,
                referred_id BIGINT NOT NULL,
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          SERIAL PRIMARY KEY,
                booking_id  TEXT NOT NULL,
                telegram_id BIGINT NOT NULL,
                rating      INTEGER NOT NULL,
                comment     TEXT DEFAULT \'\',
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                name           TEXT PRIMARY KEY,
                experience     TEXT NOT NULL,
                specialization TEXT NOT NULL,
                work_days      TEXT DEFAULT \'1,2,3,4,5,6\',
                services       TEXT DEFAULT \'\'
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                name  TEXT PRIMARY KEY,
                price INTEGER NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_jobs (
                id         TEXT PRIMARY KEY,
                run_date   TEXT NOT NULL,
                job_type   TEXT NOT NULL,
                booking_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS slot_locks (
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                master      TEXT NOT NULL,
                locked_at   TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                PRIMARY KEY (date, time, master)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS master_service_prices (
                master  TEXT NOT NULL,
                service TEXT NOT NULL,
                price   INTEGER NOT NULL,
                PRIMARY KEY (master, service)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_date_master ON bookings(date, master, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_telegram ON bookings(telegram_id, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_waitlist_slot ON waitlist(date, time, master, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_loyalty_telegram ON loyalty(telegram_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_booking ON reviews(booking_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")


async def _init_sqlite() -> None:
    import aiosqlite
    db_path = Path(config.DB_PATH)
    db_dir = db_path.parent
    db_dir.mkdir(parents=True, exist_ok=True)

    can_write = os.access(str(db_dir), os.W_OK)
    logger.info(f"DB path: {db_path} | dir writable={can_write}")
    if not can_write:
        raise PermissionError(f"No write access to database directory: {db_dir}")

    async with _db.acquire() as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id          TEXT PRIMARY KEY,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                name        TEXT NOT NULL,
                telegram_id INTEGER NOT NULL,
                username    TEXT DEFAULT \'\',
                master      TEXT NOT NULL,
                service     TEXT NOT NULL,
                price       INTEGER NOT NULL,
                status      TEXT DEFAULT \'active\',
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_slot "
            "ON bookings(date, time, master) WHERE status=\'active\'"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                phone       TEXT,
                username    TEXT,
                first_name  TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                name        TEXT NOT NULL,
                master      TEXT NOT NULL,
                service     TEXT NOT NULL,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                status      TEXT DEFAULT \'waiting\',
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS loyalty (
                telegram_id INTEGER PRIMARY KEY,
                name        TEXT,
                visits      INTEGER DEFAULT 0,
                bonuses     INTEGER DEFAULT 0,
                ref_code    TEXT UNIQUE,
                updated_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id  TEXT NOT NULL,
                telegram_id INTEGER NOT NULL,
                rating      INTEGER NOT NULL,
                comment     TEXT DEFAULT \'\',
                created_at  TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                name          TEXT PRIMARY KEY,
                experience    TEXT NOT NULL,
                specialization TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                name  TEXT PRIMARY KEY,
                price INTEGER NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_jobs (
                id         TEXT PRIMARY KEY,
                run_date   TEXT NOT NULL,
                job_type   TEXT NOT NULL,
                booking_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS slot_locks (
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                master      TEXT NOT NULL,
                locked_at   TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                PRIMARY KEY (date, time, master)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS master_service_prices (
                master  TEXT NOT NULL,
                service TEXT NOT NULL,
                price   INTEGER NOT NULL,
                PRIMARY KEY (master, service)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_date_master ON bookings(date, master, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_telegram ON bookings(telegram_id, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_waitlist_slot ON waitlist(date, time, master, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_loyalty_telegram ON loyalty(telegram_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_reviews_booking ON reviews(booking_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        await conn.commit()
        await _migrate_masters_columns(conn)
        await _migrate_master_prices(conn)


# ======================================================================
# Users
# ======================================================================

async def save_user(telegram_id: int, phone: str = "", username: str = "", first_name: str = ""):
    now = get_now(config.TIMEZONE).isoformat()
    async with _db.acquire() as conn:
        if _db.is_postgres():
            await conn.execute(
                "INSERT INTO users (telegram_id, phone, username, first_name, created_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (telegram_id) DO NOTHING",
                telegram_id, phone or "", username, first_name, now,
            )
            if phone:
                await conn.execute(
                    "UPDATE users SET phone=?, username=?, first_name=? WHERE telegram_id=?",
                    phone, username, first_name, telegram_id,
                )
            else:
                await conn.execute(
                    "UPDATE users SET username=?, first_name=? WHERE telegram_id=?",
                    username, first_name, telegram_id,
                )
        else:
            await conn.execute(
                "INSERT OR IGNORE INTO users (telegram_id, phone, username, first_name, created_at) VALUES (?, ?, ?, ?, ?)",
                telegram_id, phone or "", username, first_name, now,
            )
            if phone:
                await conn.execute("UPDATE users SET phone=?, username=?, first_name=? WHERE telegram_id=?",
                                   phone, username, first_name, telegram_id)
            else:
                await conn.execute("UPDATE users SET username=?, first_name=? WHERE telegram_id=?",
                                   username, first_name, telegram_id)
            await conn.commit()


async def get_user(telegram_id: int) -> dict | None:
    async with _db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE telegram_id=?", telegram_id)


# ======================================================================
# Bookings
# ======================================================================

async def save_booking(booking: dict) -> str | None:
    async with _db.acquire() as conn:
        async with conn.transaction():
            now = get_now(config.TIMEZONE).isoformat()

            # Clean up expired slot_locks first
            await conn.execute("DELETE FROM slot_locks WHERE expires_at < ?", now)

            # Check if slot already booked
            existing = await conn.fetchrow(
                "SELECT id FROM bookings WHERE date=? AND time=? AND master=? AND status='active'",
                booking["date"], booking["time"], booking["master"],
            )
            if existing:
                return None

            # TTL lock (5 min)
            lock_expires = (get_now(config.TIMEZONE) + timedelta(minutes=5)).isoformat()
            try:
                await conn.upsert(
                    "slot_locks",
                    ["date", "time", "master"],
                    {"date": booking["date"], "time": booking["time"], "master": booking["master"],
                     "locked_at": now, "expires_at": lock_expires},
                )
            except Exception as e:
                logger.warning(f"slot_lock create failed (non-fatal): {e}")

            # Generate unique ID with retry
            for attempt in range(3):
                booking_id = uuid.uuid4().hex[:12]
                try:
                    await conn.execute(
                        "INSERT INTO bookings (id, date, time, name, telegram_id, username, "
                        "master, service, price, status, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
                        booking_id, booking["date"], booking["time"], booking["name"],
                        booking["telegram_id"], booking.get("username", ""),
                        booking["master"], booking["service"], booking["price"], now,
                    )
                    # Release slot_lock after successful insert
                    await conn.execute(
                        "DELETE FROM slot_locks WHERE date=? AND time=? AND master=?",
                        booking["date"], booking["time"], booking["master"],
                    )
                    return booking_id
                except Exception as e:
                    if "UNIQUE" in str(e).upper() and "PRIMARY KEY" in str(e).upper() and attempt < 2:
                        continue
                    raise
            return None


async def get_booked_slots(date: str, master: str) -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT time FROM bookings WHERE date=? AND master=? AND status='active'",
            date, master,
        )


async def get_user_bookings(telegram_id: int) -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM bookings WHERE telegram_id=? AND status='active' ORDER BY date, time",
            telegram_id,
        )


async def cancel_booking(booking_id: str, telegram_id: int = None) -> dict | None:
    async with _db.acquire() as conn:
        async with conn.transaction():
            if telegram_id:
                row = await conn.fetchrow(
                    "SELECT * FROM bookings WHERE id=? AND status='active' AND telegram_id=?",
                    booking_id, telegram_id,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM bookings WHERE id=? AND status='active'", booking_id
                )
            if not row:
                return None
            await conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", booking_id)
            await conn.execute(
                "DELETE FROM slot_locks WHERE date=? AND time=? AND master=?",
                row["date"], row["time"], row["master"],
            )
            return row


async def complete_booking(booking_id: str) -> dict | None:
    async with _db.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM bookings WHERE id=? AND status='active'", booking_id
            )
            if not row:
                return None
            await conn.execute("UPDATE bookings SET status='completed' WHERE id=?", booking_id)
            return row


async def admin_cancel_booking(booking_id: str) -> dict | None:
    async with _db.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM bookings WHERE id=? AND status='active'", booking_id
            )
            if not row:
                return None
            await conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", booking_id)
            await conn.execute(
                "DELETE FROM slot_locks WHERE date=? AND time=? AND master=?",
                row["date"], row["time"], row["master"],
            )
            return row


async def admin_complete_booking(booking_id: str) -> dict | None:
    async with _db.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM bookings WHERE id=? AND status='active'", booking_id
            )
            if not row:
                return None
            await conn.execute("UPDATE bookings SET status='completed' WHERE id=?", booking_id)
            return row


async def get_upcoming_bookings() -> list[dict]:
    now = get_now(config.TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM bookings WHERE status='active' "
            "AND (date>? OR (date=? AND time>=?)) ORDER BY date, time",
            today, today, now.strftime("%H:%M"),
        )


async def get_past_bookings_for_completion() -> list[dict]:
    now = get_now(config.TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM bookings WHERE status='active' "
            "AND (date<? OR (date=? AND time<?)) ORDER BY date, time",
            today, today, current_time,
        )


async def get_all_bookings() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch("SELECT * FROM bookings ORDER BY date, time")


async def export_bookings_csv() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch("SELECT * FROM bookings ORDER BY date, time")


async def cleanup_old_bookings(days: int = 90) -> int:
    cutoff_date = (get_now(config.TIMEZONE) - timedelta(days=days)).strftime("%Y-%m-%d")
    async with _db.acquire() as conn:
        if _db.is_postgres():
            r = await conn.execute(
                "DELETE FROM bookings WHERE date < ? AND status IN ('cancelled', 'completed')",
                cutoff_date,
            )
            # asyncpg returns "DELETE N" string
            try:
                return int(str(r).split()[-1])
            except Exception:
                return 0
        else:
            async with conn._conn.execute(
                "DELETE FROM bookings WHERE date < ? AND status IN ('cancelled', 'completed')",
                (cutoff_date,)
            ) as cursor:
                deleted = cursor.rowcount
            await conn.commit()
            return deleted


async def has_active_booking(telegram_id: int) -> bool:
    async with _db.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM bookings WHERE telegram_id=? AND status='active' AND date >= ?",
            telegram_id, get_now(config.TIMEZONE).strftime("%Y-%m-%d"),
        )
        return (count or 0) >= config.MAX_ACTIVE_BOOKINGS


async def user_rate_limit_check(telegram_id: int, window: int = 3600, max_attempts: int = 3) -> bool:
    since = (get_now(config.TIMEZONE) - timedelta(seconds=window)).isoformat()
    async with _db.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM bookings WHERE telegram_id=? AND created_at>=?",
            telegram_id, since,
        )
        return (count or 0) < max_attempts


async def get_booking_with_user(booking_id: str) -> dict | None:
    async with _db.acquire() as conn:
        return await conn.fetchrow(
            "SELECT b.*, u.phone, u.username as user_username FROM bookings b "
            "LEFT JOIN users u ON b.telegram_id = u.telegram_id WHERE b.id=?",
            booking_id,
        )


async def get_bookings_by_date_range(start_date: str, end_date: str) -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM bookings WHERE date BETWEEN ? AND ? ORDER BY date, time",
            start_date, end_date,
        )


# ======================================================================
# Waitlist
# ======================================================================

async def add_to_waitlist(telegram_id: int, name: str, master: str, service: str, date: str, time: str):
    now = get_now(config.TIMEZONE).isoformat()
    async with _db.acquire() as conn:
        await conn.execute(
            "INSERT INTO waitlist (telegram_id, name, master, service, date, time, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?)",
            telegram_id, name, master, service, date, time, now,
        )
        await conn.commit()


async def get_waitlist_for_slot(date: str, time: str, master: str) -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM waitlist WHERE date=? AND time=? AND master=? AND status='waiting' ORDER BY id",
            date, time, master,
        )


async def update_waitlist_status(waitlist_id: int, status: str):
    async with _db.acquire() as conn:
        await conn.execute("UPDATE waitlist SET status=? WHERE id=?", status, waitlist_id)
        await conn.commit()


async def get_all_waitlist() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch("SELECT * FROM waitlist ORDER BY created_at")


async def get_user_waitlist(telegram_id: int) -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM waitlist WHERE telegram_id=? AND status='waiting' ORDER BY created_at",
            telegram_id,
        )


async def get_user_waitlist_count(telegram_id: int) -> int:
    async with _db.acquire() as conn:
        return (await conn.fetchval(
            "SELECT COUNT(*) FROM waitlist WHERE telegram_id=? AND status='waiting'",
            telegram_id,
        )) or 0


# ======================================================================
# Loyalty
# ======================================================================

async def update_loyalty(telegram_id: int, name: str = "") -> int:
    async with _db.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT visits FROM loyalty WHERE telegram_id=?", telegram_id
            )
            now = get_now(config.TIMEZONE).isoformat()
            if row:
                visits = row["visits"] + 1
                await conn.execute(
                    "UPDATE loyalty SET visits=?, updated_at=? WHERE telegram_id=?",
                    visits, now, telegram_id,
                )
            else:
                visits = 1
                ref_code = uuid.uuid4().hex[:8]
                if _db.is_postgres():
                    await conn.execute(
                        "INSERT INTO loyalty (telegram_id, name, visits, bonuses, ref_code, updated_at) "
                        "VALUES (?, ?, ?, 0, ?, ?) ON CONFLICT DO NOTHING",
                        telegram_id, name, visits, ref_code, now,
                    )
                else:
                    await conn.execute(
                        "INSERT OR IGNORE INTO loyalty (telegram_id, name, visits, bonuses, ref_code, updated_at) "
                        "VALUES (?, ?, ?, 0, ?, ?)",
                        telegram_id, name, visits, ref_code, now,
                    )
            return visits


async def add_bonus(telegram_id: int, amount: int) -> bool:
    async with _db.acquire() as conn:
        exists = await conn.fetchval("SELECT telegram_id FROM loyalty WHERE telegram_id=?", telegram_id)
        if not exists:
            return False
        await conn.execute(
            "UPDATE loyalty SET bonuses=bonuses+?, updated_at=? WHERE telegram_id=?",
            amount, get_now(config.TIMEZONE).isoformat(), telegram_id,
        )
        await conn.commit()
        return True


async def get_loyalty(telegram_id: int) -> dict | None:
    async with _db.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM loyalty WHERE telegram_id=?", telegram_id)


async def get_loyalty_list() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch("SELECT * FROM loyalty ORDER BY visits DESC")


async def add_referral(referrer_id: int, referred_id: int) -> bool:
    if referrer_id == referred_id:
        return False
    async with _db.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM referrals WHERE referrer_id=? AND referred_id=?",
            referrer_id, referred_id,
        )
        if exists:
            return False
        await conn.execute(
            "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
            referrer_id, referred_id, get_now(config.TIMEZONE).isoformat(),
        )
        await conn.commit()
        return True


async def get_referrals() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch("SELECT * FROM referrals ORDER BY created_at")


async def get_user_by_ref_code(ref_code: str) -> dict | None:
    async with _db.acquire() as conn:
        return await conn.fetchrow(
            "SELECT l.telegram_id, l.name, l.ref_code, u.phone, u.username, u.first_name "
            "FROM loyalty l LEFT JOIN users u ON l.telegram_id = u.telegram_id WHERE l.ref_code=?",
            ref_code,
        )


# ======================================================================
# Reviews
# ======================================================================

async def save_review(booking_id: str, telegram_id: int, rating: int, comment: str = "") -> bool:
    async with _db.acquire() as conn:
        status_row = await conn.fetchrow("SELECT status FROM bookings WHERE id=?", booking_id)
        if not status_row or status_row["status"] != "completed":
            return False
        dup = await conn.fetchval(
            "SELECT id FROM reviews WHERE booking_id=? AND telegram_id=?", booking_id, telegram_id
        )
        if dup:
            return False
        await conn.execute(
            "INSERT INTO reviews (booking_id, telegram_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            booking_id, telegram_id, rating, comment, get_now(config.TIMEZONE).isoformat(),
        )
        await conn.commit()
        return True


async def get_reviews() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch("SELECT * FROM reviews ORDER BY created_at DESC")


# ======================================================================
# Statistics
# ======================================================================

async def get_stats() -> dict:
    async with _db.acquire() as conn:
        total    = await conn.fetchval("SELECT COUNT(*) FROM bookings") or 0
        active   = await conn.fetchval("SELECT COUNT(*) FROM bookings WHERE status='active'") or 0
        cancelled= await conn.fetchval("SELECT COUNT(*) FROM bookings WHERE status='cancelled'") or 0
        completed= await conn.fetchval("SELECT COUNT(*) FROM bookings WHERE status='completed'") or 0
        revenue  = await conn.fetchval("SELECT COALESCE(SUM(price), 0) FROM bookings WHERE status='completed'") or 0
        return {"total": total, "active": active, "cancelled": cancelled, "completed": completed, "revenue": revenue}


async def get_stats_by_master() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT master, COUNT(*) as count, SUM(price) as revenue "
            "FROM bookings WHERE status IN ('active', 'completed') GROUP BY master"
        )


async def get_stats_by_day() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT date, COUNT(*) as count FROM bookings "
            "WHERE status IN ('active', 'completed') GROUP BY date ORDER BY date"
        )


async def get_stats_by_service() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch(
            "SELECT service, COUNT(*) as count, SUM(price) as revenue "
            "FROM bookings WHERE status IN ('active', 'completed') GROUP BY service"
        )


async def get_master_stats(master_name: str) -> dict:
    async with _db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active, "
            "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed, "
            "SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) as cancelled, "
            "SUM(CASE WHEN status='completed' THEN price ELSE 0 END) as revenue "
            "FROM bookings WHERE master=?",
            master_name,
        )
        return {"total": row["total"] or 0, "active": row["active"] or 0,
                "completed": row["completed"] or 0, "cancelled": row["cancelled"] or 0,
                "revenue": row["revenue"] or 0}


async def get_service_stats(service_name: str) -> dict:
    async with _db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active, "
            "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed, "
            "SUM(CASE WHEN status='completed' THEN price ELSE 0 END) as revenue "
            "FROM bookings WHERE service=?",
            service_name,
        )
        return {"total": row["total"] or 0, "active": row["active"] or 0,
                "completed": row["completed"] or 0, "revenue": row["revenue"] or 0}


async def get_active_bookings_count() -> int:
    async with _db.acquire() as conn:
        return (await conn.fetchval("SELECT COUNT(*) FROM bookings WHERE status='active'")) or 0


async def get_bookings_summary(date_str: str) -> dict:
    async with _db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) as total, "
            "COALESCE(SUM(CASE WHEN status='active' THEN 1 ELSE 0 END),0) as active, "
            "COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0) as cancelled, "
            "COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),0) as completed, "
            "COALESCE(SUM(CASE WHEN status='completed' THEN price ELSE 0 END),0) as revenue "
            "FROM bookings WHERE date=?",
            date_str,
        )
        return {"total": row[0] or 0, "active": row[1] or 0, "cancelled": row[2] or 0,
                "completed": row[3] or 0, "revenue": row[4] or 0}


# ======================================================================
# Settings (key-value)
# ======================================================================

async def save_settings(key: str, value: str):
    async with _db.acquire() as conn:
        await conn.upsert("settings", ["key"], {"key": key, "value": value})


async def get_settings(key: str) -> str | None:
    async with _db.acquire() as conn:
        return await conn.fetchval("SELECT value FROM settings WHERE key=?", key)


async def get_all_settings() -> dict:
    async with _db.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM settings")
        return {r["key"]: r["value"] for r in rows}


# ======================================================================
# Masters
# ======================================================================

async def save_master(name: str, experience: str, specialization: str):
    """BUG-FIX: UPSERT only experience/specialization, NEVER reset work_days/services."""
    async with _db.acquire() as conn:
        if _db.is_postgres():
            await conn.execute(
                "INSERT INTO masters (name, experience, specialization) VALUES (?, ?, ?) "
                "ON CONFLICT (name) DO UPDATE SET experience=EXCLUDED.experience, specialization=EXCLUDED.specialization",
                name, experience, specialization,
            )
        else:
            # SQLite: INSERT OR IGNORE first, then UPDATE — never touches work_days/services
            await conn.execute(
                "INSERT OR IGNORE INTO masters (name, experience, specialization) VALUES (?, ?, ?)",
                name, experience, specialization,
            )
            await conn.execute(
                "UPDATE masters SET experience=?, specialization=? WHERE name=?",
                experience, specialization, name,
            )
            await conn.commit()


async def remove_master(name: str):
    async with _db.acquire() as conn:
        await conn.execute("DELETE FROM masters WHERE name=?", name)
        await conn.commit()


async def get_all_masters() -> dict:
    async with _db.acquire() as conn:
        rows = await conn.fetch("SELECT name, experience, specialization FROM masters")
        return {r["name"]: {"experience": r["experience"], "specialization": r["specialization"]} for r in rows}


async def get_master_work_days(master_name: str) -> list[int]:
    async with _db.acquire() as conn:
        val = await conn.fetchval("SELECT work_days FROM masters WHERE name=?", master_name)
        if val:
            try:
                return [int(d) for d in str(val).split(",") if d.strip().isdigit()]
            except Exception:
                pass
        return [1, 2, 3, 4, 5, 6]


async def get_master_services(master_name: str) -> list[str]:
    async with _db.acquire() as conn:
        val = await conn.fetchval("SELECT services FROM masters WHERE name=?", master_name)
        if val and str(val).strip():
            services = [s.strip() for s in str(val).split(",") if s.strip()]
            if services:
                return [s for s in services if s in config.SERVICES]
        # Fallback: all services
        return list(config.SERVICES.keys())


async def set_master_work_days(master_name: str, days: list[int]) -> bool:
    days_str = ",".join(str(d) for d in sorted(days))
    async with _db.acquire() as conn:
        exists = await conn.fetchval("SELECT name FROM masters WHERE name=?", master_name)
        if not exists:
            return False
        await conn.execute("UPDATE masters SET work_days=? WHERE name=?", days_str, master_name)
        await conn.commit()
        return True


async def set_master_services(master_name: str, services: list[str]) -> bool:
    services_str = ",".join(services)
    async with _db.acquire() as conn:
        exists = await conn.fetchval("SELECT name FROM masters WHERE name=?", master_name)
        if not exists:
            return False
        await conn.execute("UPDATE masters SET services=? WHERE name=?", services_str, master_name)
        await conn.commit()
        return True


# ======================================================================
# Services (global)
# ======================================================================

async def save_service(name: str, price: int):
    async with _db.acquire() as conn:
        await conn.upsert("services", ["name"], {"name": name, "price": price})


async def remove_service(name: str):
    async with _db.acquire() as conn:
        await conn.execute("DELETE FROM services WHERE name=?", name)
        await conn.commit()


async def get_all_services() -> dict:
    async with _db.acquire() as conn:
        rows = await conn.fetch("SELECT name, price FROM services")
        return {r["name"]: r["price"] for r in rows}


# ======================================================================
# Per-master service prices
# ======================================================================

async def get_master_service_price(master: str, service: str) -> int | None:
    """Return master-specific price for a service, or None if not set."""
    async with _db.acquire() as conn:
        return await conn.fetchval(
            "SELECT price FROM master_service_prices WHERE master=? AND service=?",
            master, service,
        )


async def set_master_service_price(master: str, service: str, price: int) -> None:
    """Set or update master-specific price for a service."""
    async with _db.acquire() as conn:
        await conn.upsert(
            "master_service_prices",
            ["master", "service"],
            {"master": master, "service": service, "price": price},
        )


async def delete_master_service_price(master: str, service: str) -> None:
    """Remove master-specific price (revert to global price)."""
    async with _db.acquire() as conn:
        await conn.execute(
            "DELETE FROM master_service_prices WHERE master=? AND service=?",
            master, service,
        )
        await conn.commit()


async def get_all_master_service_prices(master: str) -> dict[str, int]:
    """Return {service_name: price} for all custom prices of a master."""
    async with _db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT service, price FROM master_service_prices WHERE master=?", master
        )
        return {r["service"]: r["price"] for r in rows}


async def get_effective_price(master: str, service: str) -> int:
    """Return master-specific price if set, otherwise global price from config."""
    custom = await get_master_service_price(master, service)
    if custom is not None:
        return custom
    return config.SERVICES.get(service, 0)


# ======================================================================
# Scheduler jobs
# ======================================================================

async def save_scheduler_job(job_id: str, run_date: str, job_type: str, booking_id: str):
    async with _db.acquire() as conn:
        await conn.upsert(
            "scheduler_jobs",
            ["id"],
            {"id": job_id, "run_date": run_date, "job_type": job_type,
             "booking_id": booking_id, "created_at": get_now(config.TIMEZONE).isoformat()},
        )


async def remove_scheduler_job(job_id: str):
    async with _db.acquire() as conn:
        await conn.execute("DELETE FROM scheduler_jobs WHERE id=?", job_id)
        await conn.commit()


async def get_all_scheduler_jobs() -> list[dict]:
    async with _db.acquire() as conn:
        return await conn.fetch("SELECT * FROM scheduler_jobs ORDER BY run_date")


async def delete_old_scheduler_jobs():
    async with _db.acquire() as conn:
        await conn.execute(
            "DELETE FROM scheduler_jobs WHERE run_date < ?",
            get_now(config.TIMEZONE).isoformat(),
        )
        await conn.commit()


# ======================================================================
# Slot locks
# ======================================================================

async def create_slot_lock(date: str, time: str, master: str, ttl_minutes: int = 5):
    try:
        now = get_now(config.TIMEZONE)
        async with _db.acquire() as conn:
            await conn.upsert(
                "slot_locks",
                ["date", "time", "master"],
                {"date": date, "time": time, "master": master,
                 "locked_at": now.isoformat(),
                 "expires_at": (now + timedelta(minutes=ttl_minutes)).isoformat()},
            )
    except Exception as e:
        logger.warning(f"Failed to create slot_lock {date}/{time}/{master}: {e}")


async def release_slot_lock(date: str, time: str, master: str):
    try:
        async with _db.acquire() as conn:
            await conn.execute(
                "DELETE FROM slot_locks WHERE date=? AND time=? AND master=?",
                date, time, master,
            )
            await conn.commit()
    except Exception as e:
        logger.warning(f"Failed to release slot_lock {date}/{time}/{master}: {e}")


async def cleanup_slot_locks_on_startup():
    try:
        async with _db.acquire() as conn:
            await conn.execute("DELETE FROM slot_locks")
            await conn.commit()
            logger.info("slot_locks cleared on startup")
    except Exception as e:
        logger.warning(f"Failed to cleanup slot_locks: {e}")


async def cleanup_expired_slot_locks() -> int:
    try:
        now = get_now(config.TIMEZONE).isoformat()
        async with _db.acquire() as conn:
            if _db.is_postgres():
                r = await conn.execute("DELETE FROM slot_locks WHERE expires_at < ?", now)
                try:
                    deleted = int(str(r).split()[-1])
                except Exception:
                    deleted = 0
            else:
                async with conn._conn.execute("DELETE FROM slot_locks WHERE expires_at < ?", (now,)) as cur:
                    deleted = cur.rowcount
                await conn.commit()
            if deleted:
                logger.info(f"Periodic cleanup: removed {deleted} expired slot_lock(s)")
            return deleted
    except Exception as e:
        logger.warning(f"Failed to cleanup expired slot_locks: {e}")
        return 0


# ======================================================================
# Master Telegram IDs (stored in settings)
# ======================================================================

async def get_master_telegram_id(master_name: str) -> int | None:
    value = await get_settings(f"master_tg_{master_name}")
    try:
        return int(value) if value else None
    except ValueError:
        return None


async def set_master_telegram_id(master_name: str, telegram_id: int | None):
    key = f"master_tg_{master_name}"
    if telegram_id:
        await save_settings(key, str(telegram_id))
    else:
        async with _db.acquire() as conn:
            await conn.execute("DELETE FROM settings WHERE key=?", key)
            await conn.commit()


async def get_all_master_telegram_ids() -> dict:
    async with _db.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM settings WHERE key LIKE 'master_tg_%'")
        result = {}
        for r in rows:
            master_name = r["key"][len("master_tg_"):]
            try:
                result[master_name] = int(r["value"])
            except ValueError:
                pass
        return result
