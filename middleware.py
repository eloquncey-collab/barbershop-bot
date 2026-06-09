import logging
import time
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

import config

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, max_requests: int = 20, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self.user_requests: dict[int, list[float]] = {}
        super().__init__()

    async def __call__(self, handler, event, data):
        user_id = event.from_user.id if event.from_user else None
        if user_id is None:
            return await handler(event, data)

        # BUG-RLC FIX: Skip rate limiting for administrators
        if user_id in config.ADMIN_IDS:
            return await handler(event, data)

        now = time.time()
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []

        # BUG-009 FIX: Filter requests using proper time comparison
        self.user_requests[user_id] = [
            t for t in self.user_requests[user_id] if (now - t) < self.window
        ]

        if len(self.user_requests[user_id]) >= self.max_requests:
            if isinstance(event, Message):
                await event.answer("Слишком много запросов. Подождите немного.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Слишком много запросов. Подождите.", show_alert=True)
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

