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


class TestCbBook:

    async def test_user_no_phone(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="book", user_id=222)
        fsm = make_fsm()
        with patch("storage.get_user", AsyncMock(return_value=None)):
            await bk.cb_book(cb, fsm)
        cb.answer.assert_called()

    async def test_user_has_active_booking(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="book", user_id=111)
        fsm = make_fsm()
        with patch("storage.get_user", AsyncMock(return_value={"phone": "+7700"})):
            with patch("storage.has_active_booking", AsyncMock(return_value=True)):
                await bk.cb_book(cb, fsm)
        cb.answer.assert_called()

    async def test_rate_limited(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="book", user_id=111)
        fsm = make_fsm()
        with patch("storage.get_user", AsyncMock(return_value={"phone": "+7700"})):
            with patch("storage.has_active_booking", AsyncMock(return_value=False)):
                with patch("storage.user_rate_limit_check", AsyncMock(return_value=False)):
                    await bk.cb_book(cb, fsm)
        cb.answer.assert_called()

    async def test_book_success(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="book", user_id=111)
        fsm = make_fsm()
        with patch("storage.get_user", AsyncMock(return_value={"phone": "+7700"})):
            with patch("storage.has_active_booking", AsyncMock(return_value=False)):
                with patch("storage.user_rate_limit_check", AsyncMock(return_value=True)):
                    await bk.cb_book(cb, fsm)
        fsm.set_state.assert_called()

class TestCbChooseMaster:

    async def test_master_not_found(self):
        import handlers.booking as bk
        setup_booking_config()
        cb = make_callback(data="master:NotExist", user_id=111)
        fsm = make_fsm()
        await bk.cb_choose_master(cb, fsm)
        cb.answer.assert_called()

    async def test_master_found_by_name(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="master:Alibek", user_id=111)
        fsm = make_fsm()
        with patch("keyboards.services_kb", AsyncMock(return_value=MagicMock())):
            await bk.cb_choose_master(cb, fsm)
        fsm.set_state.assert_called()


class TestCbChooseService:

    async def test_service_not_found(self):
        import handlers.booking as bk
        setup_booking_config()
        cb = make_callback(data="service:NotExist", user_id=111)
        fsm = make_fsm(data={"master": "Alibek"})
        await bk.cb_choose_service(cb, fsm)
        cb.answer.assert_called()

    async def test_service_found(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="service:Haircut", user_id=111)
        fsm = make_fsm(data={"master": "Alibek"})
        with patch("storage.get_effective_price", AsyncMock(return_value=3000)):
            with patch("storage.get_master_work_days", AsyncMock(return_value=[1,2,3,4,5,6])):
                await bk.cb_choose_service(cb, fsm)
        fsm.set_state.assert_called()


class TestCbChooseDate:

    async def test_expired_session(self):
        import handlers.booking as bk
        setup_booking_config()
        cb = make_callback(data="date:2026-12-01", user_id=111)
        fsm = make_fsm(state="SomeOtherState")
        await bk.cb_choose_date(cb, fsm)
        cb.answer.assert_called()

    async def test_past_date(self):
        import handlers.booking as bk
        from handlers.booking import BookingStates
        setup_booking_config()
        cb = make_callback(data="date:2020-01-01", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_date.state)
        await bk.cb_choose_date(cb, fsm)
        cb.answer.assert_called()

    async def test_too_far_date(self):
        import handlers.booking as bk
        from handlers.booking import BookingStates
        from datetime import datetime, timedelta
        setup_booking_config()
        future = (datetime.now() + timedelta(days=61)).strftime("%Y-%m-%d")
        cb = make_callback(data=f"date:{future}", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_date.state)
        await bk.cb_choose_date(cb, fsm)
        cb.answer.assert_called()

    async def test_no_free_slots(self, db):
        import handlers.booking as bk, storage
        from handlers.booking import BookingStates
        from datetime import datetime, timedelta
        setup_booking_config()
        await storage.init_db()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        cb = make_callback(data=f"date:{tomorrow}", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_date.state, data={"master": "Alibek"})
        with patch("handlers.booking._get_available_slots", AsyncMock(return_value={"10:00": "busy"})):
            await bk.cb_choose_date(cb, fsm)
        cb.answer.assert_called()

