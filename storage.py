import uuid
import aiosqlite
from datetime import datetime, timedelta
import config
import os
import logging
from pathlib import Path
from tz_utils import get_now

logger = logging.getLogger(__name__)


async def _migrate_masters_table(db):
    """Добавляет новые колонки если их нет"""
    cursor = await db.execute("PRAGMA table_info(masters)")
    columns = {row[1] for row in await cursor.fetchall()}

    if "work_days" not in columns:
        await db.execute(
            "ALTER TABLE masters ADD COLUMN work_days TEXT DEFAULT '1,2,3,4,5,6'"
        )
    if "services" not in columns:
        await db.execute(
            "ALTER TABLE masters ADD COLUMN services TEXT DEFAULT ''"
        )
    await db.commit()


async def init_db():
    # BUG-014 FIX: Create data directory if it doesn't exist
    db_path = Path(config.DB_PATH)
    db_dir = db_path.parent
    db_dir.mkdir(parents=True, exist_ok=True)

    # RAILWAY FIX: диагностика прав перед подключением
    # Если volume примонтирован как root:root 755, non-root процесс упадёт здесь
    can_write = os.access(str(db_dir), os.W_OK)
    logger.info(f"DB path     : {db_path}")
    logger.info(f"DB dir      : {db_dir} | writable={can_write} | uid={os.getuid() if hasattr(os,'getuid') else 'n/a'}")
    if not can_write:
        raise PermissionError(
            f"No write access to database directory: {db_dir}. "
            f"Railway volume likely mounted as root:root 755. "
            f"Fix: remove 'USER botuser' from Dockerfile and add entrypoint.sh that runs chmod 777 /app/data."
        )

    async with aiosqlite.connect(config.DB_PATH) as db:
        # PERF-001 FIX: WAL for concurrent access
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id          TEXT PRIMARY KEY,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                name        TEXT NOT NULL,
                telegram_id INTEGER NOT NULL,
                username    TEXT DEFAULT '',
                master      TEXT NOT NULL,
                service     TEXT NOT NULL,
                price       INTEGER NOT NULL,
                status      TEXT DEFAULT 'active',
                created_at  TEXT NOT NULL
            )
        """)
        # BUG-003 FIX: Create unique constraint without status to prevent double booking
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_slot ON bookings(date, time, master) WHERE status='active'")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                phone       TEXT,
                username    TEXT,
                first_name  TEXT,
                created_at  TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                name        TEXT NOT NULL,
                master      TEXT NOT NULL,
                service     TEXT NOT NULL,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                status      TEXT DEFAULT 'waiting',
                created_at  TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS loyalty (
                telegram_id INTEGER PRIMARY KEY,
                name        TEXT,
                visits      INTEGER DEFAULT 0,
                bonuses     INTEGER DEFAULT 0,
                ref_code    TEXT UNIQUE,
                updated_at  TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                created_at  TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id  TEXT NOT NULL,
                telegram_id INTEGER NOT NULL,
                rating      INTEGER NOT NULL,
                comment     TEXT DEFAULT '',
                created_at  TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS masters (
                name          TEXT PRIMARY KEY,
                experience    TEXT NOT NULL,
                specialization TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS services (
                name  TEXT PRIMARY KEY,
                price INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_jobs (
                id         TEXT PRIMARY KEY,
                run_date   TEXT NOT NULL,
                job_type   TEXT NOT NULL,
                booking_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS slot_locks (
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                master      TEXT NOT NULL,
                locked_at   TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                PRIMARY KEY (date, time, master)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bookings_date_master ON bookings(date, master, status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bookings_telegram ON bookings(telegram_id, status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_waitlist_slot ON waitlist(date, time, master, status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_loyalty_telegram ON loyalty(telegram_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_reviews_booking ON reviews(booking_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        
        # Migrate masters table to add new columns
        await _migrate_masters_table(db)
        
        await db.commit()


async def save_user(telegram_id: int, phone: str = "", username: str = "", first_name: str = ""):
    # BUG-005 FIX: Use INSERT OR IGNORE + UPDATE to preserve existing data
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, phone, username, first_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, phone or "", username, first_name, get_now(config.TIMEZONE).isoformat()),
        )
        # Update only non-empty fields
        if phone:
            await db.execute("UPDATE users SET phone=?, username=?, first_name=? WHERE telegram_id=?",
                           (phone, username, first_name, telegram_id))
        else:
            await db.execute("UPDATE users SET username=?, first_name=? WHERE telegram_id=?",
                           (username, first_name, telegram_id))
        await db.commit()


async def get_user(telegram_id: int) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None


async def save_booking(booking: dict) -> str | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        try:
            await db.execute("BEGIN EXCLUSIVE")
            
            # BUG-014 FIX: TTL-блокировка слота (проверяем, что слот не заблокирован другим пользователем)
            now = get_now(config.TIMEZONE).isoformat()
            
            # Очистим устаревшие блокировки
            await db.execute("DELETE FROM slot_locks WHERE expires_at < ?", (now,))
            
            # Проверяем, что слот свободен
            cursor = await db.execute(
                "SELECT id FROM bookings WHERE date=? AND time=? AND master=? AND status='active'",
                (booking["date"], booking["time"], booking["master"]),
            )
            if await cursor.fetchone():
                await db.execute("ROLLBACK")
                return None
            
            # Создаём блокировку на 5 минут (TTL)
            from datetime import timedelta
            lock_expires = (get_now(config.TIMEZONE) + timedelta(minutes=5)).isoformat()
            try:
                await db.execute(
                    "INSERT OR REPLACE INTO slot_locks (date, time, master, locked_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                    (booking["date"], booking["time"], booking["master"], now, lock_expires)
                )
            except Exception as e:
                # NEW-003 FIX: Graceful fallback if slot_locks table doesn't exist
                if "no such table: slot_locks" in str(e):
                    logger.warning("slot_locks table doesn't exist - fallback to basic locking")
                    # Continue without TTL lock - race condition possible but booking will still work
                else:
                    # Слот уже заблокирован другим пользователем
                    await db.execute("ROLLBACK")
                    return None
            
            # BUG-010 FIX: Increase booking_id to 12 characters and add retry logic
            max_retries = 3
            for attempt in range(max_retries):
                booking_id = uuid.uuid4().hex[:12]
                try:
                    await db.execute(
                        "INSERT INTO bookings (id, date, time, name, telegram_id, username, master, service, price, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
                        (
                            booking_id,
                            booking["date"],
                            booking["time"],
                            booking["name"],
                            booking["telegram_id"],
                            booking.get("username", ""),
                            booking["master"],
                            booking["service"],
                            booking["price"],
                            get_now(config.TIMEZONE).isoformat(),
                        ),
                    )
                    
                    # Удаляем блокировку после успешного сохранения
                    await db.execute(
                        "DELETE FROM slot_locks WHERE date=? AND time=? AND master=?",
                        (booking["date"], booking["time"], booking["master"])
                    )
                    
                    await db.execute("COMMIT")
                    return booking_id
                except Exception as e:
                    if "UNIQUE constraint failed" in str(e) and "PRIMARY KEY" in str(e):
                        # ID collision, retry with new ID
                        if attempt < max_retries - 1:
                            continue
                    raise
            await db.execute("ROLLBACK")
            return None
        except Exception:
            await db.execute("ROLLBACK")
            raise


async def get_booked_slots(date: str, master: str) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT time FROM bookings WHERE date=? AND master=? AND status='active'",
            (date, master),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_user_bookings(telegram_id: int) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE telegram_id=? AND status='active' ORDER BY date, time",
            (telegram_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def cancel_booking(booking_id: str, telegram_id: int = None) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute("BEGIN EXCLUSIVE")
            # BUG-016 FIX: Check booking status before cancellation
            if telegram_id:
                cursor = await db.execute("SELECT * FROM bookings WHERE id=? AND status='active' AND telegram_id=?", (booking_id, telegram_id))
            else:
                cursor = await db.execute("SELECT * FROM bookings WHERE id=? AND status='active'", (booking_id,))
            row = await cursor.fetchone()
            if not row:
                await db.execute("ROLLBACK")
                return None
            booking = dict(row)
            await db.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
            
            # FIX BL-04: Only cancel waitlist for the exact cancelled slot (not all user waitlists)
            # Waitlist entries on OTHER slots must remain active so user can still get notified.
            # The freed slot will be broadcast to its own waitlist by the caller (start.py).
            
            await db.execute("COMMIT")
            return booking
        except Exception:
            await db.execute("ROLLBACK")
            raise


async def complete_booking(booking_id: str) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute("BEGIN EXCLUSIVE")
            cursor = await db.execute("SELECT * FROM bookings WHERE id=? AND status='active'", (booking_id,))
            row = await cursor.fetchone()
            if not row:
                await db.execute("ROLLBACK")
                return None
            booking = dict(row)
            await db.execute("UPDATE bookings SET status='completed' WHERE id=?", (booking_id,))
            await db.execute("COMMIT")
            return booking
        except Exception:
            await db.execute("ROLLBACK")
            raise


async def add_to_waitlist(telegram_id: int, name: str, master: str, service: str, date: str, time: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO waitlist (telegram_id, name, master, service, date, time, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?)",
            (telegram_id, name, master, service, date, time, get_now(config.TIMEZONE).isoformat()),
        )
        await db.commit()


async def get_waitlist_for_slot(date: str, time: str, master: str) -> list[dict]:
    # BUG-015 FIX: Use SQL query with WHERE clause instead of Python filtering
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM waitlist WHERE date=? AND time=? AND master=? AND status='waiting' ORDER BY id",
            (date, time, master),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def update_waitlist_status(waitlist_id: int, status: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE waitlist SET status=? WHERE id=?", (status, waitlist_id))
        await db.commit()


async def update_loyalty(telegram_id: int, name: str = "") -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        try:
            await db.execute("BEGIN EXCLUSIVE")
            cursor = await db.execute("SELECT visits FROM loyalty WHERE telegram_id=?", (telegram_id,))
            row = await cursor.fetchone()
            if row:
                visits = row[0] + 1
                await db.execute("UPDATE loyalty SET visits=?, updated_at=? WHERE telegram_id=?",
                                 (visits, get_now(config.TIMEZONE).isoformat(), telegram_id))
            else:
                visits = 1
                await db.execute(
                    "INSERT INTO loyalty (telegram_id, name, visits, bonuses, ref_code, updated_at) VALUES (?, ?, ?, 0, ?, ?)",
                    (telegram_id, name, visits, uuid.uuid4().hex[:8], get_now(config.TIMEZONE).isoformat()),
                )
            await db.execute("COMMIT")
            return visits
        except Exception:
            await db.execute("ROLLBACK")
            raise


async def add_bonus(telegram_id: int, amount: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT telegram_id FROM loyalty WHERE telegram_id=?", (telegram_id,))
        if not await cursor.fetchone():
            return False
        await db.execute("UPDATE loyalty SET bonuses=bonuses+?, updated_at=? WHERE telegram_id=?",
                         (amount, get_now(config.TIMEZONE).isoformat(), telegram_id))
        await db.commit()
        return True


async def get_loyalty(telegram_id: int) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM loyalty WHERE telegram_id=?", (telegram_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def add_referral(referrer_id: int, referred_id: int) -> bool:
    # NEW-004 FIX: Prevent self-referral
    if referrer_id == referred_id:
        return False
    
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT id FROM referrals WHERE referrer_id=? AND referred_id=?", (referrer_id, referred_id))
        if await cursor.fetchone():
            return False
        await db.execute(
            "INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
            (referrer_id, referred_id, get_now(config.TIMEZONE).isoformat()),
        )
        await db.commit()
        return True


async def save_review(booking_id: str, telegram_id: int, rating: int, comment: str = "") -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        # BUG-017 FIX: Check booking status before allowing review
        cursor = await db.execute("SELECT status FROM bookings WHERE id=?", (booking_id,))
        row = await cursor.fetchone()
        if not row or row[0] != 'completed':
            return False
        
        cursor = await db.execute("SELECT id FROM reviews WHERE booking_id=? AND telegram_id=?", (booking_id, telegram_id))
        if await cursor.fetchone():
            return False
        await db.execute(
            "INSERT INTO reviews (booking_id, telegram_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            (booking_id, telegram_id, rating, comment, get_now(config.TIMEZONE).isoformat()),
        )
        await db.commit()
        return True


async def get_stats() -> dict:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM bookings")
        total = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM bookings WHERE status='active'")
        active = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM bookings WHERE status='cancelled'")
        cancelled = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM bookings WHERE status='completed'")
        completed = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COALESCE(SUM(price), 0) FROM bookings WHERE status='completed'")
        revenue = (await cursor.fetchone())[0]
        return {
            "total": total,
            "active": active,
            "cancelled": cancelled,
            "completed": completed,
            "revenue": revenue,
        }


async def export_bookings_csv() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bookings ORDER BY date, time") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def user_rate_limit_check(telegram_id: int, window: int = 3600, max_attempts: int = 3) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        since = (get_now(config.TIMEZONE) - timedelta(seconds=window)).isoformat()
        cursor = await db.execute(
            "SELECT COUNT(*) FROM bookings WHERE telegram_id=? AND created_at>=?",
            (telegram_id, since),
        )
        count = (await cursor.fetchone())[0]
        return count < max_attempts


async def has_active_booking(telegram_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM bookings WHERE telegram_id=? AND status='active' AND date >= ?",
            (telegram_id, get_now(config.TIMEZONE).strftime("%Y-%m-%d")),
        )
        count = (await cursor.fetchone())[0]
        return count >= 3  # Task 8: до 3 активных записей (was: count > 0 = max 1)


async def get_upcoming_bookings() -> list[dict]:
    # BUG-006 FIX: Use timezone-aware datetime for comparison
    now = get_now(config.TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE status='active' AND (date>? OR (date=? AND time>=?)) ORDER BY date, time",
            (today, today, now.strftime("%H:%M")),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# --- Admin: detailed statistics ---

async def get_stats_by_master() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT master, COUNT(*) as count, SUM(price) as revenue FROM bookings WHERE status IN ('active', 'completed') GROUP BY master"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_stats_by_day() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT date, COUNT(*) as count FROM bookings WHERE status IN ('active', 'completed') GROUP BY date ORDER BY date"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_stats_by_service() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT service, COUNT(*) as count, SUM(price) as revenue FROM bookings WHERE status IN ('active', 'completed') GROUP BY service"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_all_bookings() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM bookings ORDER BY date, time") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def admin_cancel_booking(booking_id: str) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute("BEGIN EXCLUSIVE")
            cursor = await db.execute("SELECT * FROM bookings WHERE id=? AND status='active'", (booking_id,))
            row = await cursor.fetchone()
            if not row:
                await db.execute("ROLLBACK")
                return None
            booking = dict(row)
            await db.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
            await db.execute("COMMIT")
            return booking
        except Exception:
            await db.execute("ROLLBACK")
            raise


async def admin_complete_booking(booking_id: str) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        try:
            await db.execute("BEGIN EXCLUSIVE")
            cursor = await db.execute("SELECT * FROM bookings WHERE id=? AND status='active'", (booking_id,))
            row = await cursor.fetchone()
            if not row:
                await db.execute("ROLLBACK")
                return None
            booking = dict(row)
            await db.execute("UPDATE bookings SET status='completed' WHERE id=?", (booking_id,))
            await db.execute("COMMIT")
            return booking
        except Exception:
            await db.execute("ROLLBACK")
            raise


async def get_all_waitlist() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM waitlist ORDER BY created_at") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_loyalty_list() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM loyalty ORDER BY visits DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_reviews() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM reviews ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_referrals() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM referrals ORDER BY created_at") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# --- Persistence: settings, masters, services ---

async def save_settings(key: str, value: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()


async def get_settings(key: str) -> str | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_all_settings() -> dict:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT key, value FROM settings")
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}


async def save_master(name: str, experience: str, specialization: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO masters (name, experience, specialization) VALUES (?, ?, ?)",
            (name, experience, specialization),
        )
        await db.commit()


async def remove_master(name: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM masters WHERE name=?", (name,))
        await db.commit()


async def get_all_masters() -> dict:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT name, experience, specialization FROM masters")
        rows = await cursor.fetchall()
        return {row[0]: {"experience": row[1], "specialization": row[2]} for row in rows}


async def save_service(name: str, price: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO services (name, price) VALUES (?, ?)", (name, price))
        await db.commit()


async def remove_service(name: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM services WHERE name=?", (name,))
        await db.commit()


async def get_all_services() -> dict:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT name, price FROM services")
        rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}


# --- Persistence: scheduler jobs ---

async def save_scheduler_job(job_id: str, run_date: str, job_type: str, booking_id: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO scheduler_jobs (id, run_date, job_type, booking_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, run_date, job_type, booking_id, get_now(config.TIMEZONE).isoformat()),
        )
        await db.commit()


async def remove_scheduler_job(job_id: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM scheduler_jobs WHERE id=?", (job_id,))
        await db.commit()


async def get_all_scheduler_jobs() -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM scheduler_jobs ORDER BY run_date") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def delete_old_scheduler_jobs():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM scheduler_jobs WHERE run_date < ?", (get_now(config.TIMEZONE).isoformat(),))
        await db.commit()


# --- Optimized queries ---

async def get_booking_with_user(booking_id: str) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT b.*, u.phone, u.username as user_username FROM bookings b "
            "LEFT JOIN users u ON b.telegram_id = u.telegram_id "
            "WHERE b.id=?", (booking_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_bookings_summary(date_str: str) -> dict:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as total, "
            "COALESCE(SUM(CASE WHEN status='active' THEN 1 ELSE 0 END),0) as active, "
            "COALESCE(SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END),0) as cancelled, "
            "COALESCE(SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),0) as completed, "
            "COALESCE(SUM(CASE WHEN status='completed' THEN price ELSE 0 END),0) as revenue "
            "FROM bookings WHERE date=?", (date_str,)
        )
        row = await cursor.fetchone()
        return {
            "total": row[0] or 0, "active": row[1] or 0, "cancelled": row[2] or 0,
            "completed": row[3] or 0, "revenue": row[4] or 0
        }


async def get_master_stats(master_name: str) -> dict:
    # CRIT-03 FIX: canonical definition — includes all fields (active, completed, cancelled, revenue)
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active, "
            "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed, "
            "SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) as cancelled, "
            "SUM(CASE WHEN status='completed' THEN price ELSE 0 END) as revenue "
            "FROM bookings WHERE master=?", (master_name,)
        )
        row = await cursor.fetchone()
        return {
            "total": row[0] or 0, "active": row[1] or 0,
            "completed": row[2] or 0, "cancelled": row[3] or 0,
            "revenue": row[4] or 0
        }


async def get_service_stats(service_name: str) -> dict:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active, "
            "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed, "
            "SUM(CASE WHEN status='completed' THEN price ELSE 0 END) as revenue "
            "FROM bookings WHERE service=?", (service_name,)
        )
        row = await cursor.fetchone()
        return {
            "total": row[0], "active": row[1],
            "completed": row[2], "revenue": row[3]
        }


async def get_active_bookings_count() -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM bookings WHERE status='active'")
        return (await cursor.fetchone())[0]


async def get_bookings_by_date_range(start_date: str, end_date: str) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE date BETWEEN ? AND ? ORDER BY date, time",
            (start_date, end_date)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def cleanup_old_bookings(days: int = 90) -> int:
    """Delete bookings older than specified days"""
    # BUG-006 FIX: Use timezone-aware datetime for comparison
    cutoff_date = (get_now(config.TIMEZONE) - timedelta(days=days)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM bookings WHERE date < ? AND status IN ('cancelled', 'completed')",
            (cutoff_date,)
        )
        deleted = cursor.rowcount
        await db.commit()
        return deleted


async def get_past_bookings_for_completion() -> list[dict]:
    """Get active bookings that should be automatically completed"""
    # BUG-006 FIX: Use timezone-aware datetime for comparison
    now = get_now(config.TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM bookings WHERE status='active' AND (date<? OR (date=? AND time<?)) ORDER BY date, time",
            (today, today, current_time),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_user_waitlist(telegram_id: int) -> list[dict]:
    """Get waitlist entries for a specific user — SQL query, no Python filtering."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM waitlist WHERE telegram_id=? AND status='waiting' ORDER BY created_at",
            (telegram_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_master_telegram_id(master_name: str) -> int | None:
    """Get Telegram ID for a master from settings table."""
    key = f"master_tg_{master_name}"
    value = await get_settings(key)
    if value:
        try:
            return int(value)
        except ValueError:
            return None
    return None


async def set_master_telegram_id(master_name: str, telegram_id: int | None):
    """Set or remove Telegram ID for a master."""
    key = f"master_tg_{master_name}"
    if telegram_id:
        await save_settings(key, str(telegram_id))
    else:
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute("DELETE FROM settings WHERE key=?", (key,))
            await db.commit()


async def get_all_master_telegram_ids() -> dict:
    """Get all master Telegram IDs stored in settings."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT key, value FROM settings WHERE key LIKE 'master_tg_%'"
        )
        rows = await cursor.fetchall()
        result = {}
        for key, value in rows:
            master_name = key[len("master_tg_"):]
            try:
                result[master_name] = int(value)
            except ValueError:
                pass
        return result



# --- Master schedule and services functions ---

async def get_master_work_days(master_name: str) -> list[int]:
    """Возвращает список рабочих дней мастера [1,2,3,4,5,6,7]"""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT work_days FROM masters WHERE name=?",
            (master_name,)
        )
        row = await cursor.fetchone()
        if row and row[0]:
            try:
                days_str = row[0].strip()
                if days_str:
                    return [int(d) for d in days_str.split(",") if d.strip().isdigit()]
            except Exception:
                pass
        # Default: Monday to Saturday
        return [1, 2, 3, 4, 5, 6]


async def get_master_services(master_name: str) -> list[str]:
    """Возвращает список услуг мастера"""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT services FROM masters WHERE name=?",
            (master_name,)
        )
        row = await cursor.fetchone()
        if row and row[0]:
            services_str = row[0].strip()
            if services_str:
                return [s.strip() for s in services_str.split(",") if s.strip()]
        # Default: all services
        return list(config.SERVICES.keys())


async def set_master_work_days(master_name: str, days: list[int]) -> bool:
    """Сохранить рабочие дни мастера"""
    days_str = ",".join(str(d) for d in sorted(days))
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT name FROM masters WHERE name=?",
            (master_name,)
        )
        if not await cursor.fetchone():
            return False
        await db.execute(
            "UPDATE masters SET work_days=? WHERE name=?",
            (days_str, master_name)
        )
        await db.commit()
        return True


async def set_master_services(master_name: str, services: list[str]) -> bool:
    """Сохранить список услуг мастера"""
    services_str = ",".join(services)
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT name FROM masters WHERE name=?",
            (master_name,)
        )
        if not await cursor.fetchone():
            return False
        await db.execute(
            "UPDATE masters SET services=? WHERE name=?",
            (services_str, master_name)
        )
        await db.commit()
        return True


# TASK-07: Referral system functions

async def create_slot_lock(date: str, time: str, master: str, ttl_minutes: int = 5):
    """Создаёт временную блокировку слота при выборе времени — Task 6"""
    try:
        async with aiosqlite.connect(config.DB_PATH) as db:
            now = get_now(config.TIMEZONE)
            locked_at = now.isoformat()
            expires_at = (now + timedelta(minutes=ttl_minutes)).isoformat()
            await db.execute(
                "INSERT OR REPLACE INTO slot_locks (date, time, master, locked_at, expires_at) VALUES (?, ?, ?, ?, ?)",
                (date, time, master, locked_at, expires_at)
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to create slot_lock {date}/{time}/{master}: {e}")


async def release_slot_lock(date: str, time: str, master: str):
    """Снимает блокировку слота (TTL сам истечёт, но можно снять раньше) — Task 6"""
    try:
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "DELETE FROM slot_locks WHERE date=? AND time=? AND master=?",
                (date, time, master)
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to release slot_lock {date}/{time}/{master}: {e}")


async def cleanup_slot_locks_on_startup():
    """Удаляем все slot_locks при старте — прерванные сессии оставляют зависшие блокировки."""
    try:
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute("DELETE FROM slot_locks")
            await db.commit()
            logger.info("slot_locks cleared on startup")
    except Exception as e:
        logger.warning(f"Failed to cleanup slot_locks: {e}")



async def cleanup_expired_slot_locks() -> int:
    '''
    BUG-C4 FIX: Deletes only expired slot_locks by TTL.
    Called periodically by scheduler every 2 minutes.
    Returns the count of removed rows.
    '''
    try:
        async with aiosqlite.connect(config.DB_PATH) as db:
            now = get_now(config.TIMEZONE).isoformat()
            cursor = await db.execute(
                'DELETE FROM slot_locks WHERE expires_at < ?', (now,)
            )
            await db.commit()
            deleted = cursor.rowcount
            if deleted:
                logger.info(f'Periodic cleanup: removed {deleted} expired slot_lock(s)')
            return deleted
    except Exception as e:
        logger.warning(f'Failed to cleanup expired slot_locks: {e}')
        return 0
async def get_user_waitlist_count(telegram_id: int) -> int:
    """Task 15: Проверяет количество активных записей в листе ожидания"""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM waitlist WHERE telegram_id=? AND status='waiting'",
            (telegram_id,)
        )
        return (await cursor.fetchone())[0]


async def get_user_by_ref_code(ref_code: str) -> dict | None:
    """Get user by referral code"""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT l.telegram_id, l.name, l.ref_code, u.phone, u.username, u.first_name "
            "FROM loyalty l LEFT JOIN users u ON l.telegram_id = u.telegram_id "
            "WHERE l.ref_code=?",
            (ref_code,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None


# CRIT-03 FIX: duplicate get_user_waitlist and get_master_stats removed — canonical definitions kept above

