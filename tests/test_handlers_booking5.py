import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.helpers import make_callback, make_message, make_fsm, SAMPLE_BOOKING


def setup_booking_config():
    import config
    config.MASTERS = {"Alibek": {"experience": "5 years", "specialization": "cuts"}}
    config.SERVICES = {"Haircut": 3000}
    config.ADMIN_IDS = {100}
    config.MASTER_IDS = {}
    config.TIMEZONE = "Asia/Almaty"
    config.MIN_BOOKING_ADVANCE_MINUTES = 30
    config.RATE_LIMIT_WINDOW = 3600
    config.MAX_BOOKING_ATTEMPTS = 10


class TestSafeEdit:
    """Lines 69-70: _safe_edit fallback to answer when not 'message is not modified'."""

    async def test_safe_edit_fallback_on_other_error(self):
        import handlers.booking as bk
        setup_booking_config()
        msg = MagicMock()
        msg.edit_text = AsyncMock(side_effect=Exception("some other error"))
        msg.answer = AsyncMock()
        await bk._safe_edit(msg, "text")
        msg.answer.assert_called()

    async def test_safe_edit_ignores_not_modified(self):
        import handlers.booking as bk
        setup_booking_config()
        msg = MagicMock()
        msg.edit_text = AsyncMock(side_effect=Exception("message is not modified"))
        msg.answer = AsyncMock()
        await bk._safe_edit(msg, "text")
        msg.answer.assert_not_called()


class TestGetSlots:
    """Lines 149-158: time filter for today's slots."""

    async def test_slots_today_future_slot(self):
        import handlers.booking as bk, config
        setup_booking_config()
        config.MIN_BOOKING_ADVANCE_MINUTES = 0
        from datetime import datetime, date
        today = datetime.now().strftime("%Y-%m-%d")
        # Patch get_now to return midnight so all slots are in the future
        fake_now = datetime.now().replace(hour=0, minute=0)
        with patch("handlers.booking.get_now", return_value=fake_now):
            with patch("storage.get_booked_slots", AsyncMock(return_value=[])):
                slots = await bk._get_available_slots(today, "Alibek")
        assert any(v == "free" for v in slots.values())

    async def test_slots_today_past_slot_filtered(self):
        import handlers.booking as bk, config
        setup_booking_config()
        config.MIN_BOOKING_ADVANCE_MINUTES = 24 * 60  # 24h — all slots are too soon
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        fake_now = datetime.now().replace(hour=0, minute=0)
        with patch("handlers.booking.get_now", return_value=fake_now):
            with patch("storage.get_booked_slots", AsyncMock(return_value=[])):
                slots = await bk._get_available_slots(today, "Alibek")
        # All slots should be filtered out (not present) or all busy
        free_slots = [v for v in slots.values() if v == "free"]
        assert len(free_slots) == 0


class TestCbBookFallbacks:
    """Lines 183-184, 203-204, 222-223: edit_text exception fallbacks in cb_book."""

    async def test_book_no_phone_edit_exception(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="book", user_id=222)
        cb.message.edit_text = AsyncMock(side_effect=Exception("edit fail"))
        cb.message.answer = AsyncMock()
        fsm = make_fsm()
        with patch("storage.get_user", AsyncMock(return_value=None)):
            await bk.cb_book(cb, fsm)
        cb.message.answer.assert_called()

    async def test_book_has_active_edit_exception(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="book", user_id=111)
        cb.message.edit_text = AsyncMock(side_effect=Exception("edit fail"))
        cb.message.answer = AsyncMock()
        fsm = make_fsm()
        with patch("storage.get_user", AsyncMock(return_value={"phone": "+7700"})):
            with patch("storage.has_active_booking", AsyncMock(return_value=True)):
                await bk.cb_book(cb, fsm)
        cb.message.answer.assert_called()

    async def test_book_rate_limited_edit_exception(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="book", user_id=111)
        cb.message.edit_text = AsyncMock(side_effect=Exception("edit fail"))
        cb.message.answer = AsyncMock()
        fsm = make_fsm()
        with patch("storage.get_user", AsyncMock(return_value={"phone": "+7700"})):
            with patch("storage.has_active_booking", AsyncMock(return_value=False)):
                with patch("storage.user_rate_limit_check", AsyncMock(return_value=False)):
                    await bk.cb_book(cb, fsm)
        cb.message.answer.assert_called()


