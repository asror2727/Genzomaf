import aiosqlite
import json
from config import DB_PATH, DEFAULT_SETTINGS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    lang TEXT DEFAULT 'uz',
    lang_selected INTEGER DEFAULT 0,
    money INTEGER DEFAULT 0,
    diamond INTEGER DEFAULT 0,
    token INTEGER DEFAULT 0,
    shield INTEGER DEFAULT 0,
    killer_protect INTEGER DEFAULT 0,
    vote_protect INTEGER DEFAULT 0,
    gun INTEGER DEFAULT 0,
    mask INTEGER DEFAULT 0,
    fake_doc INTEGER DEFAULT 0,
    bomb INTEGER DEFAULT 0,
    adrenaline INTEGER DEFAULT 0,
    use_shield INTEGER DEFAULT 1,
    use_killer_protect INTEGER DEFAULT 1,
    use_vote_protect INTEGER DEFAULT 1,
    use_mask INTEGER DEFAULT 1,
    use_fake_doc INTEGER DEFAULT 1,
    use_bomb INTEGER DEFAULT 1,
    use_adrenaline INTEGER DEFAULT 1,
    next_role TEXT DEFAULT '-',
    wins INTEGER DEFAULT 0,
    total_games INTEGER DEFAULT 0,
    rating_points INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    period_wins INTEGER DEFAULT 0,
    period_games INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    owner_id INTEGER,
    settings TEXT DEFAULT '{}',
    premium INTEGER DEFAULT 0,
    premium_link TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    kind TEXT,
    amount INTEGER,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pairs (
    user_id INTEGER PRIMARY KEY,
    partner_id INTEGER
);

CREATE TABLE IF NOT EXISTS premium_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link TEXT
);

