import os

# .env yoki Render environment variables orqali beriladi
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
OWNER_ID = int(os.getenv("OWNER_ID", "7651404790"))
DB_PATH = os.getenv("DB_PATH", "mafia.db")

# O'yin default sozlamalari (guruh sozlamasi bo'lmasa shular ishlatiladi)
DEFAULT_SETTINGS = {
    "min_players": 4,
    "max_players": 30,
    "registration_time": 320,   # soniya
    "night_time": 45,
    "day_time": 60,
    "vote_time": 30,
    "last_word_time": 20,
    "auto_pin": True,
    "anonymous_vote": False,
    "show_roles_on_register": False,
    "group_roles_by_side": False,
    "skip_day_vote_allowed": False,
    "skip_night_allowed": False,
    "don_beats_mafia_vote": True,
    "emojis_enabled": True,
    "win_reward_money": 100,
    "rating_points_per_game": 5,
}

CHANNEL_USERNAME = "genzomafiauz"
PAYMENT_CARD = "8600 1234 5678 9012"

# Do'kon narxlari (almazda)
SHOP_ITEM_PRICES = {
    "shield": 2,
    "mask": 2,
    "gun": 3,
    "fake_doc": 2,
}

# Almaz sotib olish paketlari: {miqdor: narx (so'mda)}
DIAMOND_PACKAGES = {1: 1000, 10: 9000}

# Pulga konvertatsiya qilinadigan almaz miqdorlari (200 pul = 1 almaz)
MONEY_CONVERSION_RATE = 200  # 1 almaz = 200 pul
MONEY_CONVERT_OPTIONS = [1, 5, 10, 50]
