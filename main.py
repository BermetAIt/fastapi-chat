# main.py — FastAPI Chat Backend (полная версия)
# Запуск: uvicorn main:app --reload

from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
import bcrypt
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager
import logging
import random
import string
import smtplib
import os
import aiosqlite
from email.mime.text import MIMEText
from deep_translator import GoogleTranslator

# ==================== CONFIG ====================
DB_PATH = 'users.db'
SECRET_KEY = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# ==================== LIFESPAN ====================
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    # Cleanup on shutdown if needed

app = FastAPI(title="Chat Application", version="1.0", lifespan=lifespan)

# ==================== MIDDLEWARE ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ==================== SESSIONS ====================
sessions: Dict[str, Dict] = {}

def create_session(user_data: Dict) -> str:
    session_id = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    sessions[session_id] = {**user_data, 'expires_at': datetime.now() + timedelta(days=7)}
    return session_id

def get_session(request: Request) -> Optional[Dict]:
    session_id = request.cookies.get('session_id')
    if session_id and session_id in sessions:
        session = sessions[session_id]
        if datetime.now() < session['expires_at']:
            return session
        del sessions[session_id]
    return None

# ==================== HELPERS ====================
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except ValueError:
        return False

def send_email(to_email: str, code: str) -> bool:
    try:
        smtp_server, smtp_port = 'smtp.gmail.com', 587
        smtp_user = os.getenv('SMTP_USER', 'ellabaktygulova@gmail.com')
        smtp_pass = os.getenv('SMTP_PASS', 'tmyz tpza nvsw rzcv')  # ⚠️ Используйте .env в продакшене!
        
        msg = MIMEText(f'Ваш код для сброса пароля: {code}\nДействителен 10 минут.')
        msg['Subject'], msg['From'], msg['To'] = 'Код для сброса пароля', smtp_user, to_email
        
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logger.error(f"SMTP error: {e}")
        return False

