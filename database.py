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
            used BOOLEAN DEFAULT FALSE
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS purchases(
            id SERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            price INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS promocodes(
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            discount_type TEXT NOT NULL,
            discount_value INTEGER NOT NULL,
            max_uses INTEGER NOT NULL,
            used_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE
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
            bonus_value INTEGER NOT NULL
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
            user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
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
        INSERT INTO referral_config (bonus_type, bonus_value) VALUES ('rubles', 0) ON CONFLICT DO NOTHING
        """)
        
        await conn.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('shop_mode', 'auto') ON CONFLICT (key) DO NOTHING
        """)
        
        await conn.execute("""
        INSERT INTO bot_settings (key, value) VALUES ('custom_text', '⏳ Автоматические продажи временно отключены. Пожалуйста, напишите администратору @nikita1055 для ручной покупки ключа.') ON CONFLICT (key) DO NOTHING
        """)
        
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN has_purchased BOOLEAN DEFAULT FALSE")
        except:
            pass

async def get_setting(key: str) -> str:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT value FROM bot_settings WHERE key = $1", key)

async def update_setting(key: str, value: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bot_settings (key, value) VALUES ($1, $2) 
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, key, value)

async def add_user(user_id: int, referrer_id: int = None):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users(user_id, referrer_id) VALUES($1, $2) ON CONFLICT (user_id) DO NOTHING",
            user_id, referrer_id
        )

async def get_referrer(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT referrer_id FROM users WHERE user_id = $1", user_id)

async def get_referrals_count(user_id: int) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id = $1", user_id) or 0

async def get_paid_referrals_count(user_id: int) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users WHERE referrer_id = $1 AND has_purchased = TRUE", user_id) or 0

async def mark_purchased(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET has_purchased = TRUE WHERE user_id = $1", user_id)

async def has_user_purchased(user_id: int) -> bool:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT has_purchased FROM users WHERE user_id = $1", user_id) or False

async def get_referral_config():
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT bonus_type, bonus_value FROM referral_config LIMIT 1")

async def update_referral_config(bonus_type: str, bonus_value: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE referral_config SET bonus_type = $1, bonus_value = $2", bonus_type, bonus_value)

async def get_balance(user_id: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1", user_id)
        return row["balance"] if row else 0

async def update_user_balance(user_id: int, new_balance: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = $1 WHERE user_id = $2", new_balance, user_id)

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
        return await conn.fetch("SELECT id, key_value, used FROM keys_store WHERE product_id = $1 ORDER BY id", product_id)

async def delete_key(key_id: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM keys_store WHERE id = $1", key_id)

async def get_unused_key(product_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT id, key_value FROM keys_store WHERE product_id = $1 AND used = FALSE LIMIT 1", product_id)

async def mark_key_as_used(key_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE keys_store SET used = TRUE WHERE id = $1", key_id)

async def add_purchase(user_id: int, product_id: int, price: int):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO purchases (user_id, product_id, price) VALUES ($1, $2, $3)", user_id, product_id, price)

async def get_user_purchases(user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetch("""
            SELECT p.id, pr.name, p.price, p.created_at 
            FROM purchases p
            JOIN products pr ON p.product_id = pr.id
            WHERE p.user_id = $1
            ORDER BY p.created_at DESC
        """, user_id)

async def get_stats():
    async with pool.acquire() as conn:
        users = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_sales = await conn.fetchval("SELECT COALESCE(SUM(price), 0) FROM purchases")
        keys_sold = await conn.fetchval("SELECT COUNT(*) FROM keys_store WHERE used = TRUE")
        products_count = await conn.fetchval("SELECT COUNT(*) FROM products")
        keys_left = await conn.fetchval("SELECT COUNT(*) FROM keys_store WHERE used = FALSE")
        return {"users": users, "total_sales": total_sales, "keys_sold": keys_sold, "products_count": products_count, "keys_left": keys_left}

async def get_all_users():
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT user_id FROM users")

async def create_promocode(code: str, discount_type: str, discount_value: int, max_uses: int):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO promocodes (code, discount_type, discount_value, max_uses) VALUES ($1, $2, $3, $4)", code, discount_type, discount_value, max_uses)

async def get_promocode(code: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM promocodes WHERE code = $1 AND is_active = TRUE AND used_count < max_uses", code)

async def use_promocode(user_id: int, promocode_id: int):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO promocode_uses (user_id, promocode_id) VALUES ($1, $2)", user_id, promocode_id)
        await conn.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE id = $1", promocode_id)

async def check_promocode_used(user_id: int, promocode_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id FROM promocode_uses WHERE user_id = $1 AND promocode_id = $2", user_id, promocode_id)
        return row is not None

async def get_all_promocodes():
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM promocodes ORDER BY id DESC")

async def delete_promocode(promocode_id: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM promocodes WHERE id = $1", promocode_id)

async def create_manual_order(user_id: int, product_id: int, amount: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO manual_orders (user_id, product_id, amount) VALUES ($1, $2, $3) RETURNING id",
            user_id, product_id, amount
        )
        return row["id"]

async def get_manual_order(order_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM manual_orders WHERE id = $1", order_id)

async def update_manual_order_status(order_id: int, status: str):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE manual_orders SET status = $1 WHERE id = $2", status, order_id)

async def get_pending_manual_orders():
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT mo.*, p.name as product_name FROM manual_orders mo "
            "JOIN products p ON mo.product_id = p.id "
            "WHERE mo.status = 'pending' ORDER BY mo.created_at DESC"
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
