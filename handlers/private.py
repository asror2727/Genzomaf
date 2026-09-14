from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from i18n import t, SUPPORTED_LANGS
from config import (
    CHANNEL_USERNAME, OWNER_ID, PAYMENT_CARD, SHOP_ITEM_PRICES,
    DIAMOND_PACKAGES, MONEY_CONVERSION_RATE, MONEY_CONVERT_OPTIONS,
)

router = Router()
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


def lang_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"setlang_{code}")]
        for code, label in SUPPORTED_LANGS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def main_menu_keyboard(lang: str, bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_join_groups"),
                               url=f"https://t.me/{bot_username}?startgroup=true")],
        [InlineKeyboardButton(text=t(lang, "btn_premium"), callback_data="premium_groups")],
        [InlineKeyboardButton(text=t(lang, "btn_news"), url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton(text=t(lang, "btn_lang"), callback_data="open_lang"),
         InlineKeyboardButton(text=t(lang, "btn_rules"), callback_data="open_rules")],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user = await db.get_or_create_user(message.from_user.id, message.from_user.full_name)
    await message.answer(t(user["lang"], "choose_lang"), reply_markup=lang_keyboard())


@router.callback_query(F.data.startswith("setlang_"))
async def cb_set_lang(callback: CallbackQuery, bot: Bot):
    lang = callback.data.split("_", 1)[1]
    await db.set_lang(callback.from_user.id, lang)
    me = await bot.get_me()
    await callback.message.edit_text(
        t(lang, "welcome"), reply_markup=main_menu_keyboard(lang, me.username)
    )
    await callback.answer()


@router.message(Command("lang"))
async def cmd_lang(message: Message):
    lang = await db.get_lang(message.from_user.id)
    await message.answer(t(lang, "choose_lang"), reply_markup=lang_keyboard())


@router.callback_query(F.data == "open_lang")
async def cb_open_lang(callback: CallbackQuery):
    lang = await db.get_lang(callback.from_user.id)
    await callback.message.edit_text(t(lang, "choose_lang"), reply_markup=lang_keyboard())
    await callback.answer()


@router.callback_query(F.data == "open_rules")
async def cb_open_rules(callback: CallbackQuery):
    lang = await db.get_lang(callback.from_user.id)
    text = await db.kv_get("rules", "") or t(lang, "qoida_default")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back_main")]])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "premium_groups")
async def cb_premium_groups(callback: CallbackQuery):
    lang = await db.get_lang(callback.from_user.id)
    links = await db.list_premium_groups(10)
    text = "\n".join(links) if links else "—"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back_main")]])
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery, bot: Bot):
    lang = await db.get_lang(callback.from_user.id)
    me = await bot.get_me()
    await callback.message.edit_text(t(lang, "welcome"), reply_markup=main_menu_keyboard(lang, me.username))
    await callback.answer()


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    await send_profile(message.chat.id, message.from_user.id, message.bot)


async def send_profile(chat_id: int, user_id: int, bot: Bot):
    user = await db.get_user(user_id)
    if not user:
        user = await db.get_or_create_user(user_id, "Player")
    lang = user["lang"]
    text = t(
        lang, "profile",
        id=user["user_id"], name=user["name"], money=user["money"], diamond=user["diamond"],
        token=user["token"], shield=user["shield"], killer_protect=user["killer_protect"],
        vote_protect=user["vote_protect"], gun=user["gun"], mask=user["mask"],
        fake_doc=user["fake_doc"], next_role=user["next_role"], wins=user["wins"],
        total_games=user["total_games"],
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_shop"), callback_data="open_shop")],
        [InlineKeyboardButton(text=t(lang, "btn_buy_money"), callback_data="buy_money"),
         InlineKeyboardButton(text=t(lang, "btn_buy_diamond"), callback_data="buy_diamond")],
    ])
    await bot.send_message(chat_id, text, reply_markup=kb)


@router.callback_query(F.data == "back_profile")
async def cb_back_profile(callback: CallbackQuery, bot: Bot):
    await callback.message.delete()
    await send_profile(callback.message.chat.id, callback.from_user.id, bot)
    await callback.answer()


@router.message(Command("reyting"))
async def cmd_rating(message: Message):
    lang = await db.get_lang(message.from_user.id)
    top = await db.top_rating(100)
    lines = [f"#{i+1} {name} — {points} ball" for i, (uid, name, points) in enumerate(top)]
    text = "\n".join(lines) if lines else "—"
    await message.answer(text)


# ---------------- SHOP ----------------

_ITEM_LABELS = {
    "shield": "shop_item_shield",
    "mask": "shop_item_mask",
    "gun": "shop_item_gun",
    "fake_doc": "shop_item_fakedoc",
}


