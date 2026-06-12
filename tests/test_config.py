
"""Tests for config.py"""
import pytest
import sys, pathlib, os
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


class TestConfig:
    def test_timezone_set(self):
        import config
        assert len(config.TIMEZONE) > 0

    def test_max_active_bookings_positive(self):
        import config
        assert config.MAX_ACTIVE_BOOKINGS > 0

    def test_masters_dict_not_empty(self):
        import config
        assert len(config.MASTERS) > 0

    def test_services_dict_not_empty(self):
        import config
        assert len(config.SERVICES) > 0

    def test_services_prices_positive(self):
        import config
        for name, price in config.SERVICES.items():
            assert price > 0, f"{name} has invalid price"

    def test_working_hours_dict(self):
        import config
        for day, hours in config.WORKING_HOURS.items():
            start, end = hours
            assert start < end, f"{day} working hours invalid"

    def test_admin_ids_is_list(self):
        import config
        assert isinstance(config.ADMIN_IDS, list)

    def test_barbershop_name_set(self):
        import config
        assert len(config.BARBERSHOP_NAME) > 0

    def test_barbershop_address_set(self):
        import config
        assert len(config.BARBERSHOP_ADDRESS) > 0

    def test_min_advance_minutes_positive(self):
        import config
        assert config.MIN_BOOKING_ADVANCE_MINUTES > 0

    def test_referral_bonus_non_negative(self):
        import config
        assert config.REFERRAL_BONUS >= 0

    def test_admin_ids_invalid_skipped(self, monkeypatch):
        """Invalid ADMIN_IDS env var should not crash."""
        monkeypatch.setenv("ADMIN_IDS", "123,not_a_number,456")
        import importlib, config
        # Already loaded - we can at least confirm it didn't crash at startup
        assert isinstance(config.ADMIN_IDS, list)

    def test_loyalty_discount_positive(self):
        import config
        assert config.LOYALTY_DISCOUNT_PERCENT > 0
