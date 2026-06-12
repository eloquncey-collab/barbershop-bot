from emoji_config import E
from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import MASTERS, SERVICES
import config
import messages
import storage


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Записаться", callback_data="book")],
        [
            InlineKeyboardButton(text="Мои записи", callback_data="my_bookings"),
            InlineKeyboardButton(text="Услуги и цены", callback_data="prices")
        ],
        [
            InlineKeyboardButton(text="Наши мастера", callback_data="masters"),
            InlineKeyboardButton(text="Контакты", callback_data="contacts")
        ],
        [InlineKeyboardButton(text="Позвонить", callback_data="call")],
    ])


def masters_kb() -> InlineKeyboardMarkup:
    buttons = []
    master_list = list(MASTERS.keys())
    for i in range(0, len(master_list), 2):
        row = []
        for j in range(i, min(i + 2, len(master_list))):
            name = master_list[j]
            info = MASTERS[name]
            exp = info.get("experience", "")
            years = exp.split()[0] if exp and " " in exp else exp[:4] if exp else ""
            # Task 5: всегда имя в callback_data (не индекс) — индекс ломался при изменении списка мастеров
            # Для отображения текст кнопки обрезаем длинные имена (max 40 байт UTF-8 = ~20 кириллицей)
            display_name = name if len(name.encode("utf-8")) <= 40 else name.encode("utf-8")[:18].decode("utf-8", errors="ignore") + "…"
            row.append(InlineKeyboardButton(text=f"{display_name} • {years} л.", callback_data=f"master:{name}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def services_kb(master_name: str = "", back: str = "main_menu") -> InlineKeyboardMarkup:
    if master_name:
        service_list = await storage.get_master_services(master_name)
        master_prices = await storage.get_all_master_service_prices(master_name)
    else:
        service_list = list(SERVICES.keys())
        master_prices = {}
    buttons = []
    for name in service_list:
        price = master_prices.get(name, SERVICES.get(name, 0))
        display = (name[:16] + "…") if len(name.encode("utf-8")) > 35 else name
        badge = (f"☆ {price:,} ₸" if name in master_prices else f"{price:,} ₸").replace(",", " ")
        buttons.append([InlineKeyboardButton(text=f"{display} — {badge}", callback_data=f"service:{name}")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_date(date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = messages.WEEKDAYS[d.weekday()]
        month = messages.MONTHS[d.month - 1]
        return f"{weekday}, {d.day} {month}"
    except Exception:
        return date_str


def dates_kb(dates: list[str], back: str = "back_to_service") -> InlineKeyboardMarkup:
    buttons = []
    for i in range(0, len(dates), 2):
        row = []
        for j in range(i, min(i + 2, len(dates))):
            d = dates[j]
            row.append(InlineKeyboardButton(text=_format_date(d), callback_data=f"date:{d}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def time_slots_kb(slots: dict[str, str], back: str = "back_to_date") -> InlineKeyboardMarkup:
    buttons = []
    free_slots = [(time_str, status) for time_str, status in slots.items() if status == "free"]
    # BUG-011 FIX: Improved no_slots handling with waitlist option
    if not free_slots:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Нет свободных слотов", callback_data="no_slots")],
            [InlineKeyboardButton(text="Встать в лист ожидания", callback_data="go_to_waitlist")],
            [InlineKeyboardButton(text="Назад", callback_data=back)]
        ])
    for i in range(0, len(free_slots), 4):
        row = []
        for time_str, status in free_slots[i:i+4]:
            row.append(InlineKeyboardButton(text=time_str, callback_data=f"time:{time_str}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить", callback_data="confirm")],
        [
            InlineKeyboardButton(text="Изменить", callback_data="back_to_master"),
            InlineKeyboardButton(text="Отменить", callback_data="cancel_booking")
        ],
    ])


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад в меню", callback_data="main_menu")],
    ])


# UX-1 FIX: booking_id optional - adds quick cancel button
def booking_success_kb(booking_id: str = None) -> InlineKeyboardMarkup:
    buttons = []
    if booking_id:
        buttons.append([InlineKeyboardButton(
            text="Отменить запись",
            callback_data=f"ask_cancel:{booking_id}"
        )])
    buttons.append([InlineKeyboardButton(text="Мои записи", callback_data="my_bookings")])
    buttons.append([InlineKeyboardButton(text="Назад в меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def bookings_list_kb(bookings: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for b in bookings:
        date_str = _format_date(b["date"])
        buttons.append([InlineKeyboardButton(
            text="{} {} — {}".format(date_str, b["time"], b["master"]),
            callback_data="booking_detail:{}".format(b["id"])
        )])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def booking_detail_kb(booking_id: str) -> InlineKeyboardMarkup:
    # TASK-06: Two-step cancellation - first show warning, then confirm
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отменить запись", callback_data=f"ask_cancel:{booking_id}")],
        [InlineKeyboardButton(text="Мои записи", callback_data="my_bookings")],
        [InlineKeyboardButton(text="Назад", callback_data="main_menu")],
    ])


def confirm_cancel_kb(booking_id: str) -> InlineKeyboardMarkup:
    # TASK-06: Confirmation step for booking cancellation
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, отменить", callback_data=f"confirm_cancel:{booking_id}")],
        [InlineKeyboardButton(text="Нет, вернуться", callback_data=f"booking_detail:{booking_id}")],
    ])


