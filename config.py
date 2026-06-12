import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# BUG-M6 FIX: Wrap ADMIN_IDS parsing in try/except
import logging as _logging
_cfg_logger = _logging.getLogger(__name__)
ADMIN_IDS = []
for _raw_id in os.getenv("ADMIN_IDS", "").split(","):
    _raw_id = _raw_id.strip()
    if _raw_id:
        try:
            ADMIN_IDS.append(int(_raw_id))
        except ValueError:
            _cfg_logger.warning(f"config: Invalid ADMIN_ID: {_raw_id} - must be int")

# Telegram ID мастеров (формат в .env: "Имя1=123456789,Имя2=987654321")
MASTER_IDS = {}
raw_master_ids = os.getenv("MASTER_IDS", "")
if raw_master_ids:
    for pair in raw_master_ids.split(","):
        if "=" in pair:
            name, tid = pair.split("=", 1)
            try:
                telegram_id = int(tid.strip())
                MASTER_IDS[name.strip()] = telegram_id
            except ValueError:
                pass

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")

# База данных
DB_PATH = os.getenv("DB_PATH", "/app/data/barbershop.db")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Almaty")

# ========================================
# НАСТРОИКИ БАРБЕРШОПА
# ========================================

BARBERSHOP_NAME = "Barbershop «Острый»"
BARBERSHOP_ADDRESS = "г. Алматы, ул. Абая 45, 2 этаж"
BARBERSHOP_PHONE = "+7 (771) 234-56-78"
BARBERSHOP_WORKING_HOURS = "Пн-Сб: 10:00-21:00, Вс: 11:00-19:00"

# ========================================
# МАСТЕРА
# ========================================

MASTERS = {
    "Алибек": {"experience": "5 лет",  "specialization": "классика, фейды, бритьё"},
    "Дамир":  {"experience": "3 года", "specialization": "мужские стрижки, моделирование бороды"},
    "Максат": {"experience": "2 года", "specialization": "детские стрижки, творческие стрижки, фейды"},
}

# ========================================
# УСЛУГИ
# ========================================

SERVICES = {
    "Мужская стрижка":   3000,
    "Стрижка бороды":   1500,
    "Стрижка + борода": 4000,
    "Камуфляж седины":  5000,
    "Окрашивание":      6000,
    "Детская стрижка":  2500,
}

# ========================================
# РАСПИСАНИЕ
# ========================================

WORKING_HOURS = {
    "monday":    (10, 21),
    "tuesday":   (10, 21),
    "wednesday": (10, 21),
    "thursday":  (10, 21),
    "friday":    (10, 21),
    "saturday":  (10, 21),
    "sunday":    (11, 19),
}

TIME_SLOTS = [
    "10:00", "10:30", "11:00", "11:30",
    "12:00", "12:30", "13:00", "13:30",
    "14:00", "14:30", "15:00", "15:30",
    "16:00", "16:30", "17:00", "17:30",
    "18:00", "18:30", "19:00", "19:30",
    "20:00", "20:30",
]

# ========================================
# ЛИМИТЫ И БОНУСЫ
# ========================================

MAX_BOOKING_ATTEMPTS = 10
MAX_ACTIVE_BOOKINGS = 3  # BUG-S6 FIX
MIN_BOOKING_ADVANCE_MINUTES = int(os.getenv("MIN_BOOKING_ADVANCE_MINUTES", "60"))
RATE_LIMIT_WINDOW = 1800

LOYALTY_VISIT_INTERVAL = 5
LOYALTY_DISCOUNT_PERCENT = 10
REFERRAL_BONUS = 100


async def load_config_from_db():
    """\u0417\u0430\u0433\u0440\u0443\u0437\u043a\u0430 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043a \u0438\u0437 \u0431\u0430\u0437\u044b \u0434\u0430\u043d\u043d\u044b\u0445"""
    global BARBERSHOP_ADDRESS, BARBERSHOP_PHONE, BARBERSHOP_WORKING_HOURS, TIME_SLOTS, MASTERS, SERVICES, WORKING_HOURS
    try:
        from storage import get_all_settings, get_all_masters, get_all_services
        settings = await get_all_settings()
        if "address" in settings:
            BARBERSHOP_ADDRESS = settings["address"]
        if "phone" in settings:
            BARBERSHOP_PHONE = settings["phone"]
        if "hours" in settings:
            BARBERSHOP_WORKING_HOURS = settings["hours"]
        if "slots" in settings:
            TIME_SLOTS = [s.strip() for s in settings["slots"].split(",")]
        if "working_hours_json" in settings:
            import json
            try:
                WORKING_HOURS = json.loads(settings["working_hours_json"])
            except Exception:
                pass
        masters = await get_all_masters()
        if masters:
            MASTERS.clear()
            MASTERS.update(masters)
        services = await get_all_services()
        if services:
            SERVICES.clear()
            SERVICES.update(services)
        from storage import get_all_master_telegram_ids
        db_master_ids = await get_all_master_telegram_ids()
        if db_master_ids:
            MASTER_IDS.update(db_master_ids)
    except Exception:
        pass


async def save_config_to_db():
    """\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0438\u0435 \u043d\u0430\u0441\u0442\u0440\u043e\u0435\u043a \u0432 \u0431\u0430\u0437\u0443 \u0434\u0430\u043d\u043d\u044b\u0445"""
    try:
        from storage import save_settings, save_master, save_service
        import json
        await save_settings("address", BARBERSHOP_ADDRESS)
        await save_settings("phone", BARBERSHOP_PHONE)
        await save_settings("hours", BARBERSHOP_WORKING_HOURS)
        await save_settings("slots", ",".join(TIME_SLOTS))
        await save_settings("working_hours_json", json.dumps(WORKING_HOURS))
        for name, info in MASTERS.items():
            await save_master(name, info["experience"], info["specialization"])
        for name, price in SERVICES.items():
            await save_service(name, price)
    except Exception:
        pass