from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER_ID
from database import db

router = Router()
router.message.filter(F.from_user.id == OWNER_ID)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.chat.type != "private":
        return  # admin panel faqat private chatda ochiladi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Narxlar", callback_data="adm_prices")],
        [InlineKeyboardButton(text="💎 To'lovlarni tasdiqlash", callback_data="adm_transactions")],
        [InlineKeyboardButton(text="📜 Qoidalar", callback_data="adm_rules")],
        [InlineKeyboardButton(text="🏆 Premium guruhlar", callback_data="adm_premium")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="adm_broadcast")],
    ])
    await message.answer("🛠 Admin panel", reply_markup=kb)


@router.callback_query(F.data == "adm_stats")
async def cb_stats(callback: CallbackQuery):
    cur = await db._conn.execute("SELECT COUNT(*) FROM users")
    users_count = (await cur.fetchone())[0]
    cur = await db._conn.execute("SELECT COUNT(*) FROM groups")
    groups_count = (await cur.fetchone())[0]
    await callback.message.edit_text(
        f"📊 Statistika\n\n👤 Foydalanuvchilar: {users_count}\n👥 Guruhlar: {groups_count}"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("approve_tx_"))
async def cb_approve_tx(callback: CallbackQuery):
    tx_id = int(callback.data.split("_")[-1])
    tx = await db.get_transaction(tx_id)
    if not tx:
        await callback.answer("Topilmadi", show_alert=True)
        return
    _, user_id, kind, amount, status, _ = tx
    if status == "approved":
        await callback.answer("Allaqachon tasdiqlangan.", show_alert=True)
        return
    if kind == "diamond":
        await db.update_balance(user_id, diamond=amount)
    elif kind == "money":
        await db.update_balance(user_id, money=amount)
    await db.approve_transaction(tx_id)
    await callback.message.edit_text(callback.message.text + "\n\n✅ Tasdiqlandi")
    try:
        await callback.bot.send_message(user_id, f"✅ To'lovingiz tasdiqlandi! +{amount} {kind}")
    except Exception:
        pass
    await callback.answer()
