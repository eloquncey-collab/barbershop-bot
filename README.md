
# Барбершоп Бот — документация по деплою

Telegram-бот для барбершопа: онлайн-запись, напоминания, отзывы, реферальная система, программа лояльности.

## Требования

- Python 3.10+
- aiogram 3.x
- База данных: SQLite (дев) или PostgreSQL (продакшн)
- Docker + Docker Compose (опционально)

## Быстрый запуск

### 1. Настройка переменных окружения

```bash
cp .env.example .env
# Отредактируйте .env и заполните обязательные поля:
BOT_TOKEN=ваш_токен_из_BotFather
ADMIN_IDS=ваш_telegram_id
```

### 2a. Запуск через Docker

```bash
docker-compose up -d
```

### 2b. Запуск напрямую

```bash
pip install -r requirements.txt
python bot.py
```

## Деплой на Railway

1. Создайте новый проект на [railway.app](https://railway.app)
2. Подключите PostgreSQL сервис (в настройках Railway)
3. Добавьте переменные окружения (вкладка Variables):
   - `BOT_TOKEN` — токен бота
   - `ADMIN_IDS` — ваш Telegram ID
   - `DATABASE_URL` — автоматически выставляется Railway
   - `TIMEZONE` — `Asia/Almaty`
   - `REDIS_URL` — рекомендуется добавить Redis сервис
4. Деплойтесь через GitHub (push в main)

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню |
| `/me` | Профиль, записи, бонусы, реферальная ссылка |
| `/master` | Список мастеров |
| `/waitlist` | Мой лист ожидания |
| `/cancel` | Отменить запись |
| `/help` | Справка |
| `/admin` | Панель администратора (только для ADMIN_IDS) |

## Реферальная система

Каждый пользователь получает уникальную персональную ссылку через кнопку "🎁 Пригласить друга" в главном меню.
При переходе нового пользователя по ссылке пригласившему автоматически начисляется `REFERRAL_BONUS` (по умолчанию 100) бонусов.

## Структура файлов

```
barbershop_deploy/
├── bot.py              # Точка входа
├── config.py           # Настройки барбершопа
├── db.py               # Абстракция БД (SQLite/PG)
├── storage.py          # Операции с базой данных
├── scheduler.py        # Напоминания, авто-завершение броней
├── keyboards.py        # Инлайн-клавиатуры
├── messages.py         # Текстовые шаблоны
├── middleware.py       # Rate limit + Admin check
├── monitoring.py       # Health checks
├── backup.py           # Бэкап (SQLite gzip / PG SQL dump)
├── handlers/
│   ├── start.py        # /start, профиль, рефералы, отмены
│   ├── booking.py      # Полный флоу записи
│   ├── info.py         # Мастера, контакты, цены
│   └── admin.py        # Админ-панель
├── .env.example        # Шаблон переменных окружения
├── Dockerfile
└── docker-compose.yml
```

## Переменные окружения

| Переменная | Обяз.ательно | Описание |
|------------|------------|----------|
| `BOT_TOKEN` | ✅ | Токен из @BotFather |
| `ADMIN_IDS` | ✅ | Telegram ID админа(ов), через запятую |
| `DATABASE_URL` | ❌ | PostgreSQL URL (без него — SQLite) |
| `DB_PATH` | ❌ | Путь SQLite (ум. `/app/data/barbershop.db`) |
| `TIMEZONE` | ❌ | Часовой пояс (ум. `Asia/Almaty`) |
| `REDIS_URL` | ❌ | Redis URL для FSM-хранилища |
| `MASTER_IDS` | ❌ | `Имя=telegram_id,...` — уведомления мастерам |
| `MIN_BOOKING_ADVANCE_MINUTES` | ❌ | Мин. минут до записи (ум. 60) |
| `PROXY_URL` | ❌ | HTTP-прокси если Telegram заблокирован |
