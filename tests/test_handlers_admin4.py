import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.helpers import make_callback, make_message, make_fsm, SAMPLE_BOOKING


def setup_admin(admin_id=100):
    import config
    config.ADMIN_IDS = {admin_id}
    config.MASTERS = {"Alibek": {"experience": "5 years", "specialization": "cuts"}}
    config.SERVICES = {"Haircut": 3000, "Beard": 2000}
    config.MASTER_IDS = {}
    return admin_id

class TestAdminBookingsPagination:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_bookings", user_id=555)
        await adm.cb_admin_bookings(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_bookings_page_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_bookings_page:0", user_id=555)
        await adm.cb_admin_bookings_page(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_bookings_page_invalid_offset(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_bookings_page:notanumber", user_id=admin_id)
        with patch("storage.get_upcoming_bookings", AsyncMock(return_value=[])):
            await adm.cb_admin_bookings_page(cb)
        cb.answer.assert_called()

    async def test_bookings_page_with_data(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data="admin_bookings_page:0", user_id=admin_id)
        await adm.cb_admin_bookings_page(cb)
        cb.answer.assert_called()

class TestAdminManageBooking:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_manage_booking:abc", user_id=555)
        await adm.cb_admin_manage_booking(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_booking_not_found(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_manage_booking:nonexistent", user_id=admin_id)
        await adm.cb_admin_manage_booking(cb)
        cb.answer.assert_called()

    async def test_existing_booking(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"admin_manage_booking:{bid}", user_id=admin_id)
        await adm.cb_admin_manage_booking(cb)
        cb.answer.assert_called()

    async def test_exception_handled(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_manage_booking:x", user_id=admin_id)
        with patch("storage.get_booking_with_user", side_effect=Exception("fail")):
            await adm.cb_admin_manage_booking(cb)
        cb.answer.assert_called()


class TestNoop:
    async def test_noop(self):
        import handlers.admin as adm
        cb = make_callback(data="noop", user_id=100)
        await adm.cb_noop(cb)
        cb.answer.assert_called()


class TestAdminExport:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_export", user_id=555)
        await adm.cb_admin_export(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_export_success(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        with patch("storage.export_bookings_csv", AsyncMock(return_value=[])):
            cb = make_callback(data="admin_export", user_id=admin_id)
            cb.message.answer_document = AsyncMock()
            await adm.cb_admin_export(cb)
        cb.answer.assert_called()

    async def test_export_exception(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_export", user_id=admin_id)
        with patch("storage.export_bookings_csv", side_effect=Exception("db fail")):
            await adm.cb_admin_export(cb)
        cb.answer.assert_called()

class TestHandleAddMaster:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        msg = make_message(text="Name, 5 years, cuts", user_id=555)
        fsm = make_fsm()
        await adm.handle_add_master(msg, fsm)

    async def test_empty_text(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_master(msg, fsm)

    async def test_wrong_format(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="only one part", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_master(msg, fsm)
        # format error sends via msg.answer or send_with_retry

    async def test_valid_master_added(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        msg = make_message(text="Noviy, 3 years, beard", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.save_master", AsyncMock()):
                with patch("config.save_config_to_db", AsyncMock()):
                    await adm.handle_add_master(msg, fsm)
        fsm.clear.assert_called()

    async def test_name_too_long(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="X" * 41 + ", 5 years, cuts", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_master(msg, fsm)


class TestHandleEditMaster:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        msg = make_message(text="Name, 5 years, cuts", user_id=555)
        fsm = make_fsm(data={"master_name": "Alibek"})
        await adm.handle_edit_master(msg, fsm)

    async def test_empty_text(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_edit_master(msg, fsm)

    async def test_wrong_format(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="just text", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_edit_master(msg, fsm)

    async def test_valid_edit(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        msg = make_message(text="NewName, 4 years, beard", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.remove_master", AsyncMock()):
                with patch("storage.save_master", AsyncMock()):
                    with patch("config.save_config_to_db", AsyncMock()):
                        await adm.handle_edit_master(msg, fsm)
        fsm.clear.assert_called()

class TestAdminRemoveMaster:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_remove_master:Alibek", user_id=555)
        await adm.cb_admin_remove_master(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_master_with_active_bookings(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_remove_master:Alibek", user_id=admin_id)
        with patch("storage.get_master_stats", AsyncMock(return_value={"active": 2})):
            await adm.cb_admin_remove_master(cb)
        cb.answer.assert_called()

    async def test_master_not_found(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_remove_master:NotExist", user_id=admin_id)
        with patch("storage.get_master_stats", AsyncMock(return_value={"active": 0})):
            await adm.cb_admin_remove_master(cb)
        cb.answer.assert_called()

    async def test_remove_success(self, db):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        cb = make_callback(data="admin_remove_master:Alibek", user_id=admin_id)
        with patch("storage.get_master_stats", AsyncMock(return_value={"active": 0})):
            with patch("storage.remove_master", AsyncMock()):
                await adm.cb_admin_remove_master(cb)
        assert "Alibek" not in config.MASTERS
        cb.answer.assert_called()


class TestHandleAddService:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        msg = make_message(text="Cut, 3000", user_id=555)
        fsm = make_fsm()
        await adm.handle_add_service(msg, fsm)

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
        msg = make_message(text="NoComma", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_add_service(msg, fsm)

    async def test_invalid_price(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="Cut, abc", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_add_service(msg, fsm)

    async def test_zero_price(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="Cut, 0", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_add_service(msg, fsm)

    async def test_valid_service(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        msg = make_message(text="NewService, 5000", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.save_service", AsyncMock()):
                with patch("config.save_config_to_db", AsyncMock()):
                    await adm.handle_add_service(msg, fsm)
        fsm.clear.assert_called()

    async def test_name_too_long(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="X" * 36 + ", 3000", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_add_service(msg, fsm)

class TestAdminRemoveService:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_remove_service:Haircut", user_id=555)
        await adm.cb_admin_remove_service(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_service_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_remove_service:NotExist", user_id=admin_id)
        await adm.cb_admin_remove_service(cb)
        cb.answer.assert_called()

    async def test_service_with_active_bookings(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_remove_service:Haircut", user_id=admin_id)
        with patch("storage.get_service_stats", AsyncMock(return_value={"active": 3})):
            await adm.cb_admin_remove_service(cb)
        cb.answer.assert_called()

    async def test_shows_confirm_dialog(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_remove_service:Haircut", user_id=admin_id)
        with patch("storage.get_service_stats", AsyncMock(return_value={"active": 0})):
            await adm.cb_admin_remove_service(cb)
        cb.answer.assert_called()


class TestAdminConfirmRemoveServiceNew:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_confirm_remove_service:Haircut", user_id=555)
        await adm.cb_admin_confirm_remove_service(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_confirm_remove_service:NotExist", user_id=admin_id)
        await adm.cb_admin_confirm_remove_service(cb)
        cb.answer.assert_called()

class TestAdminSettings:

    async def test_settings_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_settings", user_id=555)
        await adm.cb_admin_settings(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_settings_admin(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_settings", user_id=admin_id)
        await adm.cb_admin_settings(cb)
        cb.answer.assert_called()

    async def test_change_address_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_change_address", user_id=555)
        fsm = make_fsm()
        await adm.cb_admin_change_address(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_change_address_admin(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_change_address", user_id=admin_id)
        fsm = make_fsm()
        await adm.cb_admin_change_address(cb, fsm)
        fsm.set_state.assert_called()

    async def test_handle_address_empty(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_change_address(msg, fsm)

    async def test_handle_address_too_long(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="A" * 201, user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_change_address(msg, fsm)

    async def test_handle_address_valid(self):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        msg = make_message(text="New Street 1", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.save_settings", AsyncMock()):
                with patch("config.save_config_to_db", AsyncMock()):
                    await adm.handle_change_address(msg, fsm)
        assert config.BARBERSHOP_ADDRESS == "New Street 1"

    async def test_change_phone_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_change_phone", user_id=555)
        fsm = make_fsm()
        await adm.cb_admin_change_phone(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_handle_phone_empty(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_change_phone(msg, fsm)

    async def test_handle_phone_too_long(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="1" * 201, user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_change_phone(msg, fsm)

    async def test_handle_phone_valid(self):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        msg = make_message(text="+7 700 000 0000", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.save_settings", AsyncMock()):
                with patch("config.save_config_to_db", AsyncMock()):
                    await adm.handle_change_phone(msg, fsm)
        assert config.BARBERSHOP_PHONE == "+7 700 000 0000"

    async def test_change_hours_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_change_hours", user_id=555)
        fsm = make_fsm()
        await adm.cb_admin_change_hours(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_handle_hours_empty(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_change_hours(msg, fsm)

    async def test_handle_hours_too_long(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="A" * 201, user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_change_hours(msg, fsm)

    async def test_handle_hours_valid(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="Mon-Sat: 10:00-21:00", user_id=admin_id)
        fsm = make_fsm()
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.save_settings", AsyncMock()):
                with patch("config.save_config_to_db", AsyncMock()):
                    await adm.handle_change_hours(msg, fsm)
        fsm.clear.assert_called()

class TestAdminWaitlistReviews:

    async def test_waitlist_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_waitlist", user_id=555)
        await adm.cb_admin_waitlist(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_waitlist_admin(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_waitlist", user_id=admin_id)
        await adm.cb_admin_waitlist(cb)
        cb.answer.assert_called()

    async def test_waitlist_page_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_waitlist_page:0", user_id=555)
        await adm.cb_admin_waitlist_page(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_waitlist_page_admin(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_waitlist_page:0", user_id=admin_id)
        await adm.cb_admin_waitlist_page(cb)
        cb.answer.assert_called()

    async def test_reviews_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_reviews", user_id=555)
        await adm.cb_admin_reviews(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_reviews_admin(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_reviews", user_id=admin_id)
        await adm.cb_admin_reviews(cb)
        cb.answer.assert_called()

    async def test_reviews_page_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_reviews_page:0", user_id=555)
        await adm.cb_admin_reviews_page(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_loyalty_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_loyalty", user_id=555)
        await adm.cb_admin_loyalty(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_loyalty_admin(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_loyalty", user_id=admin_id)
        await adm.cb_admin_loyalty(cb)
        cb.answer.assert_called()

    async def test_referrals_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_referrals", user_id=555)
        await adm.cb_admin_referrals(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_referrals_admin(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="admin_referrals", user_id=admin_id)
        await adm.cb_admin_referrals(cb)
        cb.answer.assert_called()

class TestMasterTgManagement:

    async def test_set_master_tg_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_set_master_tg:Alibek", user_id=555)
        fsm = make_fsm()
        await adm.cb_admin_set_master_tg(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_set_master_tg_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_set_master_tg:NotExist", user_id=admin_id)
        fsm = make_fsm()
        await adm.cb_admin_set_master_tg(cb, fsm)
        cb.answer.assert_called()

    async def test_set_master_tg_valid(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_set_master_tg:Alibek", user_id=admin_id)
        fsm = make_fsm()
        await adm.cb_admin_set_master_tg(cb, fsm)
        fsm.set_state.assert_called()

    async def test_handle_tg_id_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        msg = make_message(text="123456", user_id=555)
        fsm = make_fsm(data={"master_name": "Alibek"})
        await adm.handle_set_master_tg(msg, fsm)

    async def test_handle_tg_id_invalid(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="notanumber", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_set_master_tg(msg, fsm)

    async def test_handle_tg_id_zero_removes(self, db):
        import handlers.admin as adm, config, storage
        admin_id = setup_admin()
        await storage.init_db()
        config.MASTER_IDS["Alibek"] = 99999
        msg = make_message(text="0", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.set_master_telegram_id", AsyncMock()):
                await adm.handle_set_master_tg(msg, fsm)
        assert "Alibek" not in config.MASTER_IDS

    async def test_handle_tg_id_sets_valid(self, db):
        import handlers.admin as adm, config, storage
        admin_id = setup_admin()
        await storage.init_db()
        msg = make_message(text="99999", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek"})
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.set_master_telegram_id", AsyncMock()):
                await adm.handle_set_master_tg(msg, fsm)
        assert config.MASTER_IDS.get("Alibek") == 99999

    async def test_handle_tg_id_no_master_in_state(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="123", user_id=admin_id)
        fsm = make_fsm(data={})
        with patch("utils.send_with_retry", AsyncMock()):
            await adm.handle_set_master_tg(msg, fsm)
        fsm.clear.assert_called()

class TestMasterSchedule:

    async def test_master_schedule_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="master_schedule:Alibek", user_id=555)
        fsm = make_fsm()
        await adm.cb_master_schedule(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_master_schedule_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_schedule:NotExist", user_id=admin_id)
        fsm = make_fsm()
        await adm.cb_master_schedule(cb, fsm)
        cb.answer.assert_called()

    async def test_master_schedule_valid(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="master_schedule:Alibek", user_id=admin_id)
        fsm = make_fsm()
        with patch("storage.get_master_work_days", AsyncMock(return_value=[1, 2, 3, 4, 5])):
            await adm.cb_master_schedule(cb, fsm)
        fsm.set_state.assert_called()

    async def test_save_master_days_no_days(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="save_master_days", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "work_days": []})
        await adm.cb_save_master_days(cb, fsm)
        cb.answer.assert_called()

    async def test_save_master_days_success(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="save_master_days", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "work_days": [1, 2, 3]})
        with patch("storage.set_master_work_days", AsyncMock(return_value=True)):
            await adm.cb_save_master_days(cb, fsm)
        fsm.clear.assert_called()

    async def test_save_master_days_fail(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="save_master_days", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "work_days": [1]})
        with patch("storage.set_master_work_days", AsyncMock(return_value=False)):
            await adm.cb_save_master_days(cb, fsm)
        cb.answer.assert_called()


class TestMasterServicesManagement:

    async def test_master_services_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="master_services:Alibek", user_id=555)
        fsm = make_fsm()
        await adm.cb_master_services(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_master_services_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_services:NotExist", user_id=admin_id)
        fsm = make_fsm()
        await adm.cb_master_services(cb, fsm)
        cb.answer.assert_called()

    async def test_master_services_valid(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="master_services:Alibek", user_id=admin_id)
        fsm = make_fsm()
        with patch("storage.get_master_services", AsyncMock(return_value=["Haircut"])):
            await adm.cb_master_services(cb, fsm)
        fsm.set_state.assert_called()

    async def test_save_master_services_success(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="save_master_services", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "master_services": ["Haircut"]})
        with patch("storage.set_master_services", AsyncMock(return_value=True)):
            await adm.cb_save_master_services(cb, fsm)
        fsm.clear.assert_called()

    async def test_save_master_services_empty(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="save_master_services", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "master_services": []})
        with patch("storage.set_master_services", AsyncMock(return_value=True)):
            await adm.cb_save_master_services(cb, fsm)
        fsm.clear.assert_called()

class TestMasterPrices:

    async def test_master_prices_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="master_prices:Alibek", user_id=555)
        fsm = make_fsm()
        await adm.cb_master_prices(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_master_prices_not_found(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="master_prices:NotExist", user_id=admin_id)
        fsm = make_fsm()
        await adm.cb_master_prices(cb, fsm)
        cb.answer.assert_called()

    async def test_master_prices_valid(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="master_prices:Alibek", user_id=admin_id)
        fsm = make_fsm()
        with patch("storage.get_all_master_service_prices", AsyncMock(return_value={})):
            await adm.cb_master_prices(cb, fsm)
        cb.answer.assert_called()

    async def test_edit_master_price_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="edit_mprice:Alibek:Haircut", user_id=555)
        fsm = make_fsm()
        await adm.cb_edit_master_price(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_edit_master_price_valid(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="edit_mprice:Alibek:Haircut", user_id=admin_id)
        fsm = make_fsm()
        with patch("storage.get_master_service_price", AsyncMock(return_value=None)):
            with patch("utils.send_with_retry", AsyncMock()):
                await adm.cb_edit_master_price(cb, fsm)
        fsm.set_state.assert_called()

    async def test_handle_set_price_non_digit(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="notanumber", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_set_master_price(msg, fsm)

    async def test_handle_set_price_valid(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        msg = make_message(text="4500", user_id=admin_id)
        fsm = make_fsm(data={"master_name": "Alibek", "service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.set_master_service_price", AsyncMock()):
                await adm.handle_set_master_price(msg, fsm)
        fsm.clear.assert_called()

    async def test_delete_master_price_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="del_mprice:Alibek:Haircut", user_id=555)
        fsm = make_fsm()
        await adm.cb_delete_master_price(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_delete_master_price_valid(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="del_mprice:Alibek:Haircut", user_id=admin_id)
        fsm = make_fsm()
        with patch("storage.delete_master_service_price", AsyncMock()):
            with patch("storage.get_all_master_service_prices", AsyncMock(return_value={})):
                await adm.cb_delete_master_price(cb, fsm)
        cb.answer.assert_called()

    async def test_reset_all_prices_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="reset_mprices:Alibek", user_id=555)
        await adm.cb_reset_all_master_prices(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_reset_all_prices_valid(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        cb = make_callback(data="reset_mprices:Alibek", user_id=admin_id)
        with patch("storage.delete_master_service_price", AsyncMock()):
            await adm.cb_reset_all_master_prices(cb)
        cb.answer.assert_called()


class TestAdminPreCancel:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_pre_cancel:abc", user_id=555)
        await adm.cb_admin_pre_cancel(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_admin(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_pre_cancel:some_id", user_id=admin_id)
        await adm.cb_admin_pre_cancel(cb)
        cb.answer.assert_called()


class TestHandleEditService:

    async def test_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        msg = make_message(text="Cut, 3000", user_id=555)
        fsm = make_fsm(data={"service_name": "Haircut"})
        await adm.handle_edit_service(msg, fsm)

    async def test_empty_text(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_edit_service(msg, fsm)

    async def test_no_comma(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="Haircut", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_edit_service(msg, fsm)

    async def test_invalid_price(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="Cut, abc", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_edit_service(msg, fsm)

    async def test_zero_price(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="Cut, 0", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()) as m:
            await adm.handle_edit_service(msg, fsm)

    async def test_valid_edit(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.init_db()
        msg = make_message(text="NewCut, 4000", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "Haircut"})
        with patch("utils.send_with_retry", AsyncMock()):
            with patch("storage.remove_service", AsyncMock()):
                with patch("storage.save_service", AsyncMock()):
                    with patch("config.save_config_to_db", AsyncMock()):
                        await adm.handle_edit_service(msg, fsm)
        fsm.clear.assert_called()
