import html as html_module
from emoji_config import E


def welcome_text(name: str) -> str:
    """Генерирует приветственное сообщение с экранированием имени"""
    return (
        f"{E.BARBER} <b>Добро пожаловать в барбершоп «{html_module.escape(name)}»!</b>\n\n"
        f"{E.SCISSORS} Профессиональные мужские стрижки и уход за бородой.\n\n"
        "Выберите действие:"
    )


# ===== ПРИВЕТСТВИЕ =====

MAIN_MENU_TEXT = f"{E.HOME} <b>Главное меню</b>\n\nВыберите действие:"

# ===== ЗАПИСЬ =====

CHOOSE_MASTER = (
    f"{E.BARBER} <b>Шаг 1 из 5 — Выбор мастера</b>\n\n"
    "Выберите мастера:"
)

def master_selected(master_name: str, experience: str, specialization: str) -> str:
    """Сообщение после выбора мастера"""
    return (
        f"{E.CHECK} <b>Выбран:</b> {html_module.escape(master_name)}\n\n"
        f"{E.CHART} <b>Опыт:</b> {html_module.escape(experience)}\n"
        f"{E.TARGET} <b>Специализация:</b> {html_module.escape(specialization)}\n\n"
        f"<b>Шаг 2 из 5 — Выбор услуги</b>\n\n"
        "Выберите услугу:"
    )

CHOOSE_SERVICE = (
    f"{E.LIST} <b>Шаг 2 из 5 — Выбор услуги</b>\n\n"
    "Выберите услугу:"
)

def service_selected(service_name: str, price: int) -> str:
    """Сообщение после выбора услуги"""
    return (
        f"{E.CHECK} <b>Выбрана:</b> {html_module.escape(service_name)}\n"
        f"{E.MONEY} {price:,} ₸\n\n"
        f"<b>Шаг 3 из 5 — Выбор даты</b>\n\n"
        "Выберите удобный день:"
    )

CHOOSE_DATE = (
    f"{E.CALENDAR} <b>Шаг 3 из 5 — Дата</b>\n\n"
    "Выберите удобный день:"
)

def date_selected(date_formatted: str) -> str:
    """Сообщение после выбора даты"""
    return (
        f"{E.CHECK} <b>Выбрана дата:</b> {date_formatted}\n\n"
        f"<b>Шаг 4 из 5 — Выбор времени</b>\n\n"
        "Выберите свободный слот:"
    )

CHOOSE_TIME = (
    f"{E.CLOCK} <b>Шаг 4 из 5 — Время</b>\n\n"
    "Выберите свободный слот:"
)

ENTER_NAME = (
    f"{E.USER} <b>Шаг 5 из 5 — Ваше имя</b>\n\n"
    "Как к вам обращаться?"
)

BOOKING_CONFIRM = (
    f"{E.LIST} <b>Подтверждение записи</b>\n\n"
    f"{E.USER} <b>Имя:</b> {{name}}\n"
    f"{E.SCISSORS} <b>Мастер:</b> {{master}}\n"
    f"{E.BARBER} <b>Услуга:</b> {{service}}\n"
    f"{E.CALENDAR} <b>Дата:</b> {{date}}\n"
    f"{E.CLOCK} <b>Время:</b> {{time}}\n"
    f"{E.MONEY} <b>Стоимость:</b> {{price}} ₸\n\n"
    "Всё верно?"
)

BOOKING_CONFIRMED = (
    f"{E.CHECK} <b>Запись подтверждена!</b>\n\n"
    f"{E.CALENDAR} <b>Дата:</b> {{date}}\n"
    f"{E.CLOCK} <b>Время:</b> {{time}}\n"
    f"{E.SCISSORS} <b>Мастер:</b> {{master}}\n\n"
    f"{E.LOCATION} {{address}}\n\n"
    "Ждём вас! Напомним за 24 ч и за 2 ч до визита."
)