CREATE TABLE IF NOT EXISTS kv_store (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


_USER_COLUMNS = [
    "user_id", "name", "lang", "lang_selected", "money", "diamond", "token", "shield",
    "killer_protect", "vote_protect", "gun", "mask", "fake_doc",
    "bomb", "adrenaline",
    "use_shield", "use_killer_protect", "use_vote_protect", "use_mask",
    "use_fake_doc", "use_bomb", "use_adrenaline",
    "next_role", "wins", "total_games", "rating_points",
    "xp", "level", "period_wins", "period_games",
]
_USER_COLUMNS_SQL = ", ".join(_USER_COLUMNS)


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        await self._migrate()

    async def _migrate(self):
        """Eski (deploy qilingan) bazada yangi ustunlar bo'lmasa, xato bermasdan qo'shib qo'yadi."""
        new_columns = [
            ("bomb", "INTEGER DEFAULT 0"),
            ("adrenaline", "INTEGER DEFAULT 0"),
            ("use_shield", "INTEGER DEFAULT 1"),
            ("use_killer_protect", "INTEGER DEFAULT 1"),
            ("use_vote_protect", "INTEGER DEFAULT 1"),
            ("use_mask", "INTEGER DEFAULT 1"),
            ("use_fake_doc", "INTEGER DEFAULT 1"),
            ("use_bomb", "INTEGER DEFAULT 1"),
            ("use_adrenaline", "INTEGER DEFAULT 1"),
            ("xp", "INTEGER DEFAULT 0"),
            ("level", "INTEGER DEFAULT 1"),
            ("period_wins", "INTEGER DEFAULT 0"),
            ("period_games", "INTEGER DEFAULT 0"),
        ]
        for col, decl in new_columns:
            try:
                await self._conn.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
                await self._conn.commit()
            except Exception:
                pass  # ustun allaqachon mavjud
        try:
            await self._conn.execute("ALTER TABLE groups ADD COLUMN lang TEXT DEFAULT ''")
            await self._conn.commit()
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE users ADD COLUMN lang_selected INTEGER DEFAULT 0")
            await self._conn.commit()
        except Exception:
            pass

    async def close(self):
        if self._conn:
            await self._conn.close()

    # ---------- USERS ----------
    async def get_or_create_user(self, user_id: int, name: str) -> dict:
        cur = await self._conn.execute(f"SELECT {_USER_COLUMNS_SQL} FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if row is None:
            await self._conn.execute(
                "INSERT INTO users (user_id, name) VALUES (?, ?)", (user_id, name)
            )
            await self._conn.commit()
            cur = await self._conn.execute(f"SELECT {_USER_COLUMNS_SQL} FROM users WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
        elif row[1] != name:
            # Foydalanuvchi ismi Telegram'da o'zgargan bo'lishi mumkin — yangilab qo'yamiz
            await self._conn.execute("UPDATE users SET name=? WHERE user_id=?", (name, user_id))
            await self._conn.commit()
            row = list(row)
            row[1] = name
        return self._row_to_user(row)

    async def set_lang(self, user_id: int, lang: str):
        await self._conn.execute(
            "UPDATE users SET lang=?, lang_selected=1 WHERE user_id=?", (lang, user_id)
        )
        await self._conn.commit()

    async def update_user_name(self, user_id: int, name: str):
        """Ismni yangilaydi (agar foydalanuvchi yo'q bo'lsa yaratadi)."""
        await self.get_or_create_user(user_id, name)

    async def set_next_role(self, user_id: int, role_value: str):
        await self._conn.execute("UPDATE users SET next_role=? WHERE user_id=?", (role_value, user_id))
        await self._conn.commit()

    async def get_lang(self, user_id: int) -> str:
        cur = await self._conn.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else "uz"

    async def get_user(self, user_id: int) -> dict | None:
        cur = await self._conn.execute(f"SELECT {_USER_COLUMNS_SQL} FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return self._row_to_user(row) if row else None

    async def update_balance(self, user_id: int, money=0, diamond=0, token=0):
        await self._conn.execute(
            "UPDATE users SET money = money + ?, diamond = diamond + ?, token = token + ? WHERE user_id=?",
            (money, diamond, token, user_id),
        )
        await self._conn.commit()

    async def add_rating(self, user_id: int, points: int):
        await self._conn.execute(
            "UPDATE users SET rating_points = rating_points + ? WHERE user_id=?",
            (points, user_id),
        )
        await self._conn.commit()

    async def add_game_result(self, user_id: int, won: bool):
        await self._conn.execute(
            "UPDATE users SET total_games = total_games + 1, wins = wins + ?, "
            "period_games = period_games + 1, period_wins = period_wins + ? WHERE user_id=?",
            (1 if won else 0, 1 if won else 0, user_id),
        )
        await self._conn.commit()

    async def add_xp(self, user_id: int, amount: int):
        """XP qo'shadi va kerak bo'lsa levelni oshiradi (har 1000 xp = 1 level)."""
        user = await self.get_user(user_id)
        if not user:
            return
        xp = user["xp"] + amount
        level = user["level"]
        while xp >= level * 1000:
            xp -= level * 1000
            level += 1
        await self._conn.execute(
            "UPDATE users SET xp=?, level=? WHERE user_id=?", (xp, level, user_id)
        )
        await self._conn.commit()

    async def reset_period_stats(self):
        await self._conn.execute("UPDATE users SET period_wins=0, period_games=0")
        await self._conn.commit()

    async def top_weekly_percent(self, limit: int = 20, min_games: int = 3):
        cur = await self._conn.execute(
            "SELECT user_id, name, period_wins, period_games FROM users WHERE period_games >= ?",
            (min_games,),
        )
        rows = await cur.fetchall()
        scored = [
            (uid, name, round(wins / games * 100, 2))
            for uid, name, wins, games in rows if games > 0
        ]
        scored.sort(key=lambda x: x[2], reverse=True)
        return scored[:limit]

    async def toggle_item_use(self, user_id: int, item: str) -> bool:
        """Item yoqish/o'chirish (profildagi ON/OFF tugmasi). Yangi holatni qaytaradi."""
        col = f"use_{item}"
        user = await self.get_user(user_id)
        new_value = 0 if user.get(col, 1) else 1
        await self._conn.execute(f"UPDATE users SET {col}=? WHERE user_id=?", (new_value, user_id))
        await self._conn.commit()
        return bool(new_value)

    async def consume_item(self, user_id: int, item: str) -> bool:
        """Item'dan 1 dona sarflaydi (agar bor bo'lsa). True/False qaytaradi."""
        user = await self.get_user(user_id)
        if not user or user.get(item, 0) < 1:
            return False
        await self._conn.execute(f"UPDATE users SET {item} = {item} - 1 WHERE user_id=?", (user_id,))
        await self._conn.commit()
        return True

    async def top_rating(self, limit: int = 100):
        cur = await self._conn.execute(
            "SELECT user_id, name, rating_points FROM users ORDER BY rating_points DESC LIMIT ?",
            (limit,),
        )
        return await cur.fetchall()

    @staticmethod
    def _row_to_user(row) -> dict:
        return dict(zip(_USER_COLUMNS, row))

    # ---------- GROUPS / SETTINGS ----------
    async def get_group_settings(self, chat_id: int) -> dict:
        cur = await self._conn.execute("SELECT settings, owner_id FROM groups WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        if row is None:
            await self._conn.execute(
                "INSERT INTO groups (chat_id, settings) VALUES (?, ?)",
                (chat_id, json.dumps(DEFAULT_SETTINGS)),
            )
            await self._conn.commit()
            return dict(DEFAULT_SETTINGS)
        settings = dict(DEFAULT_SETTINGS)
        settings.update(json.loads(row[0] or "{}"))
        return settings

    async def set_group_owner(self, chat_id: int, owner_id: int):
        await self.get_group_settings(chat_id)  # ensure row exists
        await self._conn.execute("UPDATE groups SET owner_id=? WHERE chat_id=?", (owner_id, chat_id))
        await self._conn.commit()

    async def get_group_owner(self, chat_id: int) -> int | None:
        cur = await self._conn.execute("SELECT owner_id FROM groups WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return row[0] if row and row[0] else None

    async def get_group_lang(self, chat_id: int) -> str | None:
        await self.get_group_settings(chat_id)  # ensure row exists
        cur = await self._conn.execute("SELECT lang FROM groups WHERE chat_id=?", (chat_id,))
        row = await cur.fetchone()
        return row[0] if row and row[0] else None

    async def set_group_lang(self, chat_id: int, lang: str):
        await self.get_group_settings(chat_id)  # ensure row exists
        await self._conn.execute("UPDATE groups SET lang=? WHERE chat_id=?", (lang, chat_id))
        await self._conn.commit()

    async def all_group_ids(self) -> list[tuple]:
        cur = await self._conn.execute("SELECT chat_id, lang FROM groups")
        return await cur.fetchall()

    async def update_group_settings(self, chat_id: int, **kwargs):
        settings = await self.get_group_settings(chat_id)
        settings.update(kwargs)
        await self._conn.execute(
            "UPDATE groups SET settings=? WHERE chat_id=?", (json.dumps(settings), chat_id)
        )
        await self._conn.commit()

    # ---------- TRANSACTIONS (to'lov cheklari) ----------
    async def create_transaction(self, user_id: int, kind: str, amount: int) -> int:
        cur = await self._conn.execute(
            "INSERT INTO transactions (user_id, kind, amount) VALUES (?, ?, ?)",
            (user_id, kind, amount),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def approve_transaction(self, tx_id: int):
        await self._conn.execute("UPDATE transactions SET status='approved' WHERE id=?", (tx_id,))
        await self._conn.commit()

    async def get_transaction(self, tx_id: int):
        cur = await self._conn.execute("SELECT * FROM transactions WHERE id=?", (tx_id,))
        return await cur.fetchone()

    async def get_last_pending_for_user(self, user_id: int):
        cur = await self._conn.execute(
            "SELECT id, kind, amount FROM transactions WHERE user_id=? AND status='pending' "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        return await cur.fetchone()

    async def pending_transactions(self, limit: int = 20):
        cur = await self._conn.execute(
            "SELECT id, user_id, kind, amount FROM transactions WHERE status='pending' ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        return await cur.fetchall()

    # ---------- PAIRS (juftlik / "para") ----------
    async def get_pair(self, user_id: int) -> int | None:
        cur = await self._conn.execute("SELECT partner_id FROM pairs WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row[0] if row else None

    async def set_pair(self, user_a: int, user_b: int):
        await self._conn.execute(
            "INSERT INTO pairs (user_id, partner_id) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET partner_id=excluded.partner_id",
            (user_a, user_b),
        )
        await self._conn.execute(
            "INSERT INTO pairs (user_id, partner_id) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET partner_id=excluded.partner_id",
            (user_b, user_a),
        )
        await self._conn.commit()

    async def remove_pair(self, user_id: int):
        partner_id = await self.get_pair(user_id)
        await self._conn.execute("DELETE FROM pairs WHERE user_id=?", (user_id,))
        if partner_id:
            await self._conn.execute("DELETE FROM pairs WHERE user_id=?", (partner_id,))
        await self._conn.commit()
        return partner_id

    # ---------- PREMIUM GROUPS ----------
    async def add_premium_group(self, link: str):
        await self._conn.execute("INSERT INTO premium_groups (link) VALUES (?)", (link,))
        await self._conn.commit()

    async def list_premium_groups(self, limit: int = 10):
        cur = await self._conn.execute(
            "SELECT link FROM premium_groups ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]

    # ---------- KV STORE (qoidalar, narxlar va h.k.) ----------
    async def kv_get(self, key: str, default: str = "") -> str:
        cur = await self._conn.execute("SELECT value FROM kv_store WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default

    async def kv_set(self, key: str, value: str):
        await self._conn.execute(
            "INSERT INTO kv_store (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await self._conn.commit()

    async def all_user_ids(self) -> list[int]:
        cur = await self._conn.execute("SELECT user_id FROM users")
        rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def group_top(self, chat_id: int, limit: int = 20):
        """Hozircha guruh ichidagi statistika alohida saqlanmaydi — global reyting qaytariladi.
        Kelajakda group_players jadvali qo'shilib, guruh bo'yicha ajratiladi."""
        return await self.top_rating(limit)


db = Database()