class TestHandleEnterName:

    async def test_empty_name(self):
        import handlers.booking as bk
        setup_booking_config()
        msg = make_message(text="", user_id=111)
        fsm = make_fsm()
        await bk.handle_enter_name(msg, fsm)
        msg.answer.assert_called()

    async def test_invalid_chars(self):
        import handlers.booking as bk
        setup_booking_config()
        msg = make_message(text="123", user_id=111)
        fsm = make_fsm()
        await bk.handle_enter_name(msg, fsm)
        msg.answer.assert_called()

    async def test_no_letters(self):
        import handlers.booking as bk
        setup_booking_config()
        msg = make_message(text="---", user_id=111)
        fsm = make_fsm()
        await bk.handle_enter_name(msg, fsm)
        msg.answer.assert_called()

    async def test_name_too_long(self):
        import handlers.booking as bk
        setup_booking_config()
        msg = make_message(text="A" * 51, user_id=111)
        fsm = make_fsm()
        await bk.handle_enter_name(msg, fsm)
        msg.answer.assert_called()

    async def test_slot_busy_on_save(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        msg = make_message(text="John", user_id=111)
        fsm = make_fsm(data={"date": "2026-12-10", "time": "10:00", "master": "Alibek",
                             "service": "Haircut", "price": 3000})
        with patch("storage.save_booking", AsyncMock(return_value=None)):
            with patch("storage.release_slot_lock", AsyncMock()):
                await bk.handle_enter_name(msg, fsm)

    async def test_save_exception(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        msg = make_message(text="John", user_id=111)
        fsm = make_fsm(data={"date": "2026-12-10", "time": "10:00", "master": "Alibek",
                             "service": "Haircut", "price": 3000})
        with patch("storage.save_booking", side_effect=Exception("db fail")):
            await bk.handle_enter_name(msg, fsm)
        msg.answer.assert_called()


class TestRemindCallbacks:

    async def test_remind_confirm(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"remind_confirm:{bid}", user_id=111)
        bot = AsyncMock()
        with patch("config.ADMIN_IDS", {100}):
            await bk.cb_remind_confirm(cb, bot)
        cb.answer.assert_called()

    async def test_remind_cancel_found(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"remind_cancel:{bid}", user_id=111)
        bot = AsyncMock()
        with patch("scheduler.cancel_reminders", AsyncMock()):
            await bk.cb_remind_cancel(cb, bot)
        cb.answer.assert_called()

    async def test_remind_cancel_not_found(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="remind_cancel:nonexistent", user_id=111)
        bot = AsyncMock()
        await bk.cb_remind_cancel(cb, bot)
        cb.answer.assert_called()

class TestReviewCallbacks:

    async def test_review_invalid_rating(self):
        import handlers.booking as bk
        setup_booking_config()
        cb = make_callback(data="review:bid:6", user_id=111)
        fsm = make_fsm()
        await bk.cb_review(cb, fsm)
        cb.answer.assert_called()

    async def test_review_valid(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"review:{bid}:5", user_id=111)
        fsm = make_fsm()
        await bk.cb_review(cb, fsm)
        fsm.set_state.assert_called()

    async def test_review_bad_format(self):
        import handlers.booking as bk
        setup_booking_config()
        cb = make_callback(data="review:only_two_parts", user_id=111)
        fsm = make_fsm()
        await bk.cb_review(cb, fsm)
        cb.answer.assert_called()

    async def test_skip_comment(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data="skip_comment", user_id=111)
        fsm = make_fsm(data={"review_booking_id": bid, "review_rating": 4})
        with patch("storage.save_review", AsyncMock(return_value=True)):
            await bk.cb_skip_comment(cb, fsm)
        cb.answer.assert_called()

    async def test_skip_comment_no_data(self):
        import handlers.booking as bk
        setup_booking_config()
        cb = make_callback(data="skip_comment", user_id=111)
        fsm = make_fsm(data={})
        await bk.cb_skip_comment(cb, fsm)
        cb.answer.assert_called()

    async def test_handle_review_comment_empty(self):
        import handlers.booking as bk
        setup_booking_config()
        msg = make_message(text="", user_id=111)
        fsm = make_fsm(data={"review_booking_id": "bid", "review_rating": 5})
        await bk.handle_review_comment(msg, fsm)
        msg.answer.assert_called()

    async def test_handle_review_comment_too_long(self):
        import handlers.booking as bk
        setup_booking_config()
        msg = make_message(text="A" * 501, user_id=111)
        fsm = make_fsm(data={"review_booking_id": "bid", "review_rating": 5})
        await bk.handle_review_comment(msg, fsm)
        msg.answer.assert_called()

    async def test_handle_review_comment_no_booking_id(self):
        import handlers.booking as bk
        setup_booking_config()
        msg = make_message(text="Great service!", user_id=111)
        fsm = make_fsm(data={})
        await bk.handle_review_comment(msg, fsm)
        msg.answer.assert_called()

    async def test_handle_review_comment_saved(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        msg = make_message(text="Great service!", user_id=111)
        fsm = make_fsm(data={"review_booking_id": bid, "review_rating": 5})
        with patch("storage.save_review", AsyncMock(return_value=True)):
            await bk.handle_review_comment(msg, fsm)
        msg.answer.assert_called()


class TestNavigationCallbacks:

    async def test_back_to_master(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="back_to_master", user_id=111)
        fsm = make_fsm(data={"date": "2026-12-10", "time": "10:00", "master": "Alibek"})
        with patch("storage.release_slot_lock", AsyncMock()):
            await bk.cb_back_to_master(cb, fsm)
        cb.answer.assert_called()

    async def test_back_to_service(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="back_to_service", user_id=111)
        fsm = make_fsm(data={"master": "Alibek"})
        with patch("keyboards.services_kb", AsyncMock(return_value=MagicMock())):
            await bk.cb_back_to_service(cb, fsm)
        cb.answer.assert_called()

    async def test_back_to_date(self, db):
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

    async def test_no_slots_callback(self):
        import handlers.booking as bk
        setup_booking_config()
        cb = make_callback(data="no_slots", user_id=111)
        await bk.cb_no_slots(cb)
        cb.answer.assert_called()

    async def test_cancel_booking_with_slot_lock(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="cancel_booking", user_id=111)
        fsm = make_fsm(data={"date": "2026-12-10", "time": "10:00", "master": "Alibek"})
        with patch("storage.release_slot_lock", AsyncMock()):
            await bk.cb_cancel_booking(cb, fsm)
        cb.answer.assert_called()

    async def test_go_to_waitlist_no_busy(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="go_to_waitlist", user_id=111)
        fsm = make_fsm(data={"date": "2026-12-10", "master": "Alibek"})
        with patch("handlers.booking._get_available_slots", AsyncMock(return_value={"10:00": "free"})):
            await bk.cb_go_to_waitlist(cb, fsm)
        cb.answer.assert_called()

    async def test_go_to_waitlist_with_busy(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="go_to_waitlist", user_id=111)
        fsm = make_fsm(data={"date": "2026-12-10", "master": "Alibek"})
        with patch("handlers.booking._get_available_slots", AsyncMock(return_value={"10:00": "busy"})):
            await bk.cb_go_to_waitlist(cb, fsm)
        cb.answer.assert_called()

class TestWaitlist:

    async def test_waitlist_already_in(self, db):
        import handlers.booking as bk, storage
        from handlers.booking import BookingStates
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="waitlist:10:00", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_time.state,
                        data={"date": "2026-12-10", "master": "Alibek", "service": "Haircut"})
        existing = [{"telegram_id": 111, "status": "waiting"}]
        with patch("storage.get_waitlist_for_slot", AsyncMock(return_value=existing)):
            await bk.cb_waitlist(cb, fsm)
        cb.answer.assert_called()

    async def test_waitlist_limit_exceeded(self, db):
        import handlers.booking as bk, storage
        from handlers.booking import BookingStates
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="waitlist:10:00", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_time.state,
                        data={"date": "2026-12-10", "master": "Alibek", "service": "Haircut"})
        with patch("storage.get_waitlist_for_slot", AsyncMock(return_value=[])):
            with patch("storage.get_user_waitlist_count", AsyncMock(return_value=5)):
                await bk.cb_waitlist(cb, fsm)
        cb.answer.assert_called()

    async def test_waitlist_success(self, db):
        import handlers.booking as bk, storage
        from handlers.booking import BookingStates
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="waitlist:10:00", user_id=111)
        fsm = make_fsm(state=BookingStates.choose_time.state,
                        data={"date": "2026-12-10", "master": "Alibek", "service": "Haircut"})
        with patch("storage.get_waitlist_for_slot", AsyncMock(return_value=[])):
            with patch("storage.get_user_waitlist_count", AsyncMock(return_value=0)):
                with patch("storage.add_to_waitlist", AsyncMock()):
                    await bk.cb_waitlist(cb, fsm)
        cb.answer.assert_called()


class TestUseTgName:

    async def test_use_tg_name_no_name(self):
        import handlers.booking as bk
        setup_booking_config()
        cb = make_callback(data="use_tg_name", user_id=111)
        fsm = make_fsm(data={"tg_name_suggestion": ""})
        await bk.cb_use_tg_name(cb, fsm)
        cb.answer.assert_called()

    async def test_use_tg_name_slot_busy(self, db):
        import handlers.booking as bk, storage
        setup_booking_config()
        await storage.init_db()
        cb = make_callback(data="use_tg_name", user_id=111)
        fsm = make_fsm(data={"tg_name_suggestion": "John",
                             "date": "2026-12-10", "time": "10:00",
                             "master": "Alibek", "service": "Haircut", "price": 3000})
        with patch("storage.save_booking", AsyncMock(return_value=None)):
            with patch("storage.release_slot_lock", AsyncMock()):
                await bk.cb_use_tg_name(cb, fsm)
        cb.answer.assert_called()
