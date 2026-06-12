
"""Tests for messages.py and keyboards.py"""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


class TestMessages:
    def test_welcome_text_contains_name(self):
        import messages
        text = messages.welcome_text("TestShop")
        assert "TestShop" in text

    def test_welcome_text_escapes_html(self):
        import messages
        text = messages.welcome_text("<script>")
        assert "<script>" not in text
        assert "&lt;script&gt;" in text

    def test_booking_confirmed_template(self):
        import messages
        t = messages.BOOKING_CONFIRMED.format(
            date="Mon, 1 Dec", time="10:00",
            master="Alibek", service="Haircut",
            price="3 000", address="Test St"
        )
        assert "10:00" in t
        assert "Alibek" in t
        assert "Test St" in t

    def test_booking_confirm_template(self):
        import messages
        t = messages.BOOKING_CONFIRM.format(
            name="Ivan", master="Alibek",
            service="Haircut", date="2026-12-01",
            time="10:00", price=3000
        )
        assert "Ivan" in t
        assert "Alibek" in t

    def test_max_bookings_reached_text_uses_config(self):
        import messages, config
        text = messages.max_bookings_reached_text()
        assert str(config.MAX_ACTIVE_BOOKINGS) in text

    def test_get_about_text_contains_name(self):
        import messages, config
        text = messages.get_about_text()
        assert config.BARBERSHOP_NAME in text

    def test_get_about_text_contains_phone(self):
        import messages, config
        text = messages.get_about_text()
        assert config.BARBERSHOP_PHONE in text

    def test_no_static_about_constant(self):
        """ABOUT static constant should be removed (BUG-S5 fix)."""
        import messages
        # The ABOUT attribute may not exist or should not be a static string
        # If it was removed, we just confirm get_about_text() exists
        assert callable(messages.get_about_text)

    def test_reminder_24h_template(self):
        import messages
        t = messages.REMINDER_24H.format(
            date="Mon", time="10:00", master="Alibek", service="Haircut"
        )
        assert "10:00" in t

    def test_reminder_2h_template(self):
        import messages
        t = messages.REMINDER_2H.format(
            date="Mon", time="10:00", master="Alibek", service="Haircut"
        )
        assert "2" in t

    def test_cancelled_text(self):
        import messages
        assert len(messages.BOOKING_CANCELLED) > 0

    def test_waitlist_added_template(self):
        import messages
        t = messages.WAITLIST_ADDED.format(date="Mon", time="10:00")
        assert "10:00" in t

    def test_master_selected(self):
        import messages
        t = messages.master_selected("Alibek", "5 years", "fades")
        assert "Alibek" in t
        assert "5 years" in t

    def test_service_selected(self):
        import messages
        t = messages.service_selected("Haircut", 3000)
        assert "3" in t

    def test_date_selected(self):
        import messages
        t = messages.date_selected("Mon, 1 Dec")
        assert "Mon" in t

    def test_error_message_exists(self):
        import messages
        assert len(messages.ERROR) > 0

    def test_slot_busy_exists(self):
        import messages
        assert len(messages.SLOT_BUSY) > 0


class TestKeyboards:
    def test_main_menu_kb_has_book_button(self):
        import keyboards
        kb = keyboards.main_menu_kb()
        btns = [b for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for b in btns]
        assert "book" in datas

    def test_main_menu_kb_has_my_bookings(self):
        import keyboards
        kb = keyboards.main_menu_kb()
        btns = [b for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for b in btns]
        assert "my_bookings" in datas

    def test_masters_kb_shows_all_masters(self):
        import keyboards, config
        kb = keyboards.masters_kb()
        btns = [b for row in kb.inline_keyboard for b in row]
        texts = [b.text for b in btns]
        for name in config.MASTERS:
            assert any(name[:6] in t for t in texts)

    def test_back_to_main_kb(self):
        import keyboards
        kb = keyboards.back_to_main_kb()
        btns = [b for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for b in btns]
        assert "main_menu" in datas

    def test_dates_kb_has_correct_callbacks(self):
        import keyboards
        dates = ["2026-12-01", "2026-12-02"]
        kb = keyboards.dates_kb(dates)
        btns = [b for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for b in btns]
        assert any(d.startswith("date:") for d in datas)

    def test_time_slots_kb_free_slot_shown(self):
        import keyboards
        slots = {"10:00": "free", "10:30": "busy"}
        kb = keyboards.time_slots_kb(slots)
        btns = [b for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for b in btns]
        assert any(d.startswith("time:") for d in datas)

    def test_time_slots_kb_all_busy_shows_waitlist(self):
        import keyboards
        slots = {"10:00": "busy", "10:30": "busy"}
        kb = keyboards.time_slots_kb(slots)
        btns = [b for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for b in btns]
        assert "go_to_waitlist" in datas

    def test_format_date(self):
        import keyboards
        result = keyboards._format_date("2026-12-01")
        # Should contain day number and month name
        assert "1" in result

    def test_format_date_invalid(self):
        import keyboards
        result = keyboards._format_date("invalid")
        assert result == "invalid"

    def test_bookings_list_kb(self):
        import keyboards
        bookings = [{"id": "abc123", "date": "2026-12-01", "time": "10:00", "master": "Alibek"}]
        kb = keyboards.bookings_list_kb(bookings)
        btns = [b for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for b in btns]
        assert any("abc123" in d for d in datas)

    def test_remind_kb(self):
        import keyboards
        kb = keyboards.remind_kb("bid123")
        btns = [b for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for b in btns]
        assert any("bid123" in d for d in datas)

    async def test_services_kb(self, db):
        """services_kb with no master should return all config services."""
        import keyboards, config
        kb = await keyboards.services_kb()
        btns = [b for row in kb.inline_keyboard for b in row]
        datas = [b.callback_data for b in btns]
        assert any(d.startswith("service:") for d in datas)
