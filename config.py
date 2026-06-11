"""Конфигурация бота. Все настройки берутся из файла .env рядом с этим файлом."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --- Telegram ---
BOT_TOKEN = os.environ["BOT_TOKEN"]  # обязательный
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ALLOWED_USER_IDS = {
    int(x) for x in os.getenv("ALLOWED_USER_IDS", "").replace(" ", "").split(",") if x
}
if ADMIN_ID:
    ALLOWED_USER_IDS.add(ADMIN_ID)

# --- Email (дайджест). Если GMAIL_FROM/GMAIL_APP_PASSWORD пустые — email отключён ---
EMAIL_TO = os.getenv("EMAIL_TO", "")
GMAIL_FROM = os.getenv("GMAIL_FROM", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# --- Фоновый мониторинг: раз в N минут. 0 = выключить (только кнопки) ---
WATCH_INTERVAL_MIN = int(os.getenv("WATCH_INTERVAL_MIN", "30"))

# --- Кнессет: статус «закон принят» (KNS_Bill.StatusID). При необходимости поменять ---
LAW_STATUS_ID = int(os.getenv("LAW_STATUS_ID", "118"))

# --- База для отслеживания уже виденных новостей ---
DB_PATH = str(BASE_DIR / "seen.sqlite3")
