import asyncio
import random
import time
from enum import Enum

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from database import db
from i18n import t
from game.roles import (
    Role, distribute_roles, ROLE_LOCALE_KEY, ROLE_DESC_KEY, ROLE_SIDE, check_winner,
)

NPC_NAMES = [
    "Eagle", "Dust", "Falcon", "Shadow", "Ghost", "Wolf", "Tiger", "Cobra",
    "Raven", "Viper", "Storm", "Blaze", "Rex", "Nomad", "Phantom", "Hunter",
]


def mention(user_id: int, name: str, is_bot: bool = False) -> str:
    """Foydalanuvchi nomini bosiladigan (profilga o'tadigan) havola qilib qaytaradi."""
    safe_name = name.replace("<", "").replace(">", "")
    if is_bot:
        return f"🤖 {safe_name}"
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'


class Phase(str, Enum):
    REGISTRATION = "registration"
    NIGHT = "night"
    DAY = "day"
    VOTE = "vote"
    FINISHED = "finished"


class Player:
    def __init__(self, user_id: int, name: str, is_bot: bool = False):
        self.user_id = user_id
        self.name = name
        self.alive = True
        self.role: Role | None = None
        self.is_bot = is_bot

    def mention(self) -> str:
        return mention(self.user_id, self.name, self.is_bot)


class Game:
    def __init__(self, chat_id: int, settings: dict, lang: str = "uz"):
        self.chat_id = chat_id
        self.settings = settings
        self.lang = lang
        self.phase = Phase.REGISTRATION
        self.players: dict[int, Player] = {}
        self.reg_message_id: int | None = None
        self.day_number = 0
        self.started_at: float | None = None
        self.night_actions: dict[str, dict[int, int]] = {}  # role_name -> {actor: target}
        self.votes: dict[int, int] = {}  # voter -> target
        self.lock = asyncio.Lock()
        self._reg_task: asyncio.Task | None = None
        self._night_task: asyncio.Task | None = None
        self._vote_task: asyncio.Task | None = None
        self._next_npc_id = -1

    def alive_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive]

    def alive_roles(self) -> dict[int, Role]:
        return {p.user_id: p.role for p in self.alive_players()}

    def format_alive_list(self) -> str:
        lines = [f"{i+1}. {p.mention()}" for i, p in enumerate(self.alive_players())]
        return "\n".join(lines)

    def new_npc_id(self) -> int:
        npc_id = self._next_npc_id
        self._next_npc_id -= 1
        return npc_id


