from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from game_logic.engine import active_games, GameSession

router = Router()

@router.message(Command("game"))
async def cmd_game(message: Message):
    if message.chat.type == "private":
        return

    chat_id = message.chat.id
    if chat_id in active_games:
        await message.answer("Bu guruhda o'yin allaqachon boshlangan!")
        return

    session = GameSession(chat_id)
    active_games[chat_id] = session

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 O'yinga qo'shilish", url="https://t.me/bot?start=join")]
    ])
    await message.answer("Ro'yxatdan o'tish boshlandi!\nO'yinga qo'shilish uchun pastdagi tugmani bosing.", reply_markup=kb)

@router.message(Command("give"))
async def cmd_give(message: Message):
    if message.reply_to_message:
        target = message.reply_to_message.from_user.full_name
        sender = message.from_user.full_name
        await message.answer(f"{sender} 1 💎 {target} ga xayriya qildi!")
