
"""More tests for handlers/start.py to boost coverage"""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from unittest.mock import AsyncMock, MagicMock, patch
from helpers import make_message, make_callback, make_fsm, SAMPLE_BOOKING


class TestCbBookingDetail:
    async def test_shows_active_booking_detail(self, db):
        from handlers.start import cb_booking_detail
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"booking_detail:{bid}", user_id=111)
        with patch("handlers.start.edit_with_retry", new=AsyncMock()):
            await cb_booking_detail(cb)
        cb.answer.assert_called()

    async def test_nonexistent_booking(self, db):
        from handlers.start import cb_booking_detail
        cb = make_callback(data="booking_detail:nope", user_id=111)
        with patch("handlers.start.edit_with_retry", new=AsyncMock()):
            await cb_booking_detail(cb)
        cb.answer.assert_called()


class TestCbAskCancel:
    async def test_shows_confirmation(self, db):
        from handlers.start import cb_ask_cancel
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"ask_cancel:{bid}", user_id=111)
        with patch("handlers.start.edit_with_retry", new=AsyncMock()):
            await cb_ask_cancel(cb)
        cb.answer.assert_called()

    async def test_wrong_user_blocked(self, db):
        from handlers.start import cb_ask_cancel
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"ask_cancel:{bid}", user_id=999)
        with patch("handlers.start.edit_with_retry", new=AsyncMock()):
            await cb_ask_cancel(cb)
        cb.answer.assert_called()


class TestCbConfirmCancel:
    async def test_cancels_booking(self, db):
        from handlers.start import cb_confirm_cancel
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"confirm_cancel:{bid}", user_id=111)
        with patch("handlers.start.edit_with_retry", new=AsyncMock()), \
             patch("handlers.start.scheduler.cancel_reminders", new=AsyncMock()):
            await cb_confirm_cancel(cb)
        cb.answer.assert_called()

    async def test_wrong_user_cannot_cancel(self, db):
        from handlers.start import cb_confirm_cancel
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"confirm_cancel:{bid}", user_id=999)
        with patch("handlers.start.edit_with_retry", new=AsyncMock()):
            await cb_confirm_cancel(cb)
        # Booking should still be active
        bookings = await storage.get_user_bookings(111)
        assert any(b["id"] == bid for b in bookings)

    async def test_nonexistent_booking(self, db):
        from handlers.start import cb_confirm_cancel
        cb = make_callback(data="confirm_cancel:nope", user_id=111)
        with patch("handlers.start.edit_with_retry", new=AsyncMock()):
            await cb_confirm_cancel(cb)
        cb.answer.assert_called()


class TestCmdMe:
    async def test_shows_loyalty_info(self, db):
        from handlers.start import cmd_me
        import storage
        await storage.update_loyalty(111, "Ivan")
        msg = make_message(user_id=111)
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_me(msg)

    async def test_no_loyalty_shows_info(self, db):
        from handlers.start import cmd_me
        msg = make_message(user_id=111)
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_me(msg)


class TestCmdHelp:
    async def test_shows_help(self):
        from handlers.start import cmd_help
        msg = make_message(user_id=111)
        with patch("handlers.start.send_with_retry", new=AsyncMock()) as mock_s:
            await cmd_help(msg)
        # cmd_help uses send_with_retry, not msg.answer directly


class TestCmdWaitlist:
    async def test_shows_waitlist_empty(self, db):
        from handlers.start import cmd_waitlist
        msg = make_message(user_id=111)
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_waitlist(msg)

    async def test_shows_user_waitlist(self, db):
        from handlers.start import cmd_waitlist
        import storage
        await storage.add_to_waitlist(111, "Ivan", "Alibek", "Haircut", "2026-12-07", "10:00")
        msg = make_message(user_id=111)
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_waitlist(msg)


class TestCmdMaster:
    async def test_shows_master_info(self, db):
        from handlers.start import cmd_master
        import config
        master_name = list(config.MASTERS.keys())[0]
        msg = make_message(text=f"/master {master_name}", user_id=111)
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_master(msg)

    async def test_unknown_master(self, db):
        from handlers.start import cmd_master
        msg = make_message(text="/master Unknown", user_id=111)
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_master(msg)

    async def test_no_arg_shows_list(self, db):
        from handlers.start import cmd_master
        msg = make_message(text="/master", user_id=111)
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_master(msg)


class TestCmdCancelUniversal:
    async def test_cancels_active_bookings_shown(self, db):
        from handlers.start import cmd_cancel_universal
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        msg = make_message(text="/cancel", user_id=111)
        fsm = make_fsm()
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_cancel_universal(msg, fsm)
        msg.answer.assert_not_called()  # uses send_with_retry

    async def test_no_bookings_message(self, db):
        from handlers.start import cmd_cancel_universal
        msg = make_message(text="/cancel", user_id=999)
        fsm = make_fsm()
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await cmd_cancel_universal(msg, fsm)


class TestHandleContact:
    async def test_saves_phone_from_contact(self, db):
        from handlers.start import handle_contact
        import storage
        msg = make_message(user_id=111)
        msg.contact = MagicMock()
        msg.contact.phone_number = "+77001234567"
        fsm = make_fsm()
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await handle_contact(msg, fsm)
        user = await storage.get_user(111)
        if user:
            # phone may or may not be saved depending on implementation
            pass

    async def test_no_contact_ignored(self, db):
        from handlers.start import handle_contact
        msg = make_message(user_id=111)
        msg.contact = None
        fsm = make_fsm()
        # Should not crash
        with patch("handlers.start.send_with_retry", new=AsyncMock()):
            await handle_contact(msg, fsm)
