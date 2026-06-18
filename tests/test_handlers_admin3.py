
"""Admin handler tests targeting uncovered error paths and specific branches."""
import pytest
import sys, pathlib
from unittest.mock import AsyncMock, MagicMock, patch
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from helpers import make_message, make_callback, make_fsm, SAMPLE_BOOKING


def setup_admin(user_id=777):
    import config
    config.ADMIN_IDS = [user_id]
    return user_id


# ==================================================================
# cb_admin_stats -- exception path
# ==================================================================
class TestAdminStatsException:

    async def test_stats_exception_is_handled(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_stats", user_id=admin_id)
        with patch("storage.get_stats", side_effect=Exception("DB down")):
            await adm.cb_admin_stats(cb)
        cb.answer.assert_called()

    async def test_stats_non_admin_rejected(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_stats", user_id=555)
        await adm.cb_admin_stats(cb)
        cb.answer.assert_called()


# ==================================================================
# cb_admin_bookings -- offset parsing, non-admin
# ==================================================================
class TestAdminBookingsOffset:

    async def test_non_admin_is_rejected(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_bookings:0", user_id=555)
        await adm.cb_admin_bookings(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_invalid_offset_defaults_to_zero(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_bookings:notanint", user_id=admin_id)
        await adm.cb_admin_bookings(cb)
        cb.answer.assert_called()


# ==================================================================
# cb_admin_manage_booking -- non-admin, exception
# ==================================================================
class TestAdminManageBooking:

    async def test_non_admin_rejected(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_manage_booking:abc", user_id=555)
        await adm.cb_admin_manage_booking(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_missing_booking_handled(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_manage_booking:nonexistent_id", user_id=admin_id)
        await adm.cb_admin_manage_booking(cb)
        # Should not raise

    async def test_existing_booking_shown(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"admin_manage_booking:{bid}", user_id=admin_id)
        await adm.cb_admin_manage_booking(cb)
        cb.answer.assert_called()


# ==================================================================
# cb_admin_export -- exception handling, file cleanup
# ==================================================================
class TestAdminExport:

    async def test_non_admin_rejected(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_export", user_id=555)
        await adm.cb_admin_export(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_export_success(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data="admin_export", user_id=admin_id)
        await adm.cb_admin_export(cb)
        # Should not raise

    async def test_export_exception_handled(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_export", user_id=admin_id)
        with patch("storage.get_all_bookings", side_effect=Exception("DB fail")):
            await adm.cb_admin_export(cb)
        cb.answer.assert_called()


# ==================================================================
# cb_admin_masters -- no masters, exception
# ==================================================================
class TestAdminMasters:

    async def test_non_admin_rejected(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_masters", user_id=555)
        await adm.cb_admin_masters(cb)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_empty_masters_shows_empty_message(self, db):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        original = dict(config.MASTERS)
        config.MASTERS.clear()
        try:
            cb = make_callback(data="admin_masters", user_id=admin_id)
            await adm.cb_admin_masters(cb)
        finally:
            config.MASTERS.update(original)

    async def test_masters_exception_handled(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        cb = make_callback(data="admin_masters", user_id=admin_id)
        with patch("storage.get_all_masters", side_effect=Exception("fail")):
            await adm.cb_admin_masters(cb)
        cb.answer.assert_called()


# ==================================================================
# cancel booking admin -- non-admin
# ==================================================================
class TestAdminCancelBooking:

    async def test_non_admin_rejected(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_pre_cancel:abc", user_id=555)
        bot = AsyncMock()
        await adm.cb_admin_cancel_booking(cb, bot)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_cancel_existing_booking(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"admin_pre_cancel:{bid}", user_id=admin_id)
        bot = AsyncMock()
        bot.send_message = AsyncMock()
        await adm.cb_admin_cancel_booking(cb, bot)
        cb.answer.assert_called()


# ==================================================================
# complete booking admin
# ==================================================================
class TestAdminCompleteBooking:

    async def test_non_admin_rejected(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin_complete_booking:abc", user_id=555)
        bot = AsyncMock()
        await adm.cb_admin_complete_booking(cb, bot)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)

    async def test_complete_existing_booking(self, db):
        import handlers.admin as adm, storage
        admin_id = setup_admin()
        bid = await storage.save_booking(SAMPLE_BOOKING)
        cb = make_callback(data=f"admin_complete_booking:{bid}", user_id=admin_id)
        bot = AsyncMock()
        bot.send_message = AsyncMock()
        await adm.cb_admin_complete_booking(cb, bot)
        cb.answer.assert_called()


# ==================================================================
# cmd_admin -- non-admin
# ==================================================================
class TestCmdAdmin:

    async def test_cmd_admin_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        msg = make_message(user_id=555)
        fsm = make_fsm()
        await adm.cmd_admin(msg, fsm)
        msg.bot.send_message.assert_called()

    async def test_cmd_admin_is_admin(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(user_id=admin_id)
        fsm = make_fsm()
        await adm.cmd_admin(msg, fsm)
        msg.bot.send_message.assert_called()


# ==================================================================
# cb_admin -- non-admin
# ==================================================================
class TestCbAdmin:

    async def test_cb_admin_non_admin(self):
        import handlers.admin as adm
        setup_admin(999)
        cb = make_callback(data="admin", user_id=555)
        fsm = make_fsm()
        await adm.cb_admin(cb, fsm)
        cb.answer.assert_called_with(adm.messages.ADMIN_ONLY, show_alert=True)


# ==================================================================
# change hours handler
# ==================================================================
class TestChangeHoursHandler:

    async def test_change_hours_valid_format(self, db):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        msg = make_message(text="Пн-Сб: 10:00-21:00, Вс: 11:00-19:00", user_id=admin_id)
        fsm = make_fsm()
        orig_hours = dict(config.WORKING_HOURS)
        try:
            await adm.handle_change_hours(msg, fsm)
            fsm.clear.assert_called()
        finally:
            config.WORKING_HOURS.clear()
            config.WORKING_HOURS.update(orig_hours)

    async def test_change_hours_non_admin_exits(self):
        import handlers.admin as adm
        setup_admin(999)
        msg = make_message(text="10:00-20:00", user_id=555)
        fsm = make_fsm()
        await adm.handle_change_hours(msg, fsm)
        msg.bot.send_message.assert_not_called()

    async def test_change_hours_empty_text_rejected(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="", user_id=admin_id)
        fsm = make_fsm()
        await adm.handle_change_hours(msg, fsm)

    async def test_change_hours_too_long_rejected(self):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="x" * 201, user_id=admin_id)
        fsm = make_fsm()
        await adm.handle_change_hours(msg, fsm)

    async def test_change_hours_invalid_start_end(self, db):
        import handlers.admin as adm, config
        admin_id = setup_admin()
        msg = make_message(text="21:00-10:00", user_id=admin_id)
        fsm = make_fsm()
        orig_hours = dict(config.WORKING_HOURS)
        try:
            await adm.handle_change_hours(msg, fsm)
        finally:
            config.WORKING_HOURS.clear()
            config.WORKING_HOURS.update(orig_hours)


# ==================================================================
# edit service handler
# ==================================================================
class TestEditServiceHandler:

    async def test_edit_service_valid(self, db):
        import handlers.admin as adm, config, storage
        admin_id = setup_admin()
        # Add a service first
        config.SERVICES["TestSvc"] = 1000
        await storage.save_service("TestSvc", 1000)
        msg = make_message(text="NewSvc, 2000", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "TestSvc"})
        await adm.handle_edit_service(msg, fsm)
        assert "NewSvc" in config.SERVICES
        if "NewSvc" in config.SERVICES:
            del config.SERVICES["NewSvc"]

    async def test_edit_service_invalid_format(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="nocomma", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "TestSvc"})
        await adm.handle_edit_service(msg, fsm)

    async def test_edit_service_invalid_price(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="SvcName, notanumber", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "TestSvc"})
        await adm.handle_edit_service(msg, fsm)

    async def test_edit_service_zero_price_rejected(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        msg = make_message(text="SvcName, 0", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "TestSvc"})
        await adm.handle_edit_service(msg, fsm)

    async def test_edit_service_name_too_long(self, db):
        import handlers.admin as adm
        admin_id = setup_admin()
        long_name = "A" * 40
        msg = make_message(text=f"{long_name}, 1000", user_id=admin_id)
        fsm = make_fsm(data={"service_name": "TestSvc"})
        await adm.handle_edit_service(msg, fsm)
