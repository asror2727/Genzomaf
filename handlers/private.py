from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from i18n import t, SUPPORTED_LANGS
from config import CHANNEL_USERNAME

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
    # Agar hali til tanlanmagan bo'lsa (yangi foydalanuvchi default 'uz' bilan keladi,
    # shuning uchun har doim tanlashni taklif qilamiz birinchi safar)
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


@router.message(Command("reyting"))
async def cmd_rating(message: Message):
    lang = await db.get_lang(message.from_user.id)
    top = await db.top_rating(100)
    lines = [f"#{i+1} {name} — {points} ball" for i, (uid, name, points) in enumerate(top)]
    text = "\n".join(lines) if lines else "—"
    await message.answer(text)
