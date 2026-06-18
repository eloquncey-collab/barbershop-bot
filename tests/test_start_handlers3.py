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


class TestCmdStartReferral:

    async def test_start_with_referral_referrer_notify_exception(self):
        """Lines 74-75: referrer notification exception is caught"""
        from handlers.start import cmd_start
        msg = make_message("/start ref_TESTCODE")
        state = AsyncMock()
        state.get_state = AsyncMock(return_value=None)
        state.get_data = AsyncMock(return_value={})
        state.clear = AsyncMock()

        with patch("handlers.start.storage.get_user", new_callable=AsyncMock, return_value=None), \
             patch("handlers.start.storage.save_user", new_callable=AsyncMock), \
             patch("handlers.start.storage.get_user_by_ref_code",
                   new_callable=AsyncMock,
                   return_value={"telegram_id": 999, "first_name": "Referrer"}), \
             patch("handlers.start.storage.add_referral",
                   new_callable=AsyncMock, return_value=True), \
             patch("handlers.start.storage.add_bonus", new_callable=AsyncMock), \
             patch.object(msg.bot, "send_message",
                          new_callable=AsyncMock, side_effect=Exception("blocked")), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock):
            await cmd_start(msg, state)

    async def test_start_with_referral_new_user_notification(self):
        """Lines 85-86: new user gets welcome notification after referral"""
        from handlers.start import cmd_start
        msg = make_message("/start ref_TESTCODE")
        state = AsyncMock()
        state.clear = AsyncMock()

        with patch("handlers.start.storage.get_user", new_callable=AsyncMock, return_value=None), \
             patch("handlers.start.storage.save_user", new_callable=AsyncMock), \
             patch("handlers.start.storage.get_user_by_ref_code",
                   new_callable=AsyncMock,
                   return_value={"telegram_id": 999, "first_name": "Ref"}), \
             patch("handlers.start.storage.add_referral",
                   new_callable=AsyncMock, return_value=True), \
             patch("handlers.start.storage.add_bonus", new_callable=AsyncMock), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await cmd_start(msg, state)
        assert mock_send.called

    async def test_start_existing_user(self):
        """Existing user just gets main menu"""
        from handlers.start import cmd_start
        msg = make_message("/start")
        state = AsyncMock()
        state.clear = AsyncMock()
        existing_user = {"telegram_id": 111, "first_name": "Test"}

        with patch("handlers.start.storage.get_user",
                   new_callable=AsyncMock, return_value=existing_user), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await cmd_start(msg, state)
        assert mock_send.called


class TestCbMyBookings:

    async def test_my_bookings_with_list(self):
        """Lines 216-238: bookings list is shown"""
        from handlers.start import cb_my_bookings
        cb = make_callback("my_bookings")
        bookings = [
            {"id": "bk1", "date": "2099-01-01", "time": "10:00",
             "master": "Alibek", "service": "Haircut", "price": 3000},
        ]
        with patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=bookings), \
             patch("handlers.start.keyboards._format_date", return_value="01.01.2099"), \
             patch("handlers.start.keyboards.bookings_list_kb", return_value=MagicMock()):
            await cb_my_bookings(cb)
        cb.message.edit_text.assert_called_once()
        cb.answer.assert_called()


class TestCbBookingDetail:

    async def test_booking_detail_not_found(self):
        """Lines 299-307: booking not found in list"""
        from handlers.start import cb_booking_detail
        cb = make_callback("booking_detail:nonexistent")
        with patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=[]):
            await cb_booking_detail(cb)
        cb.answer.assert_called()

    async def test_booking_detail_found(self):
        """Booking detail shown when found"""
        from handlers.start import cb_booking_detail
        cb = make_callback("booking_detail:bk1")
        bookings = [{"id": "bk1", "date": "2099-01-01", "time": "10:00",
                     "master": "A", "service": "S", "price": 2000}]
        with patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=bookings), \
             patch("handlers.start.keyboards._format_date", return_value="01.01.2099"), \
             patch("handlers.start.keyboards.booking_detail_kb", return_value=MagicMock()):
            await cb_booking_detail(cb)
        cb.message.edit_text.assert_called_once()


