def remind_cancel_kb(booking_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отменить запись", callback_data=f"remind_cancel:{booking_id}")],
    ])


def remind_2h_kb(booking_id: str) -> InlineKeyboardMarkup:
    """2ч — только подтверждение, нет кнопки отмены"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Буду! 👍", callback_data=f"remind_confirm:{booking_id}")],
    ])