import logging
import asyncio
from typing import Optional
from aiogram.types import InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def send_with_retry(
    bot, 
    chat_id: int, 
    text: str, 
    reply_markup: Optional[InlineKeyboardMarkup] = None, 
    max_retries: int = 3, 
    retry_delay: float = 1.0,
    parse_mode: Optional[str] = "HTML"  # HTML по умолчанию
) -> bool:
    for attempt in range(max_retries):
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
            return True
        except Exception as e:
            _es = str(e).lower()
            if any(s in _es for s in ("message is not modified", "bot was blocked", "user is deactivated", "chat not found", "forbidden")):
                logger.warning(f"Permanent error sending to {chat_id}, not retrying: {e}")
                return False
            logger.warning(f"Failed to send message to {chat_id} (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2 ** attempt))  # exponential backoff
    logger.error(f"Failed to send message to {chat_id} after {max_retries} attempts")
    return False


async def edit_with_retry(
    message, 
    text: str, 
    reply_markup: Optional[InlineKeyboardMarkup] = None, 
    max_retries: int = 3, 
    retry_delay: float = 1.0,
    parse_mode: Optional[str] = "HTML"  # HTML по умолчанию
) -> bool:
    for attempt in range(max_retries):
        try:
            await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return True
        except Exception as e:
            _es = str(e).lower()
            if any(s in _es for s in ("message is not modified", "bot was blocked", "user is deactivated", "chat not found", "forbidden")):
                logger.warning(f"Permanent error editing message, not retrying: {e}")
                return False
            logger.warning(f"Failed to edit message (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (2 ** attempt))  # exponential backoff
    logger.error(f"Failed to edit message after {max_retries} attempts")
    return False