def phone_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Поделиться номером", request_contact=True)],
    ], resize_keyboard=True, one_time_keyboard=True)


def review_kb(booking_id: str) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    labels = ["1 ⭐", "2 ⭐⭐", "3 ⭐⭐⭐", "4 ⭐⭐⭐⭐", "5 ⭐⭐⭐⭐⭐"]
    for i, label in enumerate(labels, start=1):
        row.append(InlineKeyboardButton(text=label, callback_data=f"review:{booking_id}:{i}"))
    buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def remind_kb(booking_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Приду", callback_data=f"remind_confirm:{booking_id}")],
        [InlineKeyboardButton(text="Отменить запись", callback_data=f"remind_cancel:{booking_id}")],
    ])


def remind_cancel_kb(booking_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отменить запись", callback_data=f"remind_cancel:{booking_id}")],
    ])


def remind_2h_kb(booking_id: str) -> InlineKeyboardMarkup:
    """2ч — только подтверждение, кнопка отмены убрана"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Буду!", callback_data=f"remind_confirm:{booking_id}")],
    ])


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Статистика", callback_data="admin_stats"),
            InlineKeyboardButton(text="Записи", callback_data="admin_bookings")
        ],
        [
            InlineKeyboardButton(text="Мастера", callback_data="admin_masters"),
            InlineKeyboardButton(text="Услуги", callback_data="admin_services")
        ],
        [
            InlineKeyboardButton(text="Настройки", callback_data="admin_settings"),
            InlineKeyboardButton(text="Ожидание", callback_data="admin_waitlist")
        ],
        [
            InlineKeyboardButton(text="Отзывы", callback_data="admin_reviews"),
            InlineKeyboardButton(text="Лояльность", callback_data="admin_loyalty")
        ],
        [
            InlineKeyboardButton(text="Рефералы", callback_data="admin_referrals"),
            InlineKeyboardButton(text="Экспорт CSV", callback_data="admin_export")
        ],
        [InlineKeyboardButton(text="Назад", callback_data="main_menu")],
    ])


def admin_masters_kb() -> InlineKeyboardMarkup:
    buttons = []
    master_list = list(config.MASTERS.keys())
    for i in range(0, len(master_list), 2):
        row = []
        for j in range(i, min(i + 2, len(master_list))):
            name = master_list[j]
            row.append(InlineKeyboardButton(text=name, callback_data=f"admin_master_detail:{name}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Добавить мастера", callback_data="admin_add_master")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_master_detail_kb(name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Редактировать", callback_data=f"admin_edit_master:{name}")],
        [InlineKeyboardButton(text="Расписание", callback_data=f"master_schedule:{name}")],
        [InlineKeyboardButton(text="Услуги", callback_data=f"master_services:{name}")],
        [InlineKeyboardButton(text="Цены мастера", callback_data=f"master_prices:{name}")],
        [InlineKeyboardButton(text="Telegram ID", callback_data=f"admin_set_master_tg:{name}")],
        [InlineKeyboardButton(text="Удалить", callback_data=f"admin_remove_master:{name}")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_masters")],
    ])


def admin_services_kb() -> InlineKeyboardMarkup:
    buttons = []
    for service, price in config.SERVICES.items():
        buttons.append([InlineKeyboardButton(text=f"{service} — {price:,} ₸".replace(",", " "), callback_data=f"admin_service_detail:{service}")])
    buttons.append([InlineKeyboardButton(text="Добавить услугу", callback_data="admin_add_service")])
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_service_detail_kb(name: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Редактировать", callback_data=f"admin_edit_service:{name}")],
        [InlineKeyboardButton(text="Удалить", callback_data=f"admin_remove_service:{name}")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_services")],
    ])


def admin_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Адрес", callback_data="admin_change_address")],
        [InlineKeyboardButton(text="Телефон", callback_data="admin_change_phone")],
        [InlineKeyboardButton(text="Часы работы", callback_data="admin_change_hours")],
        [InlineKeyboardButton(text="Назад", callback_data="admin")],
    ])


def admin_cancel_booking_kb(booking_id: str) -> InlineKeyboardMarkup:
    # HIGH-7 FIX: кнопка "Отменить" теперь ведёт в диалог подтверждения
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отменить запись", callback_data=f"admin_pre_cancel:{booking_id}")],
        [InlineKeyboardButton(text="Завершить запись", callback_data=f"admin_complete_booking:{booking_id}")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_bookings")],
    ])


def skip_comment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить", callback_data="skip_comment")],
    ])


def cancel_bookings_kb(bookings: list) -> InlineKeyboardMarkup:
    """Keyboard to cancel one of active bookings (for /cancel command)."""
    buttons = []
    for b in bookings:
        date_str = _format_date(b['date'])
        label = f"{date_str} {b['time']} — {b['master'][:12]}"
        buttons.append([InlineKeyboardButton(
            text=f"❌ {label}",
            callback_data=f"cancel_book:{b['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="← Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
