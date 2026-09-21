import asyncio
import random

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, ADMINISTRATOR
from aiogram.exceptions import TelegramBadRequest

from database import db
from i18n import t, SUPPORTED_LANGS
from game.engine import manager, mention
from config import OWNER_ID, GIVEAWAY_MONEY_CHUNK

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
router.callback_query.filter(F.message.chat.type.in_({"group", "supergroup"}))

# Kutilayotgan juftlik (birds) takliflari: target_id -> proposer_id (vaqtinchalik, xotirada)
_pending_pairs: dict[int, int] = {}

# Faol "olib qol" (claim) turdagi sovg'alar: message_id -> holat
_active_claims: dict[int, dict] = {}

# Berish uchun mavjud item nomlari va ularning DB ustuni + emoji + label kaliti
ITEM_ALIASES = {
    "almaz": ("diamond", "💎", None),
    "olmos": ("diamond", "💎", None),
    "diamond": ("diamond", "💎", None),
    "pul": ("money", "💵", None),
    "money": ("money", "💵", None),
    "token": ("token", "🪙", None),
    "himoya": ("shield", "🛡", "shop_item_shield"),
    "maska": ("mask", "🎭", "shop_item_mask"),
    "miltiq": ("gun", "🔫", "shop_item_gun"),
    "hujjat": ("fake_doc", "📁", "shop_item_fakedoc"),
    "bomba": ("bomb", "🧨", "shop_item_bomb"),
    "adrenalin": ("adrenaline", "💉", "shop_item_adrenaline"),
}
GIVEAWAY_TOGGLE_KEY = {
    "diamond": "giveaway_diamond_enabled",
    "money": "giveaway_money_enabled",
    "shield": "giveaway_shield_enabled",
    "mask": "giveaway_mask_enabled",
    "gun": "giveaway_gun_enabled",
    "fake_doc": "giveaway_fake_doc_enabled",
    "token": None,
    "bomb": None,
    "adrenaline": None,
}


async def _group_lang(chat_id: int) -> str | None:
    """Guruh uchun tanlangan tilni qaytaradi, hali tanlanmagan bo'lsa None."""
    return await db.get_group_lang(chat_id)


async def _require_group_lang(message: Message) -> str | None:
    """Guruh tili tanlanmagan bo'lsa ogohlantirish yuboradi va None qaytaradi."""
    lang = await _group_lang(message.chat.id)
    if not lang:
        await message.answer(t("uz", "group_lang_not_set"))
        return None
    return lang


async def _try_delete(message: Message):
    """Guruhni toza saqlash uchun buyruq xabarini o'chirishga harakat qiladi."""
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    except Exception:
        pass


# ---------------- BOT GURUHGA QO'SHILGANDA / TIL TANLASH ----------------

def _group_lang_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"glang_{code}")]
        for code, label in SUPPORTED_LANGS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
async def on_bot_promoted(event: ChatMemberUpdated):
    await db.set_group_owner(event.chat.id, event.from_user.id)
    await event.bot.send_message(event.chat.id, t("uz", "admin_bonus_granted"))
    await event.bot.send_message(event.chat.id, t("uz", "group_choose_lang"), reply_markup=_group_lang_kb())


@router.message(Command("lang"))
async def cmd_group_lang(message: Message, bot: Bot):
    if not await _is_group_admin(bot, message.chat.id, message.from_user.id):
        lang = await _group_lang(message.chat.id) or "uz"
        await message.answer(t(lang, "group_lang_admin_only"))
        return
    await message.answer(t("uz", "group_choose_lang"), reply_markup=_group_lang_kb())


