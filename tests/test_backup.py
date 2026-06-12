
"""Tests for backup.py"""
import os
import pytest
from unittest.mock import patch, MagicMock


def test_backup_database_success(tmp_path):
    import backup
    db = tmp_path / "test.db"
    db.write_bytes(b"SQLite format 3" + b"\x00" * 100)
    with patch("backup.os.path.dirname", return_value=str(tmp_path)), \
         patch("backup.os.path.abspath", return_value=str(tmp_path / "backup.py")), \
         patch("backup.config.DB_PATH", str(db)), \
         patch("backup.shutil.copy2") as mock_copy:
        mock_copy.return_value = None
        result = backup.backup_database()
    assert mock_copy.called
    assert result is not None


def test_backup_database_missing_db(tmp_path):
    import backup
    nonexistent = str(tmp_path / "nonexistent.db")
    with patch("backup.config.DB_PATH", nonexistent), \
         patch("backup.os.path.dirname", return_value=str(tmp_path)), \
         patch("backup.os.path.abspath", return_value=str(tmp_path / "backup.py")):
        result = backup.backup_database()
    assert result is None


def test_cleanup_no_dir(tmp_path):
    import backup
    nd = str(tmp_path / "no_backups")
    with patch("backup.os.path.dirname", return_value=nd), \
         patch("backup.os.path.abspath", return_value=str(nd) + "/backup.py"):
        backup.cleanup_old_backups()  # Should not raise


def test_cleanup_removes_excess(tmp_path):
    import backup
    bd = tmp_path / "backups"
    bd.mkdir()
    for i in range(35):
        (bd / f"barbershop_{i:04d}00_000000.db").write_bytes(b"x")
    with patch("backup.os.path.dirname", return_value=str(tmp_path)), \
         patch("backup.os.path.abspath", return_value=str(tmp_path / "backup.py")):
        backup.cleanup_old_backups(max_backups=30)
    assert len(list(bd.glob("*.db"))) == 30


def test_cleanup_below_limit(tmp_path):
    import backup
    bd = tmp_path / "backups"
    bd.mkdir()
    for i in range(5):
        (bd / f"barbershop_{i:04d}00_000000.db").write_bytes(b"x")
    with patch("backup.os.path.dirname", return_value=str(tmp_path)), \
         patch("backup.os.path.abspath", return_value=str(tmp_path / "backup.py")):
        backup.cleanup_old_backups(max_backups=30)
    assert len(list(bd.glob("*.db"))) == 5


def test_cleanup_exception(tmp_path):
    import backup
    bd = tmp_path / "backups"
    bd.mkdir()
    with patch("backup.os.path.dirname", return_value=str(tmp_path)), \
         patch("backup.os.path.abspath", return_value=str(tmp_path / "backup.py")), \
         patch("backup.os.listdir", side_effect=PermissionError("denied")):
        backup.cleanup_old_backups()  # Should not raise