class TestCbCancelBook:

    async def test_cancel_book_not_found(self):
        """Lines 320-321: booking not found"""
        from handlers.start import cb_cancel_book
        cb = make_callback("cancel_book:nonexistent")
        with patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=[]):
            await cb_cancel_book(cb)
        cb.answer.assert_called()

    async def test_cancel_book_found(self):
        """Lines 322-353: confirm cancel shown"""
        from handlers.start import cb_cancel_book
        cb = make_callback("cancel_book:bk1")
        bookings = [{"id": "bk1", "date": "2099-01-01", "time": "10:00",
                     "master": "A", "service": "S", "price": 2000}]
        with patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=bookings), \
             patch("handlers.start.keyboards._format_date", return_value="01.01.2099"), \
             patch("handlers.start.keyboards.confirm_cancel_kb", return_value=MagicMock()):
            await cb_cancel_book(cb)
        cb.answer.assert_called()

    async def test_cancel_book_edit_raises_uses_answer(self):
        """edit_text fails -> answer is used instead"""
        from handlers.start import cb_cancel_book
        cb = make_callback("cancel_book:bk1")
        cb.message.edit_text = AsyncMock(side_effect=Exception("cannot edit"))
        bookings = [{"id": "bk1", "date": "2099-01-01", "time": "10:00",
                     "master": "A", "service": "S", "price": 2000}]
        with patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=bookings), \
             patch("handlers.start.keyboards._format_date", return_value="01.01.2099"), \
             patch("handlers.start.keyboards.confirm_cancel_kb", return_value=MagicMock()):
            await cb_cancel_book(cb)
        cb.message.answer.assert_called_once()


class TestCbAskCancel:

    async def test_ask_cancel_not_found(self):
        """Line 366: booking not found"""
        from handlers.start import cb_ask_cancel
        cb = make_callback("ask_cancel:none")
        with patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=[]):
            await cb_ask_cancel(cb)
        cb.answer.assert_called()


class TestCmdMe:

    async def test_cmd_me_user_not_found(self):
        """Lines 437-439: user not in DB returns error message"""
        from handlers.start import cmd_me
        msg = make_message("/me")
        with patch("handlers.start.storage.get_user",
                   new_callable=AsyncMock, return_value=None), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await cmd_me(msg)
        mock_send.assert_called()

    async def test_cmd_me_with_loyalty_and_ref_code(self):
        """Lines 454-498: full profile with loyalty + referral link"""
        from handlers.start import cmd_me
        msg = make_message("/me")
        user = {"telegram_id": 111, "first_name": "Test", "phone": "+7999"}
        loyalty = {"visits": 5, "bonuses": 100, "ref_code": "MYREF"}
        bookings = [{"id": "bk1", "date": "2099-01-01", "time": "10:00",
                     "master": "A", "service": "S"}]
        with patch("handlers.start.storage.get_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=bookings), \
             patch("handlers.start.storage.get_loyalty",
                   new_callable=AsyncMock, return_value=loyalty), \
             patch("handlers.start.keyboards._format_date", return_value="01.01.2099"), \
             patch("handlers.start.keyboards.back_to_main_kb", return_value=MagicMock()), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await cmd_me(msg)
        mock_send.assert_called()

    async def test_cmd_me_with_loyalty_no_ref_code(self):
        """Loyalty present but no ref_code"""
        from handlers.start import cmd_me
        msg = make_message("/me")
        user = {"telegram_id": 111, "first_name": "Test", "phone": None}
        loyalty = {"visits": 2, "bonuses": 0, "ref_code": None}
        with patch("handlers.start.storage.get_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=[]), \
             patch("handlers.start.storage.get_loyalty",
                   new_callable=AsyncMock, return_value=loyalty), \
             patch("handlers.start.keyboards.back_to_main_kb", return_value=MagicMock()), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await cmd_me(msg)
        mock_send.assert_called()

    async def test_cmd_me_no_loyalty(self):
        """No loyalty record at all"""
        from handlers.start import cmd_me
        msg = make_message("/me")
        user = {"telegram_id": 111, "first_name": "Test", "phone": None}
        with patch("handlers.start.storage.get_user",
                   new_callable=AsyncMock, return_value=user), \
             patch("handlers.start.storage.get_user_bookings",
                   new_callable=AsyncMock, return_value=[]), \
             patch("handlers.start.storage.get_loyalty",
                   new_callable=AsyncMock, return_value=None), \
             patch("handlers.start.keyboards.back_to_main_kb", return_value=MagicMock()), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await cmd_me(msg)
        mock_send.assert_called()


class TestCmdMaster:

    async def test_cmd_master_no_masters(self):
        """Lines 513-514: no masters configured"""
        from handlers.start import cmd_master
        msg = make_message("/master")
        with patch("handlers.start.config.MASTERS", {}), \
             patch("handlers.start.keyboards.masters_kb", return_value=MagicMock()), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await cmd_master(msg)
        mock_send.assert_called()

    async def test_cmd_master_with_masters(self):
        """Masters list shown"""
        from handlers.start import cmd_master
        msg = make_message("/master")
        masters = {"Alibek": {"experience": "5 лет", "specialization": "Фейд"}}
        with patch("handlers.start.config.MASTERS", masters), \
             patch("handlers.start.keyboards.masters_kb", return_value=MagicMock()), \
             patch("handlers.start.send_with_retry", new_callable=AsyncMock) as mock_send:
            await cmd_master(msg)
        mock_send.assert_called()