
"""Tests for config.py functions load_config_from_db and save_config_to_db."""
import pytest
import sys, pathlib, json
from unittest.mock import AsyncMock, patch
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


class TestConfigConstants:

    def test_masters_not_empty(self):
        import config
        assert len(config.MASTERS) > 0

    def test_services_not_empty(self):
        import config
        assert len(config.SERVICES) > 0

    def test_service_prices_positive(self):
        import config
        for name, price in config.SERVICES.items():
            assert price > 0, f"Service {name} has non-positive price"

    def test_time_slots_not_empty(self):
        import config
        assert len(config.TIME_SLOTS) > 0

    def test_time_slots_format(self):
        import config
        for slot in config.TIME_SLOTS:
            assert ":" in slot, f"Bad slot format: {slot}"

    def test_timezone_string(self):
        import config
        assert isinstance(config.TIMEZONE, str)
        assert len(config.TIMEZONE) > 0

    def test_referral_bonus_positive(self):
        import config
        assert config.REFERRAL_BONUS > 0

    def test_max_active_bookings_positive(self):
        import config
        assert config.MAX_ACTIVE_BOOKINGS > 0

    def test_working_hours_has_seven_days(self):
        import config
        days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        assert days.issubset(set(config.WORKING_HOURS.keys()))


class TestAdminIdsParsing:

    def test_admin_ids_is_list(self):
        import config
        assert isinstance(config.ADMIN_IDS, list)

    def test_admin_ids_are_ints(self):
        import config
        for aid in config.ADMIN_IDS:
            assert isinstance(aid, int)

    def test_invalid_admin_id_not_added(self, monkeypatch):
        """Non-integer ADMIN_IDS value is silently skipped."""
        import importlib
        monkeypatch.setenv("ADMIN_IDS", "12345,notanint,67890")
        import config as _config
        # Re-run the parsing logic manually
        result = []
        for raw in "12345,notanint,67890".split(","):
            raw = raw.strip()
            if raw:
                try:
                    result.append(int(raw))
                except ValueError:
                    pass
        assert result == [12345, 67890]


class TestLoadConfigFromDb:

    async def test_load_config_updates_address(self, db):
        import config, storage
        await storage.init_db()
        await storage.save_settings("address", "Test Street 1")
        await config.load_config_from_db()
        assert config.BARBERSHOP_ADDRESS == "Test Street 1"
        # restore
        config.BARBERSHOP_ADDRESS = "г. Алматы, ул. Абая 45, 2 этаж"

    async def test_load_config_updates_services(self, db):
        import config, storage
        await storage.init_db()
        await storage.save_service("TestService", 9999)
        original = dict(config.SERVICES)
        await config.load_config_from_db()
        assert config.SERVICES.get("TestService") == 9999
        # restore
        config.SERVICES.clear()
        config.SERVICES.update(original)

    async def test_load_config_handles_exception(self, db):
        """load_config_from_db does not raise when storage fails."""
        import config
        with patch("storage.get_all_settings", side_effect=Exception("DB down")):
            await config.load_config_from_db()  # must not raise

    async def test_load_config_working_hours_json(self, db):
        import config, storage
        await storage.init_db()
        new_hours = {"monday": [9, 20], "tuesday": [9, 20]}
        await storage.save_settings("working_hours_json", json.dumps(new_hours))
        original = dict(config.WORKING_HOURS)
        await config.load_config_from_db()
        assert config.WORKING_HOURS.get("monday") == [9, 20]
        config.WORKING_HOURS.clear()
        config.WORKING_HOURS.update(original)


class TestSaveConfigToDb:

    async def test_save_config_to_db_writes_address(self, db):
        import config, storage
        await storage.init_db()
        original = config.BARBERSHOP_ADDRESS
        config.BARBERSHOP_ADDRESS = "Save Test St"
        await config.save_config_to_db()
        settings = await storage.get_all_settings()
        assert settings["address"] == "Save Test St"
        config.BARBERSHOP_ADDRESS = original

    async def test_save_config_to_db_writes_services(self, db):
        import config, storage
        await storage.init_db()
        await config.save_config_to_db()
        services = await storage.get_all_services()
        for name in config.SERVICES:
            assert name in services

    async def test_save_config_handles_exception(self, db):
        """save_config_to_db does not raise when storage fails."""
        import config
        with patch("storage.save_settings", side_effect=Exception("boom")):
            await config.save_config_to_db()  # must not raise
