import asyncio
import logging
import sys
from datetime import datetime
import aiosqlite

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
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
BOT_TOKEN = "8771087237:AAGOIl4UKrOZFPsxhz9l-GshATlOZPneQYA"
ADMIN_ID = 8488028783
DB_NAME = "bilet_bot.db"

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# ==================== FSM HOLATLAR ====================
class UserState(StatesGroup):
    waiting_for_match_search = State()
    waiting_for_route = State()
    waiting_for_date = State()
    waiting_for_receipt = State()

class AdminState(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_match_title = State()

# ==================== MA'LUMOTLAR BAZASI ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Foydalanuvchilar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                status TEXT DEFAULT 'FREE',
                joined_at TEXT
            )
        ''')
        # O'yinlar / Tadbirlar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                stadium TEXT,
                match_date TEXT
            )
        ''')
        # Sektorlar va O'rindiqlar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id INTEGER,
                sector_name TEXT,
                price INTEGER,
                total_seats INTEGER,
                available_seats TEXT
            )
        ''')
        # Monitoringlar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS monitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                category TEXT,
                details TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')
        # Buyurtma biletlar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                match_title TEXT,
                sector_name TEXT,
                seat_number INTEGER,
                price INTEGER,
                created_at TEXT
            )
        ''')
        # Sozlamalar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # Boshlang'ich sinov ma'lumotlarini kiritish (Agar DB bo'sh bo'lsa)
        async with db.execute("SELECT COUNT(*) FROM matches") as cursor:
            count = (await cursor.fetchone())[0]
            if count == 0:
                await db.execute(
                    "INSERT INTO matches (title, stadium, match_date) VALUES (?, ?, ?)",
                    ("🇺🇿 O'zbekiston - 🇮🇷 Eron", "Bunyodkor Stadioni", "15-Oktyabr, 19:00")
                )
                await db.execute(
                    "INSERT INTO matches (title, stadium, match_date) VALUES (?, ?, ?)",
                    ("🦁 Paxtakor - 🦅 Nasaf", "Paxtakor Markaziy Stadioni", "20-Oktyabr, 18:00")
                )
                
                # O'zbekiston - Eron sektori
                await db.execute(
                    "INSERT INTO sectors (match_id, sector_name, price, total_seats, available_seats) VALUES (?, ?, ?, ?, ?)",
                    (1, "VIP Tribuna", 150000, 10, "1,2,3,5,8,9,10")
                )
                await db.execute(
                    "INSERT INTO sectors (match_id, sector_name, price, total_seats, available_seats) VALUES (?, ?, ?, ?, ?)",
                    (1, "G'arb (A-Sektor)", 70000, 15, "4,5,6,11,12,13,14,15")
                )
                await db.execute(
                    "INSERT INTO sectors (match_id, sector_name, price, total_seats, available_seats) VALUES (?, ?, ?, ?, ?)",
                    (1, "Sharq (B-Sektor)", 40000, 20, "") # Bo'sh joy yo'q (Monitoring uchun)
                )

                # Paxtakor - Nasaf sektori
                await db.execute(
                    "INSERT INTO sectors (match_id, sector_name, price, total_seats, available_seats) VALUES (?, ?, ?, ?, ?)",
                    (2, "Markaziy Sektor", 50000, 10, "1,2,3,4,5,6,7,8,9,10")
                )

        defaults = {
            "card_number": "8600 0000 0000 0000",
            "card_holder": "ISOMJONOV A.",
            "pro_price": "25000"
        }
        for k, v in defaults.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
            
        await db.commit()

