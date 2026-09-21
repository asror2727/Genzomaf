import os

# .env yoki Render environment variables orqali beriladi
BOT_TOKEN = os.getenv("BOT_TOKEN", "PUT_YOUR_TOKEN_HERE")
OWNER_ID = int(os.getenv("OWNER_ID", "7651404790"))
DB_PATH = os.getenv("DB_PATH", "mafia.db")

# O'yin default sozlamalari (guruh sozlamasi bo'lmasa shular ishlatiladi)
DEFAULT_SETTINGS = {
    "lang": None,  # None = admin hali guruh tilini tanlamagan
    "min_players": 4,
    "max_players": 25,
    "registration_time": 320,   # soniya
    "night_time": 45,
    "day_time": 60,
    "vote_time": 30,
    "confirm_time": 15,     # osish tasdiqlash (like/dislike) vaqti
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
    "mafia_ratio": 4,  # 3 -> har 3-o'yinchidan 1 mafia (ko'proq), 4 -> har 4-o'yinchidan 1 (kamroq)
    "media_messages_allowed": False,
    "dead_can_chat": False,
    "anyone_can_start_registration": True,
    "anyone_can_start_game": False,
    "leave_allowed": True,
    "item_shield_enabled": True,
    "item_killer_protect_enabled": True,
    "item_vote_protect_enabled": True,
    "item_mask_enabled": True,
    "item_fake_doc_enabled": True,
    "item_gun_enabled": True,
    "item_bomb_enabled": True,
    "item_adrenaline_enabled": True,
    "giveaway_diamond_enabled": True,
    "giveaway_money_enabled": True,
    "giveaway_shield_enabled": True,
    "giveaway_mask_enabled": True,
    "giveaway_gun_enabled": True,
    "giveaway_fake_doc_enabled": True,
}

CHANNEL_USERNAME = "genzomafiauz"
PAYMENT_CARD = "8600 1234 5678 9012"

# Do'kon narxlari: (miqdor, valyuta) — valyuta "diamond" yoki "money"
SHOP_ITEMS = {
    "fake_doc": (220, "money"),
    "shield": (90, "money"),
    "mask": (2, "diamond"),
    "gun": (3, "diamond"),
    "killer_protect": (3, "diamond"),
    "vote_protect": (2, "diamond"),
    "bomb": (5, "diamond"),
    "adrenaline": (5, "diamond"),
}

# Orqaga moslik uchun (eski kod joylarida ishlatilishi mumkin)
SHOP_ITEM_PRICES = {k: v[0] for k, v in SHOP_ITEMS.items()}

# Rol oldindan sotib olish narxi (almazda)
ROLE_PURCHASE_PRICE = 5

# Almaz sotib olish paketlari: {miqdor: narx (so'mda)}
DIAMOND_PACKAGES = {1: 1000, 10: 9000}

# Pulga konvertatsiya qilinadigan almaz miqdorlari (200 pul = 1 almaz)
MONEY_CONVERSION_RATE = 200  # 1 almaz = 200 pul
MONEY_CONVERT_OPTIONS = [1, 5, 10, 50]

# Genzo tokenni reyting balliga almashtirish kursi
TOKEN_TO_RATING_RATE = 152  # 1 token = 152 ball

# Ro'yxatdan o'tish vaqti uchun tugmalarda ko'rsatiladigan tayyor variantlar (soniya)
TIME_PRESETS = [30, 45, 60, 75, 90, 120, 180, 240, 300, 360]
MAX_PLAYERS_OPTIONS = list(range(15, 31))

# Giveaway'da pul turi uchun necha kishiga bo'lib beriladi (chunk)
GIVEAWAY_MONEY_CHUNK = 10

