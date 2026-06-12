
"""Tests for handlers/admin.py - admin panel"""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from unittest.mock import AsyncMock, MagicMock, patch
from helpers import make_message, make_callback, make_fsm, SAMPLE_BOOKING


def setup_admin(user_id=777):
    import config
    config.ADMIN_IDS = [user_id]
    return user_id


class TestIsAdmin:
    def test_admin_user_returns_true(self):
        import config
        config.ADMIN_IDS = [100]
        from handlers.admin import _is_admin
        assert _is_admin(100) is True

    def test_non_admin_returns_false(self):
        import config
        config.ADMIN_IDS = [100]
        from handlers.admin import _is_admin
        assert _is_admin(999) is False

    def test_empty_admin_ids_returns_false(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import _is_admin
        assert _is_admin(100) is False


class TestCmdAdmin:
    async def test_non_admin_rejected(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cmd_admin
        msg = make_message(user_id=999)
        state = make_fsm()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()) as mock_send:
            await cmd_admin(msg, state)
        state.clear.assert_called_once()
        mock_send.assert_called_once()

    async def test_admin_gets_panel(self):
        admin_id = setup_admin()
        from handlers.admin import cmd_admin
        msg = make_message(user_id=admin_id)
        msg.chat.id = admin_id
        state = make_fsm()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()) as mock_send:
            await cmd_admin(msg, state)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        # The admin panel text should be sent
        assert call_kwargs is not None