# ==================== KEYBOARDs ====================
def main_keyboard(user_id: int):
    kb = [
        [KeyboardButton(text="⚽ Futbol va Tadbirlar Biletlari")],
        [KeyboardButton(text="🚆 Poyezd Biletlari Monitoringi")],
        [KeyboardButton(text="🎟 Mening Biletlarim"), KeyboardButton(text="🔔 Monitoringlarim")],
        [KeyboardButton(text="⭐ PRO Tarif"), KeyboardButton(text="👤 Profil")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="⚙ Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ==================== HANDLERS ====================
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, full_name, username, joined_at) VALUES (?, ?, ?, ?)",
            (message.from_user.id, message.from_user.full_name, message.from_user.username, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        await db.commit()

    await message.answer(
        f"Assalomu alaykum, <b>{message.from_user.first_name}</b>!\n"
        f"Bilet olish va avto-monitoring botiga xush kelibsiz. Qaysi xizmatdan foydalanmoqchisiz?",
        reply_markup=main_keyboard(message.from_user.id)
    )

# ---------------- Futbol / Tadbirlar Bosh Menyusi ----------------
@router.message(F.text == "⚽ Futbol va Tadbirlar Biletlari")
async def football_menu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Yaqin kunlardagi o'yinlar", callback_data="list_matches")],
        [InlineKeyboardButton(text="🔍 O'yin nomi bo'yicha qidirish", callback_data="search_match_start")]
    ])
    await message.answer("⚽ <b>Futbol va Tadbirlar Bo'limi</b>\n\nBo'sh joylarni ko'rish yoki bilet qidirish usulini tanlang:", reply_markup=kb)

@router.callback_query(F.data == "list_matches")
async def show_matches(call: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, title, match_date FROM matches") as cursor:
            matches = await cursor.fetchall()

    if not matches:
        await call.message.edit_text("Hozircha faol o'yinlar mavjud emas.")
        return

    buttons = []
    for m_id, title, m_date in matches:
        buttons.append([InlineKeyboardButton(text=f"⚽ {title} ({m_date})", callback_data=f"match_{m_id}")])

    await call.message.edit_text("<b>Chipta sotilayotgan o'yinni tanlang:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data == "search_match_start")
async def start_search_match(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserState.waiting_for_match_search)
    await call.message.answer("🔍 Qidirilayotgan jamoa yoki o'yin nomini kiriting:\n<i>(Masalan: O'zbekiston, Paxtakor, Eron)</i>")

@router.message(UserState.waiting_for_match_search)
async def process_match_search(message: Message, state: FSMContext):
    query = message.text.strip()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, title, match_date FROM matches WHERE title LIKE ?", (f"%{query}%",)) as cursor:
            matches = await cursor.fetchall()

    await state.clear()
    if not matches:
        await message.answer(f"❌ <b>'{query}'</b> bo'yicha hech qanday o'yin topilmadi.\nQaytadan urinib ko'ring:", reply_markup=main_keyboard(message.from_user.id))
        return

    buttons = []
    for m_id, title, m_date in matches:
        buttons.append([InlineKeyboardButton(text=f"⚽ {title} ({m_date})", callback_data=f"match_{m_id}")])

    await message.answer(f"🔎 <b>'{query}' bo'yicha topilgan o'yinlar:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# ---------------- O'yin va Tribuna / Sektor Tanlash ----------------
@router.callback_query(F.data.startswith("match_"))
async def select_match(call: CallbackQuery):
    match_id = int(call.data.split("_")[1])
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT title, stadium, match_date FROM matches WHERE id = ?", (match_id,)) as c1:
            match = await c1.fetchone()
        async with db.execute("SELECT id, sector_name, price, available_seats FROM sectors WHERE match_id = ?", (match_id,)) as c2:
            sectors = await c2.fetchall()

    if not match:
        await call.answer("O'yin topilmadi!")
        return

    title, stadium, m_date = match
    msg = (
        f"⚽ <b>{title}</b>\n"
        f"🏟 Stadat: {stadium}\n"
        f"📅 Vaqt: {m_date}\n\n"
        f"<b>Kerakli tribuna / sektorni tanlang:</b>"
    )

    buttons = []
    for s_id, s_name, price, av_seats in sectors:
        seats_list = [s for s in av_seats.split(",") if s]
        seats_count = len(seats_list)
        
        status_text = f"({seats_count} ta bo'sh)" if seats_count > 0 else "(❌ Bo'sh joy yo'q)"
        btn_text = f"{s_name} - {price:,} so'm {status_text}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"sec_{s_id}")])

    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="list_matches")])
    await call.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# ---------------- O'rindiq (Joy) Tanlash Interfeysi ----------------