@router.callback_query(F.data.startswith("glang_"))
async def cb_group_lang(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    if not await _is_group_admin(bot, chat_id, callback.from_user.id):
        await callback.answer(t("uz", "group_lang_admin_only"), show_alert=True)
        return
    lang = callback.data.split("_", 1)[1]
    await db.set_group_lang(chat_id, lang)
    label = SUPPORTED_LANGS.get(lang, lang)
    await callback.message.edit_text(t(lang, "group_lang_set", lang=label))
    await callback.answer()


async def _is_group_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    owner_id = await db.get_group_owner(chat_id)
    if user_id == owner_id:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except TelegramBadRequest:
        return False


# ---------------- GAME LIFECYCLE ----------------

@router.message(Command("game"))
async def cmd_game(message: Message, bot: Bot):
    await _try_delete(message)
    chat_id = message.chat.id
    lang = await _require_group_lang(message)
    if not lang:
        return
    if not manager.has_active(chat_id):
        await manager.start_registration(bot, chat_id, lang)
    else:
        # /game qayta bosildi: eski ro'yxat xabarini o'chirib, pastga qayta joylaydi va pin qiladi
        await manager.repost_registration(bot, chat_id)


@router.message(Command("start"))
async def cmd_start_group(message: Message, bot: Bot):
    await _try_delete(message)
    chat_id = message.chat.id
    lang = await _require_group_lang(message)
    if not lang:
        return
    if not manager.has_active(chat_id):
        await manager.start_registration(bot, chat_id, lang)
        return
    game = manager.get(chat_id)
    if game.phase.value != "registration":
        await message.answer(t(lang, "reg_already_active"))
        return
    if len(game.players) < game.settings.get("min_players", 4):
        await message.answer(t(lang, "not_enough_players_yet"))
        return
    await manager.try_force_start(bot, chat_id)


@router.message(Command("stop"))
async def cmd_stop(message: Message, bot: Bot):
    await _try_delete(message)
    chat_id = message.chat.id
    lang = await _group_lang(chat_id) or "uz"
    if not await _is_group_admin(bot, chat_id, message.from_user.id):
        await message.answer(t(lang, "not_owner"))
        return
    stopped = await manager.stop_game(bot, chat_id)
    await message.answer(t(lang, "stop_success") if stopped else t(lang, "stop_no_active"))


@router.message(Command("leave"))
async def cmd_leave(message: Message, bot: Bot):
    await _try_delete(message)
    chat_id = message.chat.id
    lang = await _group_lang(chat_id) or "uz"
    ok = await manager.leave_player(bot, chat_id, message.from_user.id)
    await message.answer(t(lang, "leave_success") if ok else t(lang, "leave_not_in_game"))


@router.message(Command("vaqt") | Command("extend"))
async def cmd_vaqt(message: Message, bot: Bot):
    await _try_delete(message)
    chat_id = message.chat.id
    lang = await _group_lang(chat_id) or "uz"
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(t(lang, "vaqt_usage"))
        return
    seconds = int(parts[1])
    ok = await manager.extend_registration(bot, chat_id, seconds)
    await message.answer(t(lang, "vaqt_extended", sec=seconds) if ok else t(lang, "vaqt_no_active"))


@router.message(Command("top"))
async def cmd_top(message: Message):
    await _try_delete(message)
    lang = await _group_lang(message.chat.id) or "uz"
    rows = await db.top_weekly_percent(20, min_games=3)
    if not rows:
        await message.answer(t(lang, "top_empty") + "\n" + t(lang, "top_need_more_games"))
        return
    lines = [f"{i+1}) {mention(uid, name)} - {percent}%" for i, (uid, name, percent) in enumerate(rows)]
    await message.answer(t(lang, "top_header_percent", n=len(rows), list="\n".join(lines)))


@router.message(Command("qoida"))
async def cmd_qoida_group(message: Message):
    await _try_delete(message)
    lang = await _group_lang(message.chat.id) or "uz"
    text = await db.kv_get("rules", "")
    await message.answer(text or t(lang, "qoida_default"))


# ---------------- REGISTRATION JOIN ----------------

@router.callback_query(F.data == "reg_join")
async def cb_reg_join(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user = callback.from_user
    await db.get_or_create_user(user.id, user.full_name)
    result = await manager.add_player(bot, chat_id, user.id, user.full_name)
    lang = await _group_lang(chat_id) or "uz"
    if result == "ok":
        await callback.answer(t(lang, "reg_joined_private_from_group"), show_alert=True)
        try:
            await bot.send_message(user.id, t(lang, "reg_joined_private"))
        except TelegramBadRequest:
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


# ---------------- GIVE (reply orqali to'g'ridan-to'g'ri) ----------------

@router.message(Command("give"))
async def cmd_give(message: Message):
    await _try_delete(message)
    lang = await _group_lang(message.chat.id) or "uz"
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
        return  # yetarli almaz bo'lmasa — jim, hech narsa demaydi
    await db.update_balance(giver.id, diamond=-amount)
    await db.update_balance(target.id, diamond=amount)
    await message.answer(
        t(lang, "give_announce",
          giver=mention(giver.id, giver.full_name), amount=amount,
          target=mention(target.id, target.full_name))
    )


@router.message(Command("token"))
async def cmd_token(message: Message):
    await _try_delete(message)
    if not message.reply_to_message:
        return
    parts = message.text.split()
    amount = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    giver = message.from_user
    target = message.reply_to_message.from_user
    await db.get_or_create_user(giver.id, giver.full_name)
    await db.get_or_create_user(target.id, target.full_name)
    giver_data = await db.get_user(giver.id)
    if giver_data["token"] < amount:
        return
    await db.update_balance(giver.id, token=-amount)
    await db.update_balance(target.id, token=amount)
    lang = await _group_lang(message.chat.id) or "uz"
    await message.answer(
        t(lang, "token_give_success",
          giver=mention(giver.id, giver.full_name), amount=amount,
          target=mention(target.id, target.full_name))
    )


# ---------------- CLAIM (olib-qol) tizimi: /giveaway va reply'siz /send ----------------

async def _start_claim(message: Message, bot: Bot, lang: str, giver, column: str,
                        emoji: str, label: str, total_units: int, chunk: int):
    await db.get_or_create_user(giver.id, giver.full_name)
    giver_data = await db.get_user(giver.id)
    if giver_data.get(column, 0) < total_units:
        return  # yetarli emas — jim
    await db._conn.execute(
        f"UPDATE users SET {column} = {column} - ? WHERE user_id=?", (total_units, giver.id)
    )
    await db._conn.commit()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "claim_btn"), callback_data="claim_gift")]
    ])
    item_text = f"{total_units}{emoji}" if column in ("diamond", "money", "token") else f"{total_units} {label}"
    msg = await message.answer(
        t(lang, "claim_giveaway_start", giver=mention(giver.id, giver.full_name),
          amount=total_units, item=f"{label}{emoji}" if label else emoji),
        reply_markup=kb,
    )
    _active_claims[msg.message_id] = {
        "chat_id": message.chat.id,
        "giver_id": giver.id,
        "giver_name": giver.full_name,
        "column": column,
        "emoji": emoji,
        "label": label,
        "remaining": total_units,
        "chunk": chunk,
        "claimed": set(),
        "log": [],
        "lang": lang,
    }


