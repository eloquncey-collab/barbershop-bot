
"""More admin handler tests to boost coverage"""
import pytest
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from unittest.mock import AsyncMock, MagicMock, patch
from helpers import make_message, make_callback, make_fsm, SAMPLE_BOOKING


def setup_admin(user_id=777):
    import config
    config.ADMIN_IDS = [user_id]
    return user_id


class TestCbAdminBookingsPages:
    async def test_first_page(self, db):
        admin_id = setup_admin()
        import storage
        for i in range(5):
            await storage.save_booking({**SAMPLE_BOOKING, "time": f"1{i}:00"})
        from handlers.admin import cb_admin_bookings
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_bookings(cb)
        cb.answer.assert_called()

    async def test_bookings_page_navigation(self, db):
        admin_id = setup_admin()
        import storage
        for i in range(15):
            await storage.save_booking({**SAMPLE_BOOKING, "time": f"10:{i:02d}"})
        from handlers.admin import cb_admin_bookings_page
        cb = make_callback(data="admin_bookings_page:1", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_bookings_page(cb)
        cb.answer.assert_called()


class TestCbAdminManageBooking:
    async def test_shows_booking_detail(self, db):
        admin_id = setup_admin()
        import storage
        bid = await storage.save_booking(SAMPLE_BOOKING)
        from handlers.admin import cb_admin_manage_booking
        cb = make_callback(data=f"admin_manage:{bid}", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_manage_booking(cb)
        cb.answer.assert_called()

    async def test_nonexistent_booking(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_manage_booking
        cb = make_callback(data="admin_manage:nope", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_manage_booking(cb)
        cb.answer.assert_called()


class TestCbAdminMasterDetail:
    async def test_shows_master_detail(self, db):
        admin_id = setup_admin()
        import config
        master_name = list(config.MASTERS.keys())[0]
        from handlers.admin import cb_admin_master_detail
        cb = make_callback(data=f"admin_master_detail:{master_name}", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_master_detail(cb)
        cb.answer.assert_called()

    async def test_nonexistent_master(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_master_detail
        cb = make_callback(data="admin_master_detail:Unknown", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_master_detail(cb)
        cb.answer.assert_called()


class TestCbAdminRemoveMaster:
    async def test_removes_existing_master(self, db):
        admin_id = setup_admin()
        import config
        master_name = list(config.MASTERS.keys())[0]
        from handlers.admin import cb_admin_remove_master
        cb = make_callback(data=f"admin_remove_master:{master_name}", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_remove_master(cb)
        cb.answer.assert_called()

    async def test_non_admin_blocked(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin_remove_master
        cb = make_callback(data="admin_remove_master:any", user_id=999)
        await cb_admin_remove_master(cb)
        cb.answer.assert_called()


class TestCbAdminServiceDetail:
    async def test_shows_service_detail(self, db):
        admin_id = setup_admin()
        import config
        svc = list(config.SERVICES.keys())[0]
        from handlers.admin import cb_admin_service_detail
        cb = make_callback(data=f"admin_service_detail:{svc}", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_service_detail(cb)
        cb.answer.assert_called()


class TestCbAdminAddService:
    async def test_starts_add_service_flow(self):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_add_service
        cb = make_callback(user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_add_service(cb, state)
        state.set_state.assert_called_once()
        cb.answer.assert_called()

    async def test_non_admin_blocked(self):
        import config
        config.ADMIN_IDS = []
        from handlers.admin import cb_admin_add_service
        cb = make_callback(user_id=999)
        state = make_fsm()
        await cb_admin_add_service(cb, state)
        state.set_state.assert_not_called()


class TestCbAdminConfirmRemoveService:
    async def test_removes_service(self, db):
        admin_id = setup_admin()
        import config, storage
        svc = list(config.SERVICES.keys())[0]
        await storage.save_service(svc, config.SERVICES[svc])
        from handlers.admin import cb_admin_confirm_remove_service
        cb = make_callback(data=f"admin_confirm_remove_service:{svc}", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_confirm_remove_service(cb)
        cb.answer.assert_called()


class TestCbAdminChangeAddress:
    async def test_starts_change_address(self):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_change_address
        cb = make_callback(user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_change_address(cb, state)
        state.set_state.assert_called_once()
        cb.answer.assert_called()


class TestCbAdminChangePhone:
    async def test_starts_change_phone(self):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_change_phone
        cb = make_callback(user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_change_phone(cb, state)
        state.set_state.assert_called_once()
        cb.answer.assert_called()


class TestCbAdminChangeHours:
    async def test_starts_change_hours(self):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_change_hours
        cb = make_callback(user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_change_hours(cb, state)
        state.set_state.assert_called_once()
        cb.answer.assert_called()


class TestHandleChangeAddress:
    async def test_valid_address_saved(self, db):
        admin_id = setup_admin()
        from handlers.admin import handle_change_address
        msg = make_message(text="New Street 123", user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_change_address(msg, state)
        state.clear.assert_called_once()

    async def test_empty_address_rejected(self):
        admin_id = setup_admin()
        from handlers.admin import handle_change_address
        msg = make_message(text="  ", user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_change_address(msg, state)
        state.clear.assert_not_called()


class TestHandleChangePhone:
    async def test_valid_phone_saved(self, db):
        admin_id = setup_admin()
        from handlers.admin import handle_change_phone
        msg = make_message(text="+77001234567", user_id=admin_id)
        state = make_fsm()
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_change_phone(msg, state)
        state.clear.assert_called_once()


class TestCbAdminReferrals:
    async def test_shows_referrals(self, db):
        admin_id = setup_admin()
        import storage
        await storage.add_referral(111, 222)
        from handlers.admin import cb_admin_referrals
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_referrals(cb)
        cb.answer.assert_called()

    async def test_empty_referrals(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_referrals
        cb = make_callback(user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_referrals(cb)
        cb.answer.assert_called()


class TestCbAdminReviewsPage:
    async def test_navigates_reviews_pages(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_reviews_page
        cb = make_callback(data="admin_reviews_page:0", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_reviews_page(cb)
        cb.answer.assert_called()


class TestCbAdminWaitlistPage:
    async def test_navigates_waitlist_pages(self, db):
        admin_id = setup_admin()
        from handlers.admin import cb_admin_waitlist_page
        cb = make_callback(data="admin_waitlist_page:0", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_admin_waitlist_page(cb)
        cb.answer.assert_called()


class TestCbMasterSchedule:
    async def test_shows_master_schedule(self, db):
        admin_id = setup_admin()
        import config
        master_name = list(config.MASTERS.keys())[0]
        from handlers.admin import cb_master_schedule
        cb = make_callback(data=f"master_schedule:{master_name}", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_master_schedule(cb, make_fsm())
        cb.answer.assert_called()


class TestCbMasterServices:
    async def test_shows_master_services(self, db):
        admin_id = setup_admin()
        import config
        master_name = list(config.MASTERS.keys())[0]
        from handlers.admin import cb_master_services
        cb = make_callback(data=f"master_services:{master_name}", user_id=admin_id)
        with patch("handlers.admin.edit_with_retry", new=AsyncMock()):
            await cb_master_services(cb, make_fsm())
        cb.answer.assert_called()


class TestCbNoop:
    async def test_answers_empty(self):
        from handlers.admin import cb_noop
        cb = make_callback(data="noop")
        await cb_noop(cb)
        cb.answer.assert_called_once_with()


class TestHandleSetMasterTg:
    async def test_valid_id_saved(self, db):
        admin_id = setup_admin()
        import config
        master_name = list(config.MASTERS.keys())[0]
        from handlers.admin import handle_set_master_tg
        msg = make_message(text="123456789", user_id=admin_id)
        state = make_fsm(data={"master_name": master_name})
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_set_master_tg(msg, state)
        state.clear.assert_called_once()

    async def test_invalid_id_rejected(self):
        admin_id = setup_admin()
        from handlers.admin import handle_set_master_tg
        msg = make_message(text="not_a_number", user_id=admin_id)
        state = make_fsm(data={"master_name": "Alibek"})
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_set_master_tg(msg, state)
        state.clear.assert_not_called()


class TestHandleEditMaster:
    async def test_valid_edit_saves(self, db):
        admin_id = setup_admin()
        import config
        master_name = list(config.MASTERS.keys())[0]
        from handlers.admin import handle_edit_master
        msg = make_message(text="New, 6 years, new spec", user_id=admin_id)
        state = make_fsm(data={"master_name": master_name})
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_edit_master(msg, state)
        state.clear.assert_called_once()

    async def test_invalid_format_rejected(self):
        admin_id = setup_admin()
        from handlers.admin import handle_edit_master
        msg = make_message(text="onlyone", user_id=admin_id)
        state = make_fsm(data={"master_name": "Alibek"})
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_edit_master(msg, state)
        state.clear.assert_not_called()


class TestHandleEditService:
    async def test_valid_edit_saves(self, db):
        admin_id = setup_admin()
        import config
        svc = list(config.SERVICES.keys())[0]
        from handlers.admin import handle_edit_service
        msg = make_message(text="4000", user_id=admin_id)
        state = make_fsm(data={"service_name": svc})
        with patch("handlers.admin.send_with_retry", new=AsyncMock()) as mock_s:
            await handle_edit_service(msg, state)
        mock_s.assert_called()  # at least sends a reply

    async def test_invalid_price_rejected(self):
        admin_id = setup_admin()
        from handlers.admin import handle_edit_service
        msg = make_message(text="abc", user_id=admin_id)
        state = make_fsm(data={"service_name": "Haircut"})
        with patch("handlers.admin.send_with_retry", new=AsyncMock()):
            await handle_edit_service(msg, state)
        state.clear.assert_not_called()
