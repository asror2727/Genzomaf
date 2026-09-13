import sys
import os
import logging
import asyncio

# Render uchun yo'lni eng tepada qo'shish
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import BOT_TOKEN, BOT_USERNAME, ADMIN_ID

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Foydalanuvchi tillari va o'yin holatlari xotirasi (Vaqtinchalik storage)
user_languages = {}
games_data = {}

# Lug'at (O'zbek, Rus va Ingliz tillari uchun)
TEXTS = {
    'uz': {
        'welcome': "Xush kelibsiz! Mafia botiga marhamat.",
        'choose_lang': "Tilni tanlang / Choose language:",
        'lang_set': "Til O'zbek tiliga o'zgartirildi!",
        'add_group': "Guruhga qo'shish",
        'game_start': "🎮 Mafia o'yini boshlandi!\nQo'shilish uchun pastdagi tugmani bosing.",
        'join': "🎮 Qo'shilish",
        'joined': " o'yinga qo'shildi!",
        'already_joined': "Siz allaqachon o'yindasiz!",
        'no_rights': "Bot guruhda xabarni pin qilish (qadash) huquqiga ega emas! Botga Admin huquqini bering.",
        'admin_panel': "👨‍✈️ Admin panelga xush kelibsiz!",
        'not_admin': "Siz admin emassiz!",
        'settings': "⚙️ Sozlamalar menyusi"
    },
    'ru': {
        'welcome': "Добро пожаловать в Мафия бот!",
        'choose_lang': "Выберите язык / Choose language:",
        'lang_set': "Язык изменен на Русский!",
        'add_group': "Добавить в группу",
        'game_start': "🎮 Игра Мафия началась!\nНажмите кнопку ниже, чтобы присоединиться.",
        'join': "🎮 Присоединиться",
        'joined': " присоединился к игре!",
        'already_joined': "Вы уже в игре!",
        'no_rights': "У бота нет прав для закрепления сообщений! Дайте боту права Администратора.",
        'admin_panel': "👨‍✈️ Добро пожаловать в админ-панель!",
        'not_admin': "Вы не администратор!",
        'settings': "⚙️ Меню настроек"
    }
}

def get_text(user_id, key):
    lang = user_languages.get(user_id, 'uz')
    return TEXTS[lang].get(key, TEXTS['uz'][key])

# --- KLAVIATURALAR ---
def get_start_keyboard(user_id):
    lang = user_languages.get(user_id, 'uz')
    add_url = f"https://t.me/{BOT_USERNAME}?startgroup=true"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=TEXTS[lang]['add_group'], url=add_url)],
        [
            InlineKeyboardButton(text="🌐 Til / Language", callback_data="change_lang"),
            InlineKeyboardButton(text="⚙️ Sozlamalar", callback_data="open_settings")
        ],
        [InlineKeyboardButton(text="👨‍✈️ Admin Panel", callback_data="open_admin")]
    ])
    return keyboard

def get_lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang_ru")
        ]
    ])

# --- HANDLERLAR ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_languages:
        user_languages[user_id] = 'uz'
    
    await message.answer(
        get_text(user_id, 'welcome'),
        reply_markup=get_start_keyboard(user_id)
    )

@dp.message(Command("game"))
async def cmd_game(message: types.Message):
    if message.chat.type in ["group", "supergroup"]:
        chat_id = message.chat.id
        games_data[chat_id] = []
        
        join_btn = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=TEXTS['uz']['join'], callback_data=f"join_game_{chat_id}")]
        ])
        
        msg = await message.answer(TEXTS['uz']['game_start'], reply_markup=join_btn)
        
        # Xabarni Pin qilishga urinish
        try:
            await bot.pin_chat_message(chat_id=chat_id, message_id=msg.message_id)
        except Exception:
            await message.answer(TEXTS['uz']['no_rights'])
    else:
        await message.answer(" /game buyrug'i faqat guruhlarda ishlaydi!")

@dp.callback_query(F.data.startswith("join_game_"))
async def join_game_callback(call: CallbackQuery):
    chat_id = int(call.data.split("_")[2])
    user = call.from_user
    
    if chat_id not in games_data:
        games_data[chat_id] = []
        
    if user.id in [u['id'] for u in games_data[chat_id]]:
        await call.answer(TEXTS['uz']['already_joined'], show_alert=True)
    else:
        games_data[chat_id].append({'id': user.id, 'name': user.full_name})
        await call.answer("Muvaffaqiyatli qo'shildingiz!")
        await call.message.answer(f"👤 {user.full_name}{TEXTS['uz']['joined']}")

@dp.callback_query(F.data == "change_lang")
async def process_change_lang(call: CallbackQuery):
    await call.message.edit_text(
        get_text(call.from_user.id, 'choose_lang'),
        reply_markup=get_lang_keyboard()
    )

@dp.callback_query(F.data.startswith("set_lang_"))
async def set_language(call: CallbackQuery):
    lang_code = call.data.split("_")[2]
    user_id = call.from_user.id
    user_languages[user_id] = lang_code
    
    await call.answer(get_text(user_id, 'lang_set'))
    await call.message.edit_text(
        get_text(user_id, 'welcome'),
        reply_markup=get_start_keyboard(user_id)
    )

@dp.callback_query(F.data == "open_admin")
async def open_admin_panel(call: CallbackQuery):
    user_id = call.from_user.id
    if user_id == ADMIN_ID:
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Statistikani ko'rish", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main")]
        ])
        await call.message.edit_text(get_text(user_id, 'admin_panel'), reply_markup=admin_kb)
    else:
        await call.answer(get_text(user_id, 'not_admin'), show_alert=True)

@dp.callback_query(F.data == "open_settings")
async def open_settings(call: CallbackQuery):
    user_id = call.from_user.id
    sett_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Tilni o'zgartirish", callback_data="change_lang")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main")]
    ])
    await call.message.edit_text(get_text(user_id, 'settings'), reply_markup=sett_kb)

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery):
    user_id = call.from_user.id
    await call.message.edit_text(
        get_text(user_id, 'welcome'),
        reply_markup=get_start_keyboard(user_id)
    )

async def main():
    print("✅ Mafia Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot to'xtatildi.")