class TestChooseServiceEdge:
    """Line 305: price fallback when master is empty."""

    async def test_service_empty_master(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="service:Haircut", user_id=111)
        # master is empty in FSM data
        fsm = make_fsm(data={"master": ""})
        with patch("storage.get_master_work_days", AsyncMock(return_value=[1,2,3,4,5,6])):
            await bk.cb_choose_service(cb, fsm)
        fsm.set_state.assert_called()


class TestCbChooseDateEdge:
    """Lines 338-340: invalid date format; 362-364: past date fallback; 377-386: too far."""

    async def test_invalid_date_format(self):
        import handlers.booking as bk
        from handlers.booking import BookingStates
        setup_booking_config()
        cb = make_callback(data="date:not-a-date", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_date.state)
        await bk.cb_choose_date(cb, fsm)
        cb.answer.assert_called()

    async def test_date_slots_exception(self, db):
        import handlers.booking as bk, storage
        from handlers.booking import BookingStates
        from datetime import datetime, timedelta
        setup_booking_config()
        await storage.init_db()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        cb = make_callback(data=f"date:{tomorrow}", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_date.state, data={"master": "Alibek"})
        # _get_available_slots throws — should fallback to free slots dict
        with patch("handlers.booking._get_available_slots", AsyncMock(side_effect=Exception("db fail"))):
            await bk.cb_choose_date(cb, fsm)
        # Should not crash, callback answered
        cb.answer.assert_called()


class TestCbChooseTime:
    """Lines 408-431: slot None / busy; 435-436: time not in list."""

    async def test_slot_none(self, db):
        import handlers.booking as bk, storage
        from handlers.booking import BookingStates
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="time:10:00", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_time.state,
                       data={"date": "2026-12-10", "master": "Alibek"})
        # slot is missing from dict — returns None
        with patch("handlers.booking._get_available_slots",
                   AsyncMock(return_value={"11:00": "free"})):
            await bk.cb_choose_time(cb, fsm)
        cb.answer.assert_called()

    async def test_slot_busy(self, db):
        import handlers.booking as bk, storage
        from handlers.booking import BookingStates
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="time:10:00", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_time.state,
                       data={"date": "2026-12-10", "master": "Alibek"})
        with patch("handlers.booking._get_available_slots",
                   AsyncMock(return_value={"10:00": "busy"})):
            await bk.cb_choose_time(cb, fsm)
        cb.answer.assert_called()

    async def test_time_not_in_generated(self, db):
        import handlers.booking as bk, storage
        from handlers.booking import BookingStates
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="time:99:99", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_time.state,
                       data={"date": "2026-12-10", "master": "Alibek"})
        with patch("handlers.booking._get_available_slots",
                   AsyncMock(side_effect=Exception("fail"))):
            await bk.cb_choose_time(cb, fsm)
        cb.answer.assert_called()


class TestHandleEnterNameEdge:
    """Lines 496-501: save_booking exception; 513-520: save_booking returns None."""

    async def test_save_booking_save_exception_in_name(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        msg = make_message(text="Alex", user_id=111)
        fsm = make_fsm(data={"date": "2026-12-10", "time": "10:00",
                             "master": "Alibek", "service": "Haircut", "price": 3000})
        with patch("storage.save_booking", AsyncMock(side_effect=Exception("fail"))):
            await bk.handle_enter_name(msg, fsm)
        msg.answer.assert_called()


class TestBackToTime:
    """Lines 538-539: back_to_time releases slot lock."""

    async def test_back_to_time_releases_lock(self, db):
        import handlers.booking as bk, storage
        from handlers.booking import BookingStates
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="back_to_time", user_id=111)
        fsm = make_fsm(data={"date": "2026-12-10", "time": "10:00", "master": "Alibek"})
        with patch("storage.release_slot_lock", AsyncMock()) as mock_release:
            with patch("handlers.booking._get_available_slots",
                       AsyncMock(return_value={"10:00": "free", "11:00": "busy"})):
                await bk.cb_back_to_time(cb, fsm)
        mock_release.assert_called_once()
        cb.answer.assert_called()


class TestBackToDateWithService:
    """Line 737: back_to_date shows service info when service is in FSM."""

    async def test_back_to_date_with_service(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="back_to_date", user_id=111)
        fsm = make_fsm(data={"master": "Alibek", "service": "Haircut", "price": 3000,
                             "date": "2026-12-10", "time": "10:00"})
        with patch("storage.release_slot_lock", AsyncMock()):
            with patch("storage.get_master_work_days", AsyncMock(return_value=[1,2,3,4,5,6])):
                await bk.cb_back_to_date(cb, fsm)
        cb.answer.assert_called()


