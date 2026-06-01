import sqlite3
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_file="bot_db.sqlite"):
        self.connection = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self._init_tables()
    
    def _init_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0,
                subscription_type TEXT,
                subscription_end TEXT,
                registered_at TEXT,
                is_admin INTEGER DEFAULT 0
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscription_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_code TEXT UNIQUE,
                subscription_type TEXT,
                duration_days INTEGER,
                is_used INTEGER DEFAULT 0,
                used_by INTEGER,
                created_at TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                subscription_type TEXT,
                duration_days INTEGER,
                status TEXT,
                payment_id TEXT,
                created_at TEXT
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                review_text TEXT,
                rating INTEGER,
                created_at TEXT,
                is_approved INTEGER DEFAULT 0
            )
        """)
        
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS activations_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                key_code TEXT,
                subscription_type TEXT,
                activated_at TEXT
            )
        """)
        
        self.connection.commit()
    
    def add_user(self, user_id, username):
        is_admin = 1 if user_id in [1302493787, 6784034490] else 0
        self.cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, registered_at, is_admin) VALUES (?, ?, ?, ?)",
            (user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), is_admin)
        )
        self.connection.commit()
    
    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return result
    
    def activate_subscription(self, user_id, sub_type, days):
        current_user = self.get_user(user_id)
        
        if current_user is None:
            return datetime.now() + timedelta(days=days)
        
        current_end_str = current_user[4]
        
        if current_end_str:
            try:
                current_end = datetime.strptime(current_end_str, "%Y-%m-%d %H:%M:%S")
            except:
                current_end = datetime.now()
        else:
            current_end = datetime.now()
        
        if current_end > datetime.now() and current_user[3] == sub_type:
            new_end = current_end + timedelta(days=days)
        else:
            new_end = datetime.now() + timedelta(days=days)
        
        new_end_str = new_end.strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute(
            "UPDATE users SET subscription_type = ?, subscription_end = ? WHERE user_id = ?",
            (sub_type, new_end_str, user_id)
        )
        self.connection.commit()
        return new_end
    
    def check_subscription(self, user_id):
        user = self.get_user(user_id)
        if user and user[4]:
            try:
                end_date = datetime.strptime(user[4], "%Y-%m-%d %H:%M:%S")
                if end_date > datetime.now():
                    return user[3], end_date
            except:
                return None, None
        return None, None
    
    def add_key(self, key_code, sub_type, duration_days):
        try:
            self.cursor.execute(
                "INSERT INTO subscription_keys (key_code, subscription_type, duration_days, created_at) VALUES (?, ?, ?, ?)",
                (key_code, sub_type, duration_days, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            self.connection.commit()
            return True
        except:
            return False
    
    def get_key(self, key_code):
        self.cursor.execute("SELECT * FROM subscription_keys WHERE key_code = ?", (key_code,))
        return self.cursor.fetchone()
    
    def use_key(self, key_code, user_id):
        key = self.get_key(key_code)
        if key and key[4] == 0:
            self.activate_subscription(user_id, key[2], key[3])
            self.cursor.execute(
                "UPDATE subscription_keys SET is_used = 1, used_by = ? WHERE key_code = ?",
                (user_id, key_code)
            )
            self.cursor.execute(
                "INSERT INTO activations_log (user_id, key_code, subscription_type, activated_at) VALUES (?, ?, ?, ?)",
                (user_id, key_code, key[2], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            self.connection.commit()
            return True, key[2], key[3]
        return False, None, None
    
    def get_all_keys(self):
        self.cursor.execute("SELECT id, key_code, subscription_type, duration_days, is_used, used_by FROM subscription_keys ORDER BY id DESC")
        return self.cursor.fetchall()
    
    def delete_key(self, key_id):
        self.cursor.execute("DELETE FROM subscription_keys WHERE id = ?", (key_id,))
        self.connection.commit()
    
    def create_payment(self, user_id, amount, sub_type, days, payment_id):
        self.cursor.execute(
            "INSERT INTO payments (user_id, amount, subscription_type, duration_days, status, payment_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, amount, sub_type, days, "confirmed", payment_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        self.connection.commit()
    
    def add_review(self, user_id, review_text, rating):
        self.cursor.execute(
            "INSERT INTO reviews (user_id, review_text, rating, created_at) VALUES (?, ?, ?, ?)",
            (user_id, review_text, rating, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        self.connection.commit()
    
    def get_approved_reviews(self):
        self.cursor.execute(
            "SELECT r.id, u.username, r.review_text, r.rating, r.created_at FROM reviews r "
            "JOIN users u ON r.user_id = u.user_id WHERE r.is_approved = 1 ORDER BY r.created_at DESC LIMIT 20"
        )
        return self.cursor.fetchall()
    
    def get_pending_reviews(self):
        self.cursor.execute("SELECT * FROM reviews WHERE is_approved = 0")
        return self.cursor.fetchall()
    
    def approve_review(self, review_id):
        self.cursor.execute("UPDATE reviews SET is_approved = 1 WHERE id = ?", (review_id,))
        self.connection.commit()
    
    def delete_review(self, review_id):
        self.cursor.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        self.connection.commit()
    
    def get_stats(self):
        self.cursor.execute("SELECT COUNT(*) FROM users WHERE subscription_end > datetime('now')")
        active_subs = self.cursor.fetchone()[0] or 0
        
        self.cursor.execute("SELECT COUNT(*) FROM users")
        total_users = self.cursor.fetchone()[0] or 0
        
        self.cursor.execute("SELECT COUNT(*) FROM activations_log")
        total_activations = self.cursor.fetchone()[0] or 0
        
        self.cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'confirmed'")
        total_income = self.cursor.fetchone()[0] or 0
        
        self.cursor.execute("SELECT COUNT(*) FROM subscription_keys WHERE is_used = 0")
        unused_keys = self.cursor.fetchone()[0] or 0
        
        return {
            "active_subs": active_subs,
            "total_users": total_users,
            "total_activations": total_activations,
            "total_income": total_income,
            "unused_keys": unused_keys
        }
    
    def close(self):
        self.connection.close()