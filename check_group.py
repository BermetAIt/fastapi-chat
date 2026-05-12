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
DEFAULT_GROUP_NAME = '123'

async def check_and_populate_group(group_name: str = DEFAULT_GROUP_NAME):
    try:
        logger.info(f"🔍 Проверяю группу '{group_name}'...")
        
        async with aiosqlite.connect(DB_PATH) as db:
            # 1. Проверяем/создаём группу
            cursor = await db.execute("SELECT id FROM groups WHERE name = ?", (group_name,))
            group = await cursor.fetchone()
            
            if not group:
                logger.info(f"📝 Группа '{group_name}' не найдена. Создаю...")
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
            
            # 2. Получаем всех пользователей
            cursor = await db.execute("SELECT id, username FROM users")
            users_list = await cursor.fetchall()
            users = list(users_list)  # Конвертируем в список для len()
            logger.info(f"👥 Найдено пользователей: {len(users)}")
            
            added_count = 0
            for user_row in users:
                user_id, username = user_row[0], user_row[1]
                logger.info(f"🔹 Проверяю: {username} (ID: {user_id})")
                
                # 3. Проверяем членство в группе
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
                    logger.info(f" Пользователь {username} добавлен в группу '{group_name}'")
                    added_count += 1
                else:
                    logger.info(f"️  Пользователь {username} уже в группе")
            
            await db.commit()
            logger.info(f"🎉 Операция завершена! Добавлено новых участников: {added_count}")
            
    except Exception as e:
        logger.error(f"❌ Произошла ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    target_group = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GROUP_NAME
    asyncio.run(check_and_populate_group(target_group))