class GameManager:
    """Barcha guruhlardagi faol o'yinlarni boshqaradi."""

    def __init__(self):
        self.games: dict[int, Game] = {}

    def has_active(self, chat_id: int) -> bool:
        return chat_id in self.games

    def get(self, chat_id: int) -> Game | None:
        return self.games.get(chat_id)

    # ---------------- REGISTRATION ----------------

    async def start_registration(self, bot: Bot, chat_id: int, lang: str):
        settings = await db.get_group_settings(chat_id)
        game = Game(chat_id, settings, lang)
        self.games[chat_id] = game

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "reg_join_btn"), callback_data="reg_join")]
        ])
        text = t(lang, "reg_started", players="-", count=0)
        msg = await bot.send_message(chat_id, text, reply_markup=kb)
        game.reg_message_id = msg.message_id
        # Birinchi ochilishda PIN qilinmaydi — faqat /game qayta bosilganda (repost_registration) pin bo'ladi.

        game._reg_task = asyncio.create_task(
            self._registration_timeout(bot, chat_id, settings.get("registration_time", 320))
        )

    async def _registration_timeout(self, bot: Bot, chat_id: int, seconds: int):
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.REGISTRATION:
            return
        if len(game.players) < game.settings.get("min_players", 4):
            await bot.send_message(chat_id, t(game.lang, "reg_not_enough"))
            await self._unpin(bot, game)
            self.games.pop(chat_id, None)
        # yetarli bo'lsa — owner/admin /start bosishini kutadi (avto boshlanmaydi)

    async def extend_registration(self, bot: Bot, chat_id: int, seconds: int) -> bool:
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.REGISTRATION:
            return False
        if game._reg_task and not game._reg_task.done():
            game._reg_task.cancel()
        game._reg_task = asyncio.create_task(
            self._registration_timeout(bot, chat_id, seconds)
        )
        return True

    async def add_player(self, bot: Bot, chat_id: int, user_id: int, name: str) -> str:
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.REGISTRATION:
            return "no_active"
        async with game.lock:
            if user_id in game.players:
                return "already"
            if len(game.players) >= game.settings.get("max_players", 30):
                return "full"
            game.players[user_id] = Player(user_id, name)
        await self._refresh_registration_message(bot, game)
        return "ok"

    async def add_npc_players(self, bot: Bot, chat_id: int, count: int) -> list[str]:
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.REGISTRATION:
            return []
        added_names = []
        async with game.lock:
            available_names = [n for n in NPC_NAMES if n not in {p.name for p in game.players.values()}]
            random.shuffle(available_names)
            for i in range(count):
                if len(game.players) >= game.settings.get("max_players", 30):
                    break
                name = available_names[i] if i < len(available_names) else f"Bot{-game._next_npc_id}"
                npc_id = game.new_npc_id()
                game.players[npc_id] = Player(npc_id, name, is_bot=True)
                added_names.append(name)
        await self._refresh_registration_message(bot, game)
        return added_names

    async def repost_registration(self, bot: Bot, chat_id: int):
        """/game qayta bosilganda: eski ro'yxat xabarini unpin+o'chirib, xuddi shu ro'yxatni
        (mavjud o'yinchilar bilan) pastga qayta joylaydi va pin qiladi."""
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.REGISTRATION:
            return False
        old_message_id = game.reg_message_id
        if old_message_id:
            try:
                await bot.unpin_chat_message(chat_id, old_message_id)
            except TelegramBadRequest:
                pass
            try:
                await bot.delete_message(chat_id, old_message_id)
            except TelegramBadRequest:
                pass

        names = ", ".join(p.mention() for p in game.players.values()) or "-"
        text = t(game.lang, "reg_started", players=names, count=len(game.players))
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(game.lang, "reg_join_btn"), callback_data="reg_join")]
        ])
        msg = await bot.send_message(chat_id, text, reply_markup=kb)
        game.reg_message_id = msg.message_id
        if game.settings.get("auto_pin", True):
            try:
                await bot.pin_chat_message(chat_id, msg.message_id, disable_notification=True)
            except TelegramBadRequest:
                pass
        return True

    async def _refresh_registration_message(self, bot: Bot, game: Game):
        names = ", ".join(p.mention() for p in game.players.values()) or "-"
        text = t(game.lang, "reg_started", players=names, count=len(game.players))
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(game.lang, "reg_join_btn"), callback_data="reg_join")]
        ])
        try:
            await bot.edit_message_text(
                text, chat_id=game.chat_id, message_id=game.reg_message_id, reply_markup=kb
            )
        except TelegramBadRequest:
            pass

    async def try_force_start(self, bot: Bot, chat_id: int) -> bool:
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.REGISTRATION:
            return False
        if len(game.players) < game.settings.get("min_players", 4):
            return False
        if game._reg_task and not game._reg_task.done():
            game._reg_task.cancel()
        await self._unpin(bot, game)
        await self._begin_game(bot, game)
        return True

    async def _unpin(self, bot: Bot, game: Game):
        try:
            await bot.unpin_chat_message(game.chat_id, game.reg_message_id)
        except TelegramBadRequest:
            pass

    # ---------------- STOP / LEAVE ----------------

    async def stop_game(self, bot: Bot, chat_id: int) -> bool:
        """/stop — istalgan fazadagi o'yin yoki ro'yxatni to'xtatadi va tozalaydi."""
        game = self.games.pop(chat_id, None)
        if not game:
            return False
        for task in (game._reg_task, game._night_task, game._vote_task):
            if task and not task.done():
                task.cancel()
        if game.reg_message_id:
            await self._unpin(bot, game)
        return True

    async def leave_player(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        game = self.games.get(chat_id)
        if not game or user_id not in game.players:
            return False
        if game.phase == Phase.REGISTRATION:
            del game.players[user_id]
            await self._refresh_registration_message(bot, game)
        else:
            player = game.players[user_id]
            player.alive = False
            winner = check_winner(game.alive_roles())
            if winner:
                await self._finish_game(bot, game, winner)
        return True

    # ---------------- GAME START / ROLE ASSIGNMENT ----------------

    async def _begin_game(self, bot: Bot, game: Game):
        game.phase = Phase.NIGHT
        game.started_at = time.time()
        game.day_number = 0

        mafia_ratio = game.settings.get("mafia_ratio", 4)
        role_list = distribute_roles(len(game.players), mafia_ratio)
        players_list = list(game.players.values())

        # Rol sotib olgan (next_role) o'yinchilarga, agar shu rol ro'yxatda mavjud bo'lsa, ustunlik beriladi
        remaining_roles = list(role_list)
        remaining_players = []
        for player in players_list:
            if not player.is_bot:
                preferred = await self._consume_role_preference(player.user_id)
                if preferred and preferred in remaining_roles:
                    player.role = preferred
                    remaining_roles.remove(preferred)
                    continue
            remaining_players.append(player)
        random.shuffle(remaining_roles)
        for player, role in zip(remaining_players, remaining_roles):
            player.role = role

        await bot.send_message(game.chat_id, t(game.lang, "game_start_announce"))

        for player in game.players.values():
            if player.is_bot:
                continue
            role_name = t(game.lang, ROLE_LOCALE_KEY[player.role])
            desc = t(game.lang, ROLE_DESC_KEY[player.role])
            try:
                await bot.send_message(
                    player.user_id, t(game.lang, "you_are_role", role=role_name, description=desc)
                )
            except TelegramBadRequest:
                pass

        await self._run_night(bot, game)

    async def _consume_role_preference(self, user_id: int) -> Role | None:
        """Foydalanuvchi oldindan sotib olgan rolini (agar bo'lsa) qaytaradi va DB'dan tozalaydi
        (bir martalik — keyingi o'yinga saqlanib qolmaydi)."""
        user = await db.get_user(user_id)
        if not user or not user.get("next_role") or user["next_role"] == "-":
            return None
        try:
            role = Role(user["next_role"])
        except ValueError:
            role = None
        await db._conn.execute("UPDATE users SET next_role='-' WHERE user_id=?", (user_id,))
        await db._conn.commit()
        return role

    # ---------------- NIGHT ----------------

    async def _run_night(self, bot: Bot, game: Game):
        game.phase = Phase.NIGHT
        game.day_number += 1
        game.night_actions = {}

        await bot.send_message(game.chat_id, t(game.lang, "night_intro"))
        alive = game.alive_players()
        await bot.send_message(
            game.chat_id,
            t(game.lang, "alive_players_header", players=game.format_alive_list(), count=len(alive)),
        )

        night_roles = {Role.DON: "night_don_choose", Role.DOCTOR: "night_doctor_choose",
                       Role.COMMISSIONER: "night_commissioner_choose"}

        pending = []
        for player in alive:
            if player.role not in night_roles:
                continue
            if player.is_bot:
                self._npc_night_action(game, player)
            else:
                pending.append(self._send_night_choice(bot, game, player, night_roles[player.role]))
        if pending:
            await asyncio.gather(*pending)

        try:
            game._night_task = asyncio.current_task()
            await asyncio.sleep(game.settings.get("night_time", 45))
        except asyncio.CancelledError:
            return
        await self._resolve_night(bot, game)

    def _npc_night_action(self, game: Game, npc: Player):
        """Bot (NPC) o'yinchi tungi harakatini avtomatik, tasodifiy tanlaydi."""
        targets = [p for p in game.alive_players() if p.user_id != npc.user_id]
        if not targets:
            return
        target = random.choice(targets)
        game.night_actions.setdefault(npc.role.value, {})[npc.user_id] = target.user_id

    async def _send_night_choice(self, bot: Bot, game: Game, player: Player, prompt_key: str):
        targets = [p for p in game.alive_players() if p.user_id != player.user_id]
        buttons = [
            [InlineKeyboardButton(text=p.name, callback_data=f"night_{player.role.value}_{p.user_id}")]
            for p in targets
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        try:
            await bot.send_message(player.user_id, t(game.lang, prompt_key), reply_markup=kb)
        except TelegramBadRequest:
            pass

    def register_night_action(self, chat_id: int, role: str, actor: int, target: int):
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.NIGHT:
            return
        game.night_actions.setdefault(role, {})[actor] = target

    # ---------------- ITEM EFFEKTLARI (Himoya, Maska, Bomba, Adrenalin) ----------------

    async def _try_use_disguise(self, target: "Player") -> bool:
        """Komissar tekshiruvida Maska yoki Soxta hujjat orqali yashirinish (mafiya bo'lsa ham
        natija 'tinch' ko'rinadi). Item 1 donaga kamayadi."""
        if target.is_bot:
            return False
        user = await db.get_user(target.user_id)
        if not user:
            return False
        if user.get("use_mask") and user.get("mask", 0) > 0:
            await db.consume_item(target.user_id, "mask")
            return True
        if user.get("use_fake_doc") and user.get("fake_doc", 0) > 0:
            await db.consume_item(target.user_id, "fake_doc")
            return True
        return False

    async def _try_use_life_save(self, victim: "Player") -> bool:
        """Tunda o'ldirilayotgan o'yinchida Himoya yoki Qotildan himoya bo'lsa, hayoti saqlanadi."""
        if victim.is_bot:
            return False
        user = await db.get_user(victim.user_id)
        if not user:
            return False
        if user.get("use_shield") and user.get("shield", 0) > 0:
            await db.consume_item(victim.user_id, "shield")
            return True
        if user.get("use_killer_protect") and user.get("killer_protect", 0) > 0:
            await db.consume_item(victim.user_id, "killer_protect")
            return True
        return False

    async def _try_use_bomb(self, victim: "Player") -> bool:
        user = await db.get_user(victim.user_id)
        if not user:
            return False
        if user.get("use_bomb") and user.get("bomb", 0) > 0:
            await db.consume_item(victim.user_id, "bomb")
            return True
        return False

    async def _try_use_vote_protection(self, target: "Player") -> bool:
        """Osilish arafasida Ovoz berishdan himoya (yoki Don bo'lsa Adrenalin) ishlatiladi."""
        if target.is_bot:
            return False
        user = await db.get_user(target.user_id)
        if not user:
            return False
        if target.role == Role.DON and user.get("use_adrenaline") and user.get("adrenaline", 0) > 0:
            await db.consume_item(target.user_id, "adrenaline")
            return True
        if user.get("use_vote_protect") and user.get("vote_protect", 0) > 0:
            await db.consume_item(target.user_id, "vote_protect")
            return True
        return False

    async def _try_use_bomb_on_vote(self, target: "Player", game: "Game") -> int | None:
        """Osilgan o'yinchida bomba bo'lsa, unga ovoz bergan birontasini ham o'zi bilan olib ketadi."""
        user = await db.get_user(target.user_id)
        if not user or not (user.get("use_bomb") and user.get("bomb", 0) > 0):
            return None
        voters = [uid for uid, t_id in game.votes.items() if t_id == target.user_id and uid != target.user_id]
        alive_voters = [uid for uid in voters if game.players.get(uid) and game.players[uid].alive]
        if not alive_voters:
            return None
        await db.consume_item(target.user_id, "bomb")
        chosen = random.choice(alive_voters)
        game.players[chosen].alive = False
        return chosen

    async def _resolve_night(self, bot: Bot, game: Game):
        # Vaqtida javob bermagan faol rollarga (Don/Doktor/Komissar) avtomatik tasodifiy
        # tanlov beriladi — aks holda hech kim harakat qilmasa o'yin cheksiz davom etib qolardi.
        night_roles = {Role.DON, Role.DOCTOR, Role.COMMISSIONER}
        for player in game.alive_players():
            if player.role not in night_roles:
                continue
            role_actions = game.night_actions.setdefault(player.role.value, {})
            if player.user_id not in role_actions:
                targets = [p for p in game.alive_players() if p.user_id != player.user_id]
                if targets:
                    role_actions[player.user_id] = random.choice(targets).user_id

        don_targets = game.night_actions.get(Role.DON.value, {})
        doctor_targets = game.night_actions.get(Role.DOCTOR.value, {})
        commissioner_targets = game.night_actions.get(Role.COMMISSIONER.value, {})

        killed_id = next(iter(don_targets.values()), None)
        saved_ids = set(doctor_targets.values())

        for actor, target in commissioner_targets.items():
            target_player = game.players.get(target)
            if not target_player:
                continue
            actor_player = game.players.get(actor)
            if actor_player and actor_player.is_bot:
                continue
            is_mafia = ROLE_SIDE.get(target_player.role) == "mafia"
            disguised = is_mafia and await self._try_use_disguise(target_player)
            if is_mafia and not disguised:
                await self._safe_send(bot, actor, t(game.lang, "commissioner_result_mafia", name=target_player.name))
            else:
                await self._safe_send(bot, actor, t(game.lang, "commissioner_result_clean", name=target_player.name))

        died_player = None
        killer_died_by_bomb = False
        if killed_id and killed_id not in saved_ids:
            victim = game.players.get(killed_id)
            if victim and victim.alive:
                survived = await self._try_use_life_save(victim)
                if not survived:
                    victim.alive = False
                    died_player = victim
                    # Bomba: agar qurbonda faol bomba bo'lsa, o'ldirgan Don ham o'ladi
                    if not victim.is_bot and await self._try_use_bomb(victim):
                        for don_id in don_targets.keys():
                            don_player = game.players.get(don_id)
                            if don_player and don_player.alive:
                                don_player.alive = False
                                killer_died_by_bomb = True
                                break

        game.phase = Phase.DAY
        await bot.send_message(game.chat_id, t(game.lang, "day_intro", day=game.day_number))
        await bot.send_message(
            game.chat_id,
            t(game.lang, "alive_players_header", players=game.format_alive_list(),
              count=len(game.alive_players())),
        )

        if died_player:
            killer_role_name = t(game.lang, ROLE_LOCALE_KEY[Role.DON])
            await bot.send_message(
                game.chat_id,
                t(game.lang, "died_announce", name=died_player.mention(), killer_role=killer_role_name),
            )
            if killer_died_by_bomb:
                await bot.send_message(game.chat_id, t(game.lang, "bomb_exploded", name=died_player.mention()))
        else:
            await bot.send_message(game.chat_id, t(game.lang, "no_one_died"))

        winner = check_winner(game.alive_roles())
        if winner:
            await self._finish_game(bot, game, winner)
            return

        try:
            await asyncio.sleep(game.settings.get("day_time", 60))
        except asyncio.CancelledError:
            return
        await self._start_vote(bot, game)

    async def _safe_send(self, bot: Bot, user_id: int, text: str, **kwargs):
        try:
            await bot.send_message(user_id, text, **kwargs)
        except TelegramBadRequest:
            pass

    # ---------------- VOTE ----------------

    async def _start_vote(self, bot: Bot, game: Game):
        game.phase = Phase.VOTE
        game.votes = {}

        # NPC'lar darhol tasodifiy ovoz beradi
        for npc in [p for p in game.alive_players() if p.is_bot]:
            targets = [p for p in game.alive_players() if p.user_id != npc.user_id]
            if targets:
                game.votes[npc.user_id] = random.choice(targets).user_id

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(game.lang, "vote_btn"), callback_data="open_vote")]
        ])
        await bot.send_message(game.chat_id, t(game.lang, "vote_start"), reply_markup=kb)
        try:
            game._vote_task = asyncio.current_task()
            await asyncio.sleep(game.settings.get("vote_time", 30))
        except asyncio.CancelledError:
            return
        await self._resolve_vote(bot, game)

    async def open_vote_menu(self, bot: Bot, chat_id: int, user_id: int):
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.VOTE:
            return
        voter = game.players.get(user_id)
        if not voter or not voter.alive:
            return
        targets = [p for p in game.alive_players() if p.user_id != user_id]
        buttons = [
            [InlineKeyboardButton(text=p.name, callback_data=f"votefor_{p.user_id}")]
            for p in targets
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await self._safe_send(bot, user_id, t(game.lang, "vote_choose"), reply_markup=kb)

    async def register_vote(self, bot: Bot, chat_id: int, voter_id: int, target_id: int):
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.VOTE:
            return
        game.votes[voter_id] = target_id
        voter = game.players[voter_id]
        target = game.players[target_id]
        if not game.settings.get("anonymous_vote", False):
            await bot.send_message(
                chat_id, t(game.lang, "vote_cast_announce", voter=voter.mention(), target=target.mention())
            )

    async def _resolve_vote(self, bot: Bot, game: Game):
        tally: dict[int, int] = {}
        for target in game.votes.values():
            tally[target] = tally.get(target, 0) + 1

        if not tally:
            await bot.send_message(game.chat_id, t(game.lang, "vote_tie"))
        else:
            max_votes = max(tally.values())
            top = [uid for uid, v in tally.items() if v == max_votes]
            if len(top) > 1:
                await bot.send_message(game.chat_id, t(game.lang, "vote_tie"))
            else:
                hanged = game.players[top[0]]
                protected = await self._try_use_vote_protection(hanged)
                if protected:
                    await bot.send_message(game.chat_id, t(game.lang, "vote_protected", name=hanged.mention()))
                else:
                    hanged.alive = False
                    role_name = t(game.lang, ROLE_LOCALE_KEY[hanged.role])
                    await bot.send_message(
                        game.chat_id, t(game.lang, "vote_hanged", name=hanged.mention(), role=role_name)
                    )
                    exploded_on = await self._try_use_bomb_on_vote(hanged, game)
                    if exploded_on:
                        victim2 = game.players[exploded_on]
                        await bot.send_message(
                            game.chat_id, t(game.lang, "bomb_exploded", name=victim2.mention())
                        )

        winner = check_winner(game.alive_roles())
        if winner:
            await self._finish_game(bot, game, winner)
            return

        await self._run_night(bot, game)

    # ---------------- GAME END ----------------

    async def _finish_game(self, bot: Bot, game: Game, winner_side: str):
        game.phase = Phase.FINISHED
        winners = [p for p in game.players.values() if ROLE_SIDE[p.role] == winner_side]
        losers = [p for p in game.players.values() if ROLE_SIDE[p.role] != winner_side]

        winners_text = "\n".join(
            f"{i+1}. {p.mention()} — {t(game.lang, ROLE_LOCALE_KEY[p.role])}" for i, p in enumerate(winners)
        ) or "-"
        losers_text = "\n".join(
            f"{i+1}. {p.mention()} — {t(game.lang, ROLE_LOCALE_KEY[p.role])}" for i, p in enumerate(losers)
        ) or "-"
        minutes = max(1, int((time.time() - game.started_at) / 60))

        await bot.send_message(
            game.chat_id,
            t(game.lang, "game_over", winners=winners_text, losers=losers_text, minutes=minutes),
        )

        reward = game.settings.get("win_reward_money", 100)
        rating = game.settings.get("rating_points_per_game", 5)
        for p in game.players.values():
            if p.is_bot:
                continue
            won = p in winners
            await db.add_game_result(p.user_id, won)
            await db.add_rating(p.user_id, rating)
            if won:
                await db.update_balance(p.user_id, money=reward)
                await db.add_xp(p.user_id, 50)

        self.games.pop(game.chat_id, None)


manager = GameManager()
