import os
import sys
import asyncio
import logging
import aiosqlite
from datetime import datetime
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_NAME = "aggregator_bot.db"

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ==================== FSM HOLATLAR ====================
class TrainMonitorState(StatesGroup):
    waiting_for_route = State()
    waiting_for_date = State()

class AdminEventState(StatesGroup):
    waiting_for_title = State()
    waiting_for_date = State()
    waiting_for_status = State()
    waiting_for_url = State()

class AdminBroadcastState(StatesGroup):
    waiting_for_message = State()

# ==================== MA'LUMOTLAR BAZASI ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT, joined_at TEXT)''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, event_date TEXT, 
            status TEXT, url TEXT)''')
        
        await db.execute('''CREATE TABLE IF NOT EXISTS monitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
            type TEXT, target_id INTEGER, details TEXT, is_active INTEGER DEFAULT 1)''')
        
        # Test uchun boshlang'ich ma'lumot (agar baza bo'sh bo'lsa)
        async with db.execute("SELECT COUNT(*) FROM events") as cursor:
            if (await cursor.fetchone())[0] == 0:
                await db.execute("INSERT INTO events (title, event_date, status, url) VALUES (?, ?, ?, ?)",
                                 ("🇺🇿 O'zbekiston - 🇮🇷 Eron (VIP)", "15-Oktyabr", "SOTUVDA", "https://iticket.uz/"))
                await db.execute("INSERT INTO events (title, event_date, status, url) VALUES (?, ?, ?, ?)",
                                 ("🦁 Paxtakor - 🦅 Nasaf", "20-Oktyabr", "TUGAGAN", "https://iticket.uz/"))
        await db.commit()

# ==================== KEYBOARDs ====================
def main_keyboard(user_id: int):
    kb = [
        [KeyboardButton(text="🎟 Tadbirlar va Futbol"), KeyboardButton(text="🚆 Poyezd Monitoringi")],
        [KeyboardButton(text="🔔 Mening Monitoringlarim"), KeyboardButton(text="👤 Profil")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="⚙ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ==================== ASOSIY MENYU ====================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
                         (message.from_user.id, message.from_user.full_name, message.from_user.username, datetime.now().strftime("%Y-%m-%d %H:%M")))
        await db.commit()

    await message.answer(
        f"Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n"
        f"Chiptalarni topish va monitoring qilish botiga xush kelibsiz. Bo'limni tanlang:",
        reply_markup=main_keyboard(message.from_user.id)
    )

# ---------------- TADBIRLAR VA FUTBOL ----------------
@router.message(F.text == "🎟 Tadbirlar va Futbol")
async def show_events(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, title, event_date, status FROM events ORDER BY id DESC") as cursor:
            events = await cursor.fetchall()

    if not events:
        await message.answer("Hozircha faol tadbirlar yo'q.")
        return

    buttons = []
    for e_id, title, date, status in events:
        icon = "🟢" if status == "SOTUVDA" else "🔴"
        buttons.append([InlineKeyboardButton(text=f"{icon} {title} ({date})", callback_data=f"event_{e_id}")])

    await message.answer("<b>Qaysi tadbir sizni qiziqtiradi?</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("event_"))
async def event_details(call: CallbackQuery):
    e_id = int(call.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT title, event_date, status, url FROM events WHERE id = ?", (e_id,)) as cursor:
            event = await cursor.fetchone()

    if not event:
        await call.answer("Tadbir topilmadi!")
        return

    title, date, status, url = event
    msg = f"🎟 <b>Tadbir:</b> {title}\n📅 <b>Sana:</b> {date}\n📊 <b>Holat:</b> {status}\n\n"

    buttons = []
    if status == "SOTUVDA":
        msg += "✅ <i>Biletlar sotuvda mavjud. Quyidagi havola orqali rasmiy saytdan xarid qilishingiz mumkin:</i>"
        buttons.append([InlineKeyboardButton(text="🎫 Rasmiy saytdan sotib olish", url=url)])
    else:
        msg += "❌ <i>Hozircha barcha biletlar sotilgan. Joy ochilishi bilan xabar olish uchun monitoringni yoqing!</i>"
        buttons.append([InlineKeyboardButton(text="🔔 Joy bo'shasa xabar berish", callback_data=f"mon_event_{e_id}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_events")])
    await call.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data == "back_events")
async def back_to_events(call: CallbackQuery):
    await call.message.delete()
    await show_events(call.message)

# ---------------- MONITORING YOQISH (FUTBOL) ----------------
@router.callback_query(F.data.startswith("mon_event_"))
async def enable_event_monitor(call: CallbackQuery):
    e_id = int(call.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT title FROM events WHERE id = ?", (e_id,)) as cursor:
            event = await cursor.fetchone()
        
        if event:
            await db.execute("INSERT INTO monitors (user_id, type, target_id, details) VALUES (?, ?, ?, ?)",
                             (call.from_user.id, "TADBIR", e_id, event[0]))
            await db.commit()
            
    await call.answer("✅ Monitoring yoqildi!", show_alert=True)
    await call.message.edit_text(f"✅ <b>{event[0]}</b> uchun monitoring yoqildi.\n\nBilet paydo bo'lishi bilan sizga havola yuboramiz!")

# ---------------- POYEZD MONITORINGI ----------------
@router.message(F.text == "🚆 Poyezd Monitoringi")
async def train_monitor_start(message: Message, state: FSMContext):
    await state.set_state(TrainMonitorState.waiting_for_route)
    await message.answer("🚆 <b>Poyezd yo'nalishini kiriting:</b>\n<i>(Masalan: Toshkent - Buxoro)</i>")

@router.message(TrainMonitorState.waiting_for_route)
async def train_route_get(message: Message, state: FSMContext):
    await state.update_data(route=message.text)
    await state.set_state(TrainMonitorState.waiting_for_date)
    await message.answer("📅 <b>Sanani kiriting:</b>\n<i>(Masalan: 12-Noyabr)</i>")

@router.message(TrainMonitorState.waiting_for_date)
async def train_date_get(message: Message, state: FSMContext):
    data = await state.get_data()
    details = f"{data['route']} | {message.text}"
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO monitors (user_id, type, target_id, details) VALUES (?, ?, ?, ?)",
                         (message.from_user.id, "POYEZD", 0, details))
        await db.commit()
        
    await state.clear()
    await message.answer(f"✅ <b>Poyezd monitoringi yoqildi!</b>\n📍 {details}\n\nJoy bo'shasa bot sizga xabar yuboradi.", 
                         reply_markup=main_keyboard(message.from_user.id))

# ---------------- FOYDALANUVCHI PROFILI VA MONITORINGLARI ----------------
@router.message(F.text == "🔔 Mening Monitoringlarim")
async def my_monitors(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, type, details FROM monitors WHERE user_id = ? AND is_active = 1", (message.from_user.id,)) as cursor:
            monitors = await cursor.fetchall()

    if not monitors:
        await message.answer("Sizda faol monitoringlar yo'q.")
        return

    msg = "<b>🔔 Faol Monitoringlaringiz:</b>\n\n"
    buttons = []
    for m_id, m_type, details in monitors:
        msg += f"▪️ <b>{m_type}</b>: {details}\n"
        buttons.append([InlineKeyboardButton(text=f"❌ O'chirish ({details[:10]}...)", callback_data=f"del_mon_{m_id}")])

    await message.answer(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("del_mon_"))
async def del_monitor(call: CallbackQuery):
    m_id = int(call.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM monitors WHERE id = ?", (m_id,))
        await db.commit()
    await call.answer("Monitoring o'chirildi ✅")
    await call.message.delete()

@router.message(F.text == "👤 Profil")
async def profile(message: Message):
    await message.answer(f"<b>👤 Profil:</b>\n\n🆔 ID: <code>{message.from_user.id}</code>\n👤 Ism: {message.from_user.full_name}")

# ==================== ADMIN PANEL ====================
@router.message(F.text == "⚙ Admin Panel", F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi Tadbir Qo'shish", callback_data="admin_add_event")],
        [InlineKeyboardButton(text="🔄 Test: Joy Ochish (Xabar yuborish)", callback_data="admin_test_restock")],
        [InlineKeyboardButton(text="📣 Hammaga Xabar Yuborish", callback_data="admin_broadcast")]
    ])
    await message.answer("⚙ <b>Admin Panel:</b>", reply_markup=kb)

# 1. Tadbir Qo'shish
@router.callback_query(F.data == "admin_add_event", F.from_user.id == ADMIN_ID)
async def admin_add_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminEventState.waiting_for_title)
    await call.message.answer("1️⃣ Tadbir nomini kiriting:")

@router.message(AdminEventState.waiting_for_title)
async def admin_add_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminEventState.waiting_for_date)
    await message.answer("2️⃣ Sanasini kiriting (Masalan: 25-Noyabr):")

@router.message(AdminEventState.waiting_for_date)
async def admin_add_date(message: Message, state: FSMContext):
    await state.update_data(date=message.text)
    await state.set_state(AdminEventState.waiting_for_status)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="SOTUVDA", callback_data="status_SOTUVDA"),
         InlineKeyboardButton(text="TUGAGAN", callback_data="status_TUGAGAN")]
    ])
    await message.answer("3️⃣ Bilet holatini tanlang:", reply_markup=kb)

@router.callback_query(F.data.startswith("status_"), AdminEventState.waiting_for_status)
async def admin_add_status(call: CallbackQuery, state: FSMContext):
    status = call.data.split("_")[1]
    await state.update_data(status=status)
    await state.set_state(AdminEventState.waiting_for_url)
    await call.message.answer("4️⃣ Rasmiy sayt havolasini kiriting (URL):")

@router.message(AdminEventState.waiting_for_url)
async def admin_add_url(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO events (title, event_date, status, url) VALUES (?, ?, ?, ?)",
                         (data['title'], data['date'], data['status'], message.text))
        await db.commit()
    await state.clear()
    await message.answer("✅ Tadbir muvaffaqiyatli qo'shildi!")

# 2. Xabar Yuborish (Reklama/Elon)
@router.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def admin_broad_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminBroadcastState.waiting_for_message)
    await call.message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:")

@router.message(AdminBroadcastState.waiting_for_message, F.from_user.id == ADMIN_ID)
async def admin_broad_send(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚀 Yuborilmoqda...")
    count = 0
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
            
    for (u_id,) in users:
        try:
            await message.copy_to(u_id)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Xabar {count} ta odamga yetkazildi.")

# 3. TEST JOY OCHISH (Ushbu funksiya real qanday ishlashini sinash uchun)
@router.callback_query(F.data == "admin_test_restock", F.from_user.id == ADMIN_ID)
async def admin_test_restock(call: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        # TUGAGAN tadbirlarni topamiz
        async with db.execute("SELECT id, title, url FROM events WHERE status = 'TUGAGAN'") as cursor:
            events = await cursor.fetchall()
            
    if not events:
        await call.message.answer("Hozircha 'TUGAGAN' holatidagi tadbir yo'q.")
        return
        
    buttons = [[InlineKeyboardButton(text=t, callback_data=f"restock_{e_id}")] for e_id, t, u in events]
    await call.message.edit_text("Qaysi tadbirga 'Joy ochildi' deb hammaga xabar beramiz?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("restock_"), F.from_user.id == ADMIN_ID)
async def execute_restock(call: CallbackQuery):
    e_id = int(call.data.split("_")[1])
    
    async with aiosqlite.connect(DB_NAME) as db:
        # 1. Tadbirni SOTUVDA holatiga o'tkazamiz
        await db.execute("UPDATE events SET status = 'SOTUVDA' WHERE id = ?", (e_id,))
        async with db.execute("SELECT title, url FROM events WHERE id = ?", (e_id,)) as c:
            title, url = await c.fetchone()
            
        # 2. Shu tadbirni kutayotgan foydalanuvchilarni topamiz
        async with db.execute("SELECT id, user_id FROM monitors WHERE target_id = ? AND is_active = 1", (e_id,)) as c:
            monitors = await c.fetchall()
            
        # 3. Ularning monitoringini o'chiramiz (xabar ketgach)
        await db.execute("UPDATE monitors SET is_active = 0 WHERE target_id = ?", (e_id,))
        await db.commit()

    # 4. Foydalanuvchilarga xabar yuboramiz
    count = 0
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎫 Rasmiy saytdan xarid qilish", url=url)]])
    for m_id, u_id in monitors:
        try:
            await bot.send_message(
                u_id,
                f"🎉 <b>BO'SH JOY PAYDO BO'LDI!</b>\n\n"
                f"🎟 <b>Tadbir:</b> {title}\n\n"
                f"Boshqalar olib qo'ymasidan tezroq quyidagi havola orqali xarid qiling:",
                reply_markup=kb
            )
            count += 1
        except Exception:
            pass
            
    await call.message.edit_text(f"✅ {title} 'SOTUVDA' rejimiga o'tdi va <b>{count} ta</b> foydalanuvchiga bildirishnoma yuborildi.")

# ==================== MAIN ====================
async def main():
    await init_db()
    print("🚀 Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