async def update_user_activity(db: aiosqlite.Connection, user_id: int):
    await db.execute('UPDATE users SET last_activity = ? WHERE id = ?',
                     (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
    await db.commit()

# ==================== DATABASE ====================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            last_activity TIMESTAMP,
            created_at TIMESTAMP
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS reset_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL, code TEXT NOT NULL, expires_at TIMESTAMP NOT NULL
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(group_id, user_id)
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL,
            target TEXT NOT NULL, mode TEXT NOT NULL, text TEXT NOT NULL,
            time TEXT NOT NULL, status TEXT DEFAULT 'sent',
            FOREIGN KEY (sender_id) REFERENCES users(id)
        )''')
        await db.execute('''CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, contact_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (contact_id) REFERENCES users(id),
            UNIQUE(user_id, contact_id)
        )''')
        
        # Создаём админа по умолчанию
        cursor = await db.execute('SELECT id FROM users WHERE username = ?', ('admin',))
        if not await cursor.fetchone():
            admin_pw = hash_password('admin123')
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await db.execute(
                'INSERT INTO users (username, email, password, is_admin, last_activity, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                ('admin', 'admin@example.com', admin_pw, 1, now, now)
            )
            logger.info("✅ Создан админ: admin / admin123")
        await db.commit()
        logger.info("✅ База данных инициализирована")

async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

# ==================== PYDANTIC MODELS ====================
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    username: str
    password: str

class PasswordResetRequest(BaseModel): email: EmailStr
class PasswordResetConfirm(BaseModel):
    email: EmailStr
    code: str
    new_password: str = Field(..., min_length=6)

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    members: List[str] = []

class GroupRename(BaseModel): oldName: str; newName: str
class GroupDelete(BaseModel): name: str
class AddGroupMembers(BaseModel): group: str; members: List[str]

class MessageCreate(BaseModel):
    target: str
    mode: str  # 'contacts' or 'groups'
    text: str
    time: str

class MessageDelete(BaseModel):
    mode: str
    target: str
    time: str
    text: str

class AddContact(BaseModel): contact_username: str
class RemoveContact(BaseModel): contact_username: str
class TranslateRequest(BaseModel):
    text: str
    source_lang: Optional[str] = 'auto'

# ==================== ROUTES: PAGES ====================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    session = get_session(request)
    if not session or not session.get('is_admin'):
        return templates.TemplateResponse("index.html", {"request": request, "admin_error": True})
    return templates.TemplateResponse("admin.html", {"request": request})

# Serve images from /img/ -> /static/img/
@app.get("/img/{filename:path}")
async def serve_img(filename: str):
    path = os.path.join("static", "img", filename)
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(404, "Image not found")

# ==================== ROUTES: AUTH ====================
@app.post("/api/register", status_code=201)
async def register(data: UserRegister, db=Depends(get_db)):
    try:
        hashed = hash_password(data.password)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        await db.execute(
            'INSERT INTO users (username, email, password, last_activity, created_at) VALUES (?, ?, ?, ?, ?)',
            (data.username, data.email, hashed, now, now)
        )
        await db.commit()
        return {'message': 'Пользователь зарегистрирован'}, 201
    except aiosqlite.IntegrityError:
        raise HTTPException(400, "Имя пользователя или email уже существуют")

@app.post("/api/login")
async def login(data: UserLogin, request: Request, db=Depends(get_db)):
    cursor = await db.execute('SELECT id, password, is_admin FROM users WHERE username = ?', (data.username,))
    user = await cursor.fetchone()
    if user and verify_password(data.password, user[1]):
        session_data = {'username': data.username, 'user_id': user[0], 'is_admin': bool(user[2])}
        await update_user_activity(db, user[0])
        session_id = create_session(session_data)
        response = JSONResponse({'message': 'Авторизация успешна'})
        response.set_cookie(key='session_id', value=session_id, httponly=True, max_age=604800)
        return response
    raise HTTPException(401, "Неверные учетные данные")

@app.post("/api/admin/login")
async def admin_login(data: UserLogin, request: Request, db=Depends(get_db)):
    cursor = await db.execute('SELECT id, password, is_admin FROM users WHERE username = ?', (data.username,))
    user = await cursor.fetchone()
    if not user: raise HTTPException(401, "Пользователь не найден")
    
    user_id, hashed_pw, is_admin = user
    # Сброс пароля для admin (как в оригинале)
    if data.username == 'admin':
        new_hash = hash_password('admin123')
        await db.execute('UPDATE users SET password = ? WHERE username = ?', (new_hash, 'admin'))
        await db.commit()
    
    if data.username == 'admin' or (verify_password(data.password, hashed_pw) and is_admin):
        session_data = {'username': data.username, 'user_id': user_id, 'is_admin': True}
        await update_user_activity(db, user_id)
        session_id = create_session(session_data)
        response = JSONResponse({'message': 'Авторизация админа успешна'})
        response.set_cookie(key='session_id', value=session_id, httponly=True, max_age=604800)
        return response
    raise HTTPException(401, "Неверные учетные данные")

@app.post("/api/logout")
async def logout(request: Request):
    session_id = request.cookies.get('session_id')
    if session_id and session_id in sessions: del sessions[session_id]
    response = JSONResponse({'success': True, 'message': 'Выход выполнен'})
    response.delete_cookie('session_id')
    return response

# ==================== ROUTES: PASSWORD RESET ====================
@app.post("/api/request-reset")
async def request_reset(data: PasswordResetRequest, db=Depends(get_db)):
    cursor = await db.execute('SELECT email FROM users WHERE LOWER(email) = LOWER(?)', (data.email,))
    if not await cursor.fetchone(): raise HTTPException(404, "Email не найден")
    code = ''.join(random.choices(string.digits, k=6))
    expires = datetime.now() + timedelta(minutes=10)
    await db.execute('INSERT INTO reset_codes (email, code, expires_at) VALUES (?, ?, ?)',
                     (data.email, code, expires.strftime('%Y-%m-%d %H:%M:%S')))
    await db.commit()
    if send_email(data.email, code): return {'message': 'Код отправлен'}
    raise HTTPException(500, "Ошибка отправки email")

@app.post("/api/reset-password")
async def reset_password(data: PasswordResetConfirm, db=Depends(get_db)):
    cursor = await db.execute(
        'SELECT code, expires_at FROM reset_codes WHERE email = ? ORDER BY expires_at DESC LIMIT 1', (data.email,))
    reset = await cursor.fetchone()
    if not reset: raise HTTPException(400, "Код не найден")
    stored_code, expires_str = reset
    expires = datetime.strptime(expires_str, '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expires: raise HTTPException(400, "Код истек")
    if data.code != stored_code: raise HTTPException(400, "Неверный код")
    hashed = hash_password(data.new_password)
    await db.execute('UPDATE users SET password = ? WHERE email = ?', (hashed, data.email))
    await db.execute('DELETE FROM reset_codes WHERE email = ?', (data.email,))
    await db.commit()
    return {'message': 'Пароль изменён'}

# ==================== ROUTES: USERS ====================
@app.get("/api/users")
async def get_users(db=Depends(get_db)):
    cursor = await db.execute('SELECT username FROM users')
    users = [row[0] for row in await cursor.fetchall()]
    return {'users': users}

@app.get("/api/users/details")
async def get_users_details(request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session or not session.get('is_admin'): raise HTTPException(401, "Только для админов")
    if session.get('user_id'): await update_user_activity(db, session['user_id'])
    
    cursor = await db.execute('SELECT id, username, email, is_admin, last_activity, created_at FROM users')
    rows = await cursor.fetchall()
    active_threshold = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    today_start = datetime.now().replace(hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
    
    users = []
    for row in rows:
        user = {'id': row[0], 'username': row[1], 'email': row[2], 'is_admin': bool(row[3]),
                'last_activity': row[4], 'is_active': row[4] and row[4] > active_threshold}
        if row[5]:
            user['created_at'] = row[5]
            user['is_new'] = row[5] >= today_start
        users.append(user)
    return {'users': users}

@app.get("/api/user/profile")
async def get_profile(request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    cursor = await db.execute('SELECT username, email FROM users WHERE username = ?', (session['username'],))
    user = await cursor.fetchone()
    if user: return {'success': True, 'name': user[0], 'email': user[1]}
    raise HTTPException(404, "Пользователь не найден")

# ==================== ROUTES: CONTACTS ====================
@app.get("/api/contacts")
async def get_contacts(request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    await update_user_activity(db, session['user_id'])
    cursor = await db.execute('''SELECT u.username FROM contacts c JOIN users u ON c.contact_id = u.id WHERE c.user_id = ?''',
                               (session['user_id'],))
    contacts = [row[0] for row in await cursor.fetchall()]
    return {'success': True, 'contacts': contacts}

@app.post("/api/contacts", status_code=201)
async def add_contact(data: AddContact, request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    if data.contact_username == session['username']:
        raise HTTPException(400, "Нельзя добавить себя в контакты")
    
    await update_user_activity(db, session['user_id'])
    cursor = await db.execute('SELECT id FROM users WHERE username = ?', (data.contact_username,))
    contact = await cursor.fetchone()
    if not contact: raise HTTPException(404, "Контакт не найден")
    
    contact_id = contact[0]
    # Проверяем, не добавлен ли уже
    cursor = await db.execute('SELECT 1 FROM contacts WHERE user_id = ? AND contact_id = ?',
                               (session['user_id'], contact_id))
    if await cursor.fetchone(): raise HTTPException(400, "Контакт уже добавлен")
    
    await db.execute('INSERT INTO contacts (user_id, contact_id) VALUES (?, ?)', (session['user_id'], contact_id))
    await db.execute('INSERT OR IGNORE INTO contacts (user_id, contact_id) VALUES (?, ?)', (contact_id, session['user_id']))
    await db.commit()
    return {'success': True, 'message': f'Контакт {data.contact_username} добавлен'}, 201

@app.post("/api/contacts/remove")
async def remove_contact(data: RemoveContact, request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    cursor = await db.execute('SELECT id FROM users WHERE username = ?', (data.contact_username,))
    contact = await cursor.fetchone()
    if not contact: raise HTTPException(404, "Контакт не найден")
    
    contact_id = contact[0]
    await db.execute('DELETE FROM contacts WHERE user_id = ? AND contact_id = ?', (session['user_id'], contact_id))
    await db.execute('DELETE FROM contacts WHERE user_id = ? AND contact_id = ?', (contact_id, session['user_id']))
    await db.commit()
    return {'success': True, 'message': f'Контакт {data.contact_username} удален'}

@app.post("/api/contacts/clear")
async def clear_contacts(request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    await db.execute('DELETE FROM contacts WHERE user_id = ?', (session['user_id'],))
    await db.commit()
    return {'success': True, 'message': 'Список контактов очищен'}

# ==================== ROUTES: GROUPS ====================
@app.get("/api/groups")
async def get_groups(request: Request, db=Depends(get_db)):
    session = get_session(request)
    if session and 'user_id' in session: await update_user_activity(db, session['user_id'])
    cursor = await db.execute('SELECT id, name FROM groups')
    groups = [{'id': r[0], 'name': r[1]} for r in await cursor.fetchall()]
    return {'groups': groups}

@app.post("/api/groups", status_code=201)
async def create_group(data: GroupCreate, request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    
    members = list(set(data.members + [session['username']]))
    placeholders = ','.join('?' * len(members))
    cursor = await db.execute(f'SELECT id, username FROM users WHERE LOWER(username) IN ({placeholders})',
                               [m.lower() for m in members])
    valid = await cursor.fetchall()
    valid_names = [r[1].lower() for r in valid]
    invalid = [m for m in members if m.lower() not in valid_names]
    if invalid: raise HTTPException(400, f"Пользователи не найдены: {', '.join(invalid)}")
    
    try:
        await db.execute('INSERT INTO groups (name) VALUES (?)', (data.name,))
        cursor = await db.execute('SELECT last_insert_rowid()')
        group_id = (await cursor.fetchone())[0]
        for user_id, _ in valid:
            await db.execute('INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)', (group_id, user_id))
        await db.commit()
        return {'success': True}, 201
    except aiosqlite.IntegrityError:
        raise HTTPException(400, "Группа с таким именем уже существует")

@app.get("/api/groups/members")
async def get_group_members(group: str, request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    cursor = await db.execute('SELECT id FROM groups WHERE name = ?', (group,))
    grp = await cursor.fetchone()
    if not grp: raise HTTPException(404, "Группа не найдена")
    cursor = await db.execute('SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?', (grp[0], session['user_id']))
    if not await cursor.fetchone(): raise HTTPException(403, "Вы не в этой группе")
    
    cursor = await db.execute('''SELECT u.username FROM group_members gm JOIN users u ON gm.user_id = u.id WHERE gm.group_id = ?''', (grp[0],))
    members = [row[0] for row in await cursor.fetchall()]
    return {'success': True, 'members': members}

@app.post("/api/groups/members/add")
async def add_group_members(data: AddGroupMembers, request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    cursor = await db.execute('SELECT id FROM groups WHERE name = ?', (data.group,))
    grp = await cursor.fetchone()
    if not grp: raise HTTPException(404, "Группа не найдена")
    cursor = await db.execute('SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?', (grp[0], session['user_id']))
    if not await cursor.fetchone(): raise HTTPException(403, "Вы не в этой группе")
    
    placeholders = ','.join('?' * len(data.members))
    cursor = await db.execute(f'SELECT id FROM users WHERE LOWER(username) IN ({placeholders})', [m.lower() for m in data.members])
    valid = await cursor.fetchall()
    added = 0
    for (user_id,) in valid:
        await db.execute('INSERT OR IGNORE INTO group_members (group_id, user_id) VALUES (?, ?)', (grp[0], user_id))
        added += 1
    await db.commit()
    return {'success': True, 'added_count': added}

@app.post("/api/groups/rename")
async def rename_group(data: GroupRename, request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    cursor = await db.execute('SELECT id FROM groups WHERE name = ?', (data.oldName,))
    grp = await cursor.fetchone()
    if not grp: raise HTTPException(404, "Группа не найдена")
    cursor = await db.execute('SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?', (grp[0], session['user_id']))
    if not await cursor.fetchone(): raise HTTPException(403, "Вы не в этой группе")
    
    await db.execute('UPDATE groups SET name = ? WHERE id = ?', (data.newName, grp[0]))
    await db.execute('UPDATE messages SET target = ? WHERE target = ? AND mode = ?', (data.newName, data.oldName, 'groups'))
    await db.commit()
    return {'success': True}

@app.post("/api/groups/delete")
async def delete_group(data: GroupDelete, request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    cursor = await db.execute('SELECT id FROM groups WHERE name = ?', (data.name,))
    grp = await cursor.fetchone()
    if not grp: raise HTTPException(404, "Группа не найдена")
    cursor = await db.execute('SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?', (grp[0], session['user_id']))
    if not await cursor.fetchone(): raise HTTPException(403, "Вы не в этой группе")
    
    await db.execute('DELETE FROM group_members WHERE group_id = ?', (grp[0],))
    await db.execute('DELETE FROM messages WHERE target = ? AND mode = ?', (data.name, 'groups'))
    await db.execute('DELETE FROM groups WHERE id = ?', (grp[0],))
    await db.commit()
    return {'success': True}

@app.post("/api/groups/clear")
async def clear_groups(request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    cursor = await db.execute('SELECT group_id FROM group_members WHERE user_id = ?', (session['user_id'],))
    group_ids = [row[0] for row in await cursor.fetchall()]
    await db.execute('DELETE FROM group_members WHERE user_id = ?', (session['user_id'],))
    for gid in group_ids:
        cursor = await db.execute('SELECT COUNT(*) FROM group_members WHERE group_id = ?', (gid,))
        if (await cursor.fetchone())[0] == 0:
            await db.execute('DELETE FROM groups WHERE id = ?', (gid,))
    await db.commit()
    return {'success': True, 'message': 'Вы покинули все группы'}

# ==================== ROUTES: MESSAGES ====================
@app.post("/api/messages", status_code=201)
async def send_message(data: MessageCreate, request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    if data.mode not in ['contacts', 'groups']: raise HTTPException(400, "Недопустимый режим")
    await update_user_activity(db, session['user_id'])
    
    if data.mode == 'contacts':
        cursor = await db.execute('SELECT id FROM users WHERE username = ?', (data.target,))
        contact = await cursor.fetchone()
        if not contact: raise HTTPException(404, "Контакт не найден")
        contact_id = contact[0]
        await db.execute('INSERT OR IGNORE INTO contacts (user_id, contact_id) VALUES (?, ?)', (session['user_id'], contact_id))
        await db.execute('INSERT OR IGNORE INTO contacts (user_id, contact_id) VALUES (?, ?)', (contact_id, session['user_id']))
        await db.execute('''INSERT INTO messages (sender_id, receiver_id, target, mode, text, time, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (session['user_id'], contact_id, data.target, data.mode, data.text, data.time, 'sent'))
        await db.execute('''INSERT INTO messages (sender_id, receiver_id, target, mode, text, time, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (session['user_id'], contact_id, session['username'], data.mode, data.text, data.time, 'sent'))
    else:  # groups
        cursor = await db.execute('SELECT id FROM groups WHERE name = ?', (data.target,))
        group = await cursor.fetchone()
        if not group: raise HTTPException(404, "Группа не найдена")
        cursor = await db.execute('SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?', (group[0], session['user_id']))
        if not await cursor.fetchone(): raise HTTPException(403, "Вы не в этой группе")
        await db.execute('''INSERT INTO messages (sender_id, receiver_id, target, mode, text, time, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                         (session['user_id'], 0, data.target, data.mode, data.text, data.time, 'sent'))
    await db.commit()
    return {'success': True}, 201

@app.get("/api/messages")
async def get_messages(request: Request, mode: str, target: str, since: Optional[str] = None, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    if mode not in ['contacts', 'groups']: raise HTTPException(400, "Недопустимый режим")
    await update_user_activity(db, session['user_id'])
    
    if mode == 'contacts':
        cursor = await db.execute('SELECT id FROM users WHERE username = ?', (target,))
        contact = await cursor.fetchone()
        if not contact: raise HTTPException(404, "Контакт не найден")
        contact_id = contact[0]
        query = '''SELECT m.id, m.text, m.time, m.status, m.sender_id, u.username
                   FROM messages m JOIN users u ON m.sender_id = u.id
                   WHERE m.mode = ? AND (
                       (m.sender_id = ? AND m.receiver_id = ? AND m.target = ?) OR
                       (m.sender_id = ? AND m.receiver_id = ? AND m.target = ?)
                   )'''
        params = [mode, session['user_id'], contact_id, target, contact_id, session['user_id'], session['username']]
    else:
        cursor = await db.execute('SELECT id FROM groups WHERE name = ?', (target,))
        group = await cursor.fetchone()
        if not group: raise HTTPException(404, "Группа не найдена")
        cursor = await db.execute('SELECT 1 FROM group_members WHERE group_id = ? AND user_id = ?', (group[0], session['user_id']))
        if not await cursor.fetchone(): raise HTTPException(403, "Вы не в этой группе")
        query = '''SELECT m.id, m.text, m.time, m.status, m.sender_id, u.username
                   FROM messages m JOIN users u ON m.sender_id = u.id
                   WHERE m.mode = ? AND m.target = ?'''
        params = [mode, target]
    
    if since:
        query += ' AND m.time > ?'
        params.append(since)
    query += ' ORDER BY m.time ASC'
    cursor = await db.execute(query, params)
    
    seen, messages = set(), []
    for row in await cursor.fetchall():
        key = f"{row[4]}:{row[1]}:{row[2]}"
        if key not in seen:
            seen.add(key)
            messages.append({'text': row[1], 'time': row[2], 'status': row[3],
                            'isSent': row[4] == session['user_id'], 'sender': row[5]})
    
    # Обновляем статус на 'read'
    if mode == 'contacts':
        await db.execute('''UPDATE messages SET status = 'read'
                            WHERE mode = ? AND target = ? AND sender_id = ? AND receiver_id = ? AND status = 'sent' ''',
                         (mode, session['username'], contact_id, session['user_id']))
    else:
        await db.execute('''UPDATE messages SET status = 'read'
                            WHERE mode = ? AND target = ? AND sender_id != ? AND status = 'sent' ''',
                         (mode, target, session['user_id']))
    await db.commit()
    return {'success': True, 'messages': messages}

@app.post("/api/messages/deleteForAll")
async def delete_message_for_all(data: MessageDelete, request: Request, db=Depends(get_db)):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    if data.mode == 'contacts':
        await db.execute('''DELETE FROM messages WHERE mode = ? AND sender_id = ? AND time = ? AND text = ?''',
                         (data.mode, session['user_id'], data.time, data.text))
    else:
        await db.execute('''DELETE FROM messages WHERE mode = ? AND target = ? AND sender_id = ? AND time = ? AND text = ?''',
                         (data.mode, data.target, session['user_id'], data.time, data.text))
    await db.commit()
    return {'success': True, 'message': 'Сообщение удалено'}

# ==================== ROUTES: TRANSLATION ====================
@app.post("/api/translate")
async def translate_text(data: TranslateRequest, request: Request):
    session = get_session(request)
    if not session: raise HTTPException(401, "Не авторизован")
    text, source = data.text, data.source_lang or 'auto'
    if source == 'auto':
        ru = sum(1 for c in text.lower() if 'а' <= c <= 'я' or c == 'ё')
        en = sum(1 for c in text.lower() if 'a' <= c <= 'z')
        source = 'ru' if ru > en else 'en'
    target = 'en' if source == 'ru' else 'ru'
    try:
        translator = GoogleTranslator(source=source, target=target)
        translated = translator.translate(text)
        return {'success': True, 'text': text, 'translated_text': translated, 'source_lang': source, 'target_lang': target}
    except Exception as e:
        logger.warning(f"Translation fallback: {e}")
        fallback = f"Перевод: {text}" if source == 'en' else f"Translation: {text}"
        return {'success': True, 'text': text, 'translated_text': fallback, 'source_lang': source, 'target_lang': target, 'fallback': True}
# ==================== ROUTES: STATS (для админ-панели) ====================
@app.get("/api/messages/stats")
async def get_messages_stats(request: Request, db=Depends(get_db)):
    """Статистика сообщений и пользователей для админ-панели"""
    session = get_session(request)
    if not session or not session.get('is_admin'):
        raise HTTPException(401, "Только для админов")
    
    # Общее количество уникальных сообщений
    cursor = await db.execute('''
        SELECT COUNT(*) FROM (
            SELECT DISTINCT sender_id, receiver_id, text, time FROM messages
        )
    ''')
    total_messages = (await cursor.fetchone())[0]
    
    # Сообщения за последние 24 часа
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    cursor = await db.execute('''
        SELECT COUNT(*) FROM (
            SELECT DISTINCT sender_id, receiver_id, text, time 
            FROM messages WHERE time > ?
        )
    ''', (yesterday,))
    recent_messages = (await cursor.fetchone())[0]
    
    # Активные пользователи (за 24 часа, не админы)
    active_since = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
    cursor = await db.execute('''
        SELECT COUNT(*) FROM users 
        WHERE last_activity > ? AND is_admin = 0
    ''', (active_since,))
    active_users = (await cursor.fetchone())[0]
    
    # Новые пользователи сегодня
    today = datetime.now().replace(hour=0, minute=0, second=0).strftime('%Y-%m-%d %H:%M:%S')
    cursor = await db.execute('''
        SELECT COUNT(*) FROM users 
        WHERE created_at >= ? AND is_admin = 0
    ''', (today,))
    new_users = (await cursor.fetchone())[0]
    
    # Топ-5 отправителей сообщений
    cursor = await db.execute('''
        SELECT sender_id, COUNT(*) as cnt FROM (
            SELECT DISTINCT sender_id, text, time FROM messages
        ) GROUP BY sender_id ORDER BY cnt DESC LIMIT 5
    ''')
    top_raw = await cursor.fetchall()
    top_senders = []
    for sender_id, count in top_raw:
        cursor = await db.execute('SELECT username FROM users WHERE id = ?', (sender_id,))
        row = await cursor.fetchone()
        if row:
            top_senders.append({'username': row[0], 'count': count})
    
    return {
        'total_messages': total_messages,
        'recent_messages': recent_messages,
        'active_users': active_users,
        'new_users': new_users,
        'top_senders': top_senders
    }
# ==================== WEBSOCKET (BONUS) ====================
@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")  # В продакшене: реальная рассылка
    except WebSocketDisconnect:
        logger.info("🔌 Клиент отключился")


if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)