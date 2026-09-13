import sys
import os

# 1. AVVAL YO'LNI QO'SHAMIZ (Eng tepada turishi shart!)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import asyncio
import logging
from aiogram import Bot, Dispatcher

# 2. KEYIN CONFIG VA DATABASE IMPORT QILINADI
from config import BOT_TOKEN
from database import init_db
from handlers import start, game, admin, settings

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_routers(
        start.router,
        game.router,
        admin.router,
        settings.router
    )

    print("✅ Mafia Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot to'xtatildi.")