@router.callback_query(F.data == "claim_gift")
async def cb_claim_gift(callback: CallbackQuery, bot: Bot):
    data = _active_claims.get(callback.message.message_id)
    if not data:
        await callback.answer()
        return
    lang = data["lang"]
    user = callback.from_user
    if user.id == data["giver_id"]:
        await callback.answer(t(lang, "claim_self_error"), show_alert=True)
        return
    if user.id in data["claimed"]:
        await callback.answer(t(lang, "claim_already"), show_alert=True)
        return
    if data["remaining"] <= 0:
        await callback.answer()
        return

    await db.get_or_create_user(user.id, user.full_name)
    claim_amount = min(data["chunk"], data["remaining"])
    column = data["column"]
    await db._conn.execute(
        f"UPDATE users SET {column} = {column} + ? WHERE user_id=?", (claim_amount, user.id)
    )
    await db._conn.commit()

    data["remaining"] -= claim_amount
    data["claimed"].add(user.id)
    item_str = f"{data['emoji']}" if column in ("diamond", "money", "token") else f"{data['label']}{data['emoji']}"
    data["log"].append(t(lang, "claim_line", name=mention(user.id, user.full_name),
                          amount=claim_amount, item=item_str))
    await callback.answer("✅")

    list_text = "\n".join(data["log"])
    if data["remaining"] <= 0:
        text = t(lang, "claim_finished_header",
                  giver=mention(data["giver_id"], data["giver_name"]), list=list_text)
        try:
            await callback.message.edit_text(text)
        except TelegramBadRequest:
            pass
        _active_claims.pop(callback.message.message_id, None)
    else:
        total = sum(1 for _ in data["log"]) and (data["remaining"] + sum(data["chunk"] for _ in data["claimed"]))
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "claim_btn"), callback_data="claim_gift")]
        ])
        text = t(lang, "claim_remaining_header",
                 giver=mention(data["giver_id"], data["giver_name"]),
                 total=data["remaining"] + sum(1 for _ in data["claimed"]) * data["chunk"],
                 item=f"{data['label']}{data['emoji']}" if data["label"] else data["emoji"],
                 list=list_text, remaining=data["remaining"])
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except TelegramBadRequest:
            pass


