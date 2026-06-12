import asyncpg
from config import DB_URL

pool = None

async def connect_db():
    global pool
    pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
    
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id BIGINT PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            referrer_id BIGINT DEFAULT NULL,
            has_purchased BOOLEAN DEFAULT FALSE
        )
        """)
        
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            price INTEGER NOT NULL
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS keys_store(
            id SERIAL PRIMARY KEY,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            key_value TEXT NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            used_by BIGINT DEFAULT NULL,
            used_at TIMESTAMP DEFAULT NULL
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS purchases(
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            product_name TEXT NOT NULL,
            price INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS promocodes(
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            value INTEGER NOT NULL,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            expires_at TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS promocode_uses(
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            promocode_id INTEGER REFERENCES promocodes(id) ON DELETE CASCADE,
            used_at TIMESTAMP DEFAULT NOW()
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS referral_config(
            id SERIAL PRIMARY KEY,
            bonus_type TEXT NOT NULL,
            bonus_value INTEGER NOT NULL,
            enabled BOOLEAN DEFAULT TRUE
        )
        """)
        
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS manual_orders(
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_orders(
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            order_id TEXT NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)
        
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_purchased_products(
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            product_id INTEGER NOT NULL,
            purchased_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, product_id)
        )
        """)
        
        await conn.execute("""
        INSERT INTO referral_config (bonus_type, bonus_value, enabled) VALUES ('rubles', 0, TRUE) ON CONFLICT DO NOTHING
        """)
        
        await conn.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('shop_mode', 'auto') ON CONFLICT (key) DO NOTHING
        """)
        
        await conn.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('custom_payment_text', 'Переведите сумму на карту и отправьте скриншот чека') ON CONFLICT (key) DO NOTHING
        """)
        
        await conn.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('crypto_fee', '0') ON CONFLICT (key) DO NOTHING
        """)
        
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN has_purchased BOOLEAN DEFAULT FALSE")
        except:
            pass
        
        try:
            await conn.execute("ALTER TABLE keys_store ADD COLUMN used_by BIGINT DEFAULT NULL")
        except:
            pass
        
        try:
            await conn.execute("ALTER TABLE keys_store ADD COLUMN used_at TIMESTAMP DEFAULT NULL")
        except:
            pass
        
        try:
            await conn.execute("ALTER TABLE purchases ALTER COLUMN product_name TYPE TEXT")
        except:
            pass

async def get_setting(key: str) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchval("SELECT value FROM bot_settings WHERE key = $1", key)
        return row

async def update_setting(key: str, value: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bot_settings (key, value) VALUES ($1, $2) 
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, key, value)

async def get_crypto_fee() -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchval("SELECT value FROM bot_settings WHERE key = 'crypto_fee'")
        if row:
            return int(row)
        return 0

async def set_crypto_fee(fee: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bot_settings (key, value) VALUES ('crypto_fee', $1)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, str(fee))

async def add_user(user_id: int, referrer_id: int = None):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users(user_id, referrer_id) VALUES($1, $2) ON CONFLICT (user_id) DO NOTHING",
            user_id, referrer_id
        )

