import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from io import BytesIO

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

TOKEN = "9025997763:AAFF_6hSgwzjk0NrLko3-xZNiBOVNtofYHc"
OWNER_ID = 1739585715

CLASS_NAME = "10И"
CLASS_TEACHER = "Семёнова Ольга Забировна"
TEACHER_PASSWORD = "новый год"

CLASS_LIST = [
    "Акимова Ксения Владимировна",
    "Александрова Кира Павловна",
    "Алексеева Дарья Леонидовна",
    "Андреев Кирилл Русланович",
    "Андреева Дарья Андреевна",
    "Андреева Полина Дмитриевна",
    "Артемьева Полина Евгеньевна",
    "Васильева Полина Артёмовна",
    "Григорьева Полина Андреевна",
    "Домрачев Александр Романович",
    "Ефимова Диана Алексеевна",
    "Костина Ева Геннадьевна",
    "Кузнецов Алексей Иванович",
    "Лезин Илья Андреевич",
    "Леонтьев Артем Николаевич",
    "Лесив Арина Михайловна",
    "Морозов Даниил Константинович",
    "Мыльникова Вероника Владимировна",
    "Николаев Александр Николаевич",
    "Павлова Олеся Владимировна",
    "Прописнова Дарья Николаевна",
    "Прохорова Алена Юрьевна",
    "Прохорова Илемпи Сергеевна",
    "Семенов Артём Павлович",
    "Сосновский Леонид Евгеньевич",
    "Тимофеев Никита Русланович",
    "Трифонов Ростислав Евгеньевич",
    "Трубин Максим Александрович",
    "Устинов Матвей Ильич",
    "Хлебникова Александра Андреевна",
    "Штранц Кирилл Александрович",
    "Шумилов Илья Андреевич",
    "Яковлев Роман Сергеевич",
]

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

ADMINS = [OWNER_ID]

def normalize_name(name):
    return name.lower().replace('ё', 'е').replace('  ', ' ').strip()

