import re
import html
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import messages
import keyboards
import config
import storage
import scheduler
from tz_utils import get_now, get_today, is_past
from emoji_config import E, P
from handlers.start import ContactStates

logger = logging.getLogger(__name__)

router = Router()



class BookingStates(StatesGroup):
    choose_master = State()
    choose_service = State()
    choose_date = State()
    choose_time = State()
    enter_name = State()
    confirm = State()
    enter_review_comment = State()


async def _get_next_dates(master_name: str = "", count: int = 14) -> list[str]:
    today = get_now(config.TIMEZONE).date()
    work_days = []
    if master_name:
        work_days = await storage.get_master_work_days(master_name)
    else:
        work_days = [1, 2, 3, 4, 5, 6]  # пн-сб по умолчанию

    dates = []
    checked = 0
    i = 0
    while len(dates) < count and checked < 60:
        d = today + timedelta(days=i)
        # isoweekday(): пн=1 ... вс=7
        if d.isoweekday() in work_days:
            dates.append(d.strftime("%Y-%m-%d"))
        i += 1
        checked += 1
    return dates


def _generate_time_slots(date_str: str) -> list[str]:
    from datetime import datetime
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return config.TIME_SLOTS
    weekday = d.weekday()
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    day_name = day_names[weekday]
    hours = config.WORKING_HOURS.get(day_name, (10, 21))
    start_h, end_h = hours
    slots = []
    for h in range(start_h, end_h + 1):
        slots.append(f"{h:02d}:00")
        if h < end_h:
            slots.append(f"{h:02d}:30")
    return slots


async def _get_available_slots(date_str: str, master: str) -> dict[str, str]:
    slots = {}
    booked = set()
    if date_str:
        try:
            booked_slots = await storage.get_booked_slots(date_str, master)
            booked = {s["time"] for s in booked_slots}
        except Exception as e:
            logger.error(f"Failed to get booked slots: {e}")
        # MED-07 FIX: Also mark slot_locks as busy so user doesn't see a slot
        # as free while another user is in the booking process (5-min TTL)
        try:
            import aiosqlite
            from tz_utils import get_now as _get_now
            now_iso = _get_now(config.TIMEZONE).isoformat()
            async with aiosqlite.connect(config.DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT time FROM slot_locks WHERE date=? AND master=? AND expires_at > ?",
                    (date_str, master, now_iso)
                )
                locked_rows = await cursor.fetchall()
                for row in locked_rows:
                    booked.add(row[0])
        except Exception as e:
            logger.warning(f"Failed to check slot_locks: {e}")
    time_slots = _generate_time_slots(date_str)

    # BUG-A FIX: Filter past time slots for today's date
    now = get_now(config.TIMEZONE)
    today_str = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")

    for t in time_slots:
        if t in booked:
            slots[t] = "busy"
        elif date_str == today_str and t <= current_time:
            pass
        else:
            slots[t] = "free"
    return slots