async def get_balance(user_id: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
        return row["balance"] if row else 0

async def update_user_balance(user_id: int, amount_change: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount_change, user_id)

async def add_balance(user_id: int, amount: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, user_id)

async def get_all_products():
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT id, name, price FROM products ORDER BY id")

async def get_product_by_id(product_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT id, name, price FROM products WHERE id = $1", product_id)

async def add_product(name: str, price: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("INSERT INTO products (name, price) VALUES ($1, $2) RETURNING id", name, price)
        return row["id"]

async def delete_product(product_id: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM products WHERE id = $1", product_id)

async def add_keys_to_product(product_id: int, keys_list: list):
    async with pool.acquire() as conn:
        for key in keys_list:
            if key.strip():
                await conn.execute("INSERT INTO keys_store (product_id, key_value) VALUES ($1, $2)", product_id, key.strip())

async def get_keys_by_product(product_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT id, key_value, used, used_by FROM keys_store WHERE product_id = $1 ORDER BY id", product_id)

async def delete_key(key_id: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM keys_store WHERE id = $1", key_id)

async def get_unused_key(product_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT id, key_value FROM keys_store WHERE product_id = $1 AND used = FALSE LIMIT 1", product_id)

async def mark_key_as_used(key_id: int, user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE keys_store SET used = TRUE, used_by = $1, used_at = NOW() 
            WHERE id = $2
        """, user_id, key_id)

async def add_purchase(user_id: int, product_name: str, price: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO purchases (user_id, product_name, price) VALUES ($1, $2, $3)", 
            user_id, product_name, price
        )

async def get_user_purchases(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT id, product_name, price, created_at 
            FROM purchases 
            WHERE user_id = $1
            ORDER BY created_at DESC
        """, user_id)

async def get_stats():
    async with pool.acquire() as conn:
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_sales = await conn.fetchval("SELECT COALESCE(SUM(price), 0) FROM purchases")
        total_keys_sold = await conn.fetchval("SELECT COUNT(*) FROM keys_store WHERE used = TRUE")
        total_promocodes = await conn.fetchval("SELECT COUNT(*) FROM promocodes")
        total_referrals = await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id IS NOT NULL")
        
        return {
            "total_users": total_users,
            "total_sales": total_sales,
            "total_keys_sold": total_keys_sold,
            "total_promocodes": total_promocodes,
            "total_referrals": total_referrals
        }

async def get_all_users():
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id FROM users")

async def create_promocode(code: str, bonus_type: str, bonus_value: int, max_uses: int = None):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO promocodes (code, type, value, max_uses) VALUES ($1, $2, $3, $4)", 
            code, bonus_type, bonus_value, max_uses
        )

async def get_promocode(code: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM promocodes WHERE code = $1", code)

async def use_promocode(user_id: int, code: str):
    async with pool.acquire() as conn:
        promo = await conn.fetchrow("SELECT id FROM promocodes WHERE code = $1", code)
        if promo:
            await conn.execute(
                "INSERT INTO promocode_uses (user_id, promocode_id) VALUES ($1, $2)", 
                user_id, promo["id"]
            )
            await conn.execute(
                "UPDATE promocodes SET used_count = used_count + 1 WHERE id = $1", 
                promo["id"]
            )

async def check_promocode_used(user_id: int, code: str):
    async with pool.acquire() as conn:
        result = await conn.fetchval("""
            SELECT COUNT(*) FROM promocode_uses pu
            JOIN promocodes p ON pu.promocode_id = p.id
            WHERE pu.user_id = $1 AND p.code = $2
        """, user_id, code)
        return result > 0

async def get_all_promocodes():
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM promocodes ORDER BY id DESC")

async def delete_promocode(code: str):
    async with pool.acquire() as conn:
        promo = await conn.fetchrow("SELECT id FROM promocodes WHERE code = $1", code)
        if promo:
            await conn.execute("DELETE FROM promocode_uses WHERE promocode_id = $1", promo["id"])
            await conn.execute("DELETE FROM promocodes WHERE id = $1", promo["id"])

async def get_referrer(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT referrer_id FROM users WHERE user_id = $1", user_id)

async def get_referrals_count(user_id: int) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id = $1", user_id) or 0

async def get_paid_referrals_count(user_id: int) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE referrer_id = $1 AND has_purchased = TRUE", 
            user_id
        ) or 0

async def get_referral_config():
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT bonus_type, bonus_value, enabled FROM referral_config LIMIT 1")

async def update_referral_config(key: str, value):
    async with pool.acquire() as conn:
        if key == "enabled":
            await conn.execute("UPDATE referral_config SET enabled = $1", value)
        elif key == "bonus_type":
            await conn.execute("UPDATE referral_config SET bonus_type = $1", value)
        elif key == "bonus_value":
            await conn.execute("UPDATE referral_config SET bonus_value = $1", value)

async def mark_purchased(user_id: int, product_id: int = None):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET has_purchased = TRUE WHERE user_id = $1", user_id)
        if product_id:
            await conn.execute("""
                INSERT INTO user_purchased_products (user_id, product_id) 
                VALUES ($1, $2) ON CONFLICT DO NOTHING
            """, user_id, product_id)

async def has_user_purchased(user_id: int, product_id: int = None) -> bool:
    async with pool.acquire() as conn:
        if product_id:
            result = await conn.fetchval("""
                SELECT COUNT(*) FROM user_purchased_products 
                WHERE user_id = $1 AND product_id = $2
            """, user_id, product_id)
            return result > 0
        else:
            return await conn.fetchval("SELECT has_purchased FROM users WHERE user_id = $1", user_id) or False

async def create_manual_order(user_id: int, amount: int, status: str = "pending") -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO manual_orders (user_id, amount, status) VALUES ($1, $2, $3) RETURNING id",
            user_id, amount, status
        )
        return row["id"]

async def get_manual_order(order_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM manual_orders WHERE id = $1", order_id)

async def update_manual_order_status(order_id: int, status: str) -> bool:
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE manual_orders SET status = $1 WHERE id = $2", 
            status, order_id
        )
        return result == "UPDATE 1"

async def get_pending_manual_orders():
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM manual_orders WHERE status = 'pending' ORDER BY created_at DESC"
        )

async def save_pending_order(user_id: int, order_id: str, amount: int):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pending_orders (user_id, order_id, amount) VALUES ($1, $2, $3)",
            user_id, order_id, amount
        )

async def get_pending_order(order_id: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM pending_orders WHERE order_id = $1 AND status = 'pending'", order_id)

async def update_order_status(order_id: str, status: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE pending_orders SET status = $1 WHERE order_id = $2", status, order_id)