@router.callback_query(F.data.startswith("sec_"))
async def select_sector(call: CallbackQuery):
    sec_id = int(call.data.split("_")[1])

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT s.sector_name, s.price, s.available_seats, m.title, m.id "
            "FROM sectors s JOIN matches m ON s.match_id = m.id WHERE s.id = ?", (sec_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        await call.answer("Sektor topilmadi!")
        return

    s_name, price, av_seats, match_title, match_id = row
    seats_list = [s.strip() for s in av_seats.split(",") if s.strip()]

    # Agar bo'sh joy bo'lmasa -> Monitoring o'rnatishni taklif qilish
    if not seats_list:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Bo'sh joy paydo bo'lganda ogohlantirish", callback_data=f"add_mon_{sec_id}")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"match_{match_id}")]
        ])
        await call.message.edit_text(
            f"❌ <b>{match_title}</b> o'yinining <b>{s_name}</b> sektorida hozircha hamma biletlar sotib bo'lingan.\n\n"
            f"Siz ushbu sektorga monitoring o'rnatishingiz mumkin. Birev bileti qaytarsa yoki yangi joy ochilsa, bot sizga darhol xabar yuboradi!",
            reply_markup=kb
        )
        return

    # Bo'sh joylar bo'lsa -> Inline tugmalar paneli (Kreslolar grid-i)
    msg = (
        f"🎟 <b>O'yin:</b> {match_title}\n"
        f"📍 <b>Sektor:</b> {s_name}\n"
        f"💵 <b>Narx:</b> {price:,} so'm\n\n"
        f"<b>Kerakli o'rindiq (joy) raqamini tanlang:</b>"
    )

    buttons = []
    row_btns = []
    for seat in seats_list:
        row_btns.append(InlineKeyboardButton(text=f"💺 Joy #{seat}", callback_data=f"buy_{sec_id}_{seat}"))
        if len(row_btns) == 3: # Har bir qatorda 3 tadan joy
            buttons.append(row_btns)
            row_btns = []
    if row_btns:
        buttons.append(row_btns)

    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"match_{match_id}")])
    await call.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

# ---------------- Biletni Muvaffaqiyatli Band Qilish ----------------
@router.callback_query(F.data.startswith("buy_"))
async def process_buy_ticket(call: CallbackQuery):
    _, sec_id_str, seat_num_str = call.data.split("_")
    sec_id = int(sec_id_str)
    seat_num = seat_num_str

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT s.sector_name, s.price, s.available_seats, s.match_id, m.title "
            "FROM sectors s JOIN matches m ON s.match_id = m.id WHERE s.id = ?", (sec_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await call.answer("Xatolik yuz berdi!", show_alert=True)
            return

        s_name, price, av_seats, match_id, match_title = row
        seats_list = [s.strip() for s in av_seats.split(",") if s.strip()]

        if seat_num not in seats_list:
            await call.answer("⚠️ Bu joy allaqachon band qilingan!", show_alert=True)
            return

        # Joyni olib tashlaymiz
        seats_list.remove(seat_num)
        new_av_seats = ",".join(seats_list)

        await db.execute("UPDATE sectors SET available_seats = ? WHERE id = ?", (new_av_seats, sec_id))
        await db.execute(
            "INSERT INTO tickets (user_id, match_title, sector_name, seat_number, price, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (call.from_user.id, match_title, s_name, int(seat_num), price, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        await db.commit()

    await call.message.edit_text(
        f"🎉 <b>BILET MUVAFFAQIYATLI XARID QILINDI!</b>\n\n"
        f"⚽ <b>O'yin:</b> {match_title}\n"
        f"📍 <b>Sektor:</b> {s_name}\n"
        f"💺 <b>O'rindiq raqami:</b> #{seat_num}\n"
        f"💵 <b>To'langan summa:</b> {price:,} so'm\n\n"
        f"Biletingiz <b>'🎟 Mening Biletlarim'</b> bo'limida saqlandi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Bosh Menyu", callback_data="go_main")]])
    )