class TestRemindConfirmEdge:
    """Lines 821-822: booking is None; 832-833: edit exception."""

    async def test_remind_confirm_booking_none(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="remind_confirm:nonexistent", user_id=111)
        bot = AsyncMock()
        with patch("storage.get_booking_with_user", AsyncMock(return_value=None)):
            await bk.cb_remind_confirm(cb, bot)
        cb.answer.assert_called()

    async def test_remind_confirm_edit_exception(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"remind_confirm:{bid}", user_id=111)
        cb.message.edit_text = AsyncMock(side_effect=Exception("edit fail"))
        bot = AsyncMock()
        with patch("config.ADMIN_IDS", {100}):
            await bk.cb_remind_confirm(cb, bot)
        cb.answer.assert_called()


class TestRemindCancelEdge:
    """Lines 845-846: edit exception; 854-866: last-minute; 870-879: waitlist; 883-884: not found."""

    async def test_remind_cancel_edit_exception(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"remind_cancel:{bid}", user_id=111)
        cb.message.edit_text = AsyncMock(side_effect=Exception("edit fail"))
        cb.message.answer = AsyncMock()
        bot = AsyncMock()
        with patch("scheduler.cancel_reminders", AsyncMock()):
            await bk.cb_remind_cancel(cb, bot)
        cb.answer.assert_called()

    async def test_remind_cancel_last_minute(self, db):
        import handlers.booking as bk, storage
        from datetime import datetime, timedelta
        setup_booking_config()
        await storage.init_db()
        # Booking within 2h from now
        from datetime import timezone
        now = datetime.now()
        soon = now + timedelta(minutes=30)
        booking_data = {
            **SAMPLE_BOOKING,
            "date": soon.strftime("%Y-%m-%d"),
            "time": soon.strftime("%H:%M"),
        }
        bid = await storage.save_booking(booking_data)
        cb = make_callback(data=f"remind_cancel:{bid}", user_id=111)
        bot = AsyncMock()
        with patch("scheduler.cancel_reminders", AsyncMock()):
            with patch("storage.get_waitlist_for_slot", AsyncMock(return_value=[])):
                await bk.cb_remind_cancel(cb, bot)
        bot.send_message.assert_called()

    async def test_remind_cancel_waitlist_notify(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"remind_cancel:{bid}", user_id=111)
        bot = AsyncMock()
        wl = [{"telegram_id": 999, "id": "wl1"}]
        with patch("scheduler.cancel_reminders", AsyncMock()):
            with patch("storage.get_waitlist_for_slot", AsyncMock(return_value=wl)):
                with patch("storage.update_waitlist_status", AsyncMock()):
                    await bk.cb_remind_cancel(cb, bot)
        bot.send_message.assert_called()

    async def test_remind_cancel_not_found(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="remind_cancel:nonexistent", user_id=111)
        cb.message.edit_text = AsyncMock(side_effect=Exception("fail"))
        cb.message.answer = AsyncMock()
        bot = AsyncMock()
        await bk.cb_remind_cancel(cb, bot)
        cb.answer.assert_called()


class TestReviewEdge:
    """Lines 898-900: bad rating text; 952: already reviewed."""

    async def test_review_rating_not_int(self):
        import handlers.booking as bk
        setup_booking_config()
        cb = make_callback(data="review:bid:abc", user_id=111)
        fsm = make_fsm()
        await bk.cb_review(cb, fsm)
        cb.answer.assert_called()

    async def test_review_comment_already_reviewed(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        msg = make_message(text="Nice!", user_id=111)
        fsm = make_fsm(data={"review_booking_id": bid, "review_rating": 5})
        with patch("storage.save_review", AsyncMock(return_value=False)):
            await bk.handle_review_comment(msg, fsm)
        msg.answer.assert_called()


class TestSkipCommentEdge:
    """Lines 977-989: skip_comment when already reviewed."""

    async def test_skip_comment_already_reviewed(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data="skip_comment", user_id=111)
        cb.message.edit_text = AsyncMock(side_effect=Exception("fail"))
        cb.message.answer = AsyncMock()
        fsm = make_fsm(data={"review_booking_id": bid, "review_rating": 4})
        with patch("storage.save_review", AsyncMock(return_value=False)):
            await bk.cb_skip_comment(cb, fsm)
        cb.answer.assert_called()
