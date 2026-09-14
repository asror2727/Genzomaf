import asyncio
import random

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, ADMINISTRATOR
from aiogram.exceptions import TelegramBadRequest

from database import db
from i18n import t
from game.engine import manager, mention
from config import OWNER_ID

router = Router()
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
router.callback_query.filter(F.message.chat.type.in_({"group", "supergroup"}))

# Kutilayotgan juftlik takliflari: proposer_id -> target_id (vaqtinchalik, xotirada)
_pending_pairs: dict[int, int] = {}

# Faol giveaway'lar: message_id -> {"chat_id", "giver_id", "amount", "participants": set, "lang"}
_active_giveaways: dict[int, dict] = {}


async def _group_lang(chat_id: int) -> str:
    # Hozircha guruh darajasida til alohida saqlanmaydi — default uz.
    # (Kelajakda groups jadvaliga lang ustuni qo'shilishi mumkin.)
    return "uz"


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
async def on_bot_promoted(event: ChatMemberUpdated):
    await db.set_group_owner(event.chat.id, event.from_user.id)
    lang = await _group_lang(event.chat.id)
    await event.bot.send_message(event.chat.id, t(lang, "admin_bonus_granted"))


# ---------------- GAME LIFECYCLE ----------------

@router.message(Command("game"))
async def cmd_game(message: Message, bot: Bot):
    chat_id = message.chat.id
    lang = await _group_lang(chat_id)
    if manager.has_active(chat_id):
        await message.answer(t(lang, "reg_already_active"))
        return
    await manager.start_registration(bot, chat_id, lang)


@router.message(Command("start"))
async def cmd_start_group(message: Message, bot: Bot):
    chat_id = message.chat.id
    lang = await _group_lang(chat_id)
    if not manager.has_active(chat_id):
        await manager.start_registration(bot, chat_id, lang)
        return
    started = await manager.try_force_start(bot, chat_id)
    if not started:
        await message.answer(t(lang, "reg_already_active"))


@router.message(Command("stop"))
async def cmd_stop(message: Message, bot: Bot):
    chat_id = message.chat.id
    lang = await _group_lang(chat_id)
    # Guruh admin/owner yoki bot owneri to'xtata oladi
    member = await bot.get_chat_member(chat_id, message.from_user.id)
    is_admin = member.status in ("administrator", "creator")
    if not (is_admin or message.from_user.id == OWNER_ID):
        await message.answer(t(lang, "not_owner"))
        return
    stopped = await manager.stop_game(bot, chat_id)
    await message.answer(t(lang, "stop_success") if stopped else t(lang, "stop_no_active"))


@router.message(Command("leave"))
async def cmd_leave(message: Message, bot: Bot):
    chat_id = message.chat.id
    lang = await _group_lang(chat_id)
    ok = await manager.leave_player(bot, chat_id, message.from_user.id)
    await message.answer(t(lang, "leave_success") if ok else t(lang, "leave_not_in_game"))


@router.message(Command("vaqt"))
async def cmd_vaqt(message: Message, bot: Bot):
    chat_id = message.chat.id
    lang = await _group_lang(chat_id)
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(t(lang, "vaqt_usage"))
        return
    seconds = int(parts[1])
    ok = await manager.extend_registration(bot, chat_id, seconds)
    if ok:
        await message.answer(t(lang, "vaqt_extended", sec=seconds))
    else:
        await message.answer(t(lang, "vaqt_no_active"))


@router.message(Command("top"))
async def cmd_top(message: Message):
    lang = await _group_lang(message.chat.id)
    rows = await db.group_top(message.chat.id, 20)
    if not rows:
        await message.answer(t(lang, "top_empty"))
        return
    lines = [f"#{i+1} {mention(uid, name)} — {points} ball" for i, (uid, name, points) in enumerate(rows)]
    await message.answer(t(lang, "top_header", list="\n".join(lines)))


@router.message(Command("qoida"))
async def cmd_qoida_group(message: Message):
    lang = await _group_lang(message.chat.id)
    text = await db.kv_get("rules", "")
    await message.answer(text or t(lang, "qoida_default"))


# ---------------- REGISTRATION JOIN ----------------

@router.callback_query(F.data == "reg_join")
async def cb_reg_join(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user = callback.from_user
    await db.get_or_create_user(user.id, user.full_name)
    result = await manager.add_player(bot, chat_id, user.id, user.full_name)
    lang = await _group_lang(chat_id)
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


# ---------------- GIVE / SEND / TOKEN ----------------

@router.message(Command("give"))
async def cmd_give(message: Message):
    lang = await _group_lang(message.chat.id)
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
          giver=mention(giver.id, giver.full_name),
          amount=amount,
          target=mention(target.id, target.full_name))
    )