@router.callback_query(F.data == "go_main")
async def back_to_main_call(call: CallbackQuery):
    await call.message.delete()
    await call.message.answer("Bosh menyu:", reply_markup=main_keyboard(call.from_user.id))

# ---------------- Sektorga Monitoring Qo'shish ----------------
@router.callback_query(F.data.startswith("add_mon_"))
async def add_sector_monitor(call: CallbackQuery):
    sec_id = int(call.data.split("_")[2])

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT s.sector_name, m.title FROM sectors s JOIN matches m ON s.match_id = m.id WHERE s.id = ?", (sec_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row:
            s_name, match_title = row
            await db.execute(
                "INSERT INTO monitors (user_id, category, details) VALUES (?, ?, ?)",
                (call.from_user.id, "Futbol Sektor", f"{match_title} | {s_name} (ID: {sec_id})")
            )
            await db.commit()
            await call.answer("✅ Monitoring o'rnatildi! Joy bo'shasa xabar beramiz.", show_alert=True)
            await call.message.edit_text("✅ <b>Monitoring faollashtirildi!</b> Ushbu sektorga joy qo'shilishi bilan sizga tezkor xabar keladi.")

# ---------------- Poyezd Monitoringi Bo'limi ----------------
@router.message(F.text == "🚆 Poyezd Biletlari Monitoringi")
async def train_monitor_start(message: Message, state: FSMContext):
    await state.set_state(UserState.waiting_for_route)
    await message.answer("🚆 Poyezd uchun yo'nalishni kiriting:\n<i>(Masalan: Toshkent - Samarqand yoki Buxoro - Toshkent)</i>")

@router.message(UserState.waiting_for_route)
async def process_train_route(message: Message, state: FSMContext):
    await state.update_data(route=message.text)
    await state.set_state(UserState.waiting_for_date)
    await message.answer("📅 Bilet kerakli sanani kiriting:\n<i>(Masalan: 2026-10-15)</i>")

@router.message(UserState.waiting_for_date)
async def process_train_date(message: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO monitors (user_id, category, details) VALUES (?, ?, ?)",
            (message.from_user.id, "Poyezd", f"{data['route']} | {message.text}")
        )
        await db.commit()

    await state.clear()
    await message.answer(
        f"✅ <b>Poyezd monitoringi ishga tushdi!</b>\n\n"
        f"📍 Yo'nalish: <b>{data['route']}</b>\n"
        f"📅 Sana: <b>{message.text}</b>\n\n"
        f"Bo'sh joy paydo bo'lishi bilan xabar yuboramiz!",
        reply_markup=main_keyboard(message.from_user.id)
    )

