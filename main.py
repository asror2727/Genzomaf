import asyncio
import logging
import os
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database import db
from i18n import t
from handlers import private, group, admin

logging.basicConfig(level=logging.INFO)


async def _loan_collector(bot: Bot):
    """Muddati o'tgan qarzlarni (/loan) har soatda tekshirib, foydalanuvchida qancha pul bo'lsa
    shunchasini avtomatik yechib oladi va qolganini kechiradi (balans yetmasa)."""
    while True:
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            overdue = await db.overdue_loans(now_iso)
            for loan_id, user_id, owed in overdue:
                user = await db.get_user(user_id)
                if not user:
                    await db.force_close_loan(loan_id)
                    continue
                pay = min(owed, user["money"])
                if pay > 0:
                    await db.update_balance(user_id, money=-pay)
                await db.force_close_loan(loan_id)
                try:
                    lang = user["lang"]
                    await bot.send_message(user_id, t(lang, "loan_overdue_collected", amount=pay))
                except Exception:
                    pass
        except Exception:
            logging.exception("Qarz yig'ish vazifasida xato")
        await asyncio.sleep(3600)  # har soatda tekshiradi


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
        await asyncio.gather(_run_health_server(), _loan_collector(bot), dp.start_polling(bot))
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
