from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import OWNER_ID
from database import db
from i18n import t
from game.engine import manager

router = Router()
router.message.filter(F.from_user.id == OWNER_ID)
router.callback_query.filter(F.from_user.id == OWNER_ID)

# Owner hozir nima kiritishini kutayotganini saqlaydi: None yoki
# "broadcast" / "rules" / "premium" / "npc"
_admin_state: dict[int, str] = {}


def _admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Narxlar", callback_data="adm_prices")],
        [InlineKeyboardButton(text="💎 To'lovlarni tasdiqlash", callback_data="adm_transactions")],
        [InlineKeyboardButton(text="📜 Qoidalar", callback_data="adm_rules")],
        [InlineKeyboardButton(text="🏆 Premium guruhlar", callback_data="adm_premium")],
        [InlineKeyboardButton(text="🤖 NPC qo'shish", callback_data="adm_npc")],
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="adm_broadcast")],
    ])


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.chat.type != "private":
        return  # admin panel faqat private chatda ochiladi
    _admin_state.pop(message.from_user.id, None)
    await message.answer("🛠 Admin panel", reply_markup=_admin_menu_kb())


@router.callback_query(F.data == "adm_back")
async def cb_back(callback: CallbackQuery):
    _admin_state.pop(callback.from_user.id, None)
    await callback.message.edit_text("🛠 Admin panel", reply_markup=_admin_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "adm_stats")
async def cb_stats(callback: CallbackQuery):
    cur = await db._conn.execute("SELECT COUNT(*) FROM users")
    users_count = (await cur.fetchone())[0]
    cur = await db._conn.execute("SELECT COUNT(*) FROM groups")
    groups_count = (await cur.fetchone())[0]
    active_games = len(manager.games)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")]])
    await callback.message.edit_text(
        f"📊 Statistika\n\n👤 Foydalanuvchilar: {users_count}\n👥 Guruhlar: {groups_count}\n"
        f"🎮 Faol o'yinlar: {active_games}",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "adm_prices")
async def cb_prices(callback: CallbackQuery):
    from config import SHOP_ITEM_PRICES, DIAMOND_PACKAGES, MONEY_CONVERSION_RATE
    lines = ["💰 Joriy narxlar (o'zgartirish uchun config.py fayli tahrirlanadi):\n"]
    lines.append("Do'kon (almazda):")
    for k, v in SHOP_ITEM_PRICES.items():
        lines.append(f"  {k}: {v}💎")
    lines.append("\nAlmaz paketlari:")
    for amount, price in DIAMOND_PACKAGES.items():
        lines.append(f"  {amount}💎 — {price} so'm")
    lines.append(f"\n1 almaz = {MONEY_CONVERSION_RATE} pul")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")]])
    await callback.message.edit_text("\n".join(lines), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "adm_transactions")
async def cb_transactions(callback: CallbackQuery):
    rows = await db.pending_transactions(20)
    if not rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")]])
        await callback.message.edit_text("Kutilayotgan to'lovlar yo'q.", reply_markup=kb)
        await callback.answer()
        return
    buttons = []
    for tx_id, user_id, kind, amount in rows:
        buttons.append([InlineKeyboardButton(
            text=f"#{tx_id} — {user_id} — {amount} {kind}", callback_data=f"approve_tx_{tx_id}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="adm_back")])
    await callback.message.edit_text("💎 Kutilayotgan to'lovlar (bosib tasdiqlang):", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("approve_tx_"))
async def cb_approve_tx(callback: CallbackQuery, bot: Bot):
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
    try:
        if callback.message.text:
            await callback.message.edit_text(callback.message.text + "\n\n✅ Tasdiqlandi")
        else:
            await callback.message.edit_caption((callback.message.caption or "") + "\n\n✅ Tasdiqlandi")
    except Exception:
        pass
    try:
        user = await db.get_user(user_id)
        lang = user["lang"] if user else "uz"
        await bot.send_message(user_id, t(lang, "tx_approved_notice", amount=amount, kind=kind))
    except Exception:
        pass
    await callback.answer("✅ Tasdiqlandi")


@router.callback_query(F.data == "adm_rules")
async def cb_rules(callback: CallbackQuery):
    _admin_state[callback.from_user.id] = "rules"
    current = await db.kv_get("rules", "(hali kiritilmagan)")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="adm_back")]])
    await callback.message.edit_text(
        f"Joriy qoidalar:\n\n{current}\n\n---\nYangi matn yuboring:", reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "adm_premium")
