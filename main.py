import asyncio
import logging
import sys
from datetime import datetime
import aiosqlite

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)

# ==================== SOZLAMALAR ====================
BOT_TOKEN = "8771087237:AAGOIl4UKrOZFPsxhz9l-GshATlOZPneQYA"  # BotFather'dan olingan token
ADMIN_ID = 8488028783                # O'zingizning Telegram ID'ingiz (int formatda)
DB_NAME = "bilet_bot.db"

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ==================== FSM HOLATLAR ====================
class AdminState(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_card_number = State()
    waiting_for_card_holder = State()
    waiting_for_pro_price = State()
    waiting_for_channel = State()
    waiting_for_grant_pro = State()

class UserState(StatesGroup):
    waiting_for_route = State()
    waiting_for_date = State()
    waiting_for_receipt = State()

# ==================== MA'LUMOTLAR BAZASI ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Foydalanuvchilar jadvali
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                status TEXT DEFAULT 'FREE',
                pro_until TEXT,
                joined_at TEXT
            )
        ''')
        # Monitoringlar jadvali
        await db.execute('''
            CREATE TABLE IF NOT EXISTS monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                category TEXT,
                route TEXT,
                date TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        # Tizim sozlamalari
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # Sponsor kanallar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                title TEXT,
                username TEXT
            )
        ''')
        # To'lovlar jadvali
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                photo_id TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT
            )
        ''')
        
        # Boshlang'ich sozlamalarni kiritish
        defaults = {
            "card_number": "8600 0000 0000 0000",
            "card_holder": "ISOMJONOV A.",
            "pro_price": "25000",
            "mandatory_sub": "0"
        }
        for k, v in defaults.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
        await db.commit()

async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else ""

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        await db.commit()

# ==================== TUGMALAR VA KLAVIATURALAR ====================
def main_keyboard(user_id: int):
    kb = [
        [KeyboardButton(text="🎟 Yangi Monitoring Yaratish")],
        [KeyboardButton(text="📋 Mening Monitoringlarim"), KeyboardButton(text="⭐ PRO Tarifga O'tish")],
        [KeyboardButton(text="👤 Profil va Yordam")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="⚙ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"), InlineKeyboardButton(text="📣 Reklama Yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📢 Majburiy Obuna", callback_data="admin_channels"), InlineKeyboardButton(text="💳 Karta va Narxlar", callback_data="admin_card")],
        [InlineKeyboardButton(text="⏳ Kutilayotgan To'lovlar", callback_data="admin_payments"), InlineKeyboardButton(text="👑 Qo'lda PRO Berish", callback_data="admin_grant_pro")]
    ])

# ==================== YORDAMCHI FUNKSIYALAR ====================
async def check_mandatory_sub(user_id: int) -> bool:
    is_active = await get_setting("mandatory_sub")
    if is_active != "1":
        return True
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT channel_id FROM channels") as cursor:
            channels = await cursor.fetchall()
            
    for (ch_id,) in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
                return False
        except Exception:
            pass
    return True

# ==================== HANDLERLAR (FOYDALANUVCHI) ====================
@router.message(CommandStart())
async def cmd_start(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
            (message.from_user.id, message.from_user.full_name, message.from_user.username, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        await db.commit()
    
    if not await check_mandatory_sub(message.from_user.id):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT channel_id, title, username FROM channels") as cursor:
                channels = await cursor.fetchall()
        
        buttons = []
        for ch_id, title, username in channels:
            url = f"https://t.me/{username}" if username else "https://t.me/"
            buttons.append([InlineKeyboardButton(text=f"➕ {title}", url=url)])
        buttons.append([InlineKeyboardButton(text="✅ Obunani Tekshirish", callback_data="check_sub")])
        
        await message.answer("⚠️ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        return

    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_keyboard(message.from_user.id))

@router.callback_query(F.data == "check_sub")
async def callback_check_sub(call: CallbackQuery):
    if await check_mandatory_sub(call.from_user.id):
        await call.message.delete()
        await call.message.answer("✅ Obuna tasdiqlandi!", reply_markup=main_keyboard(call.from_user.id))
    else:
        await call.answer("❌ Hali barcha kanallarga obuna bo'lmadingiz!", show_alert=True)

@router.message(F.text == "🎟 Yangi Monitoring Yaratish")
async def create_monitor_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚆 Poyezd Biletlari", callback_data="mon_poyezd")],
        [InlineKeyboardButton(text="⚽ iTicket (Tadbirlar/Futbol)", callback_data="mon_iticket")]
    ])
    await message.answer("Qaysi yo'nalish bo'yicha bilet qidirmoqchisiz?", reply_markup=kb)

