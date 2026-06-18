
"""Tests for backup.py (updated for gzip output)"""
import os, gzip, pytest
from unittest.mock import patch, MagicMock


def test_backup_database_success(tmp_path):
    """SQLite backup creates a .db.gz file."""
    import backup
    db = tmp_path / "test.db"
    db.write_bytes(b"SQLite format 3" + b"\x00" * 100)
    with patch("backup._BACKUP_DIR", str(tmp_path / "backups")), \
         patch("backup.config.DB_PATH", str(db)), \
         patch("backup.os.getenv", return_value=""):
        result = backup.backup_database()
    assert result is not None
    assert result.endswith(".db.gz")
    assert os.path.exists(result)


def test_backup_database_missing_db(tmp_path):
    """Returns None if DB file does not exist."""
    import backup
    with patch("backup._BACKUP_DIR", str(tmp_path / "backups")), \
         patch("backup.config.DB_PATH", str(tmp_path / "nonexistent.db")), \
         patch("backup.os.getenv", return_value=""):
        result = backup.backup_database()
    assert result is None


def test_backup_gzip_content(tmp_path):
    """Gzip content matches original DB bytes."""
    import backup
    payload = b"SQLite format 3" + b"Z" * 200
    db = tmp_path / "test.db"
    db.write_bytes(payload)
    with patch("backup._BACKUP_DIR", str(tmp_path / "backups")), \
         patch("backup.config.DB_PATH", str(db)), \
         patch("backup.os.getenv", return_value=""):
        result = backup.backup_database()
    with gzip.open(result, "rb") as f:
        assert f.read() == payload


def test_cleanup_no_dir(tmp_path):
    """cleanup_old_backups gracefully handles missing directory."""
    import backup
    with patch("backup._BACKUP_DIR", str(tmp_path / "no_backups")):
        backup.cleanup_old_backups()  # must not raise


def test_cleanup_removes_excess(tmp_path):
    """Removes oldest .db.gz files over the limit."""
    import backup
    bd = tmp_path / "backups"
    bd.mkdir()
    for i in range(35):
        (bd / f"barbershop_{i:04d}00_000000.db.gz").write_bytes(b"x")
    with patch("backup._BACKUP_DIR", str(bd)):
        backup.cleanup_old_backups(max_backups=30)
    assert len(list(bd.glob("*.db.gz"))) == 30


def test_cleanup_below_limit(tmp_path):
    """Does not remove files when under the limit."""
    import backup
    bd = tmp_path / "backups"
    bd.mkdir()
    for i in range(5):
        (bd / f"barbershop_{i:04d}00_000000.db.gz").write_bytes(b"x")
    with patch("backup._BACKUP_DIR", str(bd)):
        backup.cleanup_old_backups(max_backups=30)
    assert len(list(bd.glob("*.db.gz"))) == 5


def test_cleanup_exception(tmp_path):
    """cleanup_old_backups does not raise on listdir error."""
    import backup
    bd = tmp_path / "backups"
    bd.mkdir()
    with patch("backup._BACKUP_DIR", str(bd)), \
         patch("backup.os.listdir", side_effect=PermissionError("denied")):
        backup.cleanup_old_backups()  # must not raise