@router.message(Command("send"))
async def cmd_send(message: Message):
    lang = await _group_lang(message.chat.id)
    if not message.reply_to_message:
        await message.answer(t(lang, "send_usage"))
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(t(lang, "send_usage"))
        return
    amount = int(parts[1])
    giver = message.from_user
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
          giver=mention(giver.id, giver.full_name),
          amount=amount,
          target=mention(target.id, target.full_name))
    )


@router.message(Command("token"))
async def cmd_token(message: Message):
    lang = await _group_lang(message.chat.id)
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
    await message.answer(
        t(lang, "token_give_success",
          giver=mention(giver.id, giver.full_name),
          amount=amount,
          target=mention(target.id, target.full_name))
    )


# ---------------- GIVEAWAY ----------------

@router.message(Command("giveaway"))
async def cmd_giveaway(message: Message, bot: Bot):
    lang = await _group_lang(message.chat.id)
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(t(lang, "giveaway_usage"))
        return
    amount = int(parts[1])
    giver = message.from_user
    await db.get_or_create_user(giver.id, giver.full_name)
    giver_data = await db.get_user(giver.id)
    if giver_data["diamond"] < amount:
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "giveaway_join_btn"), callback_data="ga_join")]
    ])
    msg = await message.answer(
        t(lang, "giveaway_start", giver=mention(giver.id, giver.full_name), amount=amount),
        reply_markup=kb,
    )
    _active_giveaways[msg.message_id] = {
        "chat_id": message.chat.id,
        "giver_id": giver.id,
        "amount": amount,
        "participants": [],
        "lang": lang,
    }
    await db.update_balance(giver.id, diamond=-amount)  # oldindan yechib qo'yiladi
    asyncio.create_task(_resolve_giveaway(bot, msg.message_id, seconds=60))


@router.callback_query(F.data == "ga_join")
async def cb_giveaway_join(callback: CallbackQuery):
    data = _active_giveaways.get(callback.message.message_id)
    if not data:
        await callback.answer()
        return
    user = callback.from_user
    await db.get_or_create_user(user.id, user.full_name)
    if user.id not in [p[0] for p in data["participants"]]:
        data["participants"].append((user.id, user.full_name))
    await callback.answer("✅")


async def _resolve_giveaway(bot: Bot, message_id: int, seconds: int):
    await asyncio.sleep(seconds)
    data = _active_giveaways.pop(message_id, None)
    if not data:
        return
    lang = data["lang"]
    participants = data["participants"]
    if not participants:
        await bot.send_message(data["chat_id"], t(lang, "giveaway_no_participants"))
        await db.update_balance(data["giver_id"], diamond=data["amount"])  # qaytarib berish
        return
    winners = random.sample(participants, min(10, len(participants)))
    each = max(1, data["amount"] // len(winners))
    lines = []
    for i, (uid, name) in enumerate(winners):
        await db.update_balance(uid, diamond=each)
        lines.append(f"{i+1}. {mention(uid, name)} — {each}💎")
    await bot.send_message(data["chat_id"], t(lang, "giveaway_winners_header", list="\n".join(lines)))


# ---------------- MYPARA (juftlik) ----------------

@router.message(Command("mypara"))
async def cmd_mypara(message: Message, bot: Bot):
    lang = await _group_lang(message.chat.id)
    if not message.reply_to_message:
        await message.answer(t(lang, "mypara_usage"))
        return
    proposer = message.from_user
    target = message.reply_to_message.from_user
    if proposer.id == target.id:
        await message.answer(t(lang, "mypara_cant_self"))
        return
    await db.get_or_create_user(proposer.id, proposer.full_name)
    await db.get_or_create_user(target.id, target.full_name)

    if await db.get_pair(proposer.id) or await db.get_pair(target.id):
        await message.answer(t(lang, "mypara_already_paired"))
        return

    _pending_pairs[target.id] = proposer.id
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "mypara_accept_btn"), callback_data=f"para_yes_{proposer.id}"),
        InlineKeyboardButton(text=t(lang, "mypara_decline_btn"), callback_data=f"para_no_{proposer.id}"),
    ]])
    await message.answer(
        t(lang, "mypara_propose_received", from_name=mention(proposer.id, proposer.full_name)),
        reply_markup=kb,
    )
    await message.answer(t(lang, "mypara_propose_sent"))


@router.callback_query(F.data.startswith("para_yes_"))
async def cb_para_yes(callback: CallbackQuery):
    proposer_id = int(callback.data.split("_")[-1])
    target = callback.from_user
    lang = await _group_lang(callback.message.chat.id)
    if _pending_pairs.get(target.id) != proposer_id:
        await callback.answer()
        return
    del _pending_pairs[target.id]
    await db.set_pair(proposer_id, target.id)
    proposer = await db.get_user(proposer_id)
    await callback.message.edit_text(
        t(lang, "mypara_accepted", a=mention(proposer_id, proposer["name"]), b=mention(target.id, target.full_name))
    )
    await callback.answer()


