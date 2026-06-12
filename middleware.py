import logging
import time
import asyncio
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import config

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Таск 19: Hybrid rate limiter — in-memory с быстрым доступом,
    при перезапуске запись сбрасываются (OK для барбершопа).
    HIGH-4 FIX: убран глобальный _lock (боттлнек при нагрузке). asyncio event loop однопоточный,
    dict-операции атомарны внутри одного coroutine."""
    def __init__(self, max_requests: int = 20, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self.user_requests: dict[int, list[float]] = {}
        super().__init__()

    def _cleanup_old_entries(self, now: float) -> None:
        """HIGH-6 FIX: удаляем записи пользователей без недавних запросов, чтобы не росла RAM."""
        cutoff = now - self.window
        stale_keys = [uid for uid, ts_list in self.user_requests.items()
                      if not ts_list or ts_list[-1] < cutoff]
        for k in stale_keys:
            del self.user_requests[k]

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        # Skip rate limiting for administrators
        if user_id in config.ADMIN_IDS:
            return await handler(event, data)

        now = time.time()

        # Periodic GC: clean up stale entries every ~1000 events
        if len(self.user_requests) > 1000:
            self._cleanup_old_entries(now)

        if user_id not in self.user_requests:
            self.user_requests[user_id] = []

        # Filter expired entries for this user
        self.user_requests[user_id] = [
            t for t in self.user_requests[user_id] if (now - t) < self.window
        ]

        if len(self.user_requests[user_id]) >= self.max_requests:
            logger.warning(f"Rate limit hit for user {user_id}: {len(self.user_requests[user_id])} requests in {self.window}s")
            if isinstance(event, Message):
                await event.answer("Слишком много запросов. Подождите немного.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Слишком много запросов. Пожалуйста подождите.", show_alert=True)
            return

        self.user_requests[user_id].append(now)
        return await handler(event, data)


class AdminCheckMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is not None and user_id in config.ADMIN_IDS:
            data["is_admin"] = True
        else:
            data["is_admin"] = False
        return await handler(event, data)
