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
    config.BARBERSHOP_ADDRESS = "Test st."
    config.BARBERSHOP_PHONE = "+7700000000"
    config.BARBERSHOP_WORKING_HOURS = "10:00-21:00"
    return admin_id


class TestAdminStatsException:
    async def test_stats_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_stats", user_id=admin_id)
        with patch("storage.get_all_bookings", side_effect=Exception("fail")):
            with patch("utils.edit_with_retry", AsyncMock()):
                await adm.cb_admin_stats(cb)
        cb.answer.assert_called()


class TestAdminBookingsException:
    async def test_bookings_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_bookings", user_id=admin_id)
        with patch("storage.get_all_bookings", side_effect=Exception("fail")):
            await adm.cb_admin_bookings(cb)
        cb.answer.assert_called()


class TestAdminMasters:
    async def test_no_masters(self):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        config.MASTERS = {}
        cb = make_callback(data="admin_masters", user_id=admin_id)
        with patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_admin_masters(cb)
        cb.answer.assert_called()

    async def test_masters_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_masters", user_id=admin_id)
        with patch("utils.edit_with_retry", AsyncMock(side_effect=Exception("fail"))):
            await adm.cb_admin_masters(cb)
        cb.answer.assert_called()


class TestHandleAddMaster:
    async def test_empty_text(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_master(msg, fsm)

    async def test_bad_format(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="OnlyOnePart", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_master(msg, fsm)

    async def test_name_too_long(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text=("A" * 41) + ", 5 years, cuts", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_master(msg, fsm)

    async def test_success(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        msg = make_message(text="NewMaster, 3 years, cuts", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("config.save_config_to_db", AsyncMock()):
                await adm.handle_add_master(msg, fsm)


class TestEditRemoveMaster:
    async def test_handle_edit_master_empty(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_edit_master(msg, fsm)

    async def test_handle_edit_master_bad_format(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="NoComma", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_edit_master(msg, fsm)

    async def test_handle_edit_master_name_too_long(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text=("A" * 41) + ", 5 years, cuts", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_edit_master(msg, fsm)

    async def test_remove_master_has_active(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_remove_master:Alibek", user_id=admin_id)
        with patch("storage.get_master_stats", AsyncMock(return_value={"active": 2})):
            await adm.cb_admin_remove_master(cb)
        cb.answer.assert_called()

    async def test_remove_master_not_in_config(self):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        config.MASTERS = {}
        cb = make_callback(data="admin_remove_master:Unknown", user_id=admin_id)
        await adm.cb_admin_remove_master(cb)
        cb.answer.assert_called()


class TestAdminServicesException:
    async def test_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_services", user_id=admin_id)
        with patch("utils.edit_with_retry", AsyncMock(side_effect=Exception("fail"))):
            await adm.cb_admin_services(cb)
        cb.answer.assert_called()


class TestHandleAddService:
    async def test_empty_text(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_service(msg, fsm)

    async def test_no_comma(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="NoCommaHere", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_service(msg, fsm)

    async def test_name_too_long(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text=("A" * 36) + ", 3000", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_service(msg, fsm)

    async def test_price_not_int(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="Trim, notanumber", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_service(msg, fsm)

    async def test_price_zero(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="Trim, 0", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_service(msg, fsm)


class TestServiceDetailNotFound:
    async def test_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_service_detail:Unknown", user_id=admin_id)
        await adm.cb_admin_service_detail(cb)
        cb.answer.assert_called()


class TestHandleEditService:
    async def test_empty_text(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_edit_service(msg, fsm)

    async def test_no_comma(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="NoComma", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_edit_service(msg, fsm)

    async def test_name_too_long(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text=("A" * 36) + ", 3000", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_edit_service(msg, fsm)

    async def test_price_not_int(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="NewCut, notint", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_edit_service(msg, fsm)

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        msg = make_message(text="NewCut, 3000", user_id=555)
        fsm = make_fsm(data={"service_name": "Haircut"})
        await adm.handle_edit_service(msg, fsm)


class TestAdminRemoveService:
    async def test_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_remove_service:Unknown", user_id=admin_id)
        await adm.cb_admin_remove_service(cb)
        cb.answer.assert_called()

    async def test_has_active(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_remove_service:Haircut", user_id=admin_id)
        with patch("storage.get_service_stats", AsyncMock(return_value={"active": 3})):
            await adm.cb_admin_remove_service(cb)
        cb.answer.assert_called()

    async def test_shows_confirm(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_remove_service:Haircut", user_id=admin_id)
        with patch("storage.get_service_stats", AsyncMock(return_value={"active": 0})):
            with patch("utils.edit_with_retry", AsyncMock()):
                await adm.cb_admin_remove_service(cb)
        cb.answer.assert_called()


class TestAdminCancelBookingExtra:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_cancel_booking:x", user_id=555)
        await adm.cb_admin_cancel_booking(cb, cb.bot)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_pre_cancel_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_pre_cancel:x", user_id=555)
        await adm.cb_admin_pre_cancel(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)


class TestHandleWorkingHours:
    async def test_non_admin(self):
        import handlers.admin as adm, config
        setup_admin(999)
        old_wh = config.BARBERSHOP_WORKING_HOURS
        old_ts = list(config.TIME_SLOTS) if hasattr(config, "TIME_SLOTS") else []
        msg = make_message(text="10:00-21:00", user_id=555)
        fsm = make_fsm()
        await adm.handle_change_hours(msg, fsm)
        config.BARBERSHOP_WORKING_HOURS = old_wh
        if old_ts:
            config.TIME_SLOTS = old_ts

    async def test_empty_slots_format(self):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        old_ts = list(getattr(config, "TIME_SLOTS", []))
        old_wh = config.BARBERSHOP_WORKING_HOURS
        config.TIME_SLOTS = []
        msg = make_message(text="bad_format_no_dash", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.save_settings", AsyncMock()):
                with patch("config.save_config_to_db", AsyncMock()):
                    await adm.handle_change_hours(msg, fsm)
        config.TIME_SLOTS = old_ts
        config.BARBERSHOP_WORKING_HOURS = old_wh

    async def test_valid_hours(self):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        old_wh = config.BARBERSHOP_WORKING_HOURS
        old_ts = list(getattr(config, "TIME_SLOTS", []))
        old_wh_dict = dict(getattr(config, "WORKING_HOURS", {}))
        msg = make_message(text="09:00-18:00", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.save_settings", AsyncMock()):
                with patch("config.save_config_to_db", AsyncMock()):
                    await adm.handle_change_hours(msg, fsm)
        # Restore config to avoid polluting other tests
        config.BARBERSHOP_WORKING_HOURS = old_wh
        if old_ts:
            config.TIME_SLOTS = old_ts
        if old_wh_dict:
            config.WORKING_HOURS = old_wh_dict
        fsm.clear.assert_called()


class TestMasterSchedule:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="master_schedule:Alibek", user_id=555)
        await adm.cb_master_schedule(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_master_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_schedule:Unknown", user_id=admin_id)
        await adm.cb_master_schedule(cb, make_fsm())
        cb.answer.assert_called_with("Мастер не найден", show_alert=True)

    async def test_success(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="master_schedule:Alibek", user_id=admin_id)
        fsm = make_fsm()
        with patch("storage.get_master_work_days", AsyncMock(return_value=[1, 2, 3])):
            with patch("utils.edit_with_retry", AsyncMock()):
                await adm.cb_master_schedule(cb, fsm)
        fsm.update_data.assert_called()

    async def test_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_schedule:Alibek", user_id=admin_id)
        with patch("storage.get_master_work_days", AsyncMock(side_effect=Exception("fail"))):
            await adm.cb_master_schedule(cb, make_fsm())
        cb.answer.assert_called()


class TestSetMasterTg:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_set_master_tg:Alibek", user_id=555)
        await adm.cb_admin_set_master_tg(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_master_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_set_master_tg:Unknown", user_id=admin_id)
        await adm.cb_admin_set_master_tg(cb, make_fsm())
        cb.answer.assert_called_with("Мастер не найден", show_alert=True)

    async def test_success(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_set_master_tg:Alibek", user_id=admin_id)
        with patch("utils.edit_with_retry", AsyncMock()):
            await adm.cb_admin_set_master_tg(cb, make_fsm())
        cb.answer.assert_called()

    async def test_handle_non_digit(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="notadigit", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_set_master_tg(msg, fsm)

    async def test_handle_zero_removes(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        msg = make_message(text="0", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.set_master_telegram_id", AsyncMock()):
                await adm.handle_set_master_tg(msg, fsm)
        fsm.clear.assert_called()

    async def test_handle_no_master_name(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="12345", user_id=admin_id)
        fsm = make_fsm(data={})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_set_master_tg(msg, fsm)
        fsm.clear.assert_called()


class TestMasterPricesNonAdmin:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="master_prices:Alibek", user_id=555)
        await adm.cb_master_prices(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)


class TestHandleSetMasterPrice:
    async def test_non_digit(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="abc", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_set_master_price(msg, fsm)

    async def test_zero_price(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="0", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_set_master_price(msg, fsm)

    async def test_success(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        msg = make_message(text="5000", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.set_master_service_price", AsyncMock()):
                await adm.handle_set_master_price(msg, fsm)
        fsm.clear.assert_called()

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        msg = make_message(text="5000", user_id=555)
        fsm = make_fsm(data={"master_name": "Alibek", "service_name": "Haircut"})
        await adm.handle_set_master_price(msg, fsm)


class TestDeleteMasterPrice:
    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="del_mprice:Alibek:Haircut", user_id=555)
        await adm.cb_delete_master_price(cb, make_fsm())
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_bad_format(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="del_mprice:OnlyOne", user_id=admin_id)
        await adm.cb_delete_master_price(cb, make_fsm())
        cb.answer.assert_called_with("Ошибка", show_alert=True)

    async def test_success(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="del_mprice:Alibek:Haircut", user_id=admin_id)
        with patch("storage.delete_master_service_price", AsyncMock()):
            with patch("storage.get_all_master_service_prices", AsyncMock(return_value={})):
                with patch("utils.edit_with_retry", AsyncMock()):
                    await adm.cb_delete_master_price(cb, make_fsm())
        cb.answer.assert_called()