@router.callback_query(F.data == "book")
async def cb_book(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id

    # TASK-10: Check if user has phone number, ask if not
    user = await storage.get_user(telegram_id)
    if not user or not user.get("phone"):
        text = "<b>Для записи укажите номер телефона</b>\n\n"
        text += "Введите ваш номер телефона (например: +7 700 123 45 67)\n"
        text += f"или нажмите кнопку «{E.MOBILE} Поделиться номером»"
        try:
            await callback.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Поделиться номером", callback_data="share_phone")],
                    [InlineKeyboardButton(text="Назад", callback_data="main_menu")]
                ]),
                parse_mode="HTML"
            )
        except Exception:
            await callback.message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="Поделиться номером", callback_data="share_phone")],
                    [InlineKeyboardButton(text="Назад", callback_data="main_menu")]
                ]),
                parse_mode="HTML"
            )
        await state.set_state(ContactStates.waiting_contact)
        await callback.answer()
        return

    if await storage.has_active_booking(telegram_id):
        try:
            await callback.message.edit_text(
                messages.ONE_ACTIVE_BOOKING,
                reply_markup=keyboards.back_to_main_kb(),
                parse_mode="HTML"
            )
        except Exception:
            await callback.message.answer(
                messages.ONE_ACTIVE_BOOKING,
                reply_markup=keyboards.back_to_main_kb(),
                parse_mode="HTML"
            )
        await callback.answer()
        return

    # HIGH-002 FIX: DB-based rate limit (persists across restarts)
    if not await storage.user_rate_limit_check(
        telegram_id, window=config.RATE_LIMIT_WINDOW, max_attempts=config.MAX_BOOKING_ATTEMPTS
    ):
        try:
            await callback.message.edit_text(
                messages.RATE_LIMIT,
                reply_markup=keyboards.back_to_main_kb(),
                parse_mode="HTML",
            )
        except Exception:
            await callback.message.answer(
                messages.RATE_LIMIT,
                reply_markup=keyboards.back_to_main_kb(),
                parse_mode="HTML",
            )
        await callback.answer()
        return

    await state.set_state(BookingStates.choose_master)
    try:
        await callback.message.edit_text(
            messages.CHOOSE_MASTER,
            reply_markup=keyboards.masters_kb(),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            messages.CHOOSE_MASTER,
            reply_markup=keyboards.masters_kb(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("master:"), BookingStates.choose_master)
async def cb_choose_master(callback: CallbackQuery, state: FSMContext):
    master_key = callback.data.split(":", 1)[1]
    
    # Handle both index-based and name-based callbacks
    master_name = None
    if master_key.isdigit():
        # Index-based lookup
        idx = int(master_key)
        master_list = list(config.MASTERS.keys())
        if 0 <= idx < len(master_list):
            master_name = master_list[idx]
    else:
        # Name-based lookup
        master_name = master_key
    
    if not master_name or master_name not in config.MASTERS:
        await callback.answer(f"{P.CROSS} Мастер не найден", show_alert=True)
        return
    
    master_info = config.MASTERS[master_name]
    await state.update_data(master=master_name)
    await state.set_state(BookingStates.choose_service)
    
    text = messages.master_selected(
        master_name,
        master_info['experience'],
        master_info['specialization']
    )
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=await keyboards.services_kb(master_name=master_name),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=await keyboards.services_kb(master_name=master_name),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("service:"), BookingStates.choose_service)
async def cb_choose_service(callback: CallbackQuery, state: FSMContext):
    service_key = callback.data.split(":", 1)[1]
    
    # Handle both index-based and name-based callbacks
    service_name = None
    if service_key.isdigit():
        # Index-based lookup
        idx = int(service_key)
        service_items = list(config.SERVICES.items())
        if 0 <= idx < len(service_items):
            service_name, price = service_items[idx]
    else:
        # Name-based lookup
        service_name = service_key
        price = config.SERVICES.get(service_name)
    
    if not service_name or service_name not in config.SERVICES:
        await callback.answer(f"{P.CROSS} Услуга не найдена", show_alert=True)
        return
    
    price = config.SERVICES.get(service_name, 0)
    await state.update_data(service=service_name, price=price)
    await state.set_state(BookingStates.choose_date)
    data = await state.get_data()
    dates = await _get_next_dates(master_name=data.get("master", ""))
    
    text = messages.service_selected(service_name, price)
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboards.dates_kb(dates),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=keyboards.dates_kb(dates),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("date:"), BookingStates.choose_date)
async def cb_choose_date(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":", 1)[1]
    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        await callback.answer(f"{P.CROSS} Неверная дата", show_alert=True)
        return
    
    # Validate date is not in the past (timezone-aware)
    today = get_now(config.TIMEZONE).date()
    if selected_date < today:
        await callback.answer(f"{P.CROSS} Нельзя выбрать прошедшую дату", show_alert=True)
        return

    # MED-03 FIX: Reject dates beyond allowed booking horizon (60 days)
    MAX_DAYS_AHEAD = 60
    from datetime import timedelta as _td
    if selected_date > today + _td(days=MAX_DAYS_AHEAD):
        await callback.answer(f"{P.CROSS} Нельзя записаться более чем на {MAX_DAYS_AHEAD} дней вперёд", show_alert=True)
        return
    
    await state.update_data(date=date_str)
    await state.set_state(BookingStates.choose_time)
    data = await state.get_data()
    master = data["master"]
    
    try:
        slots = await _get_available_slots(date_str, master)
    except Exception as e:
        logger.error(f"Failed to get available slots: {e}")
        slots = {t: "free" for t in _generate_time_slots(date_str)}
    
    # BUG-E FIX: Check if there are any free slots
    free_count = sum(1 for status in slots.values() if status == "free")
    busy_count = sum(1 for status in slots.values() if status == "busy")
    
    if not any(v == "free" for v in slots.values()):
        await callback.answer(
            "На сегодня свободных слотов нет. Выберите другой день.",
            show_alert=True
        )
        return
    
    date_formatted = keyboards._format_date(date_str)
    text = messages.date_selected(date_formatted)
    text = text.replace("Выберите свободный слот:", f"Свободно: {free_count} | Занято: {busy_count}\n\nВыберите свободный слот:")
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboards.time_slots_kb(slots),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=keyboards.time_slots_kb(slots),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("time:"), BookingStates.choose_time)
async def cb_choose_time(callback: CallbackQuery, state: FSMContext):
    time_str = callback.data.split(":", 1)[1]
    data = await state.get_data()
    date_str = data.get("date", "")
    master = data.get("master", "")
    
    # TASK-08: Check slot availability before accepting time selection
    try:
        available_slots = await _get_available_slots(date_str, master)
        slot_status = available_slots.get(time_str)
        
        if slot_status != "free":
            await callback.answer(
                f"{E.CROSS} Этот слот уже занят! Пожалуйста, выберите другое время.",
                show_alert=True
            )
            # Refresh the slots display
            slots = await _get_available_slots(date_str, master)
            free_count = sum(1 for status in slots.values() if status == "free")
            busy_count = sum(1 for status in slots.values() if status == "busy")
            
            date_formatted = keyboards._format_date(date_str)
            text = messages.date_selected(date_formatted)
            text = text.replace("Выберите свободный слот:", f"Свободно: {free_count} | Занято: {busy_count}\n\nВыберите свободный слот:")
            
            try:
                await callback.message.edit_text(
                    text,
                    reply_markup=keyboards.time_slots_kb(slots),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return
    except Exception as e:
        logger.error(f"Failed to verify slot availability: {e}")
    
    available_slots = _generate_time_slots(data.get("date", ""))
    if time_str not in available_slots:
        await callback.answer(f"{P.CROSS} Неверное время", show_alert=True)
        return
    await state.update_data(time=time_str)
    await state.set_state(BookingStates.enter_name)
    
    # UX-002 FIX: Step 5 — шаг с подсказкой имени
    data_so_far = await state.get_data()
    text = f"{E.LIST} <b>Шаг 5 из 5 — Ваше имя</b>\n\n"
    text += f"Вы записываетесь:\n"
    text += f"{E.SCISSORS} {html.escape(data_so_far.get('master',''))} — {html.escape(data_so_far.get('service',''))}\n"
    text += f"{E.CALENDAR} {keyboards._format_date(data_so_far.get('date',''))} в {time_str}\n\n"
    text += f"{E.USER} <b>Как к вам обращаться?</b>\n"
    text += "Введите имя текстом ответным сообщением. Только буквы, без цифр и спецсимволов."

    tg_name = callback.from_user.first_name or ""
    await state.update_data(tg_name_suggestion=tg_name)
    name_rows = []
    if tg_name and re.match(r'^[a-zA-Zа-яА-ЯёЁ\s\-\']+$', tg_name) and re.search(r'[a-zA-Zа-яА-ЯёЁ]', tg_name) and len(tg_name) <= 50:
        name_rows.append([InlineKeyboardButton(text=f"Использовать «{tg_name}»", callback_data="use_tg_name")])
    name_rows.append([InlineKeyboardButton(text="Назад к времени", callback_data="back_to_time")])
    name_rows.append([InlineKeyboardButton(text="Отменить", callback_data="cancel_booking")])
    back_kb = InlineKeyboardMarkup(inline_keyboard=name_rows)
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=back_kb,
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=back_kb,
            parse_mode="HTML"
        )
    await callback.answer()




