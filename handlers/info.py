import html as html_lib
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

import messages
import keyboards
import config
from utils import edit_with_retry
from emoji_config import E, P

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data == "call")
async def cb_call(callback: CallbackQuery):
    try:
        text = (
            f"{E.PHONE} <b>Позвонить нам:</b>\n\n"
            f"{E.PHONE} <b>{html_lib.escape(config.BARBERSHOP_PHONE)}</b>\n\n"
            f"{E.CLOCK} <b>Часы работы:</b> {html_lib.escape(config.BARBERSHOP_WORKING_HOURS)}"
        )
        await edit_with_retry(callback.message, text, reply_markup=keyboards.back_to_main_kb(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in cb_call: {e}")
    await callback.answer()

@router.callback_query(F.data == "masters")
async def cb_masters(callback: CallbackQuery):
    try:
        text = f"{E.MASTER} <b>Наши мастера:</b>\n\n"
        text += "Выберите мастера для записи:"
        await edit_with_retry(
            callback.message,
            text,
            reply_markup=keyboards.masters_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in cb_masters: {e}")
        try:
            await edit_with_retry(callback.message, messages.ERROR, reply_markup=keyboards.back_to_main_kb(), parse_mode="HTML")
        except Exception:
            pass
    await callback.answer()


@router.callback_query(F.data.startswith("master:"))
async def cb_master_detail(callback: CallbackQuery):
    import html as html_lib
    import storage as storage_module
    master_key = callback.data.split(":", 1)[1]
    
    # BUG-008 FIX: Dual-lookup for both index and name-based callbacks
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
    
    info = config.MASTERS[master_name]
    try:
        # BUG-017 FIX: Escape master_name to prevent HTML injection
        text = f"{E.SCISSORS} <b>{html_lib.escape(master_name)}</b>\n\n"
        text += f"{E.CHART} <b>Опыт:</b> {html_lib.escape(info['experience'])}\n"
        text += f"{E.TARGET} <b>Специализация:</b> {html_lib.escape(info['specialization'])}\n\n"
        
        # Add work schedule info
        work_days = await storage_module.get_master_work_days(master_name)
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        days_str = ", ".join(day_names[d-1] for d in sorted(work_days))
        text += f"{E.CALENDAR} <b>Работает:</b> {days_str}\n\n"
        
        text += "Хотите записаться? Нажмите «Записаться» в главном меню"
        await edit_with_retry(
            callback.message,
            text,
            reply_markup=keyboards.back_to_main_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in cb_master_detail: {e}")
    await callback.answer()


@router.callback_query(F.data == "contacts")
async def cb_contacts(callback: CallbackQuery):
    try:
        text = f"{E.LOCATION} <b>Контакты:</b>\n\n"
        text += f"{E.LOCATION} <b>Адрес:</b>\n{html_lib.escape(config.BARBERSHOP_ADDRESS)}\n\n"
        text += f"{E.PHONE} <b>Телефон:</b>\n{html_lib.escape(config.BARBERSHOP_PHONE)}\n\n"
        text += f"{E.CLOCK} <b>Часы работы:</b>\n{html_lib.escape(config.BARBERSHOP_WORKING_HOURS)}\n\n"
        text += "Для записи нажмите «Записаться» в главном меню"
        await edit_with_retry(
            callback.message,
            text,
            reply_markup=keyboards.back_to_main_kb(),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error in cb_contacts: {e}")
    await callback.answer()


@router.callback_query(F.data == "prices")
async def cb_prices(callback: CallbackQuery):
    try:
        text = f"{E.MONEY} <b>Услуги и цены:</b>\n\n"
        for name, price in config.SERVICES.items():
            text += f"• {name} — <b>{price:,} ₸</b>\n".replace(","," ")
        text += f"\n{E.INFO} Цены могут отличаться в зависимости от мастера."
        await edit_with_retry(callback.message, text, reply_markup=keyboards.back_to_main_kb(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in cb_prices: {e}")
    await callback.answer()