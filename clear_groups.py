import asyncio
import aiosqlite
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_PATH = 'users.db'

async def clear_groups_data():
    try:
        logger.warning("🚨 Начинаю очистку данных групп...")
        
        async with aiosqlite.connect(DB_PATH) as db:
            # 1. Удаляем все группы
            await db.execute('DELETE FROM groups')
            logger.info("🗑️ Все группы удалены")

            # 2. Удаляем все связи пользователей с группами
            await db.execute('DELETE FROM group_members')
            logger.info(" Все связи с группами удалены")

            # 3. Удаляем групповые сообщения
            await db.execute("DELETE FROM messages WHERE mode = 'groups'")
            logger.info(" Все групповые сообщения удалены")

            # Сохраняем изменения
            await db.commit()
            
            logger.info("✅ Операция очистки успешно завершена")

    except Exception as e:
        logger.error(f"❌ Произошла ошибка: {e}")

if __name__ == "__main__":
    # Запускаем асинхронную функцию
    asyncio.run(clear_groups_data())