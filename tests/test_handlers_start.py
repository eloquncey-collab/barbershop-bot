
"""Tests for handlers/start.py and handlers/info.py"""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from unittest.mock import AsyncMock, MagicMock, patch
from helpers import make_message, make_callback, make_fsm


class TestCmdStart:
    async def test_new_user_saved(self, db):
        from handlers.start import cmd_start
        import storage
        msg = make_message(text="/start", user_id=200)
        fsm = make_fsm()
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_start(msg, fsm)
        user = await storage.get_user(200)
        assert user is not None

    async def test_existing_user_not_overwritten(self, db):
        from handlers.start import cmd_start
        import storage
        await storage.save_user(200, phone="+77001111111", username="u", first_name="Bob")
        msg = make_message(text="/start", user_id=200)
        fsm = make_fsm()
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_start(msg, fsm)
        user = await storage.get_user(200)
        assert user["phone"] == "+77001111111"  # phone preserved

    async def test_sends_main_menu(self, db):
        from handlers.start import cmd_start
        send_mock = AsyncMock()
        msg = make_message(text="/start", user_id=200)
        fsm = make_fsm()
        with patch("handlers.start.send_with_retry", new=send_mock):
            await cmd_start(msg, fsm)
        send_mock.assert_called()

    async def test_referral_processed(self, db):
        from handlers.start import cmd_start
        import storage
        # Create referrer first
        await storage.save_user(100, username="referrer", first_name="Ref")
        await storage.update_loyalty(100, "Ref")  # Create loyalty entry for referrer
        # Get their ref_code
        loyalty = await storage.get_loyalty(100)
        ref_code = loyalty["ref_code"]
        # New user with referral
        msg = make_message(text=f"/start ref_{ref_code}", user_id=201)
        msg.from_user.first_name = "NewUser"
        fsm = make_fsm()
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_start(msg, fsm)
        referrals = await storage.get_referrals()
        assert any(r["referrer_id"] == 100 and r["referred_id"] == 201 for r in referrals)

    async def test_fsm_cleared_on_start(self, db):
        from handlers.start import cmd_start
        msg = make_message(text="/start", user_id=200)
        fsm = make_fsm()
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_start(msg, fsm)
        fsm.clear.assert_called_once()


class TestCbMainMenu:
    async def test_shows_main_menu(self):
        from handlers.start import cb_main_menu
        cb = make_callback(data="main_menu")
        fsm = make_fsm()
        with patch("handlers.start.edit_with_retry", new=AsyncMock()):
            await cb_main_menu(cb, fsm)
        fsm.clear.assert_called_once()
        cb.answer.assert_called()


class TestCbMyBookings:
    async def test_no_bookings_shows_alert(self, db):
        from handlers.start import cb_my_bookings
        cb = make_callback(user_id=111)
        await cb_my_bookings(cb)
        cb.answer.assert_called()
        call_kwargs = cb.answer.call_args[1]
        assert call_kwargs.get("show_alert") is True

    async def test_with_bookings_shows_list(self, db):
        from handlers.start import cb_my_bookings
        import storage
        await storage.save_booking({
            "date": "2026-12-07", "time": "10:00", "name": "Ivan",
            "telegram_id": 111, "username": "u", "master": "Alibek",
            "service": "Haircut", "price": 3000
        })
        cb = make_callback(user_id=111)
        await cb_my_bookings(cb)
        cb.message.edit_text.assert_called_once()


class TestInfoHandlers:
    async def test_cb_contacts(self):
        from handlers.info import cb_contacts
        cb = make_callback(data="contacts")
        with patch("handlers.info.edit_with_retry", new=AsyncMock()):
            await cb_contacts(cb)
        cb.answer.assert_called()

    async def test_cb_prices(self):
        from handlers.info import cb_prices
        import config
        config.SERVICES = {"Haircut": 3000, "Shave": 1500}
        cb = make_callback(data="prices")
        with patch("handlers.info.edit_with_retry", new=AsyncMock()):
            await cb_prices(cb)
        cb.answer.assert_called()

    async def test_cb_call(self):
        from handlers.info import cb_call
        cb = make_callback(data="call")
        with patch("handlers.info.edit_with_retry", new=AsyncMock()):
            await cb_call(cb)
        cb.answer.assert_called()

    async def test_cb_masters(self):
        from handlers.info import cb_masters
        cb = make_callback(data="masters")
        with patch("handlers.info.edit_with_retry", new=AsyncMock()):
            await cb_masters(cb)
        cb.answer.assert_called()
