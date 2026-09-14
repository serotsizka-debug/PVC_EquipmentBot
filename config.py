import os
from zoneinfo import ZoneInfo

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "pvc_bot.sqlite3")
TIMEZONE = ZoneInfo("Europe/Kyiv")

WORK_START_HOUR = 11
WORK_END_HOUR = 17
TIME_STEP_MINUTES = 30
MIN_BOOKING_DAYS = 3
