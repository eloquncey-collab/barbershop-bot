import re
import html
import logging
import csv
import os
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import messages
import keyboards
import config
import storage
import scheduler
from utils import send_with_retry, edit_with_retry
from emoji_config import E

logger = logging.getLogger(__name__)

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


class AdminStates(StatesGroup):
    add_master = State()
    edit_master = State()
    add_service = State()
    edit_service = State()
    change_address = State()
    change_phone = State()
    change_hours = State()
    set_master_tg = State()
    set_master_work_days = State()
    set_master_services = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    if not _is_admin(message.from_user.id):
        await send_with_retry(message.bot, message.chat.id, messages.ADMIN_ONLY)
        return
    await send_with_retry(message.bot, message.chat.id, f"{E.LOCK} <b>Панель управления</b>", reply_markup=keyboards.admin_kb(), parse_mode="HTML")


@router.callback_query(F.data == "admin")
async def cb_admin(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    await edit_with_retry(callback.message, f"{E.LOCK} <b>Панель управления</b>", reply_markup=keyboards.admin_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    try:
        stats = await storage.get_stats()
        text = f"{E.CHART} <b>Статистика</b>\n\n"
        text += f"{E.LIST} <b>Всего записей:</b> {stats['total']}\n"
        text += f"{E.CHECK} <b>Активных:</b> {stats['active']}\n"
        text += f"{E.CROSS} <b>Отменённых:</b> {stats['cancelled']}\n"
        text += f"{E.CHECK} <b>Завершённых:</b> {stats['completed']}\n"
        text += f"{E.MONEY} <b>Выручка:</b> {stats['revenue']} ₸\n\n"
        by_master = await storage.get_stats_by_master()
        if by_master:
            text += "По мастерам:\n"
            for m in by_master:
                text += f"  {m['master']}: {m['count']} записей, {m['revenue']} ₸\n"
        by_service = await storage.get_stats_by_service()
        if by_service:
            text += "По услугам:\n"
            for s in by_service:
                text += f"  {s['service']}: {s['count']} записей, {s['revenue']} ₸\n"
        await edit_with_retry(callback.message, text, reply_markup=keyboards.admin_kb(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in admin_stats: {e}")
        try:
            await edit_with_retry(callback.message, messages.ERROR, reply_markup=keyboards.admin_kb(), parse_mode="HTML")
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data == "admin_bookings")
async def cb_admin_bookings(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    await _show_admin_bookings_page(callback, offset=0)

@router.callback_query(F.data.startswith("admin_bookings_page:"))
async def cb_admin_bookings_page(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    try:
        offset = int(callback.data.split(":",1)[1])
    except (ValueError, IndexError):
        offset = 0
    await _show_admin_bookings_page(callback, offset=offset)

async def _show_admin_bookings_page(callback, offset: int = 0):
    PAGE = 5  # CRIT-03 FIX: 5 per page to fit manage buttons within Telegram limits
    try:
        bookings = await storage.get_upcoming_bookings()
        active = [b for b in bookings if b["status"] == "active"]
        total = len(active)
        page_items = active[offset:offset + PAGE]
        text = f"{E.LIST} Активные записи ({total} всего):\n\n"
        for b in page_items:
            text += f"{E.ID} <code>{b['id']}</code>: {keyboards._format_date(b['date'])} {b['time']}\n"
            text += f"   \u2192 {html.escape(b['name'])} / {html.escape(b['master'])}\n"
        if not active:
            text += f"{E.EMPTY} Нет активных записей.\n"
        kb_rows = []
        for b in page_items:
            kb_rows.append([InlineKeyboardButton(
                text=f"\u270f\ufe0f {b['id']} \u2014 {keyboards._format_date(b['date'])} {b['time']}",
                callback_data=f"admin_manage_booking:{b['id']}"
            )])
        nav_buttons = []
        if offset > 0:
            nav_buttons.append(InlineKeyboardButton(text="\u25c4 \u041d\u0430\u0437\u0430\u0434", callback_data=f"admin_bookings_page:{offset - PAGE}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{offset // PAGE + 1}/{(total - 1) // PAGE + 1 if total else 1}", callback_data="noop"))
        if offset + PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="\u0414\u0430\u043b\u044c\u0448\u0435 \u25ba", callback_data=f"admin_bookings_page:{offset + PAGE}"))
        if nav_buttons:
            kb_rows.append(nav_buttons)
        kb_rows.append([InlineKeyboardButton(text="\u041d\u0430\u0437\u0430\u0434 \u0432 \u043f\u0430\u043d\u0435\u043b\u044c", callback_data="admin")])
        await edit_with_retry(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in admin_bookings: {e}")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_manage_booking:"))
async def cb_admin_manage_booking(callback: CallbackQuery):
    """CRIT-03 FIX: show cancel/complete/info screen for a specific booking."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    booking_id = callback.data.split(":", 1)[1]
    try:
        booking = await storage.get_booking_with_user(booking_id)
        if not booking or booking.get("status") != "active":
            await callback.answer("Запись не найдена или уже не активна", show_alert=True)
            return
        text = (
            f"{E.ID} <b>Запись</b> <code>{booking_id}</code>\n\n"
            f"{E.USER} {html.escape(booking['name'])}\n"
            f"{E.SCISSORS} {html.escape(booking['master'])} \u2014 {html.escape(booking['service'])}\n"
            f"{E.CALENDAR} {keyboards._format_date(booking['date'])} \u0432 {booking['time']}\n"
            f"{E.MONEY} {booking['price']} \u20b8"
        )
        await edit_with_retry(
            callback.message, text,
            reply_markup=keyboards.admin_cancel_booking_kb(booking_id),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in admin_manage_booking: {e}")
        await callback.answer("\u041e\u0448\u0438\u0431\u043a\u0430", show_alert=True)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    """HIGH-02 FIX: immediately answer noop (page indicator) to avoid 30s spinner."""
    await callback.answer()


@router.callback_query(F.data == "admin_export")
async def cb_admin_export(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    
    filepath = None
    try:
        bookings = await storage.export_bookings_csv()
        filename = f"bookings_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Use absolute path
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        filepath = scripts_dir / filename
        
        # Cleanup old CSV files (older than 7 days)
        try:
            cutoff = datetime.now() - timedelta(days=7)
            for old_file in scripts_dir.glob("bookings_export_*.csv"):
                try:
                    file_time = datetime.fromtimestamp(old_file.stat().st_mtime)
                    if file_time < cutoff:
                        old_file.unlink()
                        logger.info(f"Deleted old CSV: {old_file.name}")
                except Exception as e:
                    logger.warning(f"Failed to delete old CSV {old_file}: {e}")
        except Exception as e:
            logger.warning(f"Failed to cleanup old CSVs: {e}")
        
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "date", "time", "name", "telegram_id", "username", "master", "service", "price", "status", "created_at"])
            writer.writeheader()
            writer.writerows(bookings)
        
        # Send CSV file to admin
        try:
            file = FSInputFile(str(filepath))
            await callback.message.answer_document(
                document=file,
                caption=f"{E.CHART} Экспорт всех записей\nВсего: {len(bookings)} записей"
            )
            await edit_with_retry(
                callback.message,
                f"{E.CHECK} Экспорт завершён. Файл отправлен выше.",
                reply_markup=keyboards.admin_kb(),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to send CSV file: {e}")
            await edit_with_retry(
                callback.message,
                f"Экспорт завершён. Файл сохранён: {filename}",
                reply_markup=keyboards.admin_kb(),
            )
    except Exception as e:
        logger.error(f"Error in admin_export: {e}")
        try:
            await edit_with_retry(callback.message, messages.ERROR, reply_markup=keyboards.admin_kb())
        except Exception:
            pass
    finally:
        # Delete CSV after sending
        if filepath and Path(filepath).exists():
            try:
                Path(filepath).unlink()
                logger.info(f"Cleaned up CSV file: {filepath}")
            except Exception as e:
                logger.warning(f"Failed to delete CSV file {filepath}: {e}")
    
    await callback.answer()


@router.callback_query(F.data == "admin_masters")
async def cb_admin_masters(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    try:
        text = f"{E.USER} <b>Мастера:</b>\n\nВыберите мастера:"
        if not config.MASTERS:
            text = f"{E.USER} <b>Мастера:</b>\n\n{E.EMPTY} Нет мастеров."
        await edit_with_retry(
            callback.message,
            text,
            reply_markup=keyboards.admin_masters_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in admin_masters: {e}")
    await callback.answer()


@router.callback_query(F.data == "admin_add_master")
async def cb_admin_add_master(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    await state.set_state(AdminStates.add_master)
    await edit_with_retry(callback.message, "Введите данные мастера (Имя, опыт, специализация):")
    await callback.answer()


@router.message(AdminStates.add_master)
async def handle_add_master(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.text or not message.text.strip():
        await send_with_retry(message.bot, message.chat.id, "Введите данные текстом.")
        return
    # FIX: Use maxsplit=2 to allow commas in specialization field
    parts = [p.strip() for p in message.text.split(",", 2)]
    if len(parts) < 3:
        await send_with_retry(message.bot, message.chat.id, "Неверный формат. Введите: Имя, опыт, специализация")
        return
    name, experience, specialization = parts[0], parts[1], parts[2]
    
    # Validate name length
    if not name or len(name.encode("utf-8")) < 1 or len(name.encode("utf-8")) > 40:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Имя мастера должно содержать до 20 символов кириллицей или 40 символов латиницей (лимит Telegram 64 байта).", parse_mode="HTML")
        return
    
    config.MASTERS[name] = {"experience": experience, "specialization": specialization}
    try:
        await storage.save_master(name, experience, specialization)
        await config.save_config_to_db()
    except Exception as e:
        logger.error(f"Failed to save master to DB: {e}")
    await state.clear()
    await send_with_retry(message.bot, message.chat.id, f"Мастер {html.escape(name)} добавлен.", reply_markup=keyboards.admin_kb(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_master_detail:"))
async def cb_admin_master_detail(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    master_name = callback.data.split(":", 1)[1]
    info = config.MASTERS.get(master_name)
    if not info:
        await callback.answer("Мастер не найден", show_alert=True)
        return
    text = f"{master_name}\nОпыт: {info['experience']}\nСпециализация: {info['specialization']}"
    await edit_with_retry(callback.message, text, reply_markup=keyboards.admin_master_detail_kb(master_name))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_edit_master:"))
async def cb_admin_edit_master(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    master_name = callback.data.split(":", 1)[1]
    await state.update_data(master_name=master_name)
    await state.set_state(AdminStates.edit_master)
    await edit_with_retry(callback.message, "Введите новые данные (Имя, опыт, специализация):")
    await callback.answer()


@router.message(AdminStates.edit_master)
async def handle_edit_master(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.text or not message.text.strip():
        await send_with_retry(message.bot, message.chat.id, "Введите данные текстом.")
        return
    data = await state.get_data()
    master_name = data["master_name"]
    # FIX: Use maxsplit=2 to allow commas in specialization field
    parts = [p.strip() for p in message.text.split(",", 2)]
    if len(parts) < 3:
        await send_with_retry(message.bot, message.chat.id, "Неверный формат. Введите: Имя, опыт, специализация")
        return
    name, experience, specialization = parts[0], parts[1], parts[2]
    
    # Validate name length
    if not name or len(name.encode("utf-8")) < 1 or len(name.encode("utf-8")) > 40:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Имя мастера должно содержать до 20 символов кириллицей или 40 символов латиницей (лимит Telegram 64 байта).", parse_mode="HTML")
        return
    
    if master_name in config.MASTERS:
        del config.MASTERS[master_name]
    config.MASTERS[name] = {"experience": experience, "specialization": specialization}
    try:
        await storage.remove_master(master_name)
        await storage.save_master(name, experience, specialization)
        await config.save_config_to_db()
    except Exception as e:
        logger.error(f"Failed to update master in DB: {e}")
    await state.clear()
    await send_with_retry(message.bot, message.chat.id, f"Мастер {html.escape(name)} обновлён.", reply_markup=keyboards.admin_kb(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_remove_master:"))
async def cb_admin_remove_master(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    master_name = callback.data.split(":", 1)[1]
    
    # Check if master has active bookings
    try:
        stats = await storage.get_master_stats(master_name)
        if stats and stats.get("active", 0) > 0:
            await callback.answer(
                f"Невозможно удалить мастера {master_name}: у него есть {stats['active']} активных записей. Сначала завершите или отмените их.",
                show_alert=True
            )
            return
    except Exception as e:
        logger.error(f"Failed to check master stats: {e}")
    
    if master_name in config.MASTERS:
        del config.MASTERS[master_name]
        try:
            await storage.remove_master(master_name)
        except Exception as e:
            logger.error(f"Failed to remove master from DB: {e}")
        await edit_with_retry(callback.message, f"{E.CROSS} Мастер {master_name} удалён.", reply_markup=keyboards.admin_kb(), parse_mode="HTML")
    else:
        await callback.answer("Мастер не найден", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data == "admin_services")
async def cb_admin_services(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    try:
        services_text = ""
        for service, price in config.SERVICES.items():
            services_text += f"{E.SCISSORS} {service}: {price} ₸\n"
        await edit_with_retry(
            callback.message,
            f"{E.LIST} Услуги:\n\n{services_text}" if services_text else f"{E.LIST} Услуги:\n\n{E.EMPTY} Нет услуг.",
            reply_markup=keyboards.admin_services_kb(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error in admin_services: {e}")
    await callback.answer()


@router.callback_query(F.data == "admin_add_service")
async def cb_admin_add_service(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    await state.set_state(AdminStates.add_service)
    await edit_with_retry(callback.message, "Введите данные услуги (Название, цена):")
    await callback.answer()


@router.message(AdminStates.add_service)
async def handle_add_service(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.text or not message.text.strip():
        await send_with_retry(message.bot, message.chat.id, "Введите данные текстом.")
        return
    # FIX: Use maxsplit=1 to allow commas in service name (only split once)
    # Actually, we need price as last element, so split from right
    text = message.text.strip()
    if "," not in text:
        await send_with_retry(message.bot, message.chat.id, "Неверный формат. Введите: Название, цена")
        return
    # Split from right to get price as last element
    parts = text.rsplit(",", 1)
    if len(parts) < 2:
        await send_with_retry(message.bot, message.chat.id, "Неверный формат. Введите: Название, цена")
        return
    name = parts[0].strip()
    
    # HIGH-01 FIX: longest service prefix = 'admin_confirm_remove_service:' (29 bytes) → max 35 bytes
    if not name or len(name.encode("utf-8")) < 1 or len(name.encode("utf-8")) > 35:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Название услуги слишком длинное. Максимум ~17 символов кириллицей или 35 латиницей.", parse_mode="HTML")
        return
    
    try:
        price = int(parts[1].strip())
    except ValueError:
        await send_with_retry(message.bot, message.chat.id, "Цена должна быть числом.")
        return
    
    if price <= 0:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Цена должна быть больше 0.", parse_mode="HTML")
        return
    
    config.SERVICES[name] = price
    try:
        await storage.save_service(name, price)
        await config.save_config_to_db()
    except Exception as e:
        logger.error(f"Failed to save service to DB: {e}")
    await state.clear()
    await send_with_retry(message.bot, message.chat.id, f"Услуга {html.escape(name)} добавлена ({price} ₸).", reply_markup=keyboards.admin_kb(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_service_detail:"))
async def cb_admin_service_detail(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    service_name = callback.data.split(":", 1)[1]
    price = config.SERVICES.get(service_name)
    if price is None:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    text = f"{service_name}: {price} ₸"
    await edit_with_retry(callback.message, text, reply_markup=keyboards.admin_service_detail_kb(service_name))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_edit_service:"))
async def cb_admin_edit_service(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    service_name = callback.data.split(":", 1)[1]
    await state.update_data(service_name=service_name)
    await state.set_state(AdminStates.edit_service)
    await edit_with_retry(callback.message, "Введите новые данные (Название, цена):")
    await callback.answer()


@router.message(AdminStates.edit_service)
async def handle_edit_service(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.text or not message.text.strip():
        await send_with_retry(message.bot, message.chat.id, "Введите данные текстом.")
        return
    data = await state.get_data()
    service_name = data["service_name"]
    # FIX: Use rsplit from right to allow commas in service name
    text = message.text.strip()
    if "," not in text:
        await send_with_retry(message.bot, message.chat.id, "Неверный формат. Введите: Название, цена")
        return
    parts = text.rsplit(",", 1)
    if len(parts) < 2:
        await send_with_retry(message.bot, message.chat.id, "Неверный формат. Введите: Название, цена")
        return
    name = parts[0].strip()
    
    # HIGH-01 FIX: max service name = 64 - len("admin_confirm_remove_service:") = 35 bytes
    if not name or len(name.encode("utf-8")) < 1 or len(name.encode("utf-8")) > 35:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Название услуги слишком длинное. Максимум ~17 символов кириллицей или 35 латиницей.", parse_mode="HTML")
        return
    
    try:
        price = int(parts[1].strip())
    except ValueError:
        await send_with_retry(message.bot, message.chat.id, "Цена должна быть числом.")
        return
    
    # BUG-013 FIX: Validate price > 0
    if price <= 0:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Цена должна быть больше 0.", parse_mode="HTML")
        return
    
    if service_name in config.SERVICES:
        del config.SERVICES[service_name]
    config.SERVICES[name] = price
    try:
        await storage.remove_service(service_name)
        await storage.save_service(name, price)
        await config.save_config_to_db()
    except Exception as e:
        logger.error(f"Failed to update service in DB: {e}")
    await state.clear()
    await send_with_retry(message.bot, message.chat.id, f"Услуга {html.escape(name)} обновлена ({price} ₸).", reply_markup=keyboards.admin_kb(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_remove_service:"))
async def cb_admin_remove_service(callback: CallbackQuery):
    """HIGH-05 FIX: Show confirm dialog before removing service."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    service_name = callback.data.split(":", 1)[1]
    if service_name not in config.SERVICES:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    # Check active bookings for this service
    try:
        import aiosqlite
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM bookings WHERE service=? AND status='active'",
                (service_name,)
            )
            active_count = (await cursor.fetchone())[0]
        if active_count > 0:
            await callback.answer(
                f"Невозможно удалить услугу «{service_name}»: есть {active_count} активных записей. Сначала завершите или отмените их.",
                show_alert=True
            )
            return
    except Exception as e:
        logger.error(f"Failed to check active bookings for service: {e}")
    # Show confirm dialog
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"{E.CHECK} Да, удалить", callback_data=f"admin_confirm_remove_service:{service_name}"),
            InlineKeyboardButton(text=f"{E.CROSS} Отмена", callback_data=f"admin_service_detail:{service_name}"),
        ]
    ])
    await edit_with_retry(
        callback.message,
        f"Удалить услугу <b>{html.escape(service_name)}</b>?\n\nЭто действие нельзя отменить.",
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_remove_service:"))
async def cb_admin_confirm_remove_service(callback: CallbackQuery):
    """HIGH-05 FIX: Confirmed service removal."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    service_name = callback.data.split(":", 1)[1]
    if service_name in config.SERVICES:
        del config.SERVICES[service_name]
        try:
            await storage.remove_service(service_name)
            await config.save_config_to_db()
        except Exception as e:
            logger.error(f"Failed to remove service from DB: {e}")
        await edit_with_retry(callback.message, f"{E.CROSS} Услуга {html.escape(service_name)} удалена.", reply_markup=keyboards.admin_kb(), parse_mode="HTML")
    else:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data == "admin_settings")
async def cb_admin_settings(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    try:
        text = (
            f"Настройки\n\n"
            f"Адрес: {config.BARBERSHOP_ADDRESS}\n"
            f"Телефон: {config.BARBERSHOP_PHONE}\n"
            f"Часы работы: {config.BARBERSHOP_WORKING_HOURS}\n"
        )
        await edit_with_retry(callback.message, text, reply_markup=keyboards.admin_settings_kb())
    except Exception as e:
        logger.error(f"Error in admin_settings: {e}")
    await callback.answer()


@router.callback_query(F.data == "admin_change_address")
async def cb_admin_change_address(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    await state.set_state(AdminStates.change_address)
    await edit_with_retry(callback.message, "Введите новый адрес:")
    await callback.answer()


@router.message(AdminStates.change_address)
async def handle_change_address(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.text or not message.text.strip():
        await send_with_retry(message.bot, message.chat.id, "Введите адрес текстом.")
        return
    
    address = message.text.strip()
    
    # BUG-010 FIX: Validate address length
    if len(address) > 200:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Адрес слишком длинный. Максимум 200 символов.", parse_mode="HTML")
        return
    
    config.BARBERSHOP_ADDRESS = address
    try:
        await storage.save_settings("address", config.BARBERSHOP_ADDRESS)
        await config.save_config_to_db()
    except Exception as e:
        logger.error(f"Failed to save address: {e}")
    await state.clear()
    await send_with_retry(message.bot, message.chat.id, "Адрес обновлён.", reply_markup=keyboards.admin_kb())


@router.callback_query(F.data == "admin_change_phone")
async def cb_admin_change_phone(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    await state.set_state(AdminStates.change_phone)
    await edit_with_retry(callback.message, "Введите новый телефон:")
    await callback.answer()


@router.message(AdminStates.change_phone)
async def handle_change_phone(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.text or not message.text.strip():
        await send_with_retry(message.bot, message.chat.id, "Введите телефон текстом.")
        return
    
    phone = message.text.strip()
    
    # BUG-010 FIX: Validate phone length
    if len(phone) > 200:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Телефон слишком длинный. Максимум 200 символов.", parse_mode="HTML")
        return
    
    config.BARBERSHOP_PHONE = phone
    try:
        await storage.save_settings("phone", config.BARBERSHOP_PHONE)
        await config.save_config_to_db()
    except Exception as e:
        logger.error(f"Failed to save phone: {e}")
    await state.clear()
    await send_with_retry(message.bot, message.chat.id, "Телефон обновлён.", reply_markup=keyboards.admin_kb())


@router.callback_query(F.data == "admin_change_hours")
async def cb_admin_change_hours(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    await state.set_state(AdminStates.change_hours)
    await edit_with_retry(callback.message, "Введите новые часы работы (например: Пн-Сб: 10:00-21:00, Вс: 11:00-19:00):")
    await callback.answer()


@router.message(AdminStates.change_hours)
async def handle_change_hours(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.text or not message.text.strip():
        await send_with_retry(message.bot, message.chat.id, "Введите часы работы текстом.")
        return
    
    new_hours = message.text.strip()
    
    # BUG-010 FIX: Validate hours length
    if len(new_hours) > 200:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Часы работы слишком длинные. Максимум 200 символов.", parse_mode="HTML")
        return
    
    # Parse new working hours to update WORKING_HOURS dict
    # Example format: "Пн-Сб: 10:00-21:00, Вс: 11:00-19:00"
    # We need to extract the time ranges and update config.WORKING_HOURS
    try:
        # Simple parsing logic - extract hours from the text
            
        # Find all time patterns like "10:00-21:00"
        time_patterns = re.findall(r'(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})', new_hours)
        
        if time_patterns:
            # Determine which days use which hours
            # Default: all days use the first time range found
            default_hours = (int(time_patterns[0][0]), int(time_patterns[0][2]))
            
            # BUG-005 FIX: Check for Sunday (Вс/вс/Sunday/sunday) with correct regex
            sunday_pattern = re.search(r'[Вв]с[:\s]+(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})', new_hours)
            if not sunday_pattern:
                sunday_pattern = re.search(r'[Ss]unday[:\s]+(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})', new_hours, re.IGNORECASE)
            
            if sunday_pattern:
                sunday_hours = (int(sunday_pattern.group(1)), int(sunday_pattern.group(3)))
            else:
                sunday_hours = default_hours
            
            # BUG-005 FIX: Check for Saturday (Сб/сб/Saturday/saturday) with correct regex
            saturday_pattern = re.search(r'[Сс]б[:\s]+(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})', new_hours)
            if not saturday_pattern:
                saturday_pattern = re.search(r'[Ss]aturday[:\s]+(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})', new_hours, re.IGNORECASE)
            
            if saturday_pattern:
                saturday_hours = (int(saturday_pattern.group(1)), int(saturday_pattern.group(3)))
            else:
                saturday_hours = default_hours
            
            # Update WORKING_HOURS configuration
            config.WORKING_HOURS = {
                "monday":    default_hours,
                "tuesday":   default_hours,
                "wednesday": default_hours,
                "thursday":  default_hours,
                "friday":    default_hours,
                "saturday":  saturday_hours,
                "sunday":    sunday_hours,
            }
            
            # MED-04 FIX: Validate that start < end before generating slots
            start_h, end_h = default_hours
            if start_h >= end_h:
                await send_with_retry(
                    message.bot, message.chat.id,
                    f"{E.CROSS} Ошибка: время начала ({start_h}:00) должно быть меньше времени конца ({end_h}:00). Введите корректный диапазон.",
                    parse_mode="HTML"
                )
                return
            new_time_slots = []
            for h in range(start_h, end_h):  # MED-1 FIX: не включать слот в час закрытия
                new_time_slots.append(f"{h:02d}:00")
                if h < end_h:
                    new_time_slots.append(f"{h:02d}:30")

            # MED-01 FIX: Guard against empty slots list (should not happen after check above, but be safe)
            if not new_time_slots:
                await send_with_retry(
                    message.bot, message.chat.id,
                    f"{E.CROSS} Не удалось сформировать временные слоты. Проверьте формат (например: 10:00-21:00).",
                    parse_mode="HTML"
                )
                return
            config.TIME_SLOTS = new_time_slots
            
            logger.info(f"Updated working hours: {config.WORKING_HOURS}")
            logger.info(f"Updated time slots: {config.TIME_SLOTS}")
    except Exception as e:
        logger.error(f"Failed to parse working hours: {e}")
        # Continue anyway with the text update
    
    config.BARBERSHOP_WORKING_HOURS = new_hours
    try:
        await storage.save_settings("hours", config.BARBERSHOP_WORKING_HOURS)
        await storage.save_settings("slots", ",".join(config.TIME_SLOTS))
        await config.save_config_to_db()
    except Exception as e:
        logger.error(f"Failed to save hours: {e}")
    await state.clear()
    # MED-01 FIX: Guard against IndexError when TIME_SLOTS is empty
    if config.TIME_SLOTS:
        slots_info = f"Слоты: {len(config.TIME_SLOTS)} шт. (от {config.TIME_SLOTS[0]} до {config.TIME_SLOTS[-1]})"
    else:
        slots_info = "Слоты: не обновлены (не удалось распознать формат времени)"
    await send_with_retry(
        message.bot,
        message.chat.id,
        "Часы работы обновлены.\n\n"
        f"Новые часы: {config.BARBERSHOP_WORKING_HOURS}\n"
        f"{slots_info}",
        reply_markup=keyboards.admin_kb()
    )


@router.callback_query(F.data.startswith("admin_pre_cancel:"))
async def cb_admin_pre_cancel(callback: CallbackQuery):
    """HIGH-7 FIX: Confirm dialog before admin cancels booking."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    booking_id = callback.data.split(":", 1)[1]
    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, отменить",
                callback_data=f"admin_cancel_booking:{booking_id}"
            ),
            InlineKeyboardButton(
                text="❌ Нет",
                callback_data=f"admin_manage_booking:{booking_id}"
            ),
        ]
    ])
    confirm_text = (
        "⚠️ <b>Отменить запись <code>"
        + booking_id +
        "</code>?</b>\n\nПользователь получит уведомление. Действие нельзя отменить."
    )
    await edit_with_retry(
        callback.message,
        confirm_text,
        reply_markup=confirm_kb,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_cancel_booking:"))
async def cb_admin_cancel_booking(callback: CallbackQuery, bot: Bot):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    booking_id = callback.data.split(":", 1)[1]
    try:
        booking = await storage.admin_cancel_booking(booking_id)
        if booking:
            await scheduler.cancel_reminders(booking_id)
            # BUG-019: Add parse_mode to user notification
            _ub_date = keyboards._format_date(booking["date"])
            _ub_time = booking["time"]
            _ub_master = html.escape(booking["master"])
            _ub_name = html.escape(booking["name"])
            await send_with_retry(
                bot,
                booking["telegram_id"],
                f"{E.CROSS} <b>Ваша запись отменена администратором</b>\n\n"
                f"{E.ID} ID: <code>{booking_id}</code>\n"
                f"{E.CALENDAR} {_ub_date} в {_ub_time}\n"
                f"{E.SCISSORS} Мастер: {_ub_master}",
                parse_mode="HTML"
            )
            # HIGH-1 FIX: уведомить мастера об отмене записи
            _master_tg = config.MASTER_IDS.get(booking["master"])
            if _master_tg and _master_tg != booking["telegram_id"]:
                try:
                    _b_name = html.escape(booking["name"])
                    _b_date = keyboards._format_date(booking["date"])
                    _b_time = booking["time"]
                    await send_with_retry(
                        bot,
                        _master_tg,
                        f"{E.INFO} <b>Запись отменена админом</b>\n\n"
                        f"{E.USER} {_b_name}\n"
                        f"{E.CALENDAR} {_b_date} в {_b_time}",
                        parse_mode="HTML"
                    )
                except Exception as _me:
                    logger.error(f"Failed to notify master on admin cancel: {_me}")
            await edit_with_retry(callback.message, f"Запись {booking_id} отменена.", reply_markup=keyboards.admin_kb())
        else:
            await callback.answer("Запись не найдена или уже не активна", show_alert=True)
            return
    except Exception as e:
        logger.error(f"Error in admin_cancel_booking: {e}")
        await callback.answer("Ошибка", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data.startswith("admin_complete_booking:"))
async def cb_admin_complete_booking(callback: CallbackQuery, bot: Bot):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    booking_id = callback.data.split(":", 1)[1]
    try:
        booking = await storage.admin_complete_booking(booking_id)
        if booking:
            await scheduler.cancel_reminders(booking_id)
            
            # TASK-03: Update loyalty ONLY on real visit completion (not at booking)
            telegram_id = booking["telegram_id"]
            name = booking["name"]
            visits = await storage.update_loyalty(telegram_id, name)
            
            # Check if user earned a reward
            if visits % config.LOYALTY_VISIT_INTERVAL == 0:
                try:
                    reward_text = f"{E.STAR} <b>Поздравляем!</b>\n\n"
                    reward_text += f"Это ваш {visits}-й визит! Вы получили скидку {config.LOYALTY_DISCOUNT_PERCENT}% на следующую запись."
                    await bot.send_message(telegram_id, reward_text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to send loyalty reward to user {telegram_id}: {e}")
            
            # Task 18: Уведомить мастера о завершении визита
            master_name = booking["master"]
            if master_name in config.MASTER_IDS:
                try:
                    master_done_text = (
                        f"{E.CHECK} <b>Завершён визит</b>\n\n"
                        f"{E.USER} Клиент: {html.escape(name)}\n"
                        f"{E.CALENDAR} {keyboards._format_date(booking['date'])} в {booking['time']}\n"
                        f"{E.MONEY} Оплачено: " + "{:,}".format(booking["price"]).replace(","," ") + " ₸"
                    )
                    await bot.send_message(config.MASTER_IDS[master_name], master_done_text, parse_mode="HTML")
                except Exception as _me:
                    logger.error(f"Failed to notify master on completion: {_me}")
            await edit_with_retry(callback.message, f"✅ Запись {booking_id} завершена.\n\n👤 {html.escape(name)} получил +1 визит (всего: {visits})", reply_markup=keyboards.admin_kb(), parse_mode="HTML")
        else:
            await callback.answer("Запись не найдена или уже не активна", show_alert=True)
            return
    except Exception as e:
        logger.error(f"Error in admin_complete_booking: {e}")
        await callback.answer("Ошибка", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data == "admin_waitlist")
async def cb_admin_waitlist(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    await _show_admin_waitlist_page(callback, offset=0)


@router.callback_query(F.data.startswith("admin_waitlist_page:"))
async def cb_admin_waitlist_page(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    try:
        offset = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        offset = 0
    await _show_admin_waitlist_page(callback, offset=offset)


async def _show_admin_waitlist_page(callback, offset: int = 0):
    """HIGH-06 FIX: Paginated waitlist to avoid 4096-char Telegram limit."""
    PAGE = 15
    try:
        waitlist = await storage.get_all_waitlist()
        total = len(waitlist)
        page_items = waitlist[offset:offset + PAGE]
        text = f"{E.RELOAD} Список ожидания ({total} всего):\n\n"
        for w in page_items:
            text += f"{E.USER} {html.escape(w['name'])}: {keyboards._format_date(w['date'])} {w['time']} — {html.escape(w['master'])} ({html.escape(w['service'])}) [{w['status']}]\n"
        if not waitlist:
            text += f"{E.EMPTY} Список ожидания пуст.\n"
        nav_buttons = []
        if offset > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"admin_waitlist_page:{offset - PAGE}"))
        if total > 0:
            nav_buttons.append(InlineKeyboardButton(text=f"{offset // PAGE + 1}/{max(1, (total - 1) // PAGE + 1)}", callback_data="noop"))
        if offset + PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="▶ Далее", callback_data=f"admin_waitlist_page:{offset + PAGE}"))
        kb_rows = []
        if nav_buttons:
            kb_rows.append(nav_buttons)
        kb_rows.append([InlineKeyboardButton(text="Назад в панель", callback_data="admin")])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await edit_with_retry(callback.message, text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in admin_waitlist: {e}")
    await callback.answer()


@router.callback_query(F.data == "admin_reviews")
async def cb_admin_reviews(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    await _show_admin_reviews_page(callback, offset=0)


@router.callback_query(F.data.startswith("admin_reviews_page:"))
async def cb_admin_reviews_page(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    try:
        offset = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        offset = 0
    await _show_admin_reviews_page(callback, offset=offset)


async def _show_admin_reviews_page(callback, offset: int = 0):
    """HIGH-06 FIX: Paginated reviews to avoid 4096-char Telegram limit."""
    PAGE = 15
    try:
        reviews = await storage.get_reviews()
        total = len(reviews)
        page_items = reviews[offset:offset + PAGE]
        text = f"{E.COMMENT} Отзывы ({total} всего):\n\n"
        for r in page_items:
            comment_preview = html.escape(r.get("comment", "") or "")[:60]
            if len(r.get("comment", "") or "") > 60:
                comment_preview += "…"
            text += f"{E.ID} <code>{r['booking_id']}</code>: {'⭐' * r['rating']} ({keyboards._format_date(r['created_at'][:10])})\n"
            if comment_preview:
                text += f"   {comment_preview}\n"
        if not reviews:
            text += f"{E.EMPTY} Нет отзывов.\n"
        nav_buttons = []
        if offset > 0:
            nav_buttons.append(InlineKeyboardButton(text="◀ Назад", callback_data=f"admin_reviews_page:{offset - PAGE}"))
        if total > 0:
            nav_buttons.append(InlineKeyboardButton(text=f"{offset // PAGE + 1}/{max(1, (total - 1) // PAGE + 1)}", callback_data="noop"))
        if offset + PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="▶ Далее", callback_data=f"admin_reviews_page:{offset + PAGE}"))
        kb_rows = []
        if nav_buttons:
            kb_rows.append(nav_buttons)
        kb_rows.append([InlineKeyboardButton(text="Назад в панель", callback_data="admin")])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await edit_with_retry(callback.message, text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in admin_reviews: {e}")
    await callback.answer()


@router.callback_query(F.data == "admin_loyalty")
async def cb_admin_loyalty(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    try:
        loyalty = await storage.get_loyalty_list()
        text = f"{E.STAR} Клиенты с бонусами:\n\n"
        for l in loyalty[:50]:
            text += f"{E.USER} {l['name'] or 'Аноним'}: визитов {l['visits']}, бонусов {l['bonuses']}\n"
        if not loyalty:
            text += f"{E.EMPTY} Нет данных о лояльности.\n"
        elif len(loyalty) > 50:
            text += f"\n... и ещё {len(loyalty) - 50} клиентов\n"
        await edit_with_retry(callback.message, text, reply_markup=keyboards.admin_kb())
    except Exception as e:
        logger.error(f"Error in admin_loyalty: {e}")
    await callback.answer()


@router.callback_query(F.data == "admin_referrals")
async def cb_admin_referrals(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    try:
        referrals = await storage.get_referrals()
        text = f"{E.PEOPLE} Рефералы:\n\n"
        for r in referrals[:50]:
            text += f"{E.USER} {r['referrer_id']} пригласил {r['referred_id']} ({keyboards._format_date(r['created_at'][:10])})\n"
        if not referrals:
            text += f"{E.EMPTY} Нет рефералов.\n"
        elif len(referrals) > 50:
            text += f"\n... и ещё {len(referrals) - 50} рефералов\n"
        await edit_with_retry(callback.message, text, reply_markup=keyboards.admin_kb())
    except Exception as e:
        logger.error(f"Error in admin_referrals: {e}")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_set_master_tg:"))
async def cb_admin_set_master_tg(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    master_name = callback.data.split(":", 1)[1]
    if master_name not in config.MASTERS:
        await callback.answer("Мастер не найден", show_alert=True)
        return
    await state.update_data(master_name=master_name)
    await state.set_state(AdminStates.set_master_tg)
    current_tg = config.MASTER_IDS.get(master_name)
    cur = f"Текущий: <code>{current_tg}</code>" if current_tg else "не задан"
    parts = [
        f"<b>Telegram ID мастера {html.escape(master_name)}</b>",
        "",
        cur,
        "",
        "Введите Telegram ID мастера",
        "(узнать свой ID: @userinfobot)",
        "Или 0 для удаления:",
    ]
    msg = chr(10).join(parts)
    await edit_with_retry(callback.message, msg, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.set_master_tg)
async def handle_set_master_tg(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.text or not message.text.strip().lstrip("-").isdigit():
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Введите числовой Telegram ID (например: 123456789) или 0 для удаления.", parse_mode="HTML")
        return
    data = await state.get_data()
    master_name = data.get("master_name")
    if not master_name:
        await state.clear()
        await send_with_retry(message.bot, message.chat.id, "Сессия устарела. Откройте панель мастера заново.", reply_markup=keyboards.admin_kb())
        return
    tg_id_str = message.text.strip()
    try:
        tg_id = int(tg_id_str)
    except ValueError:
        await send_with_retry(message.bot, message.chat.id, f"{E.CROSS} Неверный формат. Введите число.", parse_mode="HTML")
        return
    if tg_id == 0:
        # Remove TG ID
        config.MASTER_IDS.pop(master_name, None)
        await storage.set_master_telegram_id(master_name, None)
        await state.clear()
        await send_with_retry(message.bot, message.chat.id, f"{E.CHECK} Telegram ID мастера {html.escape(master_name)} удалён.", reply_markup=keyboards.admin_kb(), parse_mode="HTML")
    else:
        config.MASTER_IDS[master_name] = tg_id
        await storage.set_master_telegram_id(master_name, tg_id)
        await state.clear()
        await send_with_retry(
            message.bot, message.chat.id,
            f"{E.CHECK} Telegram ID мастера {html.escape(master_name)} установлен: <code>{tg_id}</code>",
            reply_markup=keyboards.admin_kb(), parse_mode="HTML"
        )


# --- Master schedule management ---

@router.callback_query(F.data.startswith("master_schedule:"))
async def cb_master_schedule(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    
    try:
        master_name = callback.data.split(":", 1)[1]
        if master_name not in config.MASTERS:
            await callback.answer("Мастер не найден", show_alert=True)
            return
        
        # Load current work days from DB
        work_days = await storage.get_master_work_days(master_name)
        
        # Save to FSM state
        await state.update_data(master_name=master_name, work_days=work_days)
        await state.set_state(AdminStates.set_master_work_days)
        
        # Build keyboard
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        text = f"{E.CALENDAR} <b>Расписание мастера {html.escape(master_name)}</b>\n\n"
        text += "Выберите рабочие дни:\n\n"
        
        buttons = []
        # First 3 days
        row1 = []
        for i in range(1, 4):
            emoji = "✅" if i in work_days else "❌"
            row1.append(InlineKeyboardButton(
                text=f"{day_names[i-1]} {emoji}",
                callback_data=f"toggle_day:{i}"
            ))
        buttons.append(row1)
        
        # Next 3 days
        row2 = []
        for i in range(4, 7):
            emoji = "✅" if i in work_days else "❌"
            row2.append(InlineKeyboardButton(
                text=f"{day_names[i-1]} {emoji}",
                callback_data=f"toggle_day:{i}"
            ))
        buttons.append(row2)
        
        # Sunday
        row3 = []
        emoji = "✅" if 7 in work_days else "❌"
        row3.append(InlineKeyboardButton(
            text=f"{day_names[6]} {emoji}",
            callback_data=f"toggle_day:7"
        ))
        buttons.append(row3)
        
        # Save button
        buttons.append([InlineKeyboardButton(text="Сохранить", callback_data="save_master_days")])
        buttons.append([InlineKeyboardButton(text="Назад", callback_data=f"admin_master_detail:{master_name}")])
        
        await edit_with_retry(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in master_schedule: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_day:"), AdminStates.set_master_work_days)
async def cb_toggle_day(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    
    try:
        day_num = int(callback.data.split(":", 1)[1])
        data = await state.get_data()
        work_days = data.get("work_days", [])
        master_name = data.get("master_name", "")
        
        # Toggle day
        if day_num in work_days:
            work_days.remove(day_num)
        else:
            work_days.append(day_num)
        
        # Update state
        await state.update_data(work_days=work_days)
        
        # Rebuild keyboard
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        text = f"{E.CALENDAR} <b>Расписание мастера {html.escape(master_name)}</b>\n\n"
        text += "Выберите рабочие дни:\n\n"
        
        buttons = []
        # First 3 days
        row1 = []
        for i in range(1, 4):
            emoji = "✅" if i in work_days else "❌"
            row1.append(InlineKeyboardButton(
                text=f"{day_names[i-1]} {emoji}",
                callback_data=f"toggle_day:{i}"
            ))
        buttons.append(row1)
        
        # Next 3 days
        row2 = []
        for i in range(4, 7):
            emoji = "✅" if i in work_days else "❌"
            row2.append(InlineKeyboardButton(
                text=f"{day_names[i-1]} {emoji}",
                callback_data=f"toggle_day:{i}"
            ))
        buttons.append(row2)
        
        # Sunday
        row3 = []
        emoji = "✅" if 7 in work_days else "❌"
        row3.append(InlineKeyboardButton(
            text=f"{day_names[6]} {emoji}",
            callback_data=f"toggle_day:7"
        ))
        buttons.append(row3)
        
        # Save button
        buttons.append([InlineKeyboardButton(text="Сохранить", callback_data="save_master_days")])
        buttons.append([InlineKeyboardButton(text="Назад", callback_data=f"admin_master_detail:{master_name}")])
        
        await edit_with_retry(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in toggle_day: {e}")
    await callback.answer()


@router.callback_query(F.data == "save_master_days", AdminStates.set_master_work_days)
async def cb_save_master_days(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    
    try:
        data = await state.get_data()
        master_name = data.get("master_name", "")
        work_days = data.get("work_days", [])
        
        if not work_days:
            await callback.answer("Выберите хотя бы один рабочий день", show_alert=True)
            return
        
        # Save to DB
        success = await storage.set_master_work_days(master_name, work_days)
        
        if success:
            day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            days_str = ", ".join(day_names[d-1] for d in sorted(work_days))
            text = f"{E.CHECK} <b>Расписание сохранено</b>\n\n"
            text += f"Мастер: {html.escape(master_name)}\n"
            text += f"Работает: {days_str}"
            
            await state.clear()
            await edit_with_retry(
                callback.message,
                text,
                reply_markup=keyboards.admin_kb(),
                parse_mode="HTML"
            )
        else:
            await callback.answer("Ошибка сохранения", show_alert=True)
    except Exception as e:
        logger.error(f"Error in save_master_days: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    await callback.answer()


# --- Master services management ---

@router.callback_query(F.data.startswith("master_services:"))
async def cb_master_services(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    
    try:
        master_name = callback.data.split(":", 1)[1]
        if master_name not in config.MASTERS:
            await callback.answer("Мастер не найден", show_alert=True)
            return
        
        # Load current services from DB
        master_services = await storage.get_master_services(master_name)
        
        # Save to FSM state
        await state.update_data(master_name=master_name, master_services=master_services)
        await state.set_state(AdminStates.set_master_services)
        
        # Build keyboard
        text = f"{E.SCISSORS} <b>Услуги мастера {html.escape(master_name)}</b>\n\n"
        text += "Выберите доступные услуги:\n\n"
        
        buttons = []
        for service_name, price in config.SERVICES.items():
            emoji = "✅" if service_name in master_services else "❌"
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} {service_name} — {price:,} ₸".replace(",", " "),
                callback_data=f"toggle_service:{service_name}"
            )])
        
        # Save button
        buttons.append([InlineKeyboardButton(text="Сохранить", callback_data="save_master_services")])
        buttons.append([InlineKeyboardButton(text="Назад", callback_data=f"admin_master_detail:{master_name}")])
        
        await edit_with_retry(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in master_services: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_service:"), AdminStates.set_master_services)
async def cb_toggle_service(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    
    try:
        service_name = callback.data.split(":", 1)[1]
        data = await state.get_data()
        master_services = data.get("master_services", [])
        master_name = data.get("master_name", "")
        
        # Toggle service
        if service_name in master_services:
            master_services.remove(service_name)
        else:
            master_services.append(service_name)
        
        # Update state
        await state.update_data(master_services=master_services)
        
        # Rebuild keyboard
        text = f"{E.SCISSORS} <b>Услуги мастера {html.escape(master_name)}</b>\n\n"
        text += "Выберите доступные услуги:\n\n"
        
        buttons = []
        for svc_name, price in config.SERVICES.items():
            emoji = "✅" if svc_name in master_services else "❌"
            buttons.append([InlineKeyboardButton(
                text=f"{emoji} {svc_name} — {price:,} ₸".replace(",", " "),
                callback_data=f"toggle_service:{svc_name}"
            )])
        
        # Save button
        buttons.append([InlineKeyboardButton(text="Сохранить", callback_data="save_master_services")])
        buttons.append([InlineKeyboardButton(text="Назад", callback_data=f"admin_master_detail:{master_name}")])
        
        await edit_with_retry(
            callback.message,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in toggle_service: {e}")
    await callback.answer()


@router.callback_query(F.data == "save_master_services", AdminStates.set_master_services)
async def cb_save_master_services(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer(messages.ADMIN_ONLY, show_alert=True)
        return
    
    try:
        data = await state.get_data()
        master_name = data.get("master_name", "")
        master_services = data.get("master_services", [])
        
        # Allow empty services list (will default to all services)
        
        # Save to DB
        success = await storage.set_master_services(master_name, master_services)
        
        if success:
            if master_services:
                services_str = ", ".join(master_services)
            else:
                services_str = "все услуги"
            
            text = f"{E.CHECK} <b>Услуги сохранены</b>\n\n"
            text += f"Мастер: {html.escape(master_name)}\n"
            text += f"Услуги: {services_str}"
            
            await state.clear()
            await edit_with_retry(
                callback.message,
                text,
                reply_markup=keyboards.admin_kb(),
                parse_mode="HTML"
            )
        else:
            await callback.answer("Ошибка сохранения", show_alert=True)
    except Exception as e:
        logger.error(f"Error in save_master_services: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)
    await callback.answer()