@router.callback_query(F.data.startswith("mon_"))
async def select_category(call: CallbackQuery, state: FSMContext):
    cat = "Poyezd" if call.data == "mon_poyezd" else "iTicket"
    await state.update_data(category=cat)
    await state.set_state(UserState.waiting_for_route)
    await call.message.answer(f"📍 <b>{cat}</b> bo'yicha yo'nalish yoki tadbir nomini kiritib yuboring:\n<i>(Masalan: Toshkent - Samarqand yoki O'zbekiston - Eron)</i>")

@router.message(UserState.waiting_for_route)
async def process_route(message: Message, state: FSMContext):
    await state.update_data(route=message.text)
    await state.set_state(UserState.waiting_for_date)
    await message.answer("📅 Bilet kerakli sanani kiriting:\n<i>(Masalan: 2026-10-15 yoki Ertaga)</i>")

@router.message(UserState.waiting_for_date)
async def process_date(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO monitors (user_id, category, route, date) VALUES (?, ?, ?, ?)",
            (message.from_user.id, data['category'], data['route'], message.text)
        )
        await db.commit()
    
    await state.clear()
    await message.answer(
        f"✅ <b>Monitoring ishga tushdi!</b>\n\n"
        f"🔹 Yo'nalish: <b>{data['category']} ({data['route']})</b>\n"
        f"📅 Sana: <b>{message.text}</b>\n\n"
        f"Bilet paydo bo'lishi bilan sizga xabar yuboramiz!",
        reply_markup=main_keyboard(message.from_user.id)
    )

@router.message(F.text == "📋 Mening Monitoringlarim")
async def show_monitors(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, category, route, date FROM monitors WHERE user_id = ? AND is_active = 1", (message.from_user.id,)) as cursor:
            rows = await cursor.fetchall()
    
    if not rows:
        await message.answer("Sizda faol monitoringlar mavjud emas.")
        return
    
    msg = "<b>📋 Faol monitoringlaringiz:</b>\n\n"
    buttons = []
    for m_id, cat, route, date in rows:
        msg += f"🆔 #{m_id} | <b>{cat}</b>: {route} ({date})\n"
        buttons.append([InlineKeyboardButton(text=f"❌ O'chirish #{m_id}", callback_data=f"del_mon_{m_id}")])
    
    await message.answer(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("del_mon_"))
async def delete_monitor(call: CallbackQuery):
    m_id = call.data.split("_")[2]
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM monitors WHERE id = ?", (m_id,))
        await db.commit()
    await call.answer("Monitoring o'chirildi ✅")
    await call.message.delete()

@router.message(F.text == "⭐ PRO Tarifga O'tish")
async def buy_pro(message: Message, state: FSMContext):
    card = await get_setting("card_number")
    holder = await get_setting("card_holder")
    price = await get_setting("pro_price")
    
    msg = (
        f"<b>⭐ PRO Tarif — Cheksiz Tezkor Monitoring</b>\n\n"
        f"PRO obuna afzalliklari:\n"
        f"• Biletlar 1 daqiqalik intervalda tekshiriladi\n"
        f"• Cheksiz monitoringlar o'rnatish imkoniyati\n\n"
        f"💵 Narxi: <b>{price} so'm / oyiga</b>\n\n"
        f"To'lov uchun karta raqami:\n"
        f"💳 <code>{card}</code>\n"
        f"👤 Egasining ismi: <b>{holder}</b>\n\n"
        f"To'lovni amalga oshirgach, to'lov <b>cheki skrinshotini (rasmini)</b> ushbu chatga yuboring:"
    )
    await state.set_state(UserState.waiting_for_receipt)
    await message.answer(msg)

@router.message(UserState.waiting_for_receipt, F.photo)
async def process_receipt(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO payments (user_id, photo_id, created_at) VALUES (?, ?, ?)",
            (message.from_user.id, photo_id, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        pay_id = cursor.lastrowid
        await db.commit()
    
    await state.clear()
    await message.answer("✅ To'lov cheki adminlarga yuborildi. Tekshirilgach PRO faollashtiriladi!")
    
    # Adminga xabar yuborish
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_pay_{pay_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_pay_{pay_id}")
    ]])
    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"<b>💳 Yangi To'lov!</b>\n\nFoydalanuvchi: <a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a>\nID: <code>{message.from_user.id}</code>\nTo'lov ID: #{pay_id}",
        reply_markup=kb
    )