@router.message(Command("giveaway"))
async def cmd_giveaway(message: Message, bot: Bot):
    await _try_delete(message)
    lang = await _group_lang(message.chat.id) or "uz"
    parts = message.text.split()[1:]
    if not parts:
        await message.answer(t(lang, "giveaway_usage2"))
        return

    if len(parts) == 1:
        item_key = "almaz"
        amount_str = parts[0]
    else:
        item_key, amount_str = parts[0].lower(), parts[1]

    if item_key not in ITEM_ALIASES or not amount_str.isdigit():
        await message.answer(t(lang, "giveaway_usage2"))
        return
    amount = int(amount_str)
    if amount <= 0:
        return

    column, emoji, label_key = ITEM_ALIASES[item_key]
    toggle_key = GIVEAWAY_TOGGLE_KEY.get(column)
    if toggle_key:
        settings = await db.get_group_settings(message.chat.id)
        if not settings.get(toggle_key, True):
            await message.answer(t(lang, "giveaway_item_disabled"))
            return

    label = t(lang, label_key) if label_key else ""
    chunk = GIVEAWAY_MONEY_CHUNK if column == "money" else 1
    await _start_claim(message, bot, lang, message.from_user, column, emoji, label, amount, chunk)


@router.message(Command("send"))
async def cmd_send(message: Message, bot: Bot):
    await _try_delete(message)
    lang = await _group_lang(message.chat.id) or "uz"
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(t(lang, "send_usage"))
        return
    amount = int(parts[1])
    giver = message.from_user

    if message.reply_to_message:
        # reply bilan: to'g'ridan-to'g'ri o'sha odamga pul o'tkazish
        target = message.reply_to_message.from_user
        await db.get_or_create_user(giver.id, giver.full_name)
        await db.get_or_create_user(target.id, target.full_name)
        giver_data = await db.get_user(giver.id)
        if giver_data["money"] < amount:
            return
        await db.update_balance(giver.id, money=-amount)
        await db.update_balance(target.id, money=amount)
        await message.answer(
            t(lang, "send_success",
              giver=mention(giver.id, giver.full_name), amount=amount,
              target=mention(target.id, target.full_name))
        )
    else:
        # reply'siz: guruhga pulni bo'lib tarqatish (claim tizimi, 10 dan bo'lib)
        await _start_claim(message, bot, lang, giver, "money", "💵", "", amount, GIVEAWAY_MONEY_CHUNK)


# ---------------- BIRDS (juftlik) ----------------

