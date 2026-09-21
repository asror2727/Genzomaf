import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database import db
from handlers import private, group, admin

logging.basicConfig(level=logging.INFO)


async def _run_health_server():
    """Render'da 'Web Service' turi tanlangan bo'lsa, u $PORT ochilishini kutadi —
    aks holda bir necha daqiqadan keyin 'Deploy failed' deb belgilaydi.
    Bu funksiya shunchaki minimal HTTP javob beruvchi server ochadi.
    Agar 'Background Worker' turi ishlatilsa PORT o'zgaruvchisi bo'lmaydi va bu funksiya
    hech narsa qilmaydi (zararsiz)."""
    port = os.getenv("PORT")
    if not port:
        return
    from aiohttp import web

    async def health(_request):
        return web.Response(text="Mafia bot is running.")

    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(port))
    await site.start()
    logging.info(f"Health-check server {port}-portda ishga tushdi.")


async def main():
    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_TOKEN_HERE":
        raise RuntimeError("BOT_TOKEN environment variable o'rnatilmagan!")

    await db.connect()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(admin.router)
    dp.include_router(private.router)
    dp.include_router(group.router)

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await asyncio.gather(_run_health_server(), dp.start_polling(bot))
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
