import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def make_user(uid=111, first_name="Test", username="testuser"):
    u = MagicMock()
    u.id = uid
    u.first_name = first_name
    u.username = username
    return u


def make_message(text="/start", uid=111):
    msg = MagicMock()
    msg.from_user = make_user(uid)
    msg.text = text
    msg.chat.id = uid
    msg.bot = AsyncMock()
    msg.bot.send_message = AsyncMock()
    msg.bot.get_me = AsyncMock(return_value=MagicMock(username="testbot"))
    msg.answer = AsyncMock()
    msg.contact = None
    return msg


def make_callback(data="main_menu", uid=111):
    cb = MagicMock()
    cb.from_user = make_user(uid)
    cb.data = data
    cb.bot = AsyncMock()
    cb.bot.get_me = AsyncMock(return_value=MagicMock(username="testbot"))
    cb.message = MagicMock()
    cb.message.edit_text = AsyncMock()
    cb.message.answer = AsyncMock()
    cb.answer = AsyncMock()
    return cb


class TestStartReferralProcessException:

    async def test_referral_processing_exception_caught(self):
        """Lines 85-86: outer except catches exception in referral block"""
        from handlers.start import cmd_start
        msg = make_message("/start ref_TESTCODE")
        state = AsyncMock()
        state.clear = AsyncMock()
        with patch("handlers.start.storage.get_user", new_callable=AsyncMock, return_value=None), \
             patch("handlers.start.storage.save_user", new_callable=AsyncMock), \
             patch("handlers.start.storage.get_user_by_ref_code",
                   new_callable=AsyncMock, side_effect=Exception("db error")), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock):
            await cmd_start(msg, state)


class TestHandleContact:

    async def test_handle_contact_with_contact_object(self):
        """Lines 137-146: contact provided, phone saved"""
        from handlers.start import handle_contact
        msg = make_message()
        msg.contact = MagicMock()
        msg.contact.phone_number = "+79991234567"
        state = AsyncMock()
        state.clear = AsyncMock()
        with patch("handlers.start.storage.save_user", new_callable=AsyncMock), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock), \
             patch("handlers.start.keyboards.main_menu_kb", return_value=MagicMock()):
            await handle_contact(msg, state)
        state.clear.assert_called_once()

    async def test_handle_contact_no_contact_returns_early(self):
        """No contact provided - sends error message"""
        from handlers.start import handle_contact
        msg = make_message()
        msg.contact = None
        state = AsyncMock()
        with patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await handle_contact(msg, state)
        mock_send.assert_called_once()
        state.clear.assert_not_called()


class TestCbWaitlistException:

    async def test_cmd_waitlist_exception_handled(self):
        """Lines 437-439: exception in cmd_waitlist is caught"""
        from handlers.start import cmd_waitlist
        msg = make_message("/waitlist")
        with patch("handlers.start.storage.get_user_waitlist",
                   new_callable=AsyncMock, side_effect=Exception("db error")), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await cmd_waitlist(msg)
        mock_send.assert_called()


class TestCbInviteFriend:

    async def test_invite_friend_success(self):
        """Lines 454-498: cb_invite_friend shows referral link"""
        from handlers.start import cb_invite_friend
        cb = make_callback("invite_friend")
        with patch("handlers.start.storage.ensure_user_ref_code",
                   new_callable=AsyncMock, return_value="MYREF123"), \
             patch("handlers.start.storage.get_loyalty",
                   new_callable=AsyncMock, return_value={"bonuses": 50}), \
             patch("handlers.start.storage.get_referral_count",
                   new_callable=AsyncMock, return_value=3), \
             patch("handlers.start.edit_with_retry", new_callable=AsyncMock) as mock_edit:
            await cb_invite_friend(cb)
        mock_edit.assert_called_once()

    async def test_invite_friend_exception_handled(self):
        """cb_invite_friend exception shows alert"""
        from handlers.start import cb_invite_friend
        cb = make_callback("invite_friend")
        with patch("handlers.start.storage.ensure_user_ref_code",
                   new_callable=AsyncMock, side_effect=Exception("db error")):
            await cb_invite_friend(cb)
        cb.answer.assert_called()

    async def test_invite_friend_no_loyalty(self):
        """loyalty is None - bonuses defaults to 0"""
        from handlers.start import cb_invite_friend
        cb = make_callback("invite_friend")
        with patch("handlers.start.storage.ensure_user_ref_code",
                   new_callable=AsyncMock, return_value="CODE"), \
             patch("handlers.start.storage.get_loyalty",
                   new_callable=AsyncMock, return_value=None), \
             patch("handlers.start.storage.get_referral_count",
                   new_callable=AsyncMock, return_value=0), \
             patch("handlers.start.edit_with_retry", new_callable=AsyncMock):
            await cb_invite_friend(cb)


class TestCancelUniversalSlotLock:

    async def test_cancel_with_slot_lock_exception(self):
        """Lines 513-514: release_slot_lock raises - exception caught"""
        from handlers.start import cmd_cancel_universal
        msg = make_message("/cancel")
        state = AsyncMock()
        state.get_state = AsyncMock(return_value="booking:choosing_time")
        state.get_data = AsyncMock(return_value={
            "date": "2099-01-01", "time": "10:00", "master": "A"
        })
        state.clear = AsyncMock()
        with patch("handlers.start.storage.release_slot_lock",
                   new_callable=AsyncMock, side_effect=Exception("db error")), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock), \
             patch("handlers.start.keyboards.back_to_main_kb", return_value=MagicMock()):
            await cmd_cancel_universal(msg, state)
        state.clear.assert_called_once()

    async def test_cancel_in_fsm_state(self):
        """Cancel while in FSM state clears state and sends message"""
        from handlers.start import cmd_cancel_universal
        msg = make_message("/cancel")
        state = AsyncMock()
        state.get_state = AsyncMock(return_value="booking:choosing_master")
        state.get_data = AsyncMock(return_value={})
        state.clear = AsyncMock()
        with patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send, \
             patch("handlers.start.keyboards.back_to_main_kb", return_value=MagicMock()):
            await cmd_cancel_universal(msg, state)
        state.clear.assert_called_once()
        mock_send.assert_called_once()