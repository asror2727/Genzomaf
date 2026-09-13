from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from config import OWNER_ID

router = Router()

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id == OWNER_ID:
        await message.answer("👑 **Admin Panelga xush kelibsiz!**\nBarcha boshqaruv elementlari faol.")
