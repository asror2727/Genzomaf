import aiosqlite

async def init_db():
    async with aiosqlite.connect("mafia_bot.db") as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                lang TEXT DEFAULT 'uz',
                money INTEGER DEFAULT 0,
                diamond INTEGER DEFAULT 0,
                genzo_token INTEGER DEFAULT 0,
                score INTEGER DEFAULT 0,
                wins INTEGER DEFAULT 0,
                games INTEGER DEFAULT 0,
                shield INTEGER DEFAULT 0,
                gun INTEGER DEFAULT 0,
                mask INTEGER DEFAULT 0,
                fake_doc INTEGER DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                chat_id INTEGER PRIMARY KEY,
                reg_time INTEGER DEFAULT 320,
                night_time INTEGER DEFAULT 45,
                day_time INTEGER DEFAULT 30,
                vote_time INTEGER DEFAULT 30,
                max_players INTEGER DEFAULT 30,
                group_roles INTEGER DEFAULT 1,
                auto_pin INTEGER DEFAULT 1
            )
        ''')
        await db.commit()

async def add_user(user_id, username, full_name):
    async with aiosqlite.connect("mafia_bot.db") as db:
        await db.execute('''
            INSERT OR IGNORE INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, full_name))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect("mafia_bot.db") as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone()
