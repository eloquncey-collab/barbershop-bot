
"""Extended booking handler tests."""
import pytest
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock, patch
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from helpers import make_message, make_callback, make_fsm, SAMPLE_BOOKING


# ==================================================================
# _get_next_dates -- no master (default work_days)
# ==================================================================
class TestGetNextDates:

    async def test_no_master_uses_default_workdays(self):
        from handlers.booking import _get_next_dates
        dates = await _get_next_dates(master_name="", count=5)
        assert isinstance(dates, list)
        assert len(dates) <= 5

    async def test_with_master_name(self, db):
        import storage
        from handlers.booking import _get_next_dates
        await storage.save_master("Alibek", "5 years", "fades")
        dates = await _get_next_dates(master_name="Alibek", count=5)
        assert isinstance(dates, list)


# ==================================================================
# _get_available_slots -- slot_locks exception path
# ==================================================================
class TestGetAvailableSlots:

    async def test_slot_locks_exception_is_ignored(self, db):
        from handlers.booking import _get_available_slots
        with patch("storage.get_locked_slots", side_effect=Exception("fail")):
            slots = await _get_available_slots(SAMPLE_BOOKING["date"], "Alibek")
        assert isinstance(slots, dict)

    async def test_booked_slots_exception_is_ignored(self, db):
        from handlers.booking import _get_available_slots
        with patch("storage.get_booked_slots", side_effect=Exception("fail")):
            slots = await _get_available_slots(SAMPLE_BOOKING["date"], "Alibek")
        assert isinstance(slots, dict)


# ==================================================================
# cb_start_booking -- has_active_booking, rate_limit, no phone
# ==================================================================
class TestCbStartBooking:

    async def test_has_active_booking_rejects(self, db):
        from handlers.booking import cb_book as cb_start_booking
        cb = make_callback(data="start_booking", user_id=SAMPLE_BOOKING["telegram_id"])
        cb.message.edit_text = AsyncMock()
        cb.message.answer = AsyncMock()
        state = make_fsm()
        with patch("storage.get_user", return_value={"telegram_id": 111}), \
             patch("storage.has_active_booking", return_value=True):
            await cb_start_booking(cb, state)
        cb.answer.assert_called()

    async def test_rate_limit_rejects(self, db):
        from handlers.booking import cb_book as cb_start_booking
        cb = make_callback(data="start_booking", user_id=SAMPLE_BOOKING["telegram_id"])
        cb.message.edit_text = AsyncMock()
        cb.message.answer = AsyncMock()
        state = make_fsm()
        with patch("storage.get_user", return_value={"telegram_id": 111}), \
             patch("storage.has_active_booking", return_value=False), \
             patch("storage.user_rate_limit_check", return_value=False):
            await cb_start_booking(cb, state)
        cb.answer.assert_called()

    async def test_success_proceeds_to_choose_master(self, db):
        from handlers.booking import cb_book as cb_start_booking
        cb = make_callback(data="start_booking", user_id=SAMPLE_BOOKING["telegram_id"])
        cb.message.edit_text = AsyncMock()
        cb.message.answer = AsyncMock()
        state = make_fsm()
        with patch("storage.get_user", return_value={"telegram_id": 111}), \
             patch("storage.has_active_booking", return_value=False), \
             patch("storage.user_rate_limit_check", return_value=True):
            await cb_start_booking(cb, state)
        state.set_state.assert_called()


# ==================================================================
# cb_choose_master -- invalid master, not found
# ==================================================================
class TestCbChooseMaster:

    async def test_invalid_master_index_rejected(self, db):
        from handlers.booking import cb_choose_master
        import config
        # Use an out-of-bounds index
        big_idx = len(config.MASTERS) + 100
        cb = make_callback(data=f"master:{big_idx}")
        state = make_fsm()
        await cb_choose_master(cb, state)
        cb.answer.assert_called()

    async def test_unknown_master_name_rejected(self, db):
        from handlers.booking import cb_choose_master
        cb = make_callback(data="master:UnknownMasterXYZ")
        state = make_fsm()
        await cb_choose_master(cb, state)
        cb.answer.assert_called()

    async def test_valid_master_by_name(self, db):
        from handlers.booking import cb_choose_master
        import config
        master = list(config.MASTERS.keys())[0]
        cb = make_callback(data=f"master:{master}")
        cb.message.edit_text = AsyncMock()
        cb.message.answer = AsyncMock()
        state = make_fsm()
        await cb_choose_master(cb, state)
        state.update_data.assert_called()

    async def test_valid_master_by_index(self, db):
        from handlers.booking import cb_choose_master
        import config
        cb = make_callback(data="master:0")
        cb.message.edit_text = AsyncMock()
        cb.message.answer = AsyncMock()
        state = make_fsm()
        await cb_choose_master(cb, state)
        state.update_data.assert_called()


# ==================================================================
# cb_choose_service -- invalid, not found
# ==================================================================
class TestCbChooseService:

    async def test_unknown_service_rejected(self, db):
        from handlers.booking import cb_choose_service
        cb = make_callback(data="service:UnknownServiceXYZ")
        state = make_fsm(data={"master": "Alibek"})
        await cb_choose_service(cb, state)
        cb.answer.assert_called()

    async def test_valid_service_by_index(self, db):
        from handlers.booking import cb_choose_service
        import config
        cb = make_callback(data="service:0")
        cb.message.edit_text = AsyncMock()
        cb.message.answer = AsyncMock()
        state = make_fsm(data={"master": list(config.MASTERS.keys())[0]})
        await cb_choose_service(cb, state)
        state.update_data.assert_called()


# ==================================================================
# cb_choose_date -- past date, too far ahead, no free slots
# ==================================================================
class TestCbChooseDate:

    async def test_invalid_date_format_rejected(self):
        from handlers.booking import cb_choose_date
        cb = make_callback(data="date:notadate")
        state = make_fsm()
        await cb_choose_date(cb, state)
        cb.answer.assert_called()

    async def test_past_date_rejected(self):
        from handlers.booking import cb_choose_date
        cb = make_callback(data="date:2020-01-01")
        state = make_fsm()
        await cb_choose_date(cb, state)
        cb.answer.assert_called()

    async def test_too_far_future_rejected(self):
        from handlers.booking import cb_choose_date
        from datetime import date, timedelta
        far_future = (date.today() + timedelta(days=90)).isoformat()
        cb = make_callback(data=f"date:{far_future}")
        state = make_fsm()
        await cb_choose_date(cb, state)
        cb.answer.assert_called()

    async def test_fully_booked_day_rejected(self, db):
        from handlers.booking import cb_choose_date
        from datetime import date, timedelta
        future = (date.today() + timedelta(days=3)).isoformat()
        cb = make_callback(data=f"date:{future}")
        state = make_fsm(data={"master": "Alibek"})
        with patch("handlers.booking._get_available_slots",
                   return_value={"10:00": "busy", "10:30": "busy"}):
            await cb_choose_date(cb, state)
        cb.answer.assert_called()