BOOKING_CANCELLED = (
    f"{E.CROSS} <b>Запись отменена</b>\n\n"
    "Будем рады видеть вас снова — записывайтесь в любое время."
)

SLOT_BUSY = (
    f"{E.EXCLAMATION} Это время уже занято.\n\n"
    "Выберите другой слот или встаньте в лист ожидания."
)

RATE_LIMIT = (
    f"{E.EXCLAMATION} <b>Превышен лимит попыток.</b>\n\n"
    "Попробуйте через час."
)

ONE_ACTIVE_BOOKING = (
    f"{E.EXCLAMATION} <b>У вас уже есть активная запись.</b>\n\n"
    "Просмотреть записи — «Мои записи».\n"
    "Отменить — в меню записи."
)

NO_ACTIVE_BOOKING ="У вас нет активных записей."

MASTER_INFO = (
    f"{E.SCISSORS} <b>Мастер: {{name}}</b>\n\n"
    f"{E.CHART} <b>Опыт:</b> {{experience}}\n"
    f"{E.TARGET} <b>Специализация:</b> {{specialization}}"
)

CONTACTS = (
    f"{E.LOCATION} <b>Контакты</b>\n\n"
    f"{E.LOCATION} <b>Адрес:</b>\n{{address}}\n\n"
    f"{E.PHONE} <b>Телефон:</b>\n{{phone}}\n\n"
    f"{E.CLOCK} <b>Часы работы:</b>\n{{hours}}"
)

# ===== НАПОМИНАНИЯ =====

REMINDER_24H = (
    f"{E.CLOCK} <b>Напоминание о записи</b>\n\n"
    f"Завтра, {{date}}, в {{time}}\n"
    f"{E.SCISSORS} <b>Мастер:</b> {{master}}\n"
    f"{E.BARBER} <b>Услуга:</b> {{service}}\n\n"
    "Подтвердите визит или отмените запись:"
)

REMINDER_2H = (
    f"{E.EXCLAMATION} <b>Скоро у вас запись!</b>\n\n"
    f"Осталось <b>2 часа</b> — {{time}}\n"
    f"{E.SCISSORS} <b>Мастер:</b> {{master}}\n\n"
    "Подтвердите присутствие — мы вас ждём!\n\n"
    f"{E.INFO} <i>Если планы изменились — зайдите в «Мои записи».</i>"
)

CANCEL_LAST_MINUTE_ADMIN = (
    f"{E.EXCLAMATION} <b>Отмена за 2 часа — слот свободен!</b>\n\n"
    f"{E.USER} <b>Клиент:</b> {{name}}\n"
    f"{E.CALENDAR} <b>Дата:</b> {{date}}\n"
    f"{E.CLOCK} <b>Время:</b> {{time}}\n"
    f"{E.SCISSORS} <b>Мастер:</b> {{master}}\n\n"
    "Можно предложить это время другому клиенту."
)

REQUEST_REVIEW = (
    f"{E.STAR} <b>Как прошёл визит?</b>\n\n"
    f"{E.SCISSORS} <b>Мастер:</b> {{master}}\n"
    f"{E.CALENDAR} <b>Дата:</b> {{date}}\n\n"
    "Оцените качество обслуживания:"
)

LOYALTY_REWARD = (
    f"{E.STAR} <b>Бонус лояльности!</b>\n\n"
    "Это ваш {visit}-й визит!\n\n"
    f"{E.STAR} <b>Скидка {{discount}}%</b> на следующую услугу — сообщите администратору при записи."
)

REFERRAL_WELCOME = f"{E.PLUS} Вы пришли по реферальному коду {{code}}!"
REFERRAL_BONUS_MSG = f"{E.STAR} Начислено {{bonus}} бонусов за приглашение!"

