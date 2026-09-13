from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from database import add_user, get_user

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type == "private":
        await add_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"), InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"), InlineKeyboardButton(text="🇹🇷 Türkçe", callback_data="lang_tr")]
        ])
        await message.answer("Выберите язык / Tilni tanlang:", reply_markup=kb)
    else:
        await message.answer("Ma'mur huquqlari olingan!\nRo'yxatdan o'tishni boshlash uchun shunchaki /game yuboring.")

@router.callback_query(F.data.startswith("lang_"))
async def set_language(call: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Guruhga qo'shish", url="https://t.me/bot?startgroup=true")],
        [InlineKeyboardButton(text="💎 Premium guruhlar", callback_data="premium")],
        [InlineKeyboardButton(text="📰 Yangiliklar", url="https://t.me/genzomafiauz")],
        [InlineKeyboardButton(text="🌐 Til", callback_data="change_lang"), InlineKeyboardButton(text="📜 Qoidalar", callback_data="rules")]
    ])
    await call.message.edit_text("Salom!\nMen 🤵🏻 Mafia o'yini rasmiy botiman.", reply_markup=kb)

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return
    
    text = f'''⭐ ID: {user[0]}

👤 {user[2]}

💵 pul: {user[4]}
💎 almaz: {user[5]}
🪙 genzo token: {user[6]}

🛡 Himoya: {user[10]}
🔫 Miltiq: {user[11]}

🎭 Maska: {user[12]}
📁 Soxta hujjat: {user[13]}
🃏 Keyingi o'yindagi rolingiz: -

🎯 Побед: {user[8]}
🎲 Всего игр: {user[9]}'''

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Do'kon", callback_data="shop")],
        [InlineKeyboardButton(text="💵 Xarid qilish", callback_data="buy_money"), InlineKeyboardButton(text="💎 Xarid qiling", callback_data="buy_diamond")],
        [InlineKeyboardButton(text="🪙 GZ token xarid qilish", callback_data="buy_gz")]
    ])
    await message.answer(text, reply_markup=kb)
