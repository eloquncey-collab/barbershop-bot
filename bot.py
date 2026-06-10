import logging
import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ErrorEvent
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from config import BOT_TOKEN, load_config_from_db, save_config_to_db
from storage import init_db, delete_old_scheduler_jobs
from scheduler import start_scheduler, shutdown_scheduler
from backup import backup_database, cleanup_old_backups
from monitoring import start_monitoring, get_health_status
from handlers.start import router as start_router
from handlers.booking import router as booking_router
from handlers.info import router as info_router
from handlers.admin import router as admin_router
from middleware import RateLimitMiddleware, AdminCheckMiddleware
import keyboards
from emoji_config import E

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Please configure .env")
        return

    # Proxy configuration (optional - set PROXY_URL in .env if Telegram is blocked)
    proxy = os.getenv("PROXY_URL", None)  # e.g., "http://proxy.example.com:8080"
    
    if proxy:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiohttp import ClientTimeout
        timeout = ClientTimeout(total=60, connect=30, sock_connect=30, sock_read=30)
        session = AiohttpSession(proxy=proxy, timeout=timeout)
        bot = Bot(token=BOT_TOKEN, session=session)
        logger.info(f"Using proxy: {proxy}")
    else:
        bot = Bot(token=BOT_TOKEN)
        logger.info("No proxy configured, using direct connection")

    redis_url = os.getenv("REDIS_URL", "")
    if redis_url:
        try:
            from redis_storage import RedisStorage
            storage = RedisStorage(redis_url)
            # BUG-018 FIX: Mask password in Redis URL for logs
            masked_url = redis_url
            if "@" in masked_url:
                parts = masked_url.split("@")
                if ":" in parts[0]:
                    user_pass = parts[0].split("://", 1)
                    if len(user_pass) == 2:
                        protocol = user_pass[0]
                        credentials = user_pass[1]
                        if ":" in credentials:
                            user = credentials.split(":")[0]
                            masked_url = f"{protocol}://{user}:****@{parts[1]}"
            logger.info(f"Using Redis FSM storage: {masked_url}")
        except Exception as e:
            logger.warning(f"Redis not available, falling back to FileStorage: {e}")
            from fsm_storage import FileStorage
            storage = FileStorage()
    else:
        from fsm_storage import FileStorage
        storage = FileStorage()
        logger.info("Using FileStorage (no REDIS_URL set)")

    dp = Dispatcher(storage=storage)

    # BUG-004 FIX: Register RateLimitMiddleware to prevent flooding
    dp.message.middleware(RateLimitMiddleware(max_requests=20, window=60))
    dp.callback_query.middleware(RateLimitMiddleware(max_requests=20, window=60))

    # NEW-001 FIX: Register AdminCheckMiddleware to set is_admin in data
    dp.message.middleware(AdminCheckMiddleware())
    dp.callback_query.middleware(AdminCheckMiddleware())

    dp.include_router(start_router)
    dp.include_router(booking_router)
    dp.include_router(info_router)
    dp.include_router(admin_router)

    # FIX BUG-1/2/3: Fallback только когда нет активного FSM-state.
    # Без StateFilter(None) этот хендлер (зарегистрирован на dp напрямую)
    # перехватывает ВСЕ текстовые сообщения до sub-router'ов (booking, admin),
    # что ломало ввод имени на шаге 5/5 и все FSM-формы в admin-панели.
    @dp.message(F.text, ~F.text.regexp(r"^/"), StateFilter(None))
    async def fsm_fallback_handler(message: Message, state: FSMContext):
        """Отвечает только когда у пользователя нет активного FSM-состояния."""
        await message.answer(
            f"{E.INFO} Напишите /start для начала работы.",
            reply_markup=keyboards.back_to_main_kb(),
            parse_mode="HTML"
        )

    @dp.error()
    async def global_error_handler(event: ErrorEvent):
        logger.error("Global error handler caught exception", exc_info=True)
        try:
            if event.update.message:
                await event.update.message.answer("Произошла ошибка. Попробуйте позже.")
            elif event.update.callback_query:
                await event.update.callback_query.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)
        except Exception:
            pass

    await init_db()
    logger.info("Database initialized")

    await load_config_from_db()
    logger.info("Config loaded from DB")

    # Устанавливаем команды бота автоматически
    from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
    from config import ADMIN_IDS

    user_commands = [
        BotCommand(command="start",    description="Главное меню"),
        BotCommand(command="me",       description="Мой профиль и записи"),
        BotCommand(command="master",   description="Все мастера"),
        BotCommand(command="waitlist", description="Мой лист ожидания"),
        BotCommand(command="cancel",   description="Отменить запись"),
        BotCommand(command="help",     description="Справка по командам"),
    ]
    await bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())

    # Для каждого администратора — расширенный список команд
    admin_commands = user_commands + [
        BotCommand(command="admin", description="Панель администратора"),
    ]
    # /admin is hidden from regular users — only visible in admin scope
    for admin_id in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception as e:
            logger.warning(f"Could not set admin commands for {admin_id}: {e}")

    logger.info("Bot commands set")

    # Warn if no admins configured
    from config import ADMIN_IDS
    if not ADMIN_IDS:
        logger.warning("WARNING: ADMIN_IDS is empty! No one can access the admin panel.")
        logger.warning("Set ADMIN_IDS in .env: ADMIN_IDS=your_telegram_id")

    await delete_old_scheduler_jobs()

    # MED-006 FIX: Auto-complete past-due bookings on startup
    try:
        from storage import get_past_bookings_for_completion
        from scheduler import auto_complete_booking as _auto_complete
        _past = await get_past_bookings_for_completion()
        if _past:
            logger.info(f"Found {len(_past)} past-due bookings to auto-complete")
            for _b in _past:
                try:
                    await _auto_complete(bot, _b)
                except Exception as _e:
                    logger.error(f"Failed to auto-complete {_b['id']}: {_e}")
    except Exception as _e:
        logger.error(f"Startup past-due recovery failed: {_e}")

    # FSM-reset: clear stale states on restart (prevent stuck users)
    # TASK-01: Don't clear all states on startup - instead add fallback handler
    # Removing automatic state clearing to preserve user context across restarts
    # if hasattr(storage, 'clear_all_states'):
    #     await storage.clear_all_states()
    #     logger.info("FSM states cleared on startup")

    # BUG-009 FIX: Run backup_database in thread pool to avoid blocking
    await asyncio.to_thread(backup_database)
    await asyncio.to_thread(cleanup_old_backups)

    await start_scheduler(bot)
    start_monitoring()

    health = await get_health_status()
    logger.info(f"Health: {health}")

    # CONFLICT FIX: сбрасываем webhook и старые апдейты перед стартом поллинга.
    # Если бот запускается повторно (Railway redeploy / restart), это устраняет
    # "TelegramConflictError: terminated by other getUpdates request".
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted, pending updates dropped")
    except Exception as e:
        logger.warning(f"delete_webhook failed (non-critical): {e}")

    try:
        logger.info("Starting polling...")
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        shutdown_scheduler()
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