@router.callback_query(F.data == "open_shop")
async def cb_open_shop(callback: CallbackQuery):
    lang = await db.get_lang(callback.from_user.id)
    buttons = []
    for key, label_key in _ITEM_LABELS.items():
        price = SHOP_ITEM_PRICES[key]
        buttons.append([InlineKeyboardButton(
            text=f"{t(lang, label_key)} — {price}💎",
            callback_data=f"buyitem_{key}",
        )])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back_profile")])
    await callback.message.edit_text(t(lang, "shop_header"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("buyitem_"))
async def cb_buy_item(callback: CallbackQuery):
    item = callback.data.split("_", 1)[1]
    lang = await db.get_lang(callback.from_user.id)
    price = SHOP_ITEM_PRICES.get(item)
    if price is None:
        await callback.answer()
        return
    user = await db.get_user(callback.from_user.id)
    if user["diamond"] < price:
        await callback.answer(t(lang, "shop_not_enough"), show_alert=True)
        return
    await db._conn.execute(
        f"UPDATE users SET diamond = diamond - ?, {item} = {item} + 1 WHERE user_id=?",
        (price, callback.from_user.id),
    )
    await db._conn.commit()
    await callback.answer(t(lang, "shop_bought", item=t(lang, _ITEM_LABELS[item])), show_alert=True)


# ---------------- BUY MONEY (almazni pulga aylantirish) ----------------

@router.callback_query(F.data == "buy_money")
async def cb_buy_money(callback: CallbackQuery):
    lang = await db.get_lang(callback.from_user.id)
    buttons = [
        [InlineKeyboardButton(text=f"{n}💎 → {n * MONEY_CONVERSION_RATE}💵", callback_data=f"convmoney_{n}")]
        for n in MONEY_CONVERT_OPTIONS
    ]
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back_profile")])
    await callback.message.edit_text(t(lang, "buy_money_menu"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("convmoney_"))
async def cb_convert_money(callback: CallbackQuery):
    n = int(callback.data.split("_", 1)[1])
    lang = await db.get_lang(callback.from_user.id)
    user = await db.get_user(callback.from_user.id)
    if user["diamond"] < n:
        await callback.answer(t(lang, "shop_not_enough"), show_alert=True)
        return
    await db.update_balance(callback.from_user.id, diamond=-n, money=n * MONEY_CONVERSION_RATE)
    await callback.answer(t(lang, "shop_bought", item=f"{n * MONEY_CONVERSION_RATE}💵"), show_alert=True)


# ---------------- BUY DIAMOND (haqiqiy to'lov) ----------------

@router.callback_query(F.data == "buy_diamond")
async def cb_buy_diamond(callback: CallbackQuery):
    lang = await db.get_lang(callback.from_user.id)
    buttons = [
        [InlineKeyboardButton(text=f"{amount}💎 — {price} so'm", callback_data=f"diamondpkg_{amount}_{price}")]
        for amount, price in DIAMOND_PACKAGES.items()
    ]
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back_profile")])
    await callback.message.edit_text(t(lang, "buy_diamond_menu"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("diamondpkg_"))
async def cb_diamond_package(callback: CallbackQuery):
    _, amount, price = callback.data.split("_")
    amount, price = int(amount), int(price)
    lang = await db.get_lang(callback.from_user.id)
    await db.create_transaction(callback.from_user.id, "diamond", amount)
    await callback.message.edit_text(
        t(lang, "payment_instructions", amount=price).replace(PAYMENT_CARD, PAYMENT_CARD)
    )
    await callback.answer()


@router.message(F.photo)
async def handle_receipt_photo(message: Message, bot: Bot):
    """Foydalanuvchi to'lov chekini (skrinshot) yuborsa, kutilayotgan tranzaksiya bo'lsa
    admin(owner)ga forward qilinadi va tasdiqlash tugmasi biriktiriladi."""
    lang = await db.get_lang(message.from_user.id)
    tx = await db.get_last_pending_for_user(message.from_user.id)
    if not tx:
        return
    tx_id, kind, amount = tx
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_tx_{tx_id}")]
    ])
    caption = (
        f"💳 Yangi to'lov cheki\n"
        f"👤 {message.from_user.full_name} (ID: {message.from_user.id})\n"
        f"📦 {amount} {kind}\n"
        f"🆔 Tranzaksiya: {tx_id}"
    )
    try:
        await bot.send_photo(OWNER_ID, message.photo[-1].file_id, caption=caption, reply_markup=kb)
    except Exception:
        pass
    await message.answer(t(lang, "payment_receipt_received"))
