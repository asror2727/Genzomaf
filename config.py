import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "8218949042:AAGrMoAgIrHEddRIAP_q-635Z8f1yjfdaA8")
BOT_USERNAME = os.getenv("BOT_USERNAME", "genzomafiabot")  # @ belgisiz yozing
ADMIN_ID = int(os.getenv("ADMIN_ID", "7651404790"))  # Telegram ID ingiz