WAITLIST_OFFER = (
    f"{E.STAR} <b>Слот освободился!</b>\n\n"
    f"{E.SCISSORS} <b>Мастер:</b> {{master}}\n"
    f"{E.CALENDAR} <b>Дата:</b> {{date}}\n"
    f"{E.CLOCK} <b>Время:</b> {{time}}\n\n"
    "Хотите записаться?"
)

WAITLIST_ADDED = (
    f"{E.CHECK} <b>Вы в листе ожидания</b>\n\n"
    f"{E.CALENDAR} <b>Дата:</b> {{date}}\n"
    f"{E.CLOCK} <b>Время:</b> {{time}}\n\n"
    "Уведомим, если время освободится."
)

ERROR = (
    f"{E.CROSS} Что-то пошло не так.\n"
    f"{E.RELOAD} Попробуйте ещё раз или обратитесь к администратору."
)

CANCELLED_SUCCESS = (
    f"{E.CHECK} <b>Запись отменена</b>\n\n"
    f"{E.ID} ID: <code>{{booking_id}}</code>"
)

# ===== АДМИН =====

ADMIN_BOOKING_NOTIFY = (
    f"{E.PLUS} <b>Новая запись</b>\n\n"
    f"{E.USER} <b>Клиент:</b> {{name}}\n"
    f"{E.SCISSORS} <b>Мастер:</b> {{master}}\n"
    f"{E.BARBER} <b>Услуга:</b> {{service}}\n"
    f"{E.CALENDAR} <b>Дата:</b> {{date}}\n"
    f"{E.CLOCK} <b>Время:</b> {{time}}\n"
    f"{E.MONEY} <b>Стоимость:</b> {{price}} ₸"
)

ADMIN_CANCEL_NOTIFY = (
    f"{E.CROSS} <b>Отмена записи</b>\n\n"
    f"{E.ID} ID: <code>{{booking_id}}</code>\n"
    "Отменена клиентом."
)

ADMIN_STATS = (
    f"{E.CHART} <b>Статистика</b>\n\n"
    f"{E.LIST} <b>Всего:</b> {{total}}\n"
    f"{E.CHECK} <b>Активных:</b> {{active}}\n"
    f"{E.CROSS} <b>Отменённых:</b> {{cancelled}}\n"
    f"{E.CHECK} <b>Завершённых:</b> {{completed}}\n\n"
    f"{E.MONEY} <b>Выручка:</b> {{revenue}} ₸"
)

ADMIN_EXPORT = f"{E.CHECK} Экспорт завершён. Файл: <code>{{filename}}</code>"
# BUG-F FIX: Use plain emoji for show_alert contexts
ADMIN_ONLY = "🔒 Команда доступна только администратору."

