import asyncio
import aiosqlite
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = 'users.db'

async def fix_group_membership(group_name: str):
    try:
        logger.info(f"🔧 Исправляю доступ к группе '{group_name}'...")
        
        async with aiosqlite.connect(DB_PATH) as db:
            # 1. Получаем список всех пользователей
            cursor = await db.execute("SELECT id, username FROM users")
            users_list = await cursor.fetchall()
            users = list(users_list)  # Конвертируем в список для len()
            logger.info(f"👥 Найдено пользователей: {len(users)}")
            
            # 2. Проверка существования группы
            cursor = await db.execute("SELECT id FROM groups WHERE name = ?", (group_name,))
            group = await cursor.fetchone()
            
            if not group:
                logger.warning(f"Группа '{group_name}' не найдена. Создаю...")
                await db.execute("INSERT INTO groups (name) VALUES (?)", (group_name,))
                await db.commit()
                
                cursor = await db.execute("SELECT last_insert_rowid()")
                row = await cursor.fetchone()
                if not row:
                    logger.error("❌ Не удалось получить ID новой группы")
                    return
                group_id = row[0]
                logger.info(f"✅ Группа '{group_name}' создана с ID: {group_id}")
            else:
                group_id = group[0]
                logger.info(f"✅ Группа '{group_name}' найдена с ID: {group_id}")
            
            # 3. Проверяем и исправляем членство
            added_count = 0
            for user_row in users:
                user_id, username = user_row[0], user_row[1]
                logger.info(f"🔹 Проверяю: {username} (ID: {user_id})")
                
                cursor = await db.execute(
                    "SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?",
                    (group_id, user_id)
                )
                is_member = await cursor.fetchone()
                
                if not is_member:
                    await db.execute(
                        "INSERT INTO group_members (group_id, user_id) VALUES (?, ?)",
                        (group_id, user_id)
                    )
                    logger.info(f" Пользователь {username} добавлен в группу")
                    added_count += 1
                else:
                    logger.info(f"️  Пользователь {username} уже в группе")
            
            await db.commit()
            logger.info(f"🎉 Исправление завершено. Добавлено пользователей: {added_count}")

            # 4. Финальная статистика
            cursor = await db.execute(
                "SELECT COUNT(*) FROM group_members WHERE group_id = ?", (group_id,)
            )
            count_row = await cursor.fetchone()
            count = count_row[0] if count_row else 0
            logger.info(f"📊 Всего участников в группе '{group_name}': {count}")
            
            # Получаем список имен
            cursor = await db.execute("""
                SELECT u.username 
                FROM group_members gm 
                JOIN users u ON gm.user_id = u.id 
                WHERE gm.group_id = ?
            """, (group_id,))
            rows_list = await cursor.fetchall()
            rows = list(rows_list)
            members = [row[0] for row in rows if row and row[0]]
            
            logger.info(f"👥 Список участников: {', '.join(members)}")

    except Exception as e:
        logger.error(f" Произошла ошибка: {e}")

if __name__ == "__main__":
    target_group = sys.argv[1] if len(sys.argv) > 1 else '123'
    asyncio.run(fix_group_membership(target_group))