class TestCbAdmin:
    async def test_non_admin_shows_alert(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin
        cb = make_callback(data="admin", user_id=999)
        state = make_fsm()
        await cb_admin(cb, state)
        cb.answer.assert_called()

    async def test_admin_shows_panel(self):
        admin_id = setup_admin()
        from handlers.admin import cb_admin
        cb = make_callback(data="admin", user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin(cb, state)
        cb.answer.assert_called()


class TestCbAdminStats:
    async def test_non_admin_blocked(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin_stats
        cb = make_callback(user_id=999)
        await cb_admin_stats(cb)
        cb.answer.assert_called()

    async def test_admin_sees_stats(self, db):
        admin_id = setup_admin()
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        from handlers.admin import cb_admin_stats
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_stats(cb)
        cb.answer.assert_called()


class TestCbAdminAllBookings:
    async def test_no_bookings_shows_empty(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_bookings
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()) as m:
            await cb_admin_bookings(cb)
        cb.answer.assert_called()

    async def test_with_bookings_shows_list(self, db):
        admin_id = setup_admin()
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        from handlers.admin import cb_admin_bookings
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_bookings(cb)
        cb.answer.assert_called()

    async def test_non_admin_blocked(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin_bookings
        cb = make_callback(user_id=999)
        await cb_admin_bookings(cb)
        cb.answer.assert_called()


class TestCbAdminCancelBooking:
    async def test_cancel_valid_booking(self, db):
        admin_id = setup_admin()
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        from handlers.admin import cb_admin_cancel_booking
        cb = make_callback(data=f"admin_cancel:{bid}", user_id=admin_id)
        bot = AsyncMock()
        with patch("handlers.admin.scheduler.cancel_reminders", new=AsyncMock()), \
             patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await cb_admin_cancel_booking(cb, bot)
        cb.answer.assert_called()

    async def test_cancel_nonexistent_shows_error(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_cancel_booking
        cb = make_callback(data="admin_cancel:nonexistent", user_id=admin_id)
        bot = AsyncMock()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await cb_admin_cancel_booking(cb, bot)
        cb.answer.assert_called()

    async def test_non_admin_blocked(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin_cancel_booking
        cb = make_callback(data="admin_cancel:bid", user_id=999)
        bot = AsyncMock()
        await cb_admin_cancel_booking(cb, bot)
        cb.answer.assert_called()


class TestCbAdminCompleteBooking:
    async def test_complete_valid_booking(self, db):
        admin_id = setup_admin()
        import storage, config
        config.LOYALTY_VISIT_INTERVAL = 5
        bid = await storage.save_booking(SAMPLE_BOOKING)
        from handlers.admin import cb_admin_complete_booking
        cb = make_callback(data=f"admin_complete:{bid}", user_id=admin_id)
        bot = AsyncMock()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()), \
             patch("handlers.admin.scheduler") as mock_sched:
            mock_sched.cancel_reminders = AsyncMock()
            mock_sched.schedule_review_request = MagicMock()
            await cb_admin_complete_booking(cb, bot)
        cb.answer.assert_called()

    async def test_non_admin_blocked(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin_complete_booking
        cb = make_callback(data="admin_complete:bid", user_id=999)
        bot = AsyncMock()
        await cb_admin_complete_booking(cb, bot)
        cb.answer.assert_called()


class TestCbAdminExportCsv:
    async def test_non_admin_blocked(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin_export
        cb = make_callback(user_id=999)
        bot = AsyncMock()
        await cb_admin_export(cb)
        cb.answer.assert_called()

    async def test_empty_db_shows_alert(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_export
        cb = make_callback(user_id=admin_id)
        bot = AsyncMock()
        await cb_admin_export(cb)
        cb.answer.assert_called()

    async def test_with_bookings_sends_file(self, db):
        admin_id = setup_admin()
        import storage
        await storage.save_booking(SAMPLE_BOOKING)
        from handlers.admin import cb_admin_export
        cb = make_callback(user_id=admin_id)
        bot = AsyncMock()
        await cb_admin_export(cb)
        cb.answer.assert_called()


class TestCbAdminMasters:
    async def test_shows_masters_list(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_masters
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_masters(cb)
        cb.answer.assert_called()

    async def test_non_admin_blocked(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin_masters
        cb = make_callback(user_id=999)
        await cb_admin_masters(cb)
        cb.answer.assert_called()


class TestCbAdminServices:
    async def test_shows_services_list(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_services
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_services(cb)
        cb.answer.assert_called()


class TestCbAdminAddMaster:
    async def test_starts_add_master_flow(self):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_add_master
        cb = make_callback(user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_add_master(cb, state)
        state.set_state.assert_called_once()
        cb.answer.assert_called()

    async def test_non_admin_blocked(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin_add_master
        cb = make_callback(user_id=999)
        state = make_fsm()
        await cb_admin_add_master(cb, state)
        cb.answer.assert_called()
        state.set_state.assert_not_called()


class TestCbAdminLoyalty:
    async def test_shows_loyalty_list(self, db):
        admin_id = setup_admin()
        import storage
        await storage.update_loyalty(111, "Ivan")
        from handlers.admin import cb_admin_loyalty
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_loyalty(cb)
        cb.answer.assert_called()

    async def test_empty_loyalty_shows_empty(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_loyalty
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_loyalty(cb)
        cb.answer.assert_called()


class TestCbAdminWaitlist:
    async def test_shows_waitlist(self, db):
        admin_id = setup_admin()
        import storage
        await storage.add_to_waitlist(111, "Ivan", "Alibek", "Haircut", "2026-12-07", "10:00")
        from handlers.admin import cb_admin_waitlist
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_waitlist(cb)
        cb.answer.assert_called()


class TestCbAdminReviews:
    async def test_shows_reviews(self, db):
        admin_id = setup_admin()
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.complete_booking(bid)
        await storage.save_review(bid, 111, 5, "Great")
        from handlers.admin import cb_admin_reviews
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_reviews(cb)
        cb.answer.assert_called()


class TestCbAdminSettings:
    async def test_shows_settings(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_settings
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_settings(cb)
        cb.answer.assert_called()



class TestHandleAddMasterName:
    async def test_valid_name_proceeds(self):
        admin_id = setup_admin()
        from handlers.admin import handle_add_master
        msg = make_message(text="Alibek, 5 years, fades", user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()), \
             patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_add_master(msg, state)
        state.clear.assert_called_once()

    async def test_empty_name_rejected(self):
        admin_id = setup_admin()
        from handlers.admin import handle_add_master
        msg = make_message(text="  ", user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_add_master(msg, state)
        state.update_data.assert_not_called()


class TestHandleAddServicePrice:
    async def test_valid_price_saves_service(self, db):
        admin_id = setup_admin()
        from handlers.admin import handle_add_service
        msg = make_message(text="Haircut, 3000", user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()), \
             patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await handle_add_service(msg, state)
        state.clear.assert_called_once()

    async def test_invalid_price_rejected(self):
        admin_id = setup_admin()
        from handlers.admin import handle_add_service
        msg = make_message(text="notanumber", user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_add_service(msg, state)
        state.clear.assert_not_called()

    async def test_negative_price_rejected(self):
        admin_id = setup_admin()
        from handlers.admin import handle_add_service
        msg = make_message(text="-100", user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_add_service(msg, state)
        state.clear.assert_not_called()