@router.message(Command("birds"))
async def cmd_birds(message: Message, bot: Bot):
    await _try_delete(message)
    lang = await _group_lang(message.chat.id) or "uz"
    if not message.reply_to_message:
        await message.answer(t(lang, "birds_usage"))
        return
    proposer = message.from_user
    target = message.reply_to_message.from_user
    if proposer.id == target.id:
        await message.answer(t(lang, "birds_cant_self"))
        return
    await db.get_or_create_user(proposer.id, proposer.full_name)
    await db.get_or_create_user(target.id, target.full_name)

    if await db.get_pair(proposer.id) or await db.get_pair(target.id):
        await message.answer(t(lang, "birds_already_paired"))
        return

    _pending_pairs[target.id] = proposer.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "birds_accept_btn"), callback_data=f"birds_yes_{proposer.id}"),
        InlineKeyboardButton(text=t(lang, "birds_decline_btn"), callback_data=f"birds_no_{proposer.id}"),
    ]])
    await message.answer(
        t(lang, "birds_propose_received",
          target=mention(target.id, target.full_name),
          proposer=mention(proposer.id, proposer.full_name)),
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("birds_yes_"))
async def cb_birds_yes(callback: CallbackQuery, bot: Bot):
    proposer_id = int(callback.data.split("_")[-1])
    target = callback.from_user
    lang = await _group_lang(callback.message.chat.id) or "uz"
    # Faqat taklif yuborilgan (target) odam bosishi mumkin — boshqa hech kim emas.
    if _pending_pairs.get(target.id) != proposer_id:
        await callback.answer()
        return
    del _pending_pairs[target.id]
    await db.set_pair(proposer_id, target.id)
    proposer = await db.get_user(proposer_id)
    await callback.message.edit_text(
        t(lang, "birds_accepted_group",
          a=mention(proposer_id, proposer["name"]), b=mention(target.id, target.full_name))
    )
    for uid, partner_name, partner_id in (
        (proposer_id, target.full_name, target.id), (target.id, proposer["name"], proposer_id)
    ):
        try:
            await bot.send_message(uid, t(lang, "birds_accepted_private", partner=mention(partner_id, partner_name)))
        except TelegramBadRequest:
            pass
    await callback.answer()


@router.callback_query(F.data.startswith("birds_no_"))
async def cb_birds_no(callback: CallbackQuery):
    proposer_id = int(callback.data.split("_")[-1])
    target = callback.from_user
    lang = await _group_lang(callback.message.chat.id) or "uz"
    # Faqat taklif yuborilgan (target) odam rad eta oladi.
    if _pending_pairs.get(target.id) != proposer_id:
        await callback.answer()
        return
    del _pending_pairs[target.id]
    proposer = await db.get_user(proposer_id)
    proposer_name = proposer["name"] if proposer else str(proposer_id)
    await callback.message.edit_text(
        t(lang, "birds_declined", a=mention(proposer_id, proposer_name), b=mention(target.id, target.full_name))
    )
    await callback.answer()


@router.message(Command("unbirds"))
async def cmd_unbirds(message: Message):
    await _try_delete(message)
    lang = await _group_lang(message.chat.id) or "uz"
    partner_id = await db.remove_pair(message.from_user.id)
    await message.answer(t(lang, "unbirds_success") if partner_id else t(lang, "unbirds_none"))


@router.message(Command("lovebirds"))
async def cmd_lovebirds(message: Message):
    await _try_delete(message)
    lang = await _group_lang(message.chat.id) or "uz"
    partner_id = await db.get_pair(message.from_user.id)
    if not partner_id:
        await message.answer(t(lang, "lovebirds_none"))
        return
    partner = await db.get_user(partner_id)
    name = partner["name"] if partner else str(partner_id)
    await message.answer(t(lang, "lovebirds_show", name=mention(partner_id, name)))


# ---------------- SETTINGS (faqat guruh admin/owner) ----------------

def _settings_main_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "settings_menu_time"), callback_data="set_cat_time")],
        [InlineKeyboardButton(text=t(lang, "settings_menu_silence"), callback_data="set_cat_silence")],
        [InlineKeyboardButton(text=t(lang, "settings_menu_items"), callback_data="set_cat_items")],
        [InlineKeyboardButton(text=t(lang, "settings_menu_other"), callback_data="set_cat_other")],
    ])


