
"""Tests for keyboards.py: _safe_cb() and main_menu_kb() emoji/structure."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


class TestSafeCb:

    def _get(self):
        from keyboards import _safe_cb
        return _safe_cb

    def test_short_value_unchanged(self):
        assert self._get()("master:", "Alibek") == "master:Alibek"

    def test_combined_within_limit(self):
        result = self._get()("master:", "Alibek")
        assert len(result.encode("utf-8")) <= 62

    def test_long_ascii_truncated(self):
        result = self._get()("master:", "A" * 60)
        assert len(result.encode("utf-8")) <= 62

    def test_long_cyrillic_truncated(self):
        result = self._get()("master:", "А" * 40)  # 80 bytes
        assert len(result.encode("utf-8")) <= 62

    def test_truncation_valid_utf8(self):
        result = self._get()("master:", "Ж" * 40)
        result.encode("utf-8")  # must not raise

    def test_exact_limit_not_truncated(self):
        name = "x" * 60
        assert self._get()("a:", name) == "a:" + name

    def test_empty_value(self):
        assert self._get()("master:", "") == "master:"

    def test_service_prefix(self):
        result = self._get()("service:", "Стрижка + борода")
        assert result.startswith("service:")
        assert len(result.encode("utf-8")) <= 62

    def test_admin_long_prefix(self):
        result = self._get()("admin_service_detail:", "Камуфляж седины")
        assert result.startswith("admin_service_detail:")
        assert len(result.encode("utf-8")) <= 62

    def test_returns_string(self):
        assert isinstance(self._get()("p:", "val"), str)


class TestMainMenuKb:

    def _buttons(self):
        from keyboards import main_menu_kb
        kb = main_menu_kb()
        return [btn for row in kb.inline_keyboard for btn in row]

    def test_has_invite_friend(self):
        cbs = [b.callback_data for b in self._buttons()]
        assert "invite_friend" in cbs

    def test_all_buttons_no_raw_emoji(self):
        for btn in self._buttons():
            for ch in btn.text:
                cp = ord(ch)
                is_emoji = (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or cp == 0xFE0F
                assert not is_emoji, f"Emoji '{ch}' in '{btn.text}'  cb={btn.callback_data}"

    def test_invite_friend_text_no_emoji(self):
        btn = next(b for b in self._buttons() if b.callback_data == "invite_friend")
        for ch in btn.text:
            cp = ord(ch)
            assert not (0x1F300 <= cp <= 0x1FAFF), f"Emoji in invite_friend button: '{ch}'"

    def test_expected_callbacks_present(self):
        cbs = {b.callback_data for b in self._buttons()}
        expected = {"book", "my_bookings", "prices", "masters", "contacts", "invite_friend", "call"}
        assert expected == cbs

    def test_is_inline_keyboard_markup(self):
        from keyboards import main_menu_kb
        from aiogram.types import InlineKeyboardMarkup
        assert isinstance(main_menu_kb(), InlineKeyboardMarkup)
