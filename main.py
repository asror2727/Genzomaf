import sys
import os

# Render va serverda import xatolari (ModuleNotFoundError) chiqmasligi uchun 
# asosiy papka yo'lini tizimga qo'shamiz
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from database import init_db
from handlers import start, game, admin, settings

# Konsolda loglarni ko'rsatish
logging.basicConfig(level=logging.INFO)

async def main():
    # Ma'lumotlar bazasini ishga tushirish (jadvallarni yaratish)
    await init_db()
    
    # Bot va Dispatcher obyektlarini yaratish
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Xendlerni (marshrutlarni) ulash
    dp.include_routers(
        start.router,
        game.router,
        admin.router,
        settings.router
    )

    print("✅ Mafia Bot (aiogram 3.x) muvaffaqiyatli ishga tushdi va xabarlarni kutmoqda...")
    
    # Botni ishga tushirish (Polling rejimi)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot to'xtatildi.")
