import aiosqlite
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)
DB_PATH = 'users.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            last_activity TIMESTAMP,
            created_at TIMESTAMP
        )''')
        
        # Таблица сброса паролей
        await db.execute('''CREATE TABLE IF NOT EXISTS reset_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )''')
        
        # Таблица групп
        await db.execute('''CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )''')
        
        # Таблица участников групп
        await db.execute('''CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(group_id, user_id)
        )''')
        
        # Таблица сообщений
        await db.execute('''CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            target TEXT NOT NULL,
            mode TEXT NOT NULL,
            text TEXT NOT NULL,
            time TEXT NOT NULL,
            status TEXT DEFAULT 'sent',
            FOREIGN KEY (sender_id) REFERENCES users(id)
        )''')
        
        # Таблица контактов
        await db.execute('''CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            contact_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (contact_id) REFERENCES users(id),
            UNIQUE(user_id, contact_id)
        )''')
        
        # Создаём админа по умолчанию
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        cursor = await db.execute('SELECT id FROM users WHERE username = ?', ('admin',))
        admin = await cursor.fetchone()
        
        if not admin:
            admin_password = pwd_context.hash('admin123')
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await db.execute(
                'INSERT INTO users (username, email, password, is_admin, last_activity, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                ('admin', 'admin@example.com', admin_password, 1, now, now)
            )
            logger.info("Создан админ по умолчанию")
        
        await db.commit()
        logger.info("База данных инициализирована")

async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def update_user_activity(db: aiosqlite.Connection, user_id: int):
    await db.execute(
        'UPDATE users SET last_activity = ? WHERE id = ?',
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id)
    )
    await db.commit()