# ---------------- Foydalanuvchining Biletlari va Monitoringlari ----------------
@router.message(F.text == "🎟 Mening Biletlarim")
async def my_tickets(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT match_title, sector_name, seat_number, price, created_at FROM tickets WHERE user_id = ?",
            (message.from_user.id,)
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("Sizda hali xarid qilingan biletlar mavjud emas.")
        return

    msg = "<b>🎟 Sizning Biletlaringiz:</b>\n\n"
    for m_title, s_name, seat, price, date in rows:
        msg += f"⚽ <b>{m_title}</b>\n📍 Sektor: {s_name} | 💺 Joy: #{seat}\n💵 {price:,} so'm | 🕒 {date}\n-------------------\n"

    await message.answer(msg)

@router.message(F.text == "🔔 Monitoringlarim")
async def my_monitors(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, category, details FROM monitors WHERE user_id = ? AND is_active = 1", (message.from_user.id,)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("Sizda faol monitoringlar yo'q.")
        return

    msg = "<b>🔔 Faol Monitoringlar:</b>\n\n"
    buttons = []
    for m_id, cat, details in rows:
        msg += f"🆔 #{m_id} | <b>{cat}</b>: {details}\n"
        buttons.append([InlineKeyboardButton(text=f"❌ O'chirish #{m_id}", callback_data=f"del_mon_{m_id}")])

    await message.answer(msg, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("del_mon_"))
async def del_monitor(call: CallbackQuery):
    m_id = int(call.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM monitors WHERE id = ?", (m_id,))
        await db.commit()
    await call.answer("Monitoring o'chirildi ✅")
    await call.message.delete()

# ---------------- PRO va Profil ----------------
@router.message(F.text == "⭐ PRO Tarif")
async def show_pro(message: Message):
    await message.answer(
        "<b>⭐ PRO Tarif Xizmati:</b>\n\n"
        "• Tezlangan 10 soniyali avto-qidiruv\n"
        "• Cheksiz o'yin va poyezdlarga monitoring qo'yish\n"
        "• VIP bildirishnomalar\n\n"
        "Ulanish uchun @admin bilan bog'laning."
    )

@router.message(F.text == "👤 Profil")
async def show_profile(message: Message):
    await message.answer(
        f"<b>👤 Profilingiz:</b>\n\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"👤 Ism: {message.from_user.full_name}\n"
        f"⭐ Status: Oddiy Foydalanuvchi"
    )

# ---------------- Admin Panel ----------------
@router.message(F.text == "⚙ Admin Panel", F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📣 Reklama Yuborish", callback_data="admin_broadcast")]
    ])
    await message.answer("⚙ <b>Boshqaruv Paneli:</b>", reply_markup=kb)

@router.callback_query(F.data == "admin_stats", F.from_user.id == ADMIN_ID)
async def admin_stats(call: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1:
            u_count = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM tickets") as c2:
            t_count = (await c2.fetchone())[0]

    await call.message.edit_text(f"📊 <b>Statistika:</b>\n\n👥 Foydalanuvchilar: {u_count}\n🎟 Sotilgan biletlar: {t_count}")

# ==================== AUTOMATIC MONITORING WORKER ====================
async def background_monitoring_loop():
    """ Orqa fonda bo'sh joylarni avtomatik tekshiruvchi va xabar yuboruvchi qism """
    while True:
        try:
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT id, user_id, category, details FROM monitors WHERE is_active = 1") as cursor:
                    monitors = await cursor.fetchall()

            for m_id, u_id, cat, details in monitors:
                if cat == "Futbol Sektor" and "ID:" in details:
                    sec_id = int(details.split("ID:")[1].replace(")", "").strip())
                    async with aiosqlite.connect(DB_NAME) as db:
                        async with db.execute("SELECT available_seats, sector_name FROM sectors WHERE id = ?", (sec_id,)) as c:
                            row = await c.fetchone()
                            if row and row[0]: # Bo'sh joy paydo bo'lsa
                                await bot.send_message(
                                    u_id,
                                    f"🔔 <b>DIQQAT! BO'SH JOY PAYDO BO'LDI!</b>\n\n"
                                    f"📍 Sektor: {row[1]}\n"
                                    f"💺 Mavjud joylar: {row[0]}\n\n"
                                    f"Darhol botga kirib biletni band qiling!"
                                )
                                # Xabar yuborilgach, monitoringni o'chiramiz
                                await db.execute("UPDATE monitors SET is_active = 0 WHERE id = ?", (m_id,))
                                await db.commit()

        except Exception as e:
            logging.error(f"Worker Error: {e}")

        await asyncio.sleep(15) # Har 15 soniyada fonda tekshirib turadi

# ==================== MAIN ISHGA TUSHIRISH ====================
async def main():
    await init_db()
    asyncio.create_task(background_monitoring_loop()) # Orqa fondagi monitoringni ishga tushirish
    print("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
