import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
DB_URL = os.getenv("DB_URL")
RAILWAY_URL = os.getenv("RAILWAY_URL")
CHANNEL_ID = -1003709565134

PLATEGA_MERCHANT_ID = os.getenv("PLATEGA_MERCHANT_ID", "709e8d20-e5f9-4ad0-8bae-311460ff7991")
PLATEGA_API_SECRET = os.getenv("PLATEGA_API_SECRET", "b4gxyG1yLHYrz3AvG0QEOjxw5BuKaWie3JkP3p25ExhEX6AFLbf2ZqPMWGFWgpSXtgsrGYTjsXh7KEF8tDHdxLAvFW6XCNqG7xJ2")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")

if DB_URL:
    DB_URL = DB_URL.replace("postgresql+asyncpg://", "postgresql://")
