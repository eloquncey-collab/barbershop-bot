#!/usr/bin/env python3
"""
Скрипт миграции БД для добавления таблицы slot_locks в существующие базы данных.

Использование:
    python migrate_db.py
    
Или указать путь к БД:
    python migrate_db.py data/barbershop.db
"""

import sys
import asyncio
import aiosqlite
import os
from pathlib import Path


async def check_table_exists(db_path: str, table_name: str) -> bool:
    """Проверить существует ли таблица в БД"""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        result = await cursor.fetchone()
        return result is not None


async def create_slot_locks_table(db_path: str) -> bool:
    """Создать таблицу slot_locks если её нет"""
    try:
        async with aiosqlite.connect(db_path) as db:
            # Создаём таблицу
            await db.execute("""
                CREATE TABLE IF NOT EXISTS slot_locks (
                    date        TEXT NOT NULL,
                    time        TEXT NOT NULL,
                    master      TEXT NOT NULL,
                    locked_at   TEXT NOT NULL,
                    expires_at  TEXT NOT NULL,
                    PRIMARY KEY (date, time, master)
                )
            """)
            await db.commit()
            print(f"✅ Таблица slot_locks создана в {db_path}")
            return True
    except Exception as e:
        print(f"❌ Ошибка при создании таблицы: {e}")
        return False


async def migrate_database(db_path: str):
    """Выполнить миграцию БД"""
    print(f"\n🔍 Проверяем БД: {db_path}")
    
    # Проверяем что файл существует
    if not Path(db_path).exists():
        print(f"❌ Файл БД не найден: {db_path}")
        return False
    
    # Проверяем наличие таблицы
    exists = await check_table_exists(db_path, "slot_locks")
    
    if exists:
        print(f"✅ Таблица slot_locks уже существует — миграция не требуется")
        return True
    
    print(f"⚠️  Таблица slot_locks отсутствует — создаём...")
    success = await create_slot_locks_table(db_path)
    
    if success:
        # Проверяем что таблица создана
        exists_after = await check_table_exists(db_path, "slot_locks")
        if exists_after:
            print(f"✅ Миграция завершена успешно!")
            return True
        else:
            print(f"❌ Таблица не создана — неизвестная ошибка")
            return False
    
    return False


async def main():
    """Главная функция"""
    print("="*60)
    print("🔧 МИГРАЦИЯ БД — Добавление таблицы slot_locks")
    print("="*60)
    
    # Определяем путь к БД
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Используем путь по умолчанию
        db_path = os.getenv("DB_PATH", "data/barbershop.db")
    
    # Выполняем миграцию
    success = await migrate_database(db_path)
    
    print("\n" + "="*60)
    if success:
        print("✅ МИГРАЦИЯ ЗАВЕРШЕНА")
        print("\nТеперь можно запускать бота:")
        print("  python bot.py")
    else:
        print("❌ МИГРАЦИЯ НЕ УДАЛАСЬ")
        print("\nПроверьте:")
        print("  1. Путь к БД корректен")
        print("  2. Файл БД не повреждён")
        print("  3. Есть права на запись")
    print("="*60)
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