def init_db():
    conn = sqlite3.connect('pushkin.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (tg_id INTEGER PRIMARY KEY, name TEXT, total_balance REAL, 
                  cinema_balance REAL, theater_balance REAL, class_position INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS events 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER, name TEXT, place TEXT, 
                  event_type TEXT, price REAL, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS class_list 
                 (position INTEGER PRIMARY KEY, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS teachers 
                 (tg_id INTEGER PRIMARY KEY, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER, name TEXT, 
                  action TEXT, timestamp TEXT)''')
    count = c.execute("SELECT COUNT(*) FROM class_list").fetchone()[0]
    if count == 0:
        for i, name in enumerate(CLASS_LIST, start=1):
            c.execute("INSERT INTO class_list (position, name) VALUES (?, ?)", (i, name))
        print(f"✅ Загружен список класса: {len(CLASS_LIST)} учеников")
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect('pushkin.db')

def log_action(tg_id, name, action):
    conn = get_db()
    conn.execute("INSERT INTO logs (tg_id, name, action, timestamp) VALUES (?, ?, ?, ?)",
                 (tg_id, name, action, datetime.now().strftime('%d.%m.%Y %H:%M:%S')))
    conn.commit()
    conn.close()

def is_admin(user_id):
    return user_id in ADMINS

def get_week_dates_keyboard():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    dates = []
    current = monday
    while current <= sunday:
        dates.append(current.strftime("%d.%m"))
        current += timedelta(days=1)
    rows = []
    for i in range(0, 7, 2):
        row = [InlineKeyboardButton(text=dates[i], callback_data=f"date_{dates[i]}")]
        if i + 1 < 7:
            row.append(InlineKeyboardButton(text=dates[i+1], callback_data=f"date_{dates[i+1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def back_button(callback_data):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]
    ])

def back_with_cancel(callback_data):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")]
    ])

class RoleState(StatesGroup):
    role = State()

class RegState(StatesGroup):
    name = State()
    total = State()
    cinema = State()

class TeacherPasswordState(StatesGroup):
    password = State()

class AddEventState(StatesGroup):
    name = State()
    place = State()
    event_type = State()
    price = State()

class EditEventState(StatesGroup):
    event_id = State()
    name = State()
    place = State()
    event_type = State()
    price = State()

class EditBalanceState(StatesGroup):
    total = State()
    cinema = State()

class BroadcastState(StatesGroup):
    message = State()

@router.message(Command("start"), StateFilter("*"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE tg_id=?", (message.from_user.id,)).fetchone()
    teacher = conn.execute("SELECT * FROM teachers WHERE tg_id=?", (message.from_user.id,)).fetchone()
    conn.close()
    if user:
        log_action(message.from_user.id, user[1], "Вход в бота")
        await show_menu(message)
    elif teacher:
        log_action(message.from_user.id, teacher[1], "Вход учителя")
        await show_teacher_menu(message)
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎓 Я ученик", callback_data="role_student")],
            [InlineKeyboardButton(text="👨‍🏫 Я учитель", callback_data="role_teacher")],
        ])
        await message.answer("👋 Привет! Я бот для учёта Пушкинской карты (10И класс).\n\nВыбери свою роль:", reply_markup=kb)
        await state.set_state(RoleState.role)

@router.callback_query(F.data == "role_student")
async def role_student(cb: CallbackQuery, state: FSMContext):
    await state.update_data(role="student")
    await cb.message.answer("👤 Введи своё ФИО:")
    await state.set_state(RegState.name)
    await cb.answer()

@router.callback_query(F.data == "role_teacher")
async def role_teacher(cb: CallbackQuery, state: FSMContext):
    await state.update_data(role="teacher")
    await cb.message.answer("🔐 Введи пароль учителя:", reply_markup=back_button("back_to_role"))
    await state.set_state(TeacherPasswordState.password)
    await cb.answer()

@router.callback_query(F.data == "back_to_role")
async def back_to_role(cb: CallbackQuery, state: FSMContext):
    await cb.message.delete()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎓 Я ученик", callback_data="role_student")],
        [InlineKeyboardButton(text="👨‍🏫 Я учитель", callback_data="role_teacher")],
    ])
    await cb.message.answer("Выбери роль:", reply_markup=kb)
    await state.set_state(RoleState.role)
    await cb.answer()

@router.message(TeacherPasswordState.password)
async def teacher_password(message: Message, state: FSMContext):
    if message.text.strip().lower() != TEACHER_PASSWORD.lower():
        return await message.answer("❌ Неверный пароль. Попробуй ещё раз.")
    conn = get_db()
    existing = conn.execute("SELECT * FROM teachers WHERE tg_id=?", (message.from_user.id,)).fetchone()
    if existing:
        await state.clear()
        return await show_teacher_menu(message)
    conn.execute("INSERT INTO teachers (tg_id, name) VALUES (?, ?)", (message.from_user.id, "Учитель"))
    conn.commit()
    conn.close()
    if message.from_user.id not in ADMINS:
        ADMINS.append(message.from_user.id)
    log_action(message.from_user.id, "Учитель", "Регистрация учителя")
    await state.clear()
    await message.answer(f"✅ Здравствуйте! Вы зарегистрированы как учитель ({CLASS_NAME} класс).\n\nВам доступны все функции администратора.\n\nИспользуйте меню ниже 👇")
    await show_teacher_menu(message)

@router.message(RegState.name)
async def reg_name(message: Message, state: FSMContext):
    name_input = message.text.strip()
    name_normalized = normalize_name(name_input)
    conn = get_db()
    students = conn.execute("SELECT position, name FROM class_list ORDER BY position").fetchall()
    conn.close()
    found = None
    best_match = None
    best_score = 0
    for position, full_name in students:
        db_name = normalize_name(full_name)
        if db_name == name_normalized:
            found = (position, full_name)
            break
        if name_normalized in db_name or db_name in name_normalized:
            score = len(set(name_normalized.split()) & set(db_name.split()))
            if score > best_score:
                best_score = score
                best_match = (position, full_name)
    if not found and best_match:
        found = best_match
    if found:
        position, full_name = found
        conn = get_db()
        existing_user = conn.execute("SELECT * FROM users WHERE tg_id=?", (message.from_user.id,)).fetchone()
        if existing_user:
            conn.close()
            await state.clear()
            return await message.answer(f"⚠️ Вы уже зарегистрированы как {existing_user[1]}.\n\nЕсли это ошибка — напишите администратору.")
        existing_position = conn.execute("SELECT tg_id FROM users WHERE class_position=?", (position,)).fetchone()
        conn.close()
        if existing_position:
            await message.answer(f"⚠️ Строка {position} ({full_name}) уже занята другим аккаунтом.\n\nЕсли это вы — напишите администратору.")
            return
        await state.update_data(name=full_name, position=position)
        if "Алексеева Дарья Леонидовна" in full_name:
            if message.from_user.id not in ADMINS:
                ADMINS.append(message.from_user.id)
            print(f"✅ {full_name} добавлена в админы")
        await message.answer(f"✅ Найдено: *{full_name}*\n📍 Твоя строка в таблице: *{position}*\n\n💰 Введи ОБЩИЙ баланс (например, 2800):", parse_mode="Markdown")
        await state.set_state(RegState.total)
    else:
        conn = get_db()
        sample = conn.execute("SELECT name FROM class_list LIMIT 10").fetchall()
        conn.close()
        sample_text = "\n".join([f"• {s[0]}" for s in sample])
        await message.answer(f"❌ ФИО \"{name_input}\" не найдено.\n\nВот как выглядят имена в списке:\n{sample_text}\n\nНапиши своё ФИО ещё раз:")

@router.message(RegState.total)
async def reg_total(message: Message, state: FSMContext):
    try:
        total = float(message.text.replace(',', '.'))
    except:
        return await message.answer("❌ Введи число, например 2800")
    await state.update_data(total=total)
    await message.answer(f"✅ Общий баланс: {int(total)}₽\n\n🎬 Сколько из них на КИНО?")
    await state.set_state(RegState.cinema)

@router.message(RegState.cinema)
async def reg_cinema(message: Message, state: FSMContext):
    try:
        cinema = float(message.text.replace(',', '.'))
    except:
        return await message.answer("❌ Введи число")
    data = await state.get_data()
    total = data['total']
    theater = total - cinema
    if theater < 0:
        return await message.answer("❌ Баланс на кино больше общего. Проверь данные.")
    conn = get_db()
    conn.execute("INSERT INTO users (tg_id, name, total_balance, cinema_balance, theater_balance, class_position) VALUES (?, ?, ?, ?, ?, ?)",
                 (message.from_user.id, data['name'], total, cinema, theater, data['position']))
    conn.commit()
    conn.close()
    await state.clear()
    log_action(message.from_user.id, data['name'], f"Регистрация (общий: {int(total)}, кино: {int(cinema)}, театр: {int(theater)})")
    await message.answer(f"✅ Готово, {data['name']}!\n📍 Твоя строка в таблице: {data['position']}\n\n💰 Общий: {int(total)}₽\n🎬 Кино: {int(cinema)}₽\n🎭 Театр: {int(theater)}₽\n\nИспользуй /menu или кнопки ниже 👇")
    await show_menu(message)

async def show_menu(message: Message):
    kb_rows = [
        [InlineKeyboardButton(text="💰 Мой баланс", callback_data="balance")],
        [InlineKeyboardButton(text="➕ Добавить мероприятие", callback_data="add_event")],
        [InlineKeyboardButton(text="📋 Мои мероприятия", callback_data="week_events")],
        [InlineKeyboardButton(text="✏️ Изменить баланс", callback_data="edit_balance")],
    ]
    if is_admin(message.from_user.id):
        kb_rows.append([InlineKeyboardButton(text="📢 Рассылка всем", callback_data="broadcast")])
        kb_rows.append([InlineKeyboardButton(text="👨‍🏫 Админ-панель", callback_data="admin_panel")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    return await message.answer("📱 Меню:", reply_markup=kb)

async def show_menu_direct(user_id):
    kb_rows = [
        [InlineKeyboardButton(text="💰 Мой баланс", callback_data="balance")],
        [InlineKeyboardButton(text="➕ Добавить мероприятие", callback_data="add_event")],
        [InlineKeyboardButton(text="📋 Мои мероприятия", callback_data="week_events")],
        [InlineKeyboardButton(text="✏️ Изменить баланс", callback_data="edit_balance")],
    ]
    if is_admin(user_id):
        kb_rows.append([InlineKeyboardButton(text="📢 Рассылка всем", callback_data="broadcast")])
        kb_rows.append([InlineKeyboardButton(text="👨‍🏫 Админ-панель", callback_data="admin_panel")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await bot.send_message(user_id, "📱 Меню:", reply_markup=kb)

async def show_teacher_menu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Получить Excel", callback_data="export_now")],
        [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="broadcast")],
        [InlineKeyboardButton(text="👥 Зарегистрированные ученики", callback_data="list_users")],
        [InlineKeyboardButton(text="📋 Список класса", callback_data="view_class")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="📜 Логи действий", callback_data="logs")],
    ])
    await message.answer("👨‍🏫 Панель учителя:", reply_markup=kb)

async def show_teacher_menu_direct(user_id):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Получить Excel", callback_data="export_now")],
        [InlineKeyboardButton(text="📢 Рассылка всем", callback_data="broadcast")],
        [InlineKeyboardButton(text="👥 Зарегистрированные ученики", callback_data="list_users")],
        [InlineKeyboardButton(text="📋 Список класса", callback_data="view_class")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="📜 Логи действий", callback_data="logs")],
    ])
    await bot.send_message(user_id, "👨‍🏫 Панель учителя:", reply_markup=kb)

@router.message(Command("menu"), StateFilter("*"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    conn = get_db()
    teacher = conn.execute("SELECT * FROM teachers WHERE tg_id=?", (message.from_user.id,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE tg_id=?", (message.from_user.id,)).fetchone()
    conn.close()
    if teacher:
        await show_teacher_menu(message)
    elif user:
        await show_menu(message)
    else:
        await message.answer("❌ Сначала зарегистрируйтесь через /start")

async def get_balance_text(tg_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)).fetchone()
    spent = conn.execute("SELECT event_type, SUM(price) FROM events WHERE tg_id=? GROUP BY event_type", (tg_id,)).fetchall()
    conn.close()
    if not user:
        return "❌ Сначала нажми /start"
    _, name, total, cinema, theater, position = user
    spent_cinema = sum(p for t, p in spent if t == 'кино') or 0
    spent_theater = sum(p for t, p in spent if t == 'театр') or 0
    return (f"💰 *Пушкинская карта — {name}*\n📍 Строка в таблице: {position}\n\n"
            f"🎬 Кино: {int(cinema - spent_cinema)}₽\n🎭 Театр: {int(theater - spent_theater)}₽\n\n"
            f"📊 Потрачено: {int(spent_cinema + spent_theater)}₽")

@router.callback_query(F.data == "balance")
async def cb_balance(cb: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]])
    await cb.message.answer(await get_balance_text(cb.from_user.id), parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@router.message(Command("balance"), StateFilter("*"))
async def cmd_balance(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]])
    await message.answer(await get_balance_text(message.from_user.id), parse_mode="Markdown", reply_markup=kb)

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    conn = get_db()
    teacher = conn.execute("SELECT * FROM teachers WHERE tg_id=?", (cb.from_user.id,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE tg_id=?", (cb.from_user.id,)).fetchone()
    conn.close()
    try:
        await cb.message.delete()
    except:
        pass
    if teacher:
        await show_teacher_menu_direct(cb.from_user.id)
    elif user:
        await show_menu_direct(cb.from_user.id)
    else:
        await bot.send_message(cb.from_user.id, "❌ Сначала зарегистрируйтесь через /start")

@router.callback_query(F.data == "back_to_menu_from_admin")
async def back_to_menu_from_admin(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    try:
        await cb.message.delete()
    except:
        pass
    conn = get_db()
    teacher = conn.execute("SELECT * FROM teachers WHERE tg_id=?", (cb.from_user.id,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE tg_id=?", (cb.from_user.id,)).fetchone()
    conn.close()
    if teacher:
        await show_teacher_menu_direct(cb.from_user.id)
    elif user:
        await show_menu_direct(cb.from_user.id)
    else:
        await bot.send_message(cb.from_user.id, "❌ Сначала зарегистрируйтесь через /start")

@router.callback_query(F.data == "edit_balance")
async def edit_balance_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("✏️ *Изменение баланса*\n\nВведи НОВЫЙ общий баланс (например, 2800):", parse_mode="Markdown", reply_markup=back_with_cancel("back_to_menu"))
    await state.set_state(EditBalanceState.total)
    await cb.answer()

@router.message(EditBalanceState.total)
async def edit_balance_total(message: Message, state: FSMContext):
    try:
        total = float(message.text.replace(',', '.'))
    except:
        return await message.answer("❌ Введи число, например 2800")
    await state.update_data(total=total)
    await message.answer(f"✅ Новый общий баланс: {int(total)}₽\n\n🎬 Сколько из них на КИНО?", reply_markup=back_button("back_to_edit_total"))
    await state.set_state(EditBalanceState.cinema)

@router.callback_query(F.data == "back_to_edit_total")
async def back_to_edit_total(cb: CallbackQuery, state: FSMContext):
    await cb.message.delete()
    await cb.message.answer("✏️ Введи НОВЫЙ общий баланс:", reply_markup=back_with_cancel("back_to_menu"))
    await state.set_state(EditBalanceState.total)
    await cb.answer()

@router.message(EditBalanceState.cinema)
async def edit_balance_cinema(message: Message, state: FSMContext):
    try:
        cinema = float(message.text.replace(',', '.'))
    except:
        return await message.answer("❌ Введи число")
    data = await state.get_data()
    total = data['total']
    theater = total - cinema
    if theater < 0:
        return await message.answer("❌ Баланс на кино больше общего.")
    conn = get_db()
    conn.execute("UPDATE users SET total_balance=?, cinema_balance=?, theater_balance=? WHERE tg_id=?", (total, cinema, theater, message.from_user.id))
    conn.commit()
    conn.close()
    await state.clear()
    log_action(message.from_user.id, "Пользователь", f"Изменение баланса (общий: {int(total)}, кино: {int(cinema)}, театр: {int(theater)})")
    await message.answer(f"✅ Баланс обновлён!\n\n💰 Общий: {int(total)}₽\n🎬 Кино: {int(cinema)}₽\n🎭 Театр: {int(theater)}₽")
    await show_menu(message)

@router.callback_query(F.data == "add_event")
async def start_add_event(cb: CallbackQuery, state: FSMContext):
    kb = back_with_cancel("back_to_menu")
    await cb.message.answer("🎟 Введи НАЗВАНИЕ мероприятия (например, Ёлки 11):", reply_markup=kb)
    await state.set_state(AddEventState.name)
    await cb.answer()

@router.callback_query(F.data == "cancel_add")
async def cancel_add(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("❌ Отменено.")
    await cb.answer()

@router.message(AddEventState.name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = back_with_cancel("back_to_name")
    await message.answer("📍 Введи МЕСТО (например, Синема 5):", reply_markup=kb)
    await state.set_state(AddEventState.place)

@router.callback_query(F.data == "back_to_name")
async def back_to_name(cb: CallbackQuery, state: FSMContext):
    await cb.message.delete()
    kb = back_with_cancel("back_to_menu")
    await cb.message.answer("🎟 Введи НАЗВАНИЕ мероприятия:", reply_markup=kb)
    await state.set_state(AddEventState.name)
    await cb.answer()

@router.message(AddEventState.place)
async def add_place(message: Message, state: FSMContext):
    await state.update_data(place=message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Кино", callback_data="type_cinema")],
        [InlineKeyboardButton(text="🎭 Театр", callback_data="type_theater")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_place")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")],
    ])
    await message.answer("Выбери тип:", reply_markup=kb)

@router.callback_query(F.data == "back_to_place")
async def back_to_place(cb: CallbackQuery, state: FSMContext):
    await cb.message.delete()
    kb = back_with_cancel("back_to_name")
    await cb.message.answer("📍 Введи МЕСТО:", reply_markup=kb)
    await state.set_state(AddEventState.place)
    await cb.answer()

@router.callback_query(F.data.in_(["type_cinema", "type_theater"]))
async def add_type(cb: CallbackQuery, state: FSMContext):
    event_type = "кино" if cb.data == "type_cinema" else "театр"
    await state.update_data(event_type=event_type)
    kb = back_with_cancel("back_to_type")
    await cb.message.answer("💰 Введи ЦЕНУ билета:", reply_markup=kb)
    await state.set_state(AddEventState.price)
    await cb.answer()

@router.callback_query(F.data == "back_to_type")
async def back_to_type(cb: CallbackQuery, state: FSMContext):
    await cb.message.delete()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Кино", callback_data="type_cinema")],
        [InlineKeyboardButton(text="🎭 Театр", callback_data="type_theater")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_place")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add")],
    ])
    await cb.message.answer("Выбери тип:", reply_markup=kb)
    await cb.answer()

@router.message(AddEventState.price)
async def add_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.replace(',', '.'))
    except:
        return await message.answer("❌ Введи число")
    await state.update_data(price=price)
    await message.answer("📅 Выбери ДАТУ:", reply_markup=get_week_dates_keyboard())

@router.callback_query(F.data.startswith("date_"), AddEventState.price)
async def add_date(cb: CallbackQuery, state: FSMContext):
    selected_date = str(cb.data.split("date_")[1])
    await state.update_data(date=selected_date)
    data = await state.get_data()
    
    if 'price' not in data:
        return await cb.message.answer("❌ Ошибка: цена не сохранена.")
    
    price = float(data['price'])
    
    conn = get_db()
    conn.execute(
        "INSERT INTO events (tg_id, name, place, event_type, price, date) VALUES (?, ?, ?, ?, ?, ?)",
        (int(cb.from_user.id), str(data['name']), str(data['place']), str(data['event_type']), price, selected_date)
    )
    conn.commit()
    
    last_event = conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT 1").fetchone()
    print(f"✅ Записано в БД: ID={last_event[0]}, TG_ID={last_event[1]}, Name={last_event[2]}, Price={last_event[5]}, Date={last_event[6]}")
    
    user = conn.execute("SELECT * FROM users WHERE tg_id=?", (cb.from_user.id,)).fetchone()
    spent = conn.execute("SELECT event_type, SUM(price) FROM events WHERE tg_id=? GROUP BY event_type", (cb.from_user.id,)).fetchall()
    conn.close()
    
    _, name, total, cinema, theater, position = user
    spent_cinema = sum(p for t, p in spent if t == 'кино') or 0
    spent_theater = sum(p for t, p in spent if t == 'театр') or 0
    
    await state.clear()
    
    log_action(cb.from_user.id, name, f"Добавление: {data['name']} ({data['event_type']}, {int(price)}₽, {selected_date})")
    
    icon = "🎬" if data['event_type'] == "кино" else "🎭"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📱 В главное меню", callback_data="back_to_menu")]])
    
    await cb.message.answer(
        f"✅ Добавлено! Баланс списан.\n\n"
        f"{icon} *{data['name']}*\n"
        f"📍 {data['place']}\n"
        f"💰 {int(price)}₽\n"
        f"📅 {selected_date}\n\n"
        f"💰 *Твой баланс:*\n"
        f"🎬 Кино: {int(cinema - spent_cinema)}₽\n"
        f"🎭 Театр: {int(theater - spent_theater)}₽",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await cb.answer()

@router.callback_query(F.data == "week_events")
async def week_events(cb: CallbackQuery):
    conn = get_db()
    events = conn.execute("SELECT id, name, place, event_type, price, date FROM events WHERE tg_id=? ORDER BY date", (cb.from_user.id,)).fetchall()
    conn.close()
    if not events:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")],
            [InlineKeyboardButton(text="➕ Добавить", callback_data="add_event")]
        ])
        return await cb.message.answer("📭 Пока нет мероприятий.", reply_markup=kb)
    text = "📋 *Твои мероприятия:*\n\n"
    kb_rows = []
    for event_id, name, place, etype, price, date in events:
        icon = "🎬" if etype == "кино" else "🎭"
        text += f"{icon} *{name}*\n📍 {place}\n💰 {int(price)}₽ | 📅 {date}\n\n"
        kb_rows.append([
            InlineKeyboardButton(text=f"✏️ {name}", callback_data=f"edit_event_{event_id}"),
            InlineKeyboardButton(text=f"🗑", callback_data=f"del_event_{event_id}")
        ])
    kb_rows.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    await cb.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data.startswith("edit_event_"))
async def edit_event_start(cb: CallbackQuery, state: FSMContext):
    event_id = int(cb.data.split("edit_event_")[1])
    conn = get_db()
    event = conn.execute("SELECT * FROM events WHERE id=? AND tg_id=?", (event_id, cb.from_user.id)).fetchone()
    conn.close()
    if not event:
        return await cb.message.answer("❌ Мероприятие не найдено")
    await state.update_data(event_id=event_id, old_name=event[2], old_place=event[3], old_type=event[4], old_price=event[5], old_date=event[6])
    kb = back_with_cancel("back_to_events")
    await cb.message.answer(f"✏️ *Редактирование: {event[2]}*\n\nТекущее место: {event[3]}\nНовое название (или отправь '-' чтобы оставить):", parse_mode="Markdown", reply_markup=kb)
    await state.set_state(EditEventState.name)
    await cb.answer()

@router.callback_query(F.data == "back_to_events")
async def back_to_events(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.delete()
    await week_events(cb)
    await cb.answer()

@router.message(EditEventState.name)
async def edit_event_name(message: Message, state: FSMContext):
    data = await state.get_data()
    new_name = message.text.strip()
    if new_name == '-':
        new_name = data['old_name']
    await state.update_data(name=new_name)
    kb = back_with_cancel("back_to_events")
    await message.answer(f"📍 Новое место (или '-' чтобы оставить {data['old_place']}):", reply_markup=kb)
    await state.set_state(EditEventState.place)

@router.message(EditEventState.place)
async def edit_event_place(message: Message, state: FSMContext):
    data = await state.get_data()
    new_place = message.text.strip()
    if new_place == '-':
        new_place = data['old_place']
    await state.update_data(place=new_place)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Кино", callback_data="edit_type_cinema")],
        [InlineKeyboardButton(text="🎭 Театр", callback_data="edit_type_theater")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_edit_place")],
    ])
    await message.answer(f"Выбери тип (или отправь '-' чтобы оставить {data['old_type']}):", reply_markup=kb)

@router.callback_query(F.data == "back_to_edit_place")
async def back_to_edit_place(cb: CallbackQuery, state: FSMContext):
    await cb.message.delete()
    data = await state.get_data()
    await cb.message.answer(f"📍 Новое место (или '-' чтобы оставить {data['old_place']}):")
    await state.set_state(EditEventState.place)
    await cb.answer()

@router.callback_query(F.data.in_(["edit_type_cinema", "edit_type_theater"]))
async def edit_event_type(cb: CallbackQuery, state: FSMContext):
    event_type = "кино" if cb.data == "edit_type_cinema" else "театр"
    await state.update_data(event_type=event_type)
    kb = back_with_cancel("back_to_events")
    await cb.message.answer("💰 Новая цена (или '-' чтобы оставить):", reply_markup=kb)
    await state.set_state(EditEventState.price)
    await cb.answer()

@router.message(EditEventState.price)
async def edit_event_price(message: Message, state: FSMContext):
    data = await state.get_data()
    price_text = message.text.strip()
    if price_text == '-':
        new_price = data['old_price']
    else:
        try:
            new_price = float(price_text.replace(',', '.'))
        except:
            return await message.answer("❌ Введи число или '-'")
    conn = get_db()
    conn.execute("UPDATE events SET name=?, place=?, event_type=?, price=? WHERE id=? AND tg_id=?",
                 (data['name'], data['place'], data['event_type'], new_price, data['event_id'], message.from_user.id))
    conn.commit()
    conn.close()
    await state.clear()
    log_action(message.from_user.id, "Пользователь", f"Редактирование мероприятия ID {data['event_id']}")
    await message.answer("✅ Мероприятие обновлено!")
    await show_menu(message)

@router.callback_query(F.data.startswith("del_event_"))
async def delete_event(cb: CallbackQuery):
    event_id = int(cb.data.split("del_event_")[1])
    conn = get_db()
    event = conn.execute("SELECT name FROM events WHERE id=? AND tg_id=?", (event_id, cb.from_user.id)).fetchone()
    conn.execute("DELETE FROM events WHERE id=? AND tg_id=?", (event_id, cb.from_user.id))
    conn.commit()
    conn.close()
    log_action(cb.from_user.id, "Пользователь", f"Удаление мероприятия: {event[0] if event else 'Unknown'}")
    await cb.message.answer("🗑 Мероприятие удалено. Баланс восстановлен.")
    await cb.answer()
    await week_events(cb)

@router.callback_query(F.data == "admin_panel")
async def admin_panel(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("❌ Нет доступа", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Посмотреть список класса", callback_data="view_class")],
        [InlineKeyboardButton(text="📊 Получить Excel сейчас", callback_data="export_now")],
        [InlineKeyboardButton(text="👥 Зарегистрированные ученики", callback_data="list_users")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="📜 Логи действий", callback_data="logs")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_menu_from_admin")],
    ])
    await cb.message.answer("👨‍🏫 Админ-панель:", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data == "stats")
async def show_stats(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("❌ Нет доступа", show_alert=True)
    conn = get_db()
    total_students = len(CLASS_LIST)
    registered = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    total_spent = conn.execute("SELECT SUM(price) FROM events").fetchone()[0] or 0
    cinema_events = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='кино'").fetchone()[0]
    theater_events = conn.execute("SELECT COUNT(*) FROM events WHERE event_type='театр'").fetchone()[0]
    total_balance = conn.execute("SELECT SUM(total_balance) FROM users").fetchone()[0] or 0
    total_cinema = conn.execute("SELECT SUM(cinema_balance) FROM users").fetchone()[0] or 0
    total_theater = conn.execute("SELECT SUM(theater_balance) FROM users").fetchone()[0] or 0
    spent_cinema = conn.execute("SELECT SUM(price) FROM events WHERE event_type='кино'").fetchone()[0] or 0
    spent_theater = conn.execute("SELECT SUM(price) FROM events WHERE event_type='театр'").fetchone()[0] or 0
    conn.close()
    text = (f"📊 *Статистика {CLASS_NAME} класса*\n\n"
            f"👥 Ученики:\n• Всего в списке: {total_students}\n• Зарегистрировано: {registered}\n• Не зарегистрировано: {total_students - registered}\n\n"
            f"🎟 Мероприятия:\n• Всего: {total_events}\n• 🎬 Кино: {cinema_events}\n• 🎭 Театр: {theater_events}\n\n"
            f"💰 Финансы:\n• Общий баланс всех: {int(total_balance)}₽\n• На кино: {int(total_cinema)}₽ (потрачено: {int(spent_cinema)}₽)\n"
            f"• На театр: {int(total_theater)}₽ (потрачено: {int(spent_theater)}₽)\n• Всего потрачено: {int(total_spent)}₽")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")]])
    await cb.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data == "logs")
async def show_logs(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("❌ Нет доступа", show_alert=True)
    conn = get_db()
    logs = conn.execute("SELECT name, action, timestamp FROM logs ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    if not logs:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")]])
        return await cb.message.answer("📭 Логи пусты", reply_markup=kb)
    text = "📜 *Последние 50 действий:*\n\n"
    for name, action, timestamp in logs:
        text += f"🕐 {timestamp}\n👤 {name}\n📝 {action}\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")]])
    await cb.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data == "view_class")
async def view_class(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("❌ Нет доступа", show_alert=True)
    conn = get_db()
    students = conn.execute("SELECT position, name FROM class_list ORDER BY position").fetchall()
    conn.close()
    text = f"📋 *{CLASS_NAME} класс* ({len(students)} учеников)\n\n"
    for pos, name in students:
        text += f"{pos}. {name}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")]])
    await cb.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data == "list_users")
async def list_users(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("❌ Нет доступа", show_alert=True)
    conn = get_db()
    users = conn.execute("SELECT name, class_position FROM users ORDER BY class_position").fetchall()
    conn.close()
    if not users:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")]])
        return await cb.message.answer("📭 Пока никто не зарегистрировался", reply_markup=kb)
    text = f"👥 *Зарегистрировано: {len(users)} из {len(CLASS_LIST)}*\n\n"
    for name, position in users:
        text += f"✅ {position}. {name}\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В админ-панель", callback_data="admin_panel")]])
    await cb.message.answer(text, parse_mode="Markdown", reply_markup=kb)
    await cb.answer()

@router.callback_query(F.data == "broadcast")
async def broadcast_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("❌ Нет доступа", show_alert=True)
    await cb.message.answer("📢 *Рассылка всем ученикам*\n\nНапиши текст уведомления. Он будет отправлен всем зарегистрированным ученикам.\n\nПример:\n_Идём с классом в кино 29.11 на Мстители: Финал!_\n_Вот ссылка: https://..._",
                            parse_mode="Markdown", reply_markup=back_with_cancel("back_to_menu"))
    await state.set_state(BroadcastState.message)
    await cb.answer()

@router.message(BroadcastState.message)
async def broadcast_send(message: Message, state: FSMContext):
    text = message.text
    conn = get_db()
    users = conn.execute("SELECT tg_id, name FROM users").fetchall()
    conn.close()
    if not users:
        await state.clear()
        return await message.answer("📭 Нет зарегистрированных учеников для рассылки.")
    sent = 0
    failed = 0
    for tg_id, name in users:
        try:
            await bot.send_message(chat_id=tg_id, text=f"📢 *Уведомление от учителя:*\n\n{text}", parse_mode="Markdown")
            sent += 1
        except Exception as e:
            failed += 1
            print(f"❌ Не удалось отправить {name} (ID {tg_id}): {e}")
    await state.clear()
    log_action(message.from_user.id, "Учитель", f"Рассылка: {text[:50]}...")
    await message.answer(f"✅ Рассылка завершена!\n\n📤 Отправлено: {sent}\n❌ Ошибок: {failed}\n👥 Всего: {len(users)}")
    conn = get_db()
    teacher = conn.execute("SELECT * FROM teachers WHERE tg_id=?", (message.from_user.id,)).fetchone()
    conn.close()
    if teacher:
        await show_teacher_menu(message)
    else:
        await show_menu(message)

def create_excel_report():
    conn = get_db()
    class_list = conn.execute("SELECT position, name FROM class_list ORDER BY position").fetchall()
    users = conn.execute("SELECT * FROM users").fetchall()
    events = conn.execute("SELECT * FROM events ORDER BY date").fetchall()
    conn.close()
    
    # ОТЛАДКА
    print(f"\n{'='*60}")
    print(f"ОТЛАДКА EXCEL: пользователей={len(users)}, мероприятий={len(events)}")
    for u in users:
        print(f"  USER: tg_id={u[0]}, name={u[1]}, pos={u[5]}")
    for e in events:
        # ВАЖНО: e[5]=price, e[6]=date!
        print(f"  EVENT: id={e[0]}, tg_id={e[1]}, name={e[2]}, price={e[5]}, date='{e[6]}'")
    print(f"{'='*60}\n")
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{CLASS_NAME} пушкинская карта"
    
    thin_border = Border(
        left=Side(style='thin', color='B4B4B4'),
        right=Side(style='thin', color='B4B4B4'),
        top=Side(style='thin', color='B4B4B4'),
        bottom=Side(style='thin', color='B4B4B4')
    )
    
    ws['A1'] = f"{CLASS_NAME} КЛАСС"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A1'].border = thin_border
    today = datetime.now()
    ws['B1'] = today.strftime('%d.%m.%Y')
    ws['B1'].font = Font(bold=True, size=11)
    ws['B1'].border = thin_border
    ws['A2'] = "Классный руководитель:"
    ws['A2'].font = Font(italic=True)
    ws['A2'].border = thin_border
    ws['B2'] = CLASS_TEACHER
    ws['B2'].border = thin_border
    
    first_day = today.replace(day=1)
    last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    monday = first_day - timedelta(days=first_day.weekday())
    
    weeks = []
    current_monday = monday
    while current_monday <= last_day:
        week_dates = []
        for day in range(7):
            date = current_monday + timedelta(days=day)
            week_dates.append(date)
        weeks.append(week_dates)
        current_monday += timedelta(days=7)
    
    col = 3
    for week in weeks:
        for date in week:
            ws.cell(row=3, column=col, value=date.strftime('%d.%m'))
            ws.cell(row=3, column=col).font = Font(bold=True, size=10)
            ws.cell(row=3, column=col).alignment = Alignment(horizontal='center')
            ws.cell(row=3, column=col).border = thin_border
            col += 1
        ws.cell(row=3, column=col, value="Остаток\nкино")
        ws.cell(row=3, column=col).font = Font(bold=True, size=10)
        ws.cell(row=3, column=col).alignment = Alignment(horizontal='center', wrap_text=True)
        ws.cell(row=3, column=col).border = thin_border
        col += 1
        ws.cell(row=3, column=col, value="Остаток\nтеатр")
        ws.cell(row=3, column=col).font = Font(bold=True, size=10)
        ws.cell(row=3, column=col).alignment = Alignment(horizontal='center', wrap_text=True)
        ws.cell(row=3, column=col).border = thin_border
        col += 1
    
    col = 3
    for week in weeks:
        for date in week:
            ws.cell(row=4, column=col, value="наименование\nмероприятия,\nстоимость")
            ws.cell(row=4, column=col).alignment = Alignment(wrap_text=True, horizontal='center', vertical='top')
            ws.cell(row=4, column=col).font = Font(size=9)
            ws.cell(row=4, column=col).border = thin_border
            col += 1
        ws.cell(row=4, column=col).border = thin_border
        col += 1
        ws.cell(row=4, column=col).border = thin_border
        col += 1
    
    row = 5
    for position, student_name in class_list:
        ws.cell(row=row, column=1, value=position)
        ws.cell(row=row, column=1).alignment = Alignment(horizontal='center', vertical='top')
        ws.cell(row=row, column=1).border = thin_border
        ws.cell(row=row, column=2, value=student_name)
        ws.cell(row=row, column=2).alignment = Alignment(vertical='top', wrap_text=True)
        ws.cell(row=row, column=2).border = thin_border
        
        user = None
        pos_int = int(position)
        for u in users:
            if int(u[5]) == pos_int:
                user = u
                break
        
        if user:
            tg_id_int = int(user[0])
            name = user[1]
            total = user[2]
            cinema = user[3]
            theater = user[4]
            pos = user[5]
            
            user_events = [e for e in events if int(e[1]) == tg_id_int]
            
            print(f"\n👤 {name} (tg_id={tg_id_int}, pos={pos_int})")
            print(f"   Найдено мероприятий: {len(user_events)}")
            for e in user_events:
                print(f"   - {e[2]} на '{e[6]}' (price={e[5]})")
            
            spent_c = sum(e[4] for e in user_events if e[3] == 'кино') or 0
            spent_t = sum(e[4] for e in user_events if e[3] == 'театр') or 0
            cinema_remaining = int(cinema - spent_c)
            theater_remaining = int(theater - spent_t)
            
            col = 3
            for week in weeks:
                for date in week:
                    date_str = date.strftime('%d.%m')
                    date_events = []
                    for e in user_events:
                        event_date = str(e[6])  # ВАЖНО: e[6] это date, не e[5]!
                        if event_date == date_str or event_date.startswith(date_str + '.') or date_str in event_date:
                            date_events.append(e)
                    
                    if date_events:
                        event_text = "\n".join([f"{e[2]}\n{e[3]}\n{int(e[5])}₽" for e in date_events])
                        ws.cell(row=row, column=col, value=event_text)
                        print(f"   ✅ ЗАПИСАНО в Excel на {date_str}: {event_text}")
                    
                    ws.cell(row=row, column=col).alignment = Alignment(wrap_text=True, vertical='top')
                    ws.cell(row=row, column=col).border = thin_border
                    col += 1
                
                ws.cell(row=row, column=col, value=cinema_remaining)
                ws.cell(row=row, column=col).alignment = Alignment(horizontal='center')
                ws.cell(row=row, column=col).border = thin_border
                col += 1
                ws.cell(row=row, column=col, value=theater_remaining)
                ws.cell(row=row, column=col).alignment = Alignment(horizontal='center')
                ws.cell(row=row, column=col).border = thin_border
                col += 1
        else:
            col = 3
            for week in weeks:
                for date in week:
                    ws.cell(row=row, column=col).border = thin_border
                    col += 1
                ws.cell(row=row, column=col).border = thin_border
                col += 1
                ws.cell(row=row, column=col).border = thin_border
                col += 1
        
        row += 1
    
    ws.column_dimensions['A'].width = 5
    ws.column_dimensions['B'].width = 40
    col_idx = 3
    for week in weeks:
        for date in week:
            col_letter = get_column_letter(col_idx)
            ws.column_dimensions[col_letter].width = 20
            col_idx += 1
        col_idx += 2
    
    ws.row_dimensions[3].height = 20
    ws.row_dimensions[4].height = 40
    for r in range(5, row):
        ws.row_dimensions[r].height = 35
    
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer

@router.callback_query(F.data == "export_now")
async def export_now(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("❌ Нет доступа", show_alert=True)
    await cb.answer("⏳ Формирую отчёт...")
    excel_buffer = create_excel_report()
    filename = f"pushkin_{CLASS_NAME}_{datetime.now().strftime('%d%m%Y')}.xlsx"
    excel_file = BufferedInputFile(file=excel_buffer.read(), filename=filename)
    log_action(cb.from_user.id, "Админ", "Экспорт Excel")
    await cb.message.answer_document(document=excel_file, caption=f"📊 Отчёт {CLASS_NAME} класс — Пушкинская карта\n📅 {datetime.now().strftime('%d.%m.%Y')}")

async def send_weekly_report():
    today_str = datetime.now().strftime('%d.%m.%Y')
    print(f"📤 Рассылка отчёта за {today_str}")
    for admin_id in ADMINS:
        try:
            excel_buffer = create_excel_report()
            filename = f"pushkin_{CLASS_NAME}_{datetime.now().strftime('%d%m%Y')}.xlsx"
            excel_file = BufferedInputFile(file=excel_buffer.read(), filename=filename)
            await bot.send_document(chat_id=admin_id, document=excel_file,
                                    caption=f"📊 *Еженедельный отчёт — {CLASS_NAME} класс*\n📅 Дата: {today_str}\n👨‍🏫 Классный руководитель: {CLASS_TEACHER}\n\nФайл во вложении 👆",
                                    parse_mode="Markdown")
            print(f"✅ Отчёт отправлен админу {admin_id}")
        except Exception as e:
            print(f"❌ Ошибка отправки админу {admin_id}: {e}")

@router.message(Command("add_admin"))
async def add_admin(message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.answer("❌ Только создатель бота может добавлять админов")
    if message.reply_to_message:
        new_admin_id = message.reply_to_message.from_user.id
        if new_admin_id not in ADMINS:
            ADMINS.append(new_admin_id)
        await message.answer(f"✅ Пользователь ID {new_admin_id} добавлен в админы")
    else:
        await message.answer("👉 Ответь на сообщение пользователя командой /add_admin")

@router.message(Command("help"), StateFilter("*"))
async def cmd_help(message: Message):
    await message.answer(f"📖 *Команды бота ({CLASS_NAME} класс):*\n\n/start — регистрация / меню\n/menu — главное меню\n/balance — мой баланс\n/help — эта справка\n\nАдмин:\n/add_admin — добавить админа (ответом на сообщение)", parse_mode="Markdown")

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_weekly_report, 'cron', day_of_week='mon', hour=7, minute=0, timezone='Europe/Moscow')
    scheduler.start()
    print(f"✅ Планировщик запущен (понедельник 7:00 МСК)")
    print(f"📚 Класс: {CLASS_NAME}, учитель: {CLASS_TEACHER}")
    print(f"👥 Учеников в списке: {len(CLASS_LIST)}")
    print(f"👨‍🏫 Админы: {ADMINS}")
    print(f"🔐 Пароль учителя: {TEACHER_PASSWORD}")
    print("🤖 Бот запущен! Открой t.me/PushkinTracker_bot")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