@router.callback_query(F.data.startswith("para_no_"))
async def cb_para_no(callback: CallbackQuery):
    proposer_id = int(callback.data.split("_")[-1])
    target = callback.from_user
    lang = await _group_lang(callback.message.chat.id)
    if _pending_pairs.get(target.id) == proposer_id:
        del _pending_pairs[target.id]
    await callback.message.edit_text(t(lang, "mypara_declined"))
    await callback.answer()


@router.message(Command("parauzish"))
async def cmd_parauzish(message: Message):
    lang = await _group_lang(message.chat.id)
    partner_id = await db.remove_pair(message.from_user.id)
    await message.answer(t(lang, "parauzish_success") if partner_id else t(lang, "parauzish_none"))


@router.message(Command("parakorish"))
async def cmd_parakorish(message: Message):
    lang = await _group_lang(message.chat.id)
    partner_id = await db.get_pair(message.from_user.id)
    if not partner_id:
        await message.answer(t(lang, "parakorish_none"))
        return
    partner = await db.get_user(partner_id)
    name = partner["name"] if partner else str(partner_id)
    await message.answer(t(lang, "parakorish_show", name=mention(partner_id, name)))


# ---------------- SETTINGS (faqat guruh egasi) ----------------

def _settings_main_kb(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "settings_menu_time"), callback_data="set_cat_time")],
        [InlineKeyboardButton(text=t(lang, "settings_menu_silence"), callback_data="set_cat_silence")],
        [InlineKeyboardButton(text=t(lang, "settings_menu_items"), callback_data="set_cat_items")],
        [InlineKeyboardButton(text=t(lang, "settings_menu_other"), callback_data="set_cat_other")],
    ])


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


@router.message(Command("settings"))
async def cmd_settings(message: Message, bot: Bot):
    lang = await _group_lang(message.chat.id)
    if not await _is_group_admin(bot, message.chat.id, message.from_user.id):
        await message.answer(t(lang, "not_owner"))
        return
    await message.answer(t(lang, "settings_menu"), reply_markup=_settings_main_kb(lang))


_TIME_KEYS = ["registration_time", "night_time", "day_time", "vote_time"]
_TOGGLE_KEYS = ["auto_pin", "anonymous_vote", "show_roles_on_register", "group_roles_by_side",
                "skip_day_vote_allowed", "skip_night_allowed", "don_beats_mafia_vote"]


@router.callback_query(F.data == "set_cat_time")
async def cb_set_time(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id)
    settings = await db.get_group_settings(chat_id)
    buttons = [
        [InlineKeyboardButton(text=f"{k}: {settings.get(k)}s", callback_data=f"noop")]
        for k in _TIME_KEYS
    ]
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="set_back")])
    await callback.message.edit_text(
        t(lang, "settings_menu_time") + "\n\n(Vaqtni o'zgartirish uchun guruhda /vaqt <soniya> ishlatilsin, "
        "yoki bu qiymatlar keyingi versiyada shu yerdan +/- tugmalari bilan sozlanadi.)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "set_cat_silence")
async def cb_set_silence(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="set_back")]
    ])
    await callback.message.edit_text(t(lang, "settings_menu_silence"), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "set_cat_items")
async def cb_set_items(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="set_back")]
    ])
    await callback.message.edit_text(t(lang, "settings_menu_items"), reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data == "set_cat_other")
async def cb_set_other(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id)
    settings = await db.get_group_settings(chat_id)
    buttons = []
    for key in _TOGGLE_KEYS:
        value = settings.get(key, False)
        label = f"{key}: {t(lang, 'settings_on') if value else t(lang, 'settings_off')}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"toggle_{key}")])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="set_back")])
    await callback.message.edit_text(t(lang, "settings_menu_other"), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_"))
async def cb_toggle_setting(callback: CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    lang = await _group_lang(chat_id)
    if not await _is_group_admin(bot, chat_id, callback.from_user.id):
        await callback.answer(t(lang, "not_owner"), show_alert=True)
        return
    key = callback.data.split("_", 1)[1]
    settings = await db.get_group_settings(chat_id)
    new_value = not settings.get(key, False)
    await db.update_group_settings(chat_id, **{key: new_value})
    await callback.answer(t(lang, "settings_saved"))
    # menyuni yangilash
    await cb_set_other(callback)


@router.callback_query(F.data == "set_back")
async def cb_set_back(callback: CallbackQuery):
    lang = await _group_lang(callback.message.chat.id)
    await callback.message.edit_text(t(lang, "settings_menu"), reply_markup=_settings_main_kb(lang))
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()
