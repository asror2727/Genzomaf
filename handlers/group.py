from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, ADMINISTRATOR

from database import db
from i18n import t
from game.engine import manager
from config import OWNER_ID

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
router.callback_query.filter(F.message.chat.type.in_({"group", "supergroup"}))


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
async def on_bot_promoted(event: ChatMemberUpdated):
    await db.set_group_owner(event.chat.id, event.from_user.id)
    settings = await db.get_group_settings(event.chat.id)
    lang = "uz"
    await event.bot.send_message(event.chat.id, t(lang, "admin_bonus_granted"))


@router.message(Command("game"))
async def cmd_game(message: Message, bot: Bot):
    chat_id = message.chat.id
    lang = "uz"
    if manager.has_active(chat_id):
        await message.answer(t(lang, "reg_already_active"))
        return
    await manager.start_registration(bot, chat_id, lang)


@router.message(Command("start"))
async def cmd_start_group(message: Message, bot: Bot):
    """Guruhda /start bosilsa: faol ro'yxat bo'lmasa yangisini ochadi,
    yetarli odam yig'ilgan bo'lsa o'yinni boshlaydi."""
    chat_id = message.chat.id
    lang = "uz"
    if not manager.has_active(chat_id):
        await manager.start_registration(bot, chat_id, lang)
        return
    started = await manager.try_force_start(bot, chat_id)
    if not started:
        await message.answer(t(lang, "reg_already_active"))


@router.callback_query(F.data == "reg_join")
async def cb_reg_join(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user = callback.from_user
    await db.get_or_create_user(user.id, user.full_name)
    result = await manager.add_player(bot, chat_id, user.id, user.full_name)
    lang = "uz"
    if result == "ok":
        await callback.answer(t(lang, "reg_joined_private"), show_alert=True)
        try:
            await bot.send_message(user.id, t(lang, "reg_joined_private"))
        except Exception:
            pass
    elif result == "already":
        await callback.answer(t(lang, "reg_already_joined"), show_alert=True)
    elif result == "full":
        await callback.answer("Guruh to'lgan.", show_alert=True)
    else:
        await callback.answer()


# ---------------- NIGHT ACTION CALLBACKS ----------------

@router.callback_query(F.data.startswith("night_"))
async def cb_night_action(callback: CallbackQuery, bot: Bot):
    # format: night_<role>_<target_id> — bu private chatda keladi, lekin chat_id ni
    # aniqlash uchun foydalanuvchining faol o'yinini qidiramiz
    _, role, target_id = callback.data.split("_")
    target_id = int(target_id)
    actor_id = callback.from_user.id
    game = _find_game_for_player(actor_id)
    if not game:
        await callback.answer()
        return
    manager.register_night_action(game.chat_id, role, actor_id, target_id)
    await callback.message.edit_text("✅ Qabul qilindi.")
    await callback.answer()


# ---------------- VOTE CALLBACKS ----------------

@router.callback_query(F.data == "open_vote")
async def cb_open_vote(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    await manager.open_vote_menu(bot, chat_id, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data.startswith("votefor_"))
async def cb_vote_for(callback: CallbackQuery, bot: Bot):
    target_id = int(callback.data.split("_", 1)[1])
    voter_id = callback.from_user.id
    game = _find_game_for_player(voter_id)
    if not game:
        await callback.answer()
        return
    await manager.register_vote(bot, game.chat_id, voter_id, target_id)
    await callback.message.edit_text("✅ Ovoz qabul qilindi.")
    await callback.answer()


def _find_game_for_player(user_id: int):
    for game in manager.games.values():
        if user_id in game.players:
            return game
    return None


# ---------------- GIVE / SEND / TOKEN ----------------

@router.message(Command("give"))
async def cmd_give(message: Message):
    if not message.reply_to_message:
        return
    parts = message.text.split()
    amount = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    giver = message.from_user
    target = message.reply_to_message.from_user
    await db.get_or_create_user(giver.id, giver.full_name)
    await db.get_or_create_user(target.id, target.full_name)

    giver_data = await db.get_user(giver.id)
    if giver_data["diamond"] < amount:
        await message.answer("💎 Yetarli almazingiz yo'q.")
        return
    await db.update_balance(giver.id, diamond=-amount)
    await db.update_balance(target.id, diamond=amount)

    lang = "uz"
    await message.answer(
        t(lang, "give_announce", giver=giver.full_name, amount=amount, target=target.full_name)
    )


# ---------------- SETTINGS (faqat guruh egasi) ----------------

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    owner_id = await db.get_group_owner(message.chat.id)
    lang = "uz"
    if message.from_user.id != owner_id and message.from_user.id != OWNER_ID:
        await message.answer(t(lang, "not_owner"))
        return
    await message.answer(t(lang, "settings_menu"))
    # TODO: to'liq sozlamalar inline menyusi (vaqt, jimlik, arjament, boshqa) shu yerga qo'shiladi
