import shutil
import os
import gzip
import logging
import asyncio
from datetime import datetime
import config

logger = logging.getLogger(__name__)

_BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")


async def _pg_dump(database_url: str, backup_file: str) -> bool:
    """CRIT-01 FIX: Backup PostgreSQL using asyncpg (SQL INSERT dump, gzip-compressed)."""
    try:
        import asyncpg
        conn = await asyncpg.connect(database_url, command_timeout=60)
        tables = [
            "users", "bookings", "waitlist", "loyalty", "referrals",
            "reviews", "settings", "masters", "services",
            "scheduler_jobs", "slot_locks", "master_service_prices",
        ]
        lines = [f"-- Barbershop DB dump {datetime.now().isoformat()}", ""]
        for table in tables:
            try:
                rows = await conn.fetch(f"SELECT * FROM {table}")
                if not rows:
                    continue
                cols = list(rows[0].keys())
                cols_sql = ", ".join(cols)
                lines.append(f"-- {table}")
                for row in rows:
                    vals = []
                    for v in row.values():
                        if v is None:
                            vals.append("NULL")
                        elif isinstance(v, (int, float)):
                            vals.append(str(v))
                        else:
                            vals.append("'" + str(v).replace("'", "''") + "'")
                    lines.append(
                        f"INSERT INTO {table} ({cols_sql}) VALUES ({', '.join(vals)}) ON CONFLICT DO NOTHING;"
                    )
                lines.append("")
            except Exception as te:
                logger.warning(f"pg_dump: skipped table {table}: {te}")
        await conn.close()
        with gzip.open(backup_file, "wt", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return True
    except Exception as e:
        logger.error(f"pg_dump failed: {e}")
        return False


def backup_database():
    """CRIT-01 FIX: Backup both SQLite (gzip) and PostgreSQL (SQL dump, gzip).
    Called via asyncio.to_thread -- safe to use asyncio.run() here."""
    try:
        os.makedirs(_BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        database_url = os.getenv("DATABASE_URL", "").strip()

        if database_url:
            backup_file = os.path.join(_BACKUP_DIR, f"barbershop_{timestamp}.sql.gz")
            success = asyncio.run(_pg_dump(database_url, backup_file))
            if success:
                logger.info(f"PostgreSQL backup created: {backup_file}")
                return backup_file
            else:
                logger.error("PostgreSQL backup FAILED -- check logs above")
                return None
        else:
            backup_file = os.path.join(_BACKUP_DIR, f"barbershop_{timestamp}.db.gz")
            with open(config.DB_PATH, "rb") as f_in:
                with gzip.open(backup_file, "wb", compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)
            logger.info(f"SQLite backup created: {backup_file}")
            return backup_file
    except Exception as e:
        logger.error(f"Failed to backup database: {e}")
        return None


def cleanup_old_backups(max_backups: int = 30):
    """Remove old backup files, keeping max_backups most recent."""
    try:
        if not os.path.exists(_BACKUP_DIR):
            return
        all_files = sorted(os.listdir(_BACKUP_DIR))
        backup_files = [f for f in all_files if f.endswith(".db.gz") or f.endswith(".sql.gz")]
        if len(backup_files) > max_backups:
            for f in backup_files[:-max_backups]:
                os.remove(os.path.join(_BACKUP_DIR, f))
                logger.info(f"Removed old backup: {f}")
    except Exception as e:
        logger.error(f"Failed to cleanup backups: {e}")