@router.message(Command("settings"))
async def cmd_settings(message: Message, bot: Bot):
    await _try_delete(message)
    lang = await _group_lang(message.chat.id) or "uz"
    if not await _is_group_admin(bot, message.chat.id, message.from_user.id):
        await message.answer(t(lang, "not_owner"))
        return
    await message.answer(t(lang, "settings_menu"), reply_markup=_settings_main_kb(lang))


_TIME_KEYS = ["registration_time", "night_time", "day_time", "vote_time"]
_OTHER_TOGGLE_KEYS = ["auto_pin", "anonymous_vote", "show_roles_on_register", "group_roles_by_side",
                      "skip_day_vote_allowed", "skip_night_allowed", "don_beats_mafia_vote",
                      "leave_allowed", "anyone_can_start_registration", "anyone_can_start_game",
                      "media_messages_allowed", "dead_can_chat", "emojis_enabled"]
_ITEM_TOGGLE_KEYS = ["item_fake_doc_enabled", "item_shield_enabled", "item_mask_enabled",
                     "item_killer_protect_enabled", "item_vote_protect_enabled",
                     "item_gun_enabled", "item_bomb_enabled", "item_adrenaline_enabled"]


@router.callback_query(F.data == "set_cat_time")
async def cb_set_time(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id) or "uz"
    settings = await db.get_group_settings(chat_id)
    lines = [f"{k}: {settings.get(k)}s" for k in _TIME_KEYS]
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="set_back")]])
    await callback.message.edit_text(
        t(lang, "settings_menu_time") + "\n\n" + "\n".join(lines) +
        "\n\nO'zgartirish uchun guruhda: /vaqt <soniya>",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data == "set_cat_silence")
async def cb_set_silence(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id) or "uz"
    settings = await db.get_group_settings(chat_id)
    key = "dead_can_chat"
    value = settings.get(key, False)
    label = f"O'lganlar yoza oladimi: {t(lang, 'settings_on') if value else t(lang, 'settings_off')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"toggle_{key}")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="set_back")],
    ])
    await callback.message.edit_text(t(lang, "settings_menu_silence"), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "set_cat_items")
async def cb_set_items(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id) or "uz"
    settings = await db.get_group_settings(chat_id)
    buttons = []
    for key in _ITEM_TOGGLE_KEYS:
        value = settings.get(key, True)
        label = f"{key.replace('item_', '').replace('_enabled', '')}: {t(lang, 'settings_on') if value else t(lang, 'settings_off')}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"toggle_{key}")])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="set_back")])
    await callback.message.edit_text(t(lang, "settings_menu_items"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "set_cat_other")
async def cb_set_other(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id) or "uz"
    settings = await db.get_group_settings(chat_id)
    buttons = []
    for key in _OTHER_TOGGLE_KEYS:
        value = settings.get(key, False)
        label = f"{key}: {t(lang, 'settings_on') if value else t(lang, 'settings_off')}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"toggle_{key}")])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="set_back")])
    await callback.message.edit_text(t(lang, "settings_menu_other"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_"))
async def cb_toggle_setting(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id) or "uz"
    if not await _is_group_admin(bot, chat_id, callback.from_user.id):
        await callback.answer(t(lang, "not_owner"), show_alert=True)
        return
    key = callback.data.split("_", 1)[1]
    settings = await db.get_group_settings(chat_id)
    new_value = not settings.get(key, False)
    await db.update_group_settings(chat_id, **{key: new_value})
    await callback.answer(t(lang, "settings_saved"))
    if key in _ITEM_TOGGLE_KEYS:
        await cb_set_items(callback)
    elif key == "dead_can_chat":
        await cb_set_silence(callback, bot)
    else:
        await cb_set_other(callback)


@router.callback_query(F.data == "set_back")
async def cb_set_back(callback: CallbackQuery):
    lang = await _group_lang(callback.message.chat.id) or "uz"
    await callback.message.edit_text(t(lang, "settings_menu"), reply_markup=_settings_main_kb(lang))
    await callback.answer()
