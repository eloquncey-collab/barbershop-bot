import shutil
import os
import logging
from datetime import datetime
import config

logger = logging.getLogger(__name__)


def backup_database():
    try:
        # HIGH-07 FIX: use __file__ so path is correct regardless of CWD
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(backup_dir, f"barbershop_{timestamp}.db")
        shutil.copy2(config.DB_PATH, backup_file)
        logger.info(f"Database backup created: {backup_file}")
        return backup_file
    except Exception as e:
        logger.error(f"Failed to backup database: {e}")
        return None


def cleanup_old_backups(max_backups: int = 30):
    try:
        # HIGH-07 FIX: use __file__ so path is correct regardless of CWD
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
        if not os.path.exists(backup_dir):
            return
        files = sorted(os.listdir(backup_dir))
        db_files = [f for f in files if f.endswith(".db")]
        if len(db_files) > max_backups:
            for f in db_files[:-max_backups]:
                os.remove(os.path.join(backup_dir, f))
                logger.info(f"Removed old backup: {f}")
    except Exception as e:
        logger.error(f"Failed to cleanup backups: {e}")