@router.callback_query(F.data == "use_tg_name", BookingStates.enter_name)
async def cb_use_tg_name(callback: CallbackQuery, state: FSMContext):
    """Use Telegram first_name as booking name"""
    data = await state.get_data()
    name = data.get("tg_name_suggestion", "")
    if not name:
        await callback.answer(f"{P.CROSS} Имя не найдено, введите вручную", show_alert=True)
        return
    await state.update_data(name=name)
    await state.set_state(BookingStates.confirm)
    data = await state.get_data()
    date_str_fmt = keyboards._format_date(data.get("date",""))
    price = data.get("price",0)
    text = f"{E.LIST} <b>Подтверждение записи</b>\n\n"
    text += f"<b>Ваш выбор:</b>\n"
    text += f"{E.USER} <b>Имя:</b> {html.escape(name)}\n"
    text += f"{E.SCISSORS} <b>Мастер:</b> {html.escape(data.get('master',''))}\n"
    text += f"{E.BARBER} <b>Услуга:</b> {html.escape(data.get('service',''))} - {price:,} ₸\n".replace(","," ")
    text += f"{E.CALENDAR} <b>Дата:</b> {date_str_fmt} в {data.get('time','')}\n\n"
    text += "Всё верно?"
    try:
        await callback.message.edit_text(text, reply_markup=keyboards.confirm_kb(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=keyboards.confirm_kb(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("waitlist:"), BookingStates.choose_time)
async def cb_waitlist(callback: CallbackQuery, state: FSMContext):
    time_str = callback.data.split(":", 1)[1]
    data = await state.get_data()
    telegram_id = callback.from_user.id
    
    # BUG-012: Check if user already in waitlist for this slot
    existing_waitlist = await storage.get_waitlist_for_slot(data["date"], time_str, data["master"])
    if any(wl["telegram_id"] == telegram_id and wl["status"] == "waiting" for wl in existing_waitlist):
        try:
            await callback.message.edit_text(
                f"{E.WARNING} Вы уже в листе ожидания на это время.\n\n"
                f"Мы уведомим вас, если слот освободится.",
                reply_markup=keyboards.back_to_main_kb(),
                parse_mode="HTML"
            )
        except Exception:
            await callback.message.answer(
                f"{E.WARNING} Вы уже в листе ожидания на это время.\n\n"
                f"Мы уведомим вас, если слот освободится.",
                reply_markup=keyboards.back_to_main_kb(),
                parse_mode="HTML"
            )
        await callback.answer()
        return
    
    await storage.add_to_waitlist(
        telegram_id=telegram_id,
        name=callback.from_user.first_name or "",
        master=data["master"],
        service=data["service"],
        date=data["date"],
        time=time_str,
    )
    try:
        await callback.message.edit_text(
            messages.WAITLIST_ADDED.format(date=keyboards._format_date(data["date"]), time=time_str),
            reply_markup=keyboards.back_to_main_kb(),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            messages.WAITLIST_ADDED.format(date=keyboards._format_date(data["date"]), time=time_str),
            reply_markup=keyboards.back_to_main_kb(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.message(BookingStates.enter_name)
async def handle_enter_name(message: Message, state: FSMContext):
    
    if not message.text or not message.text.strip():
        await message.answer(f"{E.CROSS} Пожалуйста, введите имя текстом.", parse_mode="HTML")
        return
    name = message.text.strip()
    
    # BUG-023: Improved name validation - must contain at least one letter
    # Matches: Анна, Анна-Мария, O'Brien, Jean-Claude, Мария Ивановна
    # Rejects: "12", "---", "   "
    if not name or len(name) > 50:
        await message.answer(f"{E.CROSS} Имя должно содержать от 1 до 50 символов.", parse_mode="HTML")
        return
    
    # Allow letters, spaces, hyphens, and apostrophes
    if not re.match(r'^[a-zA-Zа-яА-ЯёЁ\s\-\']+$', name):
        await message.answer(f"{E.CROSS} Имя может содержать только буквы, пробелы, дефисы и апострофы.", parse_mode="HTML")
        return
    
    # BUG-023: Ensure at least one letter is present
    if not re.search(r'[a-zA-Zа-яА-ЯёЁ]', name):
        await message.answer(f"{E.CROSS} Имя должно содержать хотя бы одну букву.", parse_mode="HTML")
        return
    
    await state.update_data(name=name)
    await state.set_state(BookingStates.confirm)
    data = await state.get_data()
    
    # BUG-019 FIX: Add booking summary for better UX
    date_str = keyboards._format_date(data["date"])
    text = f"{E.LIST} <b>Подтверждение записи</b>\n\n"
    text += f"<b>Ваш выбор:</b>\n"
    text += f"{E.USER} <b>Имя:</b> {html.escape(name)}\n"
    text += f"{E.SCISSORS} <b>Мастер:</b> {html.escape(data['master'])}\n"
    text += f"{E.BARBER} <b>Услуга:</b> {html.escape(data['service'])} — {data['price']:,} ₸\n".replace(",", " ")
    text += f"{E.CALENDAR} <b>Дата:</b> {date_str} в {data['time']}\n\n"
    text += "Всё верно?"
    
    await message.answer(text, reply_markup=keyboards.confirm_kb(), parse_mode="HTML")


@router.callback_query(F.data == "confirm", BookingStates.confirm)
async def cb_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    telegram_id = callback.from_user.id

    booking = {
        "date": data["date"],
        "time": data["time"],
        "name": data["name"],
        "telegram_id": telegram_id,
        "username": callback.from_user.username or "",
        "master": data["master"],
        "service": data["service"],
        "price": data["price"],
    }

    try:
        booking_id = await storage.save_booking(booking)
    except Exception as e:
        logger.error(f"Failed to save booking: {e}")
        await callback.message.edit_text(messages.ERROR, reply_markup=keyboards.back_to_main_kb(), parse_mode="HTML")
        await callback.answer()
        return

    if not booking_id:
        await callback.message.edit_text(
            messages.SLOT_BUSY,
            reply_markup=keyboards.back_to_main_kb(),
            parse_mode="HTML",
        )
        await state.set_state(BookingStates.choose_time)
        await callback.answer()
        return
    
    # TASK-03: Loyalty update removed from here - moved to admin_complete_booking (only real visit = bonus)
    
    date_str = keyboards._format_date(booking["date"])
    text = f"{E.CHECK} Запись подтверждена!\n\n"
    text += f"{E.CALENDAR} {date_str} в {booking['time']}\n"
    text += f"{E.SCISSORS} {html.escape(booking['master'])}\n"
    text += f"{E.LIST} {html.escape(booking['service'])} — {booking['price']:,} ₸\n\n".replace(",", " ")
    text += f"{E.LOCATION} {html.escape(config.BARBERSHOP_ADDRESS)}\n\n"
    text += "Напоминания:\n"
    text += "• За 24 часа до визита\n"
    text += "• За 2 часа до визита\n\n"
    text += f"{E.INFO} <i>Бонус лояльности засчитывается после завершения визита.</i>"
    
    await callback.message.edit_text(text, reply_markup=keyboards.booking_success_kb(),
            parse_mode="HTML"
        )

    admin_text = messages.ADMIN_BOOKING_NOTIFY.format(
        name=html.escape(booking["name"]),
        master=html.escape(booking["master"]),
        service=html.escape(booking["service"]),
        date=keyboards._format_date(booking["date"]),
        time=booking["time"],
        price=booking["price"],
    )
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

    master_name = booking["master"]
    if master_name in config.MASTER_IDS:
        try:
            await bot.send_message(config.MASTER_IDS[master_name], admin_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify master {master_name}: {e}")



    # Schedule reminders with booking_id directly
    booking_with_id = booking.copy()
    booking_with_id["id"] = booking_id
    await scheduler.schedule_reminders(bot, booking_with_id)

    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "cancel_booking")
async def cb_cancel_booking(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    # UX-005 FIX: Book again button after cancellation from FSM flow
    book_again_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Записаться снова", callback_data="book")],
        [InlineKeyboardButton(text="Главное меню", callback_data="main_menu")],
    ])
    await callback.message.edit_text(
        messages.BOOKING_CANCELLED,
        reply_markup=book_again_kb,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_master")
async def cb_back_to_master(callback: CallbackQuery, state: FSMContext):
    # Clear FSM data when going back
    await state.update_data(service=None, date=None, time=None, name=None)
    await state.set_state(BookingStates.choose_master)
    try:
        await callback.message.edit_text(
            messages.CHOOSE_MASTER,
            reply_markup=keyboards.masters_kb(),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            messages.CHOOSE_MASTER,
            reply_markup=keyboards.masters_kb(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "back_to_service")
async def cb_back_to_service(callback: CallbackQuery, state: FSMContext):
    # Clear FSM data when going back
    await state.update_data(date=None, time=None, name=None)
    await state.set_state(BookingStates.choose_service)
    data = await state.get_data()
    try:
        await callback.message.edit_text(
            messages.CHOOSE_SERVICE,
            reply_markup=await keyboards.services_kb(master_name=data.get("master", "")),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            messages.CHOOSE_SERVICE,
            reply_markup=await keyboards.services_kb(master_name=data.get("master", "")),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "back_to_date")
async def cb_back_to_date(callback: CallbackQuery, state: FSMContext):
    # BUG-013: Clear FSM data when going back
    await state.update_data(time=None, name=None)
    await state.set_state(BookingStates.choose_date)
    data = await state.get_data()
    dates = await _get_next_dates(master_name=data.get("master", ""))
    
    text = messages.CHOOSE_DATE
    if data.get("service"):
        # Добавляем информацию о выбранной услуге
        text = f"{E.CHECK} {data['service']} — {data.get('price', 0):,} ₸\n\n".replace(",", " ") + text
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboards.dates_kb(dates),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=keyboards.dates_kb(dates),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "back_to_time")
async def cb_back_to_time(callback: CallbackQuery, state: FSMContext):
    # BUG-013: Clear FSM data when going back AND refresh slots
    await state.update_data(name=None)
    await state.set_state(BookingStates.choose_time)
    data = await state.get_data()
    
    # Refresh slots from DB
    slots = await _get_available_slots(data.get("date", ""), data.get("master", ""))
    free_count = sum(1 for status in slots.values() if status == "free")
    busy_count = sum(1 for status in slots.values() if status == "busy")
    
    date_formatted = keyboards._format_date(data.get('date', ''))
    text = messages.date_selected(date_formatted)
    text = text.replace("Выберите свободный слот:", f"Свободно: {free_count} | Занято: {busy_count}\n\nВыберите свободный слот:")
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboards.time_slots_kb(slots),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=keyboards.time_slots_kb(slots),
            parse_mode="HTML"
        )
    await callback.answer()


# BUG-011 FIX: Handle no_slots callback
@router.callback_query(F.data == "no_slots")
async def cb_no_slots(callback: CallbackQuery):
    await callback.answer(
        f"{E.EMPTY} Все слоты на эту дату заняты. Попробуйте выбрать другую дату или встать в лист ожидания.",
        show_alert=True,
    )


@router.callback_query(F.data == "go_to_waitlist")
async def cb_go_to_waitlist(callback: CallbackQuery, state: FSMContext):
    """Navigate user to waitlist - showing busy slots"""
    data = await state.get_data()
    date_str = data.get("date", "")
    master = data.get("master", "")
    
    # Get all slots including busy ones
    slots = await _get_available_slots(date_str, master)
    busy_slots = {k: v for k, v in slots.items() if v == "busy"}
    
    if not busy_slots:
        await callback.answer(f"{P.EMPTY} Нет занятых слотов для листа ожидания", show_alert=True)
        return
    
    text = f"{E.RELOAD} <b>Лист ожидания</b>\n\n"
    text += f"Выберите занятое время, на которое хотите встать в очередь:\n\n"
    text += f"{E.INFO} Мы уведомим вас, если это время освободится."
    
    # Show busy slots with waitlist: callback
    buttons = []
    busy_times = list(busy_slots.keys())
    for i in range(0, len(busy_times), 4):
        row = []
        for time_str in busy_times[i:i+4]:
            row.append(InlineKeyboardButton(text=f"🔴 {time_str}", callback_data=f"waitlist:{time_str}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="back_to_time")])
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data.startswith("remind_confirm:"))
async def cb_remind_confirm(callback: CallbackQuery, bot: Bot):
    booking_id = callback.data.split(":", 1)[1]
    # Notify admins that client confirmed attendance
    try:
        booking = await storage.get_booking_with_user(booking_id)
        if booking:
            notify_text = (
                f"{E.CHECK} <b>Клиент подтвердил визит</b>\n\n"
                f"{E.USER} {html.escape(booking['name'])} — "
                f"{keyboards._format_date(booking['date'])} в {booking['time']}\n"
                f"{E.MASTER} Мастер: {html.escape(booking['master'])}"
            )
            for admin_id in config.ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, notify_text, parse_mode="HTML")
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Failed to notify admin on remind_confirm: {e}")
    try:
        await callback.message.edit_text(f"{E.CHECK} <b>Визит подтверждён. Ждём вас!</b>", parse_mode="HTML")
    except Exception:
        await callback.message.answer(f"{E.CHECK} <b>Визит подтверждён. Ждём вас!</b>", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("remind_cancel:"))
async def cb_remind_cancel(callback: CallbackQuery, bot: Bot):
    booking_id = callback.data.split(":", 1)[1]
    booking = await storage.cancel_booking(booking_id, telegram_id=callback.from_user.id)
    if booking:
        await scheduler.cancel_reminders(booking_id)
        try:
            await callback.message.edit_text(messages.BOOKING_CANCELLED, parse_mode="HTML")
        except Exception:
            await callback.message.answer(messages.BOOKING_CANCELLED, parse_mode="HTML")
        # Уведомляем админа если отмена менее чем за 2 часа
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(config.TIMEZONE)
            visit_dt = datetime.strptime(f"{booking['date']} {booking['time']}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
            now = datetime.now(tz)
            if visit_dt - now <= timedelta(hours=2):
                admin_text = messages.CANCEL_LAST_MINUTE_ADMIN.format(
                    name=html.escape(booking.get("name", "Неизвестно")),
                    date=html.escape(keyboards._format_date(booking["date"])),
                    time=html.escape(booking["time"]),
                    master=html.escape(booking["master"]),
                )
                for admin_id in config.ADMIN_IDS:
                    try:
                        await bot.send_message(admin_id, admin_text, parse_mode="HTML")
                    except Exception as e:
                        logger.error(f"Failed to notify admin {admin_id} last-minute cancel: {e}")
        except Exception as e:
            logger.error(f"Last-minute cancel admin notify error: {e}")

        waitlist = await storage.get_waitlist_for_slot(booking["date"], booking["time"], booking["master"])
        for wl in waitlist:
            try:
                text = messages.WAITLIST_OFFER.format(
                    master=booking["master"],
                    date=keyboards._format_date(booking["date"]),
                    time=booking["time"],
                )
                await bot.send_message(wl["telegram_id"], text)
                await storage.update_waitlist_status(wl["id"], "offered")
            except Exception as e:
                logger.error(f"Failed to notify waitlist {wl['telegram_id']}: {e}")
    else:
        try:
            await callback.message.edit_text("Запись не найдена или уже отменена.", parse_mode="HTML")
        except Exception:
            await callback.message.answer("Запись не найдена или уже отменена.", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("review:"))
async def cb_review(callback: CallbackQuery, state: FSMContext):
    # FIX: Use maxsplit to handle booking_ids containing colons
    parts = callback.data.split(":", 2)  # Split into max 3 parts
    if len(parts) != 3:
        await callback.answer("Ошибка", show_alert=True)
        return
    booking_id = parts[1]
    try:
        rating = int(parts[2])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return
    if rating < 1 or rating > 5:
        await callback.answer("Оценка должна быть от 1 до 5", show_alert=True)
        return
    
    # Save rating in FSM and ask for comment
    await state.update_data(review_booking_id=booking_id, review_rating=rating)
    await state.set_state(BookingStates.enter_review_comment)
    
    stars = f"{E.STAR}" * rating
    text = f"Спасибо за оценку! {stars}\n\n"
    text += f"{E.COMMENT} Хотите оставить комментарий?\n\n"
    text += "Напишите ваш отзыв или нажмите «Пропустить»:"
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=keyboards.skip_comment_kb(),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=keyboards.skip_comment_kb(),
            parse_mode="HTML"
        )
    await callback.answer()


@router.message(BookingStates.enter_review_comment)
async def handle_review_comment(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer(f"{E.CROSS} Пожалуйста, введите комментарий текстом или нажмите «Пропустить».", parse_mode="HTML")
        return
    
    comment = message.text.strip()
    if len(comment) > 500:
        await message.answer(f"{E.CROSS} Комментарий слишком длинный. Максимум 500 символов.", parse_mode="HTML")
        return
    
    data = await state.get_data()
    booking_id = data.get("review_booking_id")
    rating = data.get("review_rating")
    
    if not booking_id or not rating:
        await message.answer(f"{E.CROSS} Ошибка. Попробуйте заново.", parse_mode="HTML")
        await state.clear()
        return
    
    saved = await storage.save_review(booking_id, message.from_user.id, rating, comment)
    if saved:
        await message.answer(
            f"{E.CHECK} Спасибо за подробный отзыв!\n\n"
            f"{E.STAR} Оценка: {rating}/5\n"
            f"{E.COMMENT} Комментарий: {html.escape(comment)}",
            reply_markup=keyboards.back_to_main_kb(),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"{E.WARNING} Вы уже оставляли отзыв на эту запись.",
            reply_markup=keyboards.back_to_main_kb()
        )
    
    await state.clear()


@router.callback_query(F.data == "skip_comment")
async def cb_skip_comment(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    booking_id = data.get("review_booking_id")
    rating = data.get("review_rating")
    
    if not booking_id or not rating:
        await callback.answer(f"{P.CROSS} Ошибка", show_alert=True)
        return
    
    saved = await storage.save_review(booking_id, callback.from_user.id, rating, "")
    if saved:
        try:
            await callback.message.edit_text(
                f"✅ Спасибо за оценку! ⭐ {rating}/5",
                reply_markup=keyboards.back_to_main_kb()
            )
        except Exception:
            await callback.message.answer(
                f"✅ Спасибо за оценку! ⭐ {rating}/5",
                reply_markup=keyboards.back_to_main_kb()
            )
    else:
        try:
            await callback.message.edit_text(
                "⚠️ Вы уже оставляли отзыв на эту запись.",
                reply_markup=keyboards.back_to_main_kb()
            )
        except Exception:
            await callback.message.answer(
                "⚠️ Вы уже оставляли отзыв на эту запись.",
                reply_markup=keyboards.back_to_main_kb()
            )
    
    await state.clear()
    await callback.answer()



