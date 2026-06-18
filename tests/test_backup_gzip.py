
"""Tests for updated backup.py: gzip output and PG mock."""
import gzip, os, pytest, sys, pathlib
from unittest.mock import patch, AsyncMock
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


class TestSqliteBackupGzip:

    def test_creates_db_gz_file(self, tmp_path):
        import backup
        db = tmp_path / "test.db"
        db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
        with patch("backup._BACKUP_DIR", str(tmp_path / "backups")), \
             patch("backup.config.DB_PATH", str(db)), \
             patch("backup.os.getenv", return_value=""):
            result = backup.backup_database()
        assert result is not None
        assert result.endswith(".db.gz")
        assert os.path.exists(result)

    def test_backup_content_is_valid_gzip(self, tmp_path):
        import backup
        payload = b"SQLite format 3" + b"X" * 200
        db = tmp_path / "test.db"
        db.write_bytes(payload)
        with patch("backup._BACKUP_DIR", str(tmp_path / "backups")), \
             patch("backup.config.DB_PATH", str(db)), \
             patch("backup.os.getenv", return_value=""):
            result = backup.backup_database()
        assert result is not None
        with gzip.open(result, "rb") as f:
            content = f.read()
        assert content == payload

    def test_returns_none_when_db_missing(self, tmp_path):
        import backup
        with patch("backup._BACKUP_DIR", str(tmp_path / "backups")), \
             patch("backup.config.DB_PATH", str(tmp_path / "nonexistent.db")), \
             patch("backup.os.getenv", return_value=""):
            result = backup.backup_database()
        assert result is None

    def test_backup_dir_created_if_missing(self, tmp_path):
        import backup
        db = tmp_path / "test.db"
        db.write_bytes(b"data")
        backup_dir = tmp_path / "new_backups"
        assert not backup_dir.exists()
        with patch("backup._BACKUP_DIR", str(backup_dir)), \
             patch("backup.config.DB_PATH", str(db)), \
             patch("backup.os.getenv", return_value=""):
            backup.backup_database()
        assert backup_dir.exists()


class TestPostgresBackupMock:

    def test_calls_asyncio_run_when_database_url_set(self, tmp_path):
        import backup
        with patch("backup._BACKUP_DIR", str(tmp_path / "backups")), \
             patch("backup.os.getenv", return_value="postgresql://localhost/test"), \
             patch("backup.asyncio.run") as mock_run:
            mock_run.return_value = True
            result = backup.backup_database()
        assert mock_run.called
        assert result is not None
        assert result.endswith(".sql.gz")

    def test_returns_none_when_pg_dump_fails(self, tmp_path):
        import backup
        with patch("backup._BACKUP_DIR", str(tmp_path / "backups")), \
             patch("backup.os.getenv", return_value="postgresql://localhost/test"), \
             patch("backup.asyncio.run") as mock_run:
            mock_run.return_value = False
            result = backup.backup_database()
        assert result is None

    async def test_pg_dump_returns_false_on_connection_error(self, tmp_path):
        import backup
        with patch("asyncpg.connect", side_effect=ConnectionRefusedError("no server")):
            result = await backup._pg_dump("postgresql://localhost/test", str(tmp_path / "dump.sql.gz"))
        assert result is False

    async def test_pg_dump_creates_gzip_file(self, tmp_path):
        import backup
        mock_conn = AsyncMock()
        mock_conn.fetch.return_value = []
        mock_conn.close = AsyncMock()
        with patch("asyncpg.connect", return_value=mock_conn):
            out_file = str(tmp_path / "dump.sql.gz")
            result = await backup._pg_dump("postgresql://localhost/test", out_file)
        assert result is True
        assert os.path.exists(out_file)
        with gzip.open(out_file, "rt", encoding="utf-8") as f:
            text = f.read()
        assert "Barbershop DB dump" in text


class TestCleanupUpdated:

    def test_removes_excess_db_gz(self, tmp_path):
        import backup
        bd = tmp_path / "backups"
        bd.mkdir()
        for i in range(35):
            (bd / f"barbershop_{i:04d}0000_000000.db.gz").write_bytes(b"x")
        with patch("backup._BACKUP_DIR", str(bd)):
            backup.cleanup_old_backups(max_backups=30)
        assert len(list(bd.glob("*.db.gz"))) == 30

    def test_removes_excess_sql_gz(self, tmp_path):
        import backup
        bd = tmp_path / "backups"
        bd.mkdir()
        for i in range(40):
            (bd / f"barbershop_{i:04d}0000_000000.sql.gz").write_bytes(b"x")
        with patch("backup._BACKUP_DIR", str(bd)):
            backup.cleanup_old_backups(max_backups=30)
        assert len(list(bd.glob("*.sql.gz"))) == 30

    def test_mixed_extensions_counted_together(self, tmp_path):
        import backup
        bd = tmp_path / "backups"
        bd.mkdir()
        for i in range(20):
            (bd / f"barbershop_{i:04d}0000_000000.db.gz").write_bytes(b"x")
        for i in range(20):
            (bd / f"barbershop_{(i+20):04d}0000_000000.sql.gz").write_bytes(b"x")
        with patch("backup._BACKUP_DIR", str(bd)):
            backup.cleanup_old_backups(max_backups=30)
        total = len(list(bd.glob("*.db.gz"))) + len(list(bd.glob("*.sql.gz")))
        assert total == 30

    def test_other_files_untouched(self, tmp_path):
        import backup
        bd = tmp_path / "backups"
        bd.mkdir()
        (bd / "notes.txt").write_bytes(b"keep me")
        for i in range(5):
            (bd / f"barbershop_{i:04d}0000_000000.db.gz").write_bytes(b"x")
        with patch("backup._BACKUP_DIR", str(bd)):
            backup.cleanup_old_backups(max_backups=10)
        assert (bd / "notes.txt").exists()

    def test_no_dir_does_not_raise(self, tmp_path):
        import backup
        with patch("backup._BACKUP_DIR", str(tmp_path / "missing")):
            backup.cleanup_old_backups()

    def test_below_limit_nothing_removed(self, tmp_path):
        import backup
        bd = tmp_path / "backups"
        bd.mkdir()
        for i in range(5):
            (bd / f"barbershop_{i:04d}0000_000000.db.gz").write_bytes(b"x")
        with patch("backup._BACKUP_DIR", str(bd)):
            backup.cleanup_old_backups(max_backups=30)
        assert len(list(bd.glob("*.db.gz"))) == 5
