import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.helpers import make_callback, make_message, make_fsm, SAMPLE_BOOKING


def setup_admin(admin_id=100):
    import config
    config.ADMIN_IDS = [admin_id]
    config.MASTERS = {"Alibek": {"experience": "5 years", "specialization": "cuts"}}
    config.SERVICES = {"Haircut": 3000, "Beard": 2000}
    config.MASTER_IDS = {}
    config.LOYALTY_VISIT_INTERVAL = 5
    config.LOYALTY_DISCOUNT_PERCENT = 10
    return admin_id


class TestAdminCancelMasterNotify:
    async def test_cancel_with_master_notify(self, db):
        import handlers.admin as adm, storage, config
        admin_id = setup_admin()
        config.MASTER_IDS = {"Alibek": 9999}
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data="admin_cancel_booking:" + bid, user_id=admin_id)
        with patch("utils.send_with_retry", AsyncMock()), patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_admin_cancel_booking(cb, cb.bot)
        cb.answer.assert_called()

    async def test_cancel_not_found(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_cancel_booking:nonexistent", user_id=admin_id)
        await adm.cb_admin_cancel_booking(cb, cb.bot)
        cb.answer.assert_called()

    async def test_cancel_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_cancel_booking:x", user_id=admin_id)
        with patch("storage.admin_cancel_booking", side_effect=Exception("fail")):
            await adm.cb_admin_cancel_booking(cb, cb.bot)
        cb.answer.assert_called()


class TestAdminCompleteExtras:
    async def test_complete_loyalty_reward(self, db):
        import handlers.admin as adm, storage, config
        admin_id = setup_admin()
        config.LOYALTY_VISIT_INTERVAL = 1
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data="admin_complete_booking:" + bid, user_id=admin_id)
        with patch("utils.edit_with_retry", AsyncMock()), patch("scheduler.cancel_reminders", AsyncMock()):
            await adm.cb_admin_complete_booking(cb, cb.bot)
        cb.bot.send_message.assert_called()

    async def test_complete_master_notify(self, db):
        import handlers.admin as adm, storage, config
        admin_id = setup_admin()
        config.MASTER_IDS = {"Alibek": 7777}
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data="admin_complete_booking:" + bid, user_id=admin_id)
        with patch("utils.edit_with_retry", AsyncMock()), patch("scheduler.cancel_reminders", AsyncMock()):
            await adm.cb_admin_complete_booking(cb, cb.bot)
        cb.bot.send_message.assert_called()

    async def test_complete_not_found(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_complete_booking:nonexistent", user_id=admin_id)
        await adm.cb_admin_complete_booking(cb, cb.bot)
        cb.answer.assert_called()

    async def test_complete_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_complete_booking:x", user_id=admin_id)
        with patch("storage.admin_complete_booking", side_effect=Exception("fail")):
            await adm.cb_admin_complete_booking(cb, cb.bot)
        cb.answer.assert_called()


class TestAdminWaitlist:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_waitlist", user_id=555)
        await adm.cb_admin_waitlist(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_page_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_waitlist_page:0", user_id=555)
        await adm.cb_admin_waitlist_page(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_page_bad_offset(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_waitlist_page:bad", user_id=admin_id)
        with patch("storage.get_all_waitlist", AsyncMock(return_value=[])):
            await adm.cb_admin_waitlist_page(cb)
        cb.answer.assert_called()

    async def test_with_data(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        wl = [{"name": "Ivan", "date": "2026-12-01", "time": "10:00", "master": "Alibek", "service": "Haircut", "status": "waiting"}]
        cb = make_callback(data="admin_waitlist", user_id=admin_id)
        with patch("storage.get_all_waitlist", AsyncMock(return_value=wl)), patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_admin_waitlist(cb)
        cb.answer.assert_called()


class TestAdminReviews:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_reviews", user_id=555)
        await adm.cb_admin_reviews(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_page_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_reviews_page:0", user_id=555)
        await adm.cb_admin_reviews_page(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_page_bad_offset(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_reviews_page:bad", user_id=admin_id)
        with patch("storage.get_reviews", AsyncMock(return_value=[])):
            await adm.cb_admin_reviews_page(cb)
        cb.answer.assert_called()

    async def test_with_data(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        rev = [{"booking_id": "abc", "rating": 5, "comment": "Great!", "created_at": "2026-12-01T10:00:00"}]
        cb = make_callback(data="admin_reviews", user_id=admin_id)
        with patch("storage.get_reviews", AsyncMock(return_value=rev)), patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_admin_reviews(cb)
        cb.answer.assert_called()


class TestToggleDay:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="toggle_day:1", user_id=555)
        fsm = make_fsm(data={"work_days": [1], "master_name": "Alibek"})
        await adm.cb_toggle_day(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_add_day(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="toggle_day:3", user_id=admin_id)
        fsm = make_fsm(data={"work_days": [1, 2], "master_name": "Alibek"})
        with patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_toggle_day(cb, fsm)
        fsm.update_data.assert_called()

    async def test_remove_day(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="toggle_day:1", user_id=admin_id)
        fsm = make_fsm(data={"work_days": [1, 2], "master_name": "Alibek"})
        with patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_toggle_day(cb, fsm)
        fsm.update_data.assert_called()

    async def test_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="toggle_day:1", user_id=admin_id)
        fsm = make_fsm()
        fsm.get_data = AsyncMock(side_effect=Exception("fail"))
        await adm.cb_toggle_day(cb, fsm)
        cb.answer.assert_called()


class TestSaveMasterDays:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="save_master_days", user_id=555)
        await adm.cb_save_master_days(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_no_days(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="save_master_days", user_id=admin_id)
        await adm.cb_save_master_days(cb, make_fsm(data={"master_name": "Alibek", "work_days": []}))
        cb.answer.assert_called_with("Выберите хотя бы один рабочий день", show_alert=True)

    async def test_success(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="save_master_days", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "work_days": [1, 2, 3]})
        with patch("storage.set_master_work_days", AsyncMock(return_value=True)), patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_save_master_days(cb, fsm)
        fsm.clear.assert_called()

    async def test_storage_fail(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="save_master_days", user_id=admin_id)
        with patch("storage.set_master_work_days", AsyncMock(return_value=False)):
            await adm.cb_save_master_days(cb, make_fsm(data={"master_name": "Alibek", "work_days": [1]}))
        cb.answer.assert_called_with("Ошибка сохранения", show_alert=True)

    async def test_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="save_master_days", user_id=admin_id)
        with patch("storage.set_master_work_days", side_effect=Exception("fail")):
            await adm.cb_save_master_days(cb, make_fsm(data={"master_name": "Alibek", "work_days": [1]}))
        cb.answer.assert_called_with("Произошла ошибка", show_alert=True)


class TestMasterServices:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="master_services:Alibek", user_id=555)
        await adm.cb_master_services(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_master_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_services:Unknown", user_id=admin_id)
        await adm.cb_master_services(cb, make_fsm())
        cb.answer.assert_called_with("Мастер не найден", show_alert=True)

    async def test_success(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_services:Alibek", user_id=admin_id)
        fsm = make_fsm()
        with patch("storage.get_master_services", AsyncMock(return_value=["Haircut"])), patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_master_services(cb, fsm)
        fsm.set_state.assert_called()

    async def test_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_services:Alibek", user_id=admin_id)
        with patch("storage.get_master_services", side_effect=Exception("fail")):
            await adm.cb_master_services(cb, make_fsm())
        cb.answer.assert_called_with("Произошла ошибка", show_alert=True)


class TestToggleService:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="toggle_service:Haircut", user_id=555)
        await adm.cb_toggle_service(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_add(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="toggle_service:Beard", user_id=admin_id)
        fsm = make_fsm(data={"master_services": ["Haircut"], "master_name": "Alibek"})
        with patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_toggle_service(cb, fsm)
        fsm.update_data.assert_called()

    async def test_remove(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="toggle_service:Haircut", user_id=admin_id)
        fsm = make_fsm(data={"master_services": ["Haircut"], "master_name": "Alibek"})
        with patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_toggle_service(cb, fsm)
        fsm.update_data.assert_called()

    async def test_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="toggle_service:Haircut", user_id=admin_id)
        fsm = make_fsm()
        fsm.get_data = AsyncMock(side_effect=Exception("fail"))
        await adm.cb_toggle_service(cb, fsm)
        cb.answer.assert_called()


class TestSaveMasterServices:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="save_master_services", user_id=555)
        await adm.cb_save_master_services(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_success(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="save_master_services", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "master_services": ["Haircut"]})
        with patch("storage.set_master_services", AsyncMock(return_value=True)), patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_save_master_services(cb, fsm)
        fsm.clear.assert_called()

    async def test_storage_fail(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="save_master_services", user_id=admin_id)
        with patch("storage.set_master_services", AsyncMock(return_value=False)):
            await adm.cb_save_master_services(cb, make_fsm(data={"master_name": "Alibek", "master_services": []}))
        cb.answer.assert_called_with("Ошибка сохранения", show_alert=True)

    async def test_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="save_master_services", user_id=admin_id)
        fsm = make_fsm()
        fsm.get_data = AsyncMock(side_effect=Exception("fail"))
        await adm.cb_save_master_services(cb, fsm)
        cb.answer.assert_called_with("Произошла ошибка", show_alert=True)


class TestMasterPrices:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="master_prices:Alibek", user_id=555)
        await adm.cb_master_prices(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_prices:Unknown", user_id=admin_id)
        await adm.cb_master_prices(cb, make_fsm())
        cb.answer.assert_called_with("Мастер не найден", show_alert=True)

    async def test_success(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_prices:Alibek", user_id=admin_id)
        with patch("storage.get_all_master_service_prices", AsyncMock(return_value={})), patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_master_prices(cb, make_fsm())
        cb.answer.assert_called()


class TestEditMasterPrice:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="edit_mprice:Alibek:Haircut", user_id=555)
        await adm.cb_edit_master_price(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_bad_format(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="edit_mprice:onlyonepart", user_id=admin_id)
        await adm.cb_edit_master_price(cb, make_fsm())
        cb.answer.assert_called_with("Ошибка", show_alert=True)

    async def test_success(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="edit_mprice:Alibek:Haircut", user_id=admin_id)
        fsm = make_fsm()
        with patch("storage.get_master_service_price", AsyncMock(return_value=None)), patch("utils.send_with_retry", AsyncMock()):
            await adm.cb_edit_master_price(cb, fsm)
        fsm.set_state.assert_called()