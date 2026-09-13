from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

router = Router()

@router.message(Command("setting"))
async def cmd_setting(message: Message):
    if message.chat.type == "private":
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏰ Vaqt sozlamalari", callback_data="s_time")],
        [InlineKeyboardButton(text="🔇 Jimlik", callback_data="s_silence")],
        [InlineKeyboardButton(text="🛠 Qurollar", callback_data="s_items")],
        [InlineKeyboardButton(text="🌐 Til", callback_data="s_lang")],
        [InlineKeyboardButton(text="⚙️ Boshqa sozlamalar", callback_data="s_other")]
    ])
    await message.answer("⚙️ **Sozlamalar menyusi**", reply_markup=kb)
