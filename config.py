"""
Шаблон конфигурации для барбершопа
Скопируйте этот файл как config.py и заполните реальными данными
"""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Telegram ID мастеров (формат в .env: "Имя1=123456789,Имя2=987654321")
MASTER_IDS = {}
raw_master_ids = os.getenv("MASTER_IDS", "")
if raw_master_ids:
    for pair in raw_master_ids.split(","):
        if "=" in pair:
            name, tid = pair.split("=", 1)
            try:
                telegram_id = int(tid.strip())
                if telegram_id < 1000:
                    print(f"⚠️  WARNING: MASTER_IDS contains suspicious ID for {name.strip()}: {telegram_id}")
                    print(f"    Real Telegram IDs are typically 9-10 digits. Update .env with valid IDs.")
                MASTER_IDS[name.strip()] = telegram_id
            except ValueError:
                pass

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")

# База данных
DB_PATH = os.getenv("DB_PATH","/app/data/barbershop.db")
TIMEZONE = os.getenv("TIMEZONE", "Asia/Almaty")

# ============================================================================
# НАСТРОЙКИ БАРБЕРШОПА - ЗАМЕНИТЕ НА РЕАЛЬНЫЕ ДАННЫЕ
# ============================================================================

BARBERSHOP_NAME = "ВАШ_БАРБЕРШОП"  # Замените на название вашего барбершопа
BARBERSHOP_ADDRESS = "г. [Город], ул. [Улица], [Дом]"  # Замените на реальный адрес
BARBERSHOP_PHONE = "+7 (XXX) XXX-XX-XX"  # Замените на реальный телефон
BARBERSHOP_WORKING_HOURS = "Пн-Сб: 10:00-21:00, Вс: 11:00-19:00"  # Настройте часы работы

# ============================================================================
# МАСТЕРА - ДОБАВЬТЕ РЕАЛЬНЫХ МАСТЕРОВ
# ============================================================================
# Формат: "Имя": {"experience": "X лет", "specialization": "описание"}

MASTERS = {
    "Имя Мастера 1": {"experience": "5 лет", "specialization": "мужские стрижки, бритьё"},
    "Имя Мастера 2": {"experience": "3 года", "specialization": "стрижки, моделирование бороды"},
    # Добавьте своих мастеров здесь
}

# ============================================================================
# УСЛУГИ - НАСТРОЙТЕ ПРАЙС-ЛИСТ
# ============================================================================
# Формат: "Название услуги": цена_в_тенге

SERVICES = {
    "Мужская стрижка": 3000,
    "Стрижка бороды": 1500,
    "Стрижка + борода": 4000,
    "Камуфляж седины": 5000,
    "Окрашивание": 6000,
    "Детская стрижка": 2500,
}

# ============================================================================
# РАСПИСАНИЕ И СЛОТЫ ВРЕМЕНИ
# ============================================================================

# Рабочие часы по дням недели (час начала, час окончания)
WORKING_HOURS = {
    "monday":    (10, 21),
    "tuesday":   (10, 21),
    "wednesday": (10, 21),
    "thursday":  (10, 21),
    "friday":    (10, 21),
    "saturday":  (10, 21),
    "sunday":    (11, 19),
}

# Временные слоты (автоматически генерируются из WORKING_HOURS)
TIME_SLOTS = [
    "10:00", "10:30", "11:00", "11:30",
    "12:00", "12:30", "13:00", "13:30",
    "14:00", "14:30", "15:00", "15:30",
    "16:00", "16:30", "17:00", "17:30",
    "18:00", "18:30", "19:00", "19:30",
    "20:00", "20:30",
]

# ============================================================================
# НАСТРОЙКИ ЛИМИТОВ И БОНУСОВ
# ============================================================================

MAX_BOOKING_ATTEMPTS = 10  # Максимум попыток записи
RATE_LIMIT_WINDOW = 1800  # Окно лимита в секундах (1 час)

LOYALTY_VISIT_INTERVAL = 5  # Каждый N-й визит дает бонус
LOYALTY_DISCOUNT_PERCENT = 10  # Процент скидки по программе лояльности
REFERRAL_BONUS = 100  # Бонус за приглашение друга


async def load_config_from_db():
    """Загрузка настроек из базы данных"""
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
    """Сохранение настроек в базу данных"""
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
