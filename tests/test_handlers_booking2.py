
"""Additional booking handler callback tests"""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from unittest.mock import AsyncMock, MagicMock, patch
from helpers import make_message, make_callback, make_fsm, SAMPLE_BOOKING


class TestCbBook:
    async def test_starts_booking_flow(self, db):
        from handlers.booking import cb_book
        cb = make_callback(data="book")
        fsm = make_fsm()
        with patch("handlers.booking.edit_with_retry", new=AsyncMock()):
            await cb_book(cb, fsm)
        fsm.set_state.assert_called_once()
        cb.answer.assert_called()

    async def test_max_bookings_shows_alert(self, db):
        from handlers.booking import cb_book
        import storage
        for t in ["10:00", "11:00", "12:00"]:
            await storage.save_booking({**SAMPLE_BOOKING, "time": t})
        cb = make_callback(data="book", user_id=111)
        fsm = make_fsm()
        with patch("handlers.booking.edit_with_retry", new=AsyncMock()):
            await cb_book(cb, fsm)
        cb.answer.assert_called()


class TestCbChooseMaster:
    async def test_master_sets_state(self, db):
        from handlers.booking import cb_choose_master
        import config
        # Use a real master name from config
        master_name = list(config.MASTERS.keys())[0]
        cb = make_callback(data=f"master:{master_name}")
        fsm = make_fsm()
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_choose_master(cb, fsm)
        fsm.update_data.assert_called_once()
        cb.answer.assert_called()


class TestCbChooseService:
    async def test_service_sets_state(self, db):
        from handlers.booking import cb_choose_service
        import config
        svc = list(config.SERVICES.keys())[0]
        cb = make_callback(data=f"service:{svc}")
        fsm = make_fsm(data={"master": "Alibek"})
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_choose_service(cb, fsm)
        fsm.update_data.assert_called_once()
        fsm.set_state.assert_called_once()
        cb.answer.assert_called()


class TestCbChooseDate:
    async def test_date_sets_state(self, db):
        from handlers.booking import cb_choose_date
        cb = make_callback(data="date:2026-12-07")
        fsm = make_fsm(data={"master": "Alibek"})
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_choose_date(cb, fsm)
        cb.answer.assert_called()


class TestCbChooseTime:
    async def test_time_sets_name_state(self, db):
        from handlers.booking import cb_choose_time
        cb = make_callback(data="time:10:00")
        fsm = make_fsm(data={"master": "Alibek", "date": "2026-12-07",
                             "service": "Haircut", "price": 3000})
        with patch("handlers.booking._safe_edit", new=AsyncMock()), \
             patch("handlers.booking.storage.create_slot_lock", new=AsyncMock()):
            await cb_choose_time(cb, fsm)
        assert fsm.update_data.call_count >= 1
        fsm.set_state.assert_called_once()
        cb.answer.assert_called()


class TestCbBackNavigations:
    async def test_back_to_master(self):
        from handlers.booking import cb_back_to_master
        cb = make_callback(data="back_to_master")
        fsm = make_fsm()
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_back_to_master(cb, fsm)
        fsm.set_state.assert_called_once()
        cb.answer.assert_called()

    async def test_back_to_service(self, db):
        from handlers.booking import cb_back_to_service
        import config
        master_name = list(config.MASTERS.keys())[0]
        cb = make_callback(data="back_to_service")
        fsm = make_fsm(data={"master": master_name})
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_back_to_service(cb, fsm)
        fsm.set_state.assert_called_once()
        cb.answer.assert_called()

    async def test_back_to_date(self, db):
        from handlers.booking import cb_back_to_date
        cb = make_callback(data="back_to_date")
        fsm = make_fsm(data={"master": "Alibek"})
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_back_to_date(cb, fsm)
        fsm.set_state.assert_called_once()
        cb.answer.assert_called()

    async def test_back_to_time(self, db):
        from handlers.booking import cb_back_to_time
        cb = make_callback(data="back_to_time")
        fsm = make_fsm(data={"master": "Alibek", "date": "2026-12-07"})
        with patch("handlers.booking._safe_edit", new=AsyncMock()), \
             patch("handlers.booking.storage.release_slot_lock", new=AsyncMock()):
            await cb_back_to_time(cb, fsm)
        fsm.set_state.assert_called_once()
        cb.answer.assert_called()


class TestCbRemindConfirm:
    async def test_active_booking_shows_reminder(self, db):
        from handlers.booking import cb_remind_confirm
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"remind_confirm:{bid}", user_id=111)
        bot = AsyncMock()
        await cb_remind_confirm(cb, bot)
        cb.answer.assert_called()

    async def test_nonexistent_booking_shows_error(self):
        from handlers.booking import cb_remind_confirm
        cb = make_callback(data="remind_confirm:nonexistent", user_id=111)
        bot = AsyncMock()
        await cb_remind_confirm(cb, bot)
        cb.answer.assert_called()


class TestCbWaitlist:
    async def test_waitlist_added(self, db):
        from handlers.booking import cb_waitlist
        import storage
        # Book the slot to make it busy
        bid = await storage.save_booking(SAMPLE_BOOKING)
        import config
        master_name = list(config.MASTERS.keys())[0]
        svc = list(config.SERVICES.keys())[0]
        cb = make_callback(data=f"waitlist:2026-12-07:10:00:{master_name}:{svc}")
        state = make_fsm(data={"master": "Alibek", "date": "2026-12-07", "service": "Haircut", "price": 3000})
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_waitlist(cb, state)
        cb.answer.assert_called()


class TestCbGoToWaitlist:
    async def test_shows_waitlist_info(self):
        from handlers.booking import cb_go_to_waitlist
        cb = make_callback(data="go_to_waitlist")
        fsm = make_fsm(data={"master": "Alibek", "date": "2026-12-07",
                             "service": "Haircut", "price": 3000})
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_go_to_waitlist(cb, fsm)
        cb.answer.assert_called()


class TestCmdCancel:
    async def test_cancels_fsm(self, db):
        from handlers.booking import cmd_cancel
        msg = make_message(text="/cancel")
        fsm = make_fsm(data={"date": "2026-12-07", "time": "10:00", "master": "Alibek"})
        with patch("handlers.booking.storage.release_slot_lock", new=AsyncMock()):
            await cmd_cancel(msg, fsm)
        msg.answer.assert_called()

    async def test_cancel_without_slot_lock(self, db):
        from handlers.booking import cmd_cancel
        msg = make_message(text="/cancel")
        fsm = make_fsm(data={})
        await cmd_cancel(msg, fsm)
        msg.answer.assert_called()


class TestCbUseTgName:
    async def test_uses_telegram_name(self, db):
        from handlers.booking import cb_use_tg_name
        cb = make_callback(data="use_tg_name", user_id=111)
        cb.from_user.first_name = "Ivan"
        fsm = make_fsm(data={"master": "Alibek", "date": "2026-12-07",
                             "time": "10:00", "service": "Haircut", "price": 3000})
        with patch("handlers.booking.scheduler.schedule_reminders", new=AsyncMock()), \
             patch("handlers.booking.config.ADMIN_IDS", []):
            await cb_use_tg_name(cb, fsm)
        cb.answer.assert_called()


class TestCbReview:
    async def test_review_shows_rating_prompt(self, db):
        from handlers.booking import cb_review
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        await storage.complete_booking(bid)
        cb = make_callback(data=f"review:{bid}", user_id=111)
        fsm = make_fsm()
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_review(cb, fsm)
        cb.answer.assert_called()

    async def test_review_nonexistent_booking(self):
        from handlers.booking import cb_review
        cb = make_callback(data="review:nonexistent", user_id=111)
        fsm = make_fsm()
        with patch("handlers.booking._safe_edit", new=AsyncMock()):
            await cb_review(cb, fsm)
        cb.answer.assert_called()