@router.message(F.text == "👤 Profil va Yordam")
async def show_profile(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT status, pro_until FROM users WHERE user_id = ?", (message.from_user.id,)) as cursor:
            row = await cursor.fetchone()
            status = row[0] if row else "FREE"
            until = row[1] if row and row[1] else "Cheksiz"
            
    await message.answer(
        f"<b>👤 Profilingiz:</b>\n\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"⭐ Status: <b>{status}</b>\n"
        f"⏳ PRO tugash muddati: <b>{until}</b>\n\n"
        f"💬 Qo'llab-quvvatlash: @admin"
    )

# ==================== HANDLERLAR (ADMIN PANEL) ====================
@router.message(F.text == "⚙ Admin Panel", F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    await message.answer("⚙ <b>Boshqaruv Paneli:</b>", reply_markup=admin_keyboard())

@router.callback_query(F.data == "admin_stats", F.from_user.id == ADMIN_ID)
async def admin_stats(call: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1:
            total_users = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM monitors WHERE is_active = 1") as c2:
            active_monitors = (await c2.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users WHERE status = 'PRO'") as c3:
            pro_users = (await c3.fetchone())[0]
            
    await call.message.edit_text(
        f"<b>📊 Tizim Statistikasi:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{total_users}</b>\n"
        f"👑 PRO foydalanuvchilar: <b>{pro_users}</b>\n"
        f"🎟 Faol monitoringlar: <b>{active_monitors}</b>",
        reply_markup=admin_keyboard()
    )

@router.callback_query(F.data.startswith("approve_pay_"), F.from_user.id == ADMIN_ID)
async def approve_payment(call: CallbackQuery):
    pay_id = call.data.split("_")[2]
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM payments WHERE id = ?", (pay_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id = row[0]
                await db.execute("UPDATE users SET status = 'PRO' WHERE user_id = ?", (user_id,))
                await db.execute("UPDATE payments SET status = 'APPROVED' WHERE id = ?", (pay_id,))
                await db.commit()
                
                try:
                    await bot.send_message(user_id, "🎉 <b>To'lovingiz tasdiqlandi!</b> PRO tarif faollashtirildi.")
                except Exception:
                    pass
                await call.message.edit_caption(caption=call.message.caption + "\n\n✅ <b>Tasdiqlandi!</b>")

@router.callback_query(F.data.startswith("reject_pay_"), F.from_user.id == ADMIN_ID)
async def reject_payment(call: CallbackQuery):
    pay_id = call.data.split("_")[2]
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM payments WHERE id = ?", (pay_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id = row[0]
                await db.execute("UPDATE payments SET status = 'REJECTED' WHERE id = ?", (pay_id,))
                await db.commit()
                
                try:
                    await bot.send_message(user_id, "❌ <b>To'lovingiz rad etildi.</b> Iltimos, chekni qayta tekshirib yuboring.")
                except Exception:
                    pass
                await call.message.edit_caption(caption=call.message.caption + "\n\n❌ <b>Rad etildi!</b>")

@router.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.waiting_for_broadcast)
    await call.message.answer("📢 Barcha foydalanuvchilarga yuboriladigan xabarni (matn, rasm, video) kiriting:")

@router.message(AdminState.waiting_for_broadcast, F.from_user.id == ADMIN_ID)
async def process_broadcast(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚀 Xabar yuborish boshlandi...")
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            users = await cursor.fetchall()
            
    count = 0
    for (u_id,) in users:
        try:
            await message.copy_to(chat_id=u_id)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
            
    await message.answer(f"✅ Xabar <b>{count}</b> ta foydalanuvchiga muvaffaqiyatli yetkazildi.")

# ==================== BACKGROUND WORKER (MONITORING) ====================
async def ticket_checker_loop():
    """ Orqa fonda avtomatik biletlarni tekshiruvchi skript simulation """
    while True:
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT id, user_id, category, route, date FROM monitors WHERE is_active = 1") as cursor:
                    monitors = await cursor.fetchall()
            
            # Bu yerga kelajakda real Railway/iTicket parsing kodi ulanadi.
            # Hozircha namuna uchun simulyatsiya kodi yozilgan.
            for m_id, u_id, cat, route, date in monitors:
                # Real parser ulanadigan joy
                pass
                
        except Exception as e:
            logging.error(f"Worker Error: {e}")
            
        await asyncio.sleep(60) # Har 60 sekundda tekshirib turadi

# ==================== MAIN ====================
async def main():
    await init_db()
    asyncio.create_task(ticket_checker_loop()) # Worker'ni parallel ishga tushirish
    print("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