async def cb_premium(callback: CallbackQuery):
    _admin_state[callback.from_user.id] = "premium"
    links = await db.list_premium_groups(10)
    current = "\n".join(links) if links else "(hali yo'q)"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="adm_back")]])
    await callback.message.edit_text(
        f"Joriy premium guruhlar:\n{current}\n\n---\nYangi guruh linkini yuboring:", reply_markup=kb
    )
    await callback.answer()


@router.callback_query(F.data == "adm_broadcast")
async def cb_broadcast(callback: CallbackQuery):
    _admin_state[callback.from_user.id] = "broadcast"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="adm_back")]])
    await callback.message.edit_text("Barcha foydalanuvchilarga yuboriladigan xabarni yozing:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "adm_npc")
async def cb_npc(callback: CallbackQuery):
    _admin_state[callback.from_user.id] = "npc"
    active = "\n".join(f"• {chat_id} — {len(g.players)} kishi" for chat_id, g in manager.games.items()) or "(faol ro'yxat yo'q)"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="adm_back")]])
    await callback.message.edit_text(
        f"Hozir faol ro'yxatdan o'tishlar:\n{active}\n\n"
        f"Guruh ID va bot sonini yozing.\nMasalan: -1001234567890 3",
        reply_markup=kb,
    )
    await callback.answer()


def _has_pending_admin_input(message: Message) -> bool:
    """Faqat owner /admin panelidan biror amalni tanlab, matn kiritishi kutilayotgan bo'lsa True."""
    if message.chat.type != "private":
        return False
    if not message.text or message.text.startswith("/"):
        return False
    return message.from_user.id in _admin_state


@router.message(_has_pending_admin_input)
async def handle_admin_text_input(message: Message, bot: Bot):
    """Owner /admin orqali biror amalni tanlagandan keyin yuboradigan matnni qayta ishlaydi.
    Filtr yuqorida aniq belgilangani uchun bu handler FAQAT kutilayotgan holat bo'lganda
    ishga tushadi — shu sabab boshqa barcha buyruqlar (guruhdagi va private) erkin ishlayveradi."""
    state = _admin_state.get(message.from_user.id)

    if state == "rules":
        await db.kv_set("rules", message.text)
        await message.answer("✅ Qoidalar saqlandi.", reply_markup=_admin_menu_kb())
    elif state == "premium":
        await db.add_premium_group(message.text.strip())
        await message.answer("✅ Premium guruhlar ro'yxatiga qo'shildi.", reply_markup=_admin_menu_kb())
    elif state == "broadcast":
        user_ids = await db.all_user_ids()
        sent = 0
        for uid in user_ids:
            try:
                await bot.send_message(uid, message.text)
                sent += 1
            except Exception:
                pass
        await message.answer(f"📢 Xabar {sent} ta foydalanuvchiga yuborildi.", reply_markup=_admin_menu_kb())
    elif state == "npc":
        parts = message.text.split()
        if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
            await message.answer("❌ Format noto'g'ri. Masalan: -1001234567890 3")
            return
        chat_id = int(parts[0])
        count = int(parts[1])
        names = await manager.add_npc_players(bot, chat_id, count)
        if names:
            await message.answer(f"🤖 Qo'shildi: {', '.join(names)}", reply_markup=_admin_menu_kb())
        else:
            await message.answer("❌ Bu guruhda faol ro'yxatdan o'tish topilmadi yoki joy yo'q.", reply_markup=_admin_menu_kb())
    else:
        return

    _admin_state.pop(message.from_user.id, None)