ABOUT = (
    f"{E.BARBER} <b>Barbershop «Острый»</b>\n\n"
    "Современный барбершоп в центре Астаны.\n"
    f"{E.STAR} Профессиональные мастера с опытом от 3 лет.\n"
    f"{E.SCISSORS} Мужские стрижки, уход за бородой, окрашивание."
)

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# ===== АДМИН CMS (plain text) =====
ADMIN_MASTER_LIST = "Мастера:\n\n{masters}"
ADMIN_MASTER_ADDED = "Мастер {name} добавлен."
ADMIN_MASTER_REMOVED = "Мастер {name} удалён."
ADMIN_MASTER_UPDATED = "Мастер {name} обновлён."
ADMIN_MASTER_NOT_FOUND = "Мастер {name} не найден."
ADMIN_ADD_MASTER_PROMPT = "Добавление мастера\n\nФормат: Имя, опыт, специализация\nПример: Иван, 5 лет, мужские стрижки"
ADMIN_EDIT_MASTER_PROMPT = "Редактирование мастера\n\nФормат: Имя, опыт, специализация\nПример: Иван, 6 лет, стрижки, бритьё"
ADMIN_REMOVE_MASTER_PROMPT = "Выберите мастера для удаления:"
ADMIN_SERVICE_LIST = "Услуги:\n\n{services}"
ADMIN_SERVICE_ADDED = "Услуга {name} добавлена ({price} ₸)."
ADMIN_SERVICE_REMOVED = "Услуга {name} удалена."
ADMIN_SERVICE_UPDATED = "Услуга {name} обновлена ({price} ₸)."
ADMIN_SERVICE_NOT_FOUND = "Услуга {name} не найдена."
ADMIN_ADD_SERVICE_PROMPT = "Добавление услуги\n\nФормат: Название, цена\nПример: Мужская стрижка, 3000"
ADMIN_EDIT_SERVICE_PROMPT = "Редактирование услуги\n\nФормат: Название, цена\nПример: Мужская стрижка, 3500"
ADMIN_REMOVE_SERVICE_PROMPT = "Выберите услугу для удаления:"
ADMIN_SETTINGS = "Настройки\n\nАдрес: {address}\nТелефон: {phone}\nЧасы работы: {hours}"
ADMIN_CHANGE_ADDRESS_PROMPT = "Введите новый адрес:"
ADMIN_CHANGE_PHONE_PROMPT = "Введите новый телефон:"
ADMIN_CHANGE_HOURS_PROMPT = "Часы работы (пример: Пн-Сб: 10:00-21:00, Вс: 11:00-19:00):"
ADMIN_CHANGE_SLOTS_PROMPT = "Слоты через запятую (10:00, 10:30, 11:00):"
ADMIN_SETTINGS_UPDATED = "Настройки обновлены."
ADMIN_STATS_DETAILED = (
    "Статистика\n\nВсего: {total}\nАктивных: {active}\n"
    "Отменённых: {cancelled}\nЗавершённых: {completed}\nВыручка: {revenue} ₸\n\n"
    "По мастерам:\n{by_master}\nПо дням:\n{by_day}\nПо услугам:\n{by_service}"
)
ADMIN_STATS_BY_MASTER = "  • {name}: {count} записей, {revenue} ₸\n"
ADMIN_STATS_BY_DAY = "  • {date}: {count} записей\n"
ADMIN_STATS_BY_SERVICE = "  • {name}: {count} записей, {revenue} ₸\n"
ADMIN_BOOKING_CANCEL = "Запись {booking_id} отменена администратором."
ADMIN_BOOKING_COMPLETE = "Запись {booking_id} завершена."
ADMIN_BOOKING_LIST = "Записи:\n\n{bookings}"
ADMIN_BOOKING_LIST_LINE = "• {id}: {date} {time} — {name} / {master} ({service}) [{status}]\n"
ADMIN_WAITLIST = "Лист ожидания:\n\n{waitlist}"
ADMIN_WAITLIST_LINE = "• {name}: {date} {time} — {master} ({service}) [{status}]\n"
ADMIN_LOYALTY_LIST = "Программа лояльности:\n\n{loyalty}"
ADMIN_LOYALTY_LINE = "• {name}: визитов {visits}, бонусов {bonuses}\n"
ADMIN_REVIEWS_LIST = "Отзывы:\n\n{reviews}"
ADMIN_REVIEWS_LINE = "• {booking_id}: {rating}/5 ({date})\n"
ADMIN_REFERRALS_LIST = "Рефералы:\n\n{referrals}"
ADMIN_REFERRALS_LINE = "• {referrer_id} → {referred_id} ({date})\n"

# ===== КНОПКИ =====
BACK_BUTTON = f"{E.HOME} Назад"
CONFIRM_BUTTON = f"{E.CHECK} Подтвердить"
CANCEL_BUTTON = f"{E.CROSS} Отменить"
YES_BUTTON = f"{E.CHECK} Приду"
NO_BUTTON = f"{E.CROSS} Отменить запись"
PHONE_BUTTON = f"{E.MOBILE} Поделиться номером"
CALL_BUTTON = f"{E.PHONE} Позвонить"
