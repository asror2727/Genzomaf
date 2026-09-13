import asyncio
import random
import time
from enum import Enum

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from database import db
from i18n import t
from config import DEFAULT_SETTINGS
from game.roles import (
    Role, distribute_roles, ROLE_LOCALE_KEY, ROLE_DESC_KEY, ROLE_SIDE, check_winner,
)


class Phase(str, Enum):
    REGISTRATION = "registration"
    NIGHT = "night"
    DAY = "day"
    VOTE = "vote"
    FINISHED = "finished"


class Player:
    def __init__(self, user_id: int, name: str):
        self.user_id = user_id
        self.name = name
        self.alive = True
        self.role: Role | None = None


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
        self._phase_task: asyncio.Task | None = None

    def alive_players(self) -> list[Player]:
        return [p for p in self.players.values() if p.alive]

    def alive_roles(self) -> dict[int, Role]:
        return {p.user_id: p.role for p in self.alive_players()}

    def format_alive_list(self) -> str:
        lines = [f"{i+1}. {p.name}" for i, p in enumerate(self.alive_players())]
        return "\n".join(lines)


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

        if settings.get("auto_pin", True):
            try:
                await bot.pin_chat_message(chat_id, msg.message_id, disable_notification=True)
            except TelegramBadRequest:
                pass

        game._reg_task = asyncio.create_task(
            self._registration_timeout(bot, chat_id, settings.get("registration_time", 320))
        )

    async def _registration_timeout(self, bot: Bot, chat_id: int, seconds: int):
        await asyncio.sleep(seconds)
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.REGISTRATION:
            return
        if len(game.players) < game.settings.get("min_players", 4):
            await bot.send_message(chat_id, t(game.lang, "reg_not_enough"))
            await self._unpin(bot, game)
            del self.games[chat_id]
        # yetarli bo'lsa — owner/admin /start bosishini kutadi (avto boshlanmaydi)

    async def add_player(self, bot: Bot, chat_id: int, user_id: int, name: str) -> str:
        """Callback bosilganda chaqiriladi. Natija matnini qaytaradi (guruhga yozish uchun kerak emas,
        chunki xabar tahrirlanadi)."""
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

    async def _refresh_registration_message(self, bot: Bot, game: Game):
        names = ", ".join(p.name for p in game.players.values()) or "-"
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
        """/start bosilganda chaqiriladi — yetarli odam bo'lsa o'yinni boshlaydi."""
        game = self.games.get(chat_id)
        if not game or game.phase != Phase.REGISTRATION:
            return False
        if len(game.players) < game.settings.get("min_players", 4):
            return False
        if game._reg_task:
            game._reg_task.cancel()
        await self._unpin(bot, game)
        await self._begin_game(bot, game)
        return True

    async def _unpin(self, bot: Bot, game: Game):
        try:
            await bot.unpin_chat_message(game.chat_id, game.reg_message_id)
        except TelegramBadRequest:
            pass

    # ---------------- GAME START / ROLE ASSIGNMENT ----------------

    async def _begin_game(self, bot: Bot, game: Game):
        game.phase = Phase.NIGHT
        game.started_at = time.time()
        game.day_number = 0

        role_list = distribute_roles(len(game.players))
        for player, role in zip(game.players.values(), role_list):
            player.role = role

        await bot.send_message(game.chat_id, t(game.lang, "game_start_announce"))

        # rollarni private'da yuborish
        for player in game.players.values():
            role_name = t(game.lang, ROLE_LOCALE_KEY[player.role])
            desc = t(game.lang, ROLE_DESC_KEY[player.role])
            try:
                await bot.send_message(
                    player.user_id, t(game.lang, "you_are_role", role=role_name, description=desc)
                )
            except TelegramBadRequest:
                pass  # foydalanuvchi botni bloklagan bo'lishi mumkin

        await self._run_night(bot, game)

    # ---------------- NIGHT ----------------

    async def _run_night(self, bot: Bot, game: Game):
        game.phase = Phase.NIGHT
        game.day_number += 1
        game.night_actions = {}

        await bot.send_message(game.chat_id, t(game.lang, "night_intro"))
        alive = game.alive_players()
        count_line = self._alive_count_summary(game)
        await bot.send_message(
            game.chat_id,
            t(game.lang, "alive_players_header", players=game.format_alive_list(), count=count_line),
        )

        # har bir tungi rolga ega tirik o'yinchiga tanlov yuboriladi
        night_roles = {Role.DON: "night_don_choose", Role.DOCTOR: "night_doctor_choose",
                       Role.COMMISSIONER: "night_commissioner_choose"}
        pending = []
        for player in alive:
            if player.role in night_roles:
                pending.append(self._send_night_choice(bot, game, player, night_roles[player.role]))
        if pending:
            await asyncio.gather(*pending)

        await asyncio.sleep(game.settings.get("night_time", 45))
        await self._resolve_night(bot, game)

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

    async def _resolve_night(self, bot: Bot, game: Game):
        don_targets = game.night_actions.get(Role.DON.value, {})
        doctor_targets = game.night_actions.get(Role.DOCTOR.value, {})
        commissioner_targets = game.night_actions.get(Role.COMMISSIONER.value, {})

        killed_id = next(iter(don_targets.values()), None)
        saved_ids = set(doctor_targets.values())

        # komissar natijasini xabar qilish
        for actor, target in commissioner_targets.items():
            target_player = game.players.get(target)
            if not target_player:
                continue
            if ROLE_SIDE.get(target_player.role) == "mafia":
                await self._safe_send(bot, actor, t(game.lang, "commissioner_result_mafia", name=target_player.name))
            else:
                await self._safe_send(bot, actor, t(game.lang, "commissioner_result_clean", name=target_player.name))

        died_player = None
        if killed_id and killed_id not in saved_ids:
            victim = game.players.get(killed_id)
            if victim and victim.alive:
                victim.alive = False
                died_player = victim

        game.phase = Phase.DAY
        await bot.send_message(
            game.chat_id, t(game.lang, "day_intro", day=game.day_number)
        )
        await bot.send_message(
            game.chat_id,
            t(game.lang, "alive_players_header", players=game.format_alive_list(),
              count=self._alive_count_summary(game)),
        )

        if died_player:
            killer_role_name = t(game.lang, ROLE_LOCALE_KEY[Role.DON])
            await bot.send_message(
                game.chat_id,
                t(game.lang, "died_announce", name=died_player.name, killer_role=killer_role_name),
            )
        else:
            await bot.send_message(game.chat_id, t(game.lang, "no_one_died"))

        winner = check_winner(game.alive_roles())
        if winner:
            await self._finish_game(bot, game, winner)
            return

        await asyncio.sleep(game.settings.get("day_time", 60))
        await self._start_vote(bot, game)

    def _alive_count_summary(self, game: Game) -> str:
        return str(len(game.alive_players()))

    async def _safe_send(self, bot: Bot, user_id: int, text: str, **kwargs):
        try:
            await bot.send_message(user_id, text, **kwargs)
        except TelegramBadRequest:
            pass

    # ---------------- VOTE ----------------

    async def _start_vote(self, bot: Bot, game: Game):
        game.phase = Phase.VOTE
        game.votes = {}
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(game.lang, "vote_btn"), callback_data="open_vote")]
        ])
        await bot.send_message(game.chat_id, t(game.lang, "vote_start"), reply_markup=kb)
        await asyncio.sleep(game.settings.get("vote_time", 30))
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
        voter_name = game.players[voter_id].name
        target_name = game.players[target_id].name
        if not game.settings.get("anonymous_vote", False):
            await bot.send_message(
                chat_id, t(game.lang, "vote_cast_announce", voter=voter_name, target=target_name)
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
                hanged.alive = False
                role_name = t(game.lang, ROLE_LOCALE_KEY[hanged.role])
                await bot.send_message(
                    game.chat_id, t(game.lang, "vote_hanged", name=hanged.name, role=role_name)
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
            f"{i+1}. {p.name} — {t(game.lang, ROLE_LOCALE_KEY[p.role])}" for i, p in enumerate(winners)
        ) or "-"
        losers_text = "\n".join(
            f"{i+1}. {p.name} — {t(game.lang, ROLE_LOCALE_KEY[p.role])}" for i, p in enumerate(losers)
        ) or "-"
        minutes = int((time.time() - game.started_at) / 60)

        await bot.send_message(
            game.chat_id,
            t(game.lang, "game_over", winners=winners_text, losers=losers_text, minutes=minutes),
        )

        reward = game.settings.get("win_reward_money", 100)
        rating = game.settings.get("rating_points_per_game", 5)
        for p in game.players.values():
            won = p in winners
            await db.add_game_result(p.user_id, won)
            await db.add_rating(p.user_id, rating)
            if won:
                await db.update_balance(p.user_id, money=reward)

        del self.games[game.chat_id]


manager = GameManager()
