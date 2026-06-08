import telebot
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from database import Database
import requests
import json
import traceback
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

# ============================================
# НАСТРОЙКИ (ВАШИ ДАННЫЕ)
# ============================================
BOT_TOKEN = "8664140220:AAGDF8R4pQM31nd_ZMOFgCK69MMReNxWEOA"
RAILWAY_URL = "https://telegram-bot-production-4bcc.up.railway.app"

# Platega настройки
PLATEGA_MERCHANT_ID = "709e8d20-e5f9-4ad0-8bae-311460ff7991"
PLATEGA_API_SECRET = "b4gxyG1yLHYrz3AvG0QEOjxw5BuKaWie3JkP3p25ExhEX6AFLbf2ZqPMWGFWgpSXtgsrGYTjsXh7KEF8tDHdxLAvFW6XCNqG7xJ2"
PLATEGA_API_URL = "https://app.platega.io"

# CryptoBot настройки
CRYPTOBOT_TOKEN = "589863:AA1iJtmR2y4tzd1hKzPKd4d184n9CGAyRRc"
CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"

# НАЦЕНКА НА КРИПТОПЛАТЕЖИ (ТОЛЬКО ДЛЯ ПОДПИСОК!)
CRYPTO_MARKUP_PERCENT = 30

# ГРУППЫ ДЛЯ ПОДПИСЧИКОВ
VIP_GROUP_ID = -1003709565134
LITE_GROUP_ID = -1003709565134

MAIN_ADMIN_ID = 1302493787

# Ссылки на документы
PRIVACY_POLICY_URL = "https://telegra.ph/Politika-konfidencialnosti-04-01-26"
TERMS_OF_USE_URL = "https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19"
REVIEWS_CHANNEL = "https://t.me/KeeperOtzivi"
MAIN_CHANNEL = "@keepersell"
SUPPORT_USERNAME = "nikita1055"

bot = telebot.TeleBot(BOT_TOKEN)
db = Database()
user_states = {}
app = Flask(__name__)

# Временные блокировки ключей
reserved_keys = {}

# Кэш для курса USDT
usdt_rate_cache = {"rate": 73, "timestamp": 0}

# ============================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С НАСТРОЙКАМИ
# ============================================
def get_markup_percent():
    """Получает процент наценки из БД"""
    try:
        cursor = db.connection.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'crypto_markup_percent'")
        result = cursor.fetchone()
        if result:
            return int(result[0])
    except:
        pass
    return 30

def set_markup_percent(value):
    """Сохраняет процент наценки в БД"""
    try:
        cursor = db.connection.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("crypto_markup_percent", str(value)))
        db.connection.commit()
        return True
    except:
        return False

# ============================================
# ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ АКТУАЛЬНОГО КУРСА USDT
# ============================================
def get_usdt_rate():
    global usdt_rate_cache
    if datetime.now().timestamp() - usdt_rate_cache["timestamp"] < 300:
        return usdt_rate_cache["rate"]
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub", timeout=5)
        if response.status_code == 200:
            rate = response.json().get("tether", {}).get("rub", 73)
            usdt_rate_cache = {"rate": round(rate, 2), "timestamp": datetime.now().timestamp()}
            return round(rate, 2)
    except:
        pass
    return usdt_rate_cache["rate"]

# ============================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ЦЕНАМИ И КЛЮЧАМИ
# ============================================
def get_price(key, default):
    try:
        cursor = db.connection.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (f"price_{key}",))
        result = cursor.fetchone()
        if result:
            return int(result[0])
    except:
        pass
    return default

def set_price(key, value):
    try:
        cursor = db.connection.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"price_{key}", str(value)))
        db.connection.commit()
        return True
    except:
        return False

def check_keys_available(sub_type, days):
    keys = db.get_all_keys()
    reserved_codes = set()
    for reserved in reserved_keys.values():
        reserved_codes.add(reserved.get("key"))
    for key in keys:
        if key[2] == sub_type and key[3] == days and key[4] == 0 and key[1] not in reserved_codes:
            return True
    return False

def get_key_count(sub_type, days):
    count = 0
    keys = db.get_all_keys()
    reserved_codes = set()
    for reserved in reserved_keys.values():
        reserved_codes.add(reserved.get("key"))
    for key in keys:
        if key[2] == sub_type and key[3] == days and key[4] == 0 and key[1] not in reserved_codes:
            count += 1
    return count

def reserve_key(sub_type, days, user_id):
    keys = db.get_all_keys()
    reserved_codes = set()
    for reserved in reserved_keys.values():
        reserved_codes.add(reserved.get("key"))
    for key in keys:
        if key[2] == sub_type and key[3] == days and key[4] == 0 and key[1] not in reserved_codes:
            reserved_keys[user_id] = {
                "key": key[1],
                "sub_type": sub_type,
                "days": days,
                "expires_at": datetime.now() + timedelta(minutes=30)
            }
            return key[1]
    return None

def release_key(user_id):
    if user_id in reserved_keys:
        del reserved_keys[user_id]
        return True
    return False

def create_group_link(sub_type):
    try:
        group_id = VIP_GROUP_ID if sub_type == "vip" else LITE_GROUP_ID
        invite_link = bot.create_chat_invite_link(
            chat_id=group_id,
            member_limit=1,
            expire_date=datetime.now() + timedelta(days=7)
        )
        return invite_link.invite_link
    except Exception as e:
        print(f"Ошибка создания ссылки: {e}")
        return None

# ============================================
# ФУНКЦИИ РАСЧЕТА (С КОМИССИЕЙ ТОЛЬКО ДЛЯ ПОДПИСОК)
# ============================================
def calculate_crypto_amount_with_markup(rub_amount):
    """Для покупки подписок - с наценкой"""
    usdt_rate = get_usdt_rate()
    markup_percent = get_markup_percent()
    final_rub = rub_amount * (1 + markup_percent / 100)
    usdt_amount = final_rub / usdt_rate
    return round(usdt_amount, 2), usdt_rate, markup_percent, final_rub

def calculate_crypto_amount_no_markup(rub_amount):
    """Для донатов - без наценки"""
    usdt_rate = get_usdt_rate()
    usdt_amount = rub_amount / usdt_rate
    return round(usdt_amount, 2), usdt_rate

# ============================================
# ПЛАТЕЖИ ЧЕРЕЗ PLATEGA
# ============================================
def create_platega_payment(amount, user_id, order_id):
    headers = {
        "Content-Type": "application/json",
        "X-MerchantId": PLATEGA_MERCHANT_ID,
        "X-Secret": PLATEGA_API_SECRET
    }
    data = {
        "command": "create",
        "paymentDetails": {"amount": float(amount), "currency": "RUB"},
        "description": f"Заказ {order_id} для {user_id}",
        "return": "https://t.me/KeeperMag_bot",
        "failedUrl": "https://t.me/KeeperMag_bot",
        "payload": f"user_{user_id}_{order_id}",
        "paymentMethod": ["SBP", "CRYPTO"]
    }
    try:
        response = requests.post(f"{PLATEGA_API_URL}/v2/transaction/process", headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            return {
                "success": True,
                "payment_url": result.get("url") or result.get("payment_url"),
                "transaction_id": result.get("transactionId") or result.get("id")
            }
        return {"success": False, "error": f"Ошибка {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_platega_payment(transaction_id):
    headers = {"X-MerchantId": PLATEGA_MERCHANT_ID, "X-Secret": PLATEGA_API_SECRET}
    try:
        response = requests.get(f"{PLATEGA_API_URL}/transaction/{transaction_id}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get("status")
        return None
    except:
        return None

# ============================================
# ПЛАТЕЖИ ЧЕРЕЗ CRYPTOBOT
# ============================================
def create_cryptobot_payment(amount_usdt, user_id, description, payload):
    headers = {"Content-Type": "application/json", "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    data = {
        "asset": "USDT",
        "amount": amount_usdt,
        "description": description,
        "paid_btn_name": "callback",
        "paid_btn_url": f"{RAILWAY_URL}/payment_success",
        "payload": payload
    }
    try:
        response = requests.post(f"{CRYPTOBOT_API_URL}/createInvoice", headers=headers, json=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                invoice = result.get("result")
                return {
                    "success": True,
                    "payment_url": invoice.get("pay_url"),
                    "transaction_id": str(invoice.get("invoice_id"))
                }
        return {"success": False, "error": f"Ошибка {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_cryptobot_payment(invoice_id):
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    try:
        response = requests.get(f"{CRYPTOBOT_API_URL}/getInvoices", headers=headers, params={"invoice_ids": invoice_id}, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                invoices = result.get("result", {}).get("items", [])
                if invoices:
                    status = invoices[0].get("status")
                    return "paid" if status == "paid" else "pending" if status == "active" else None
        return None
    except:
        return None

# Создаем таблицу settings
try:
    cursor = db.connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    db.connection.commit()
except:
    pass

# Загружаем цены
PRICES = {
    "lite_1day": get_price("lite_1day", 140),
    "lite_7day": get_price("lite_7day", 700),
    "vip_1day": get_price("vip_1day", 270),
    "vip_7day": get_price("vip_7day", 1200),
    "vip_14day": get_price("vip_14day", 2200)
}

# ============================================
# КЛАВИАТУРЫ
# ============================================
def main_menu(user_is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("🌟 Купить подписку"),
        KeyboardButton("👤 Мой профиль"),
        KeyboardButton("❤️ Пожертвовать"),
        KeyboardButton("ℹ️ Информация")
    ]
    if user_is_admin:
        buttons.append(KeyboardButton("⚙️ Админ-панель"))
    markup.add(*buttons)
    return markup

def choose_subscription_type():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🌟 LITE подписка", callback_data="choose_lite"),
        InlineKeyboardButton("👑 VIP подписка", callback_data="choose_vip")
    )
    return markup

def choose_payment_method(sub_type, days, amount):
    usdt_amount, usdt_rate, markup_percent, final_rub = calculate_crypto_amount_with_markup(amount)
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💳 Platega (СБП/Карта)", callback_data=f"pay_platega_{sub_type}_{days}_{amount}"),
        InlineKeyboardButton(f"🪙 Криптовалюта USDT ({usdt_amount} USDT)", callback_data=f"pay_crypto_{sub_type}_{days}_{amount}"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_to_choice")
    )
    return markup

def lite_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(f"1 день - {PRICES['lite_1day']}₽ ({get_key_count('lite', 1)} шт)", callback_data="select_lite_1day"),
        InlineKeyboardButton(f"7 дней - {PRICES['lite_7day']}₽ ({get_key_count('lite', 7)} шт)", callback_data="select_lite_7day")
    )
    return markup

def vip_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(f"1 день - {PRICES['vip_1day']}₽ ({get_key_count('vip', 1)} шт)", callback_data="select_vip_1day"),
        InlineKeyboardButton(f"7 дней - {PRICES['vip_7day']}₽ ({get_key_count('vip', 7)} шт)", callback_data="select_vip_7day"),
        InlineKeyboardButton(f"14 дней - {PRICES['vip_14day']}₽ ({get_key_count('vip', 14)} шт)", callback_data="select_vip_14day")
    )
    return markup

def info_buttons():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💬 Техподдержка", url=f"https://t.me/{SUPPORT_USERNAME}"),
        InlineKeyboardButton("📢 Основной канал", url=f"https://t.me/{MAIN_CHANNEL.lstrip('@')}"),
        InlineKeyboardButton("⭐ Канал с отзывами", url=REVIEWS_CHANNEL),
        InlineKeyboardButton("✍️ Оставить отзыв", callback_data="write_review"),
        InlineKeyboardButton("📄 Политика конфиденциальности", url=PRIVACY_POLICY_URL),
        InlineKeyboardButton("📑 Пользовательское соглашение", url=TERMS_OF_USE_URL)
    )
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("➕ Добавить ключи (массово)"),
        KeyboardButton("🗑 Удалить ключи (массово)"),
        KeyboardButton("💰 Изменить цены"),
        KeyboardButton("📊 Крипто-настройки"),
        KeyboardButton("📋 Список ключей"),
        KeyboardButton("📊 Статистика"),
        KeyboardButton("👥 Управление админами"),
        KeyboardButton("◀️ Назад в меню")
    ]
    markup.add(*buttons)
    return markup

def review_rating():
    markup = InlineKeyboardMarkup(row_width=5)
    buttons = [InlineKeyboardButton(str(i), callback_data=f"rate_{i}") for i in range(1, 6)]
    markup.add(*buttons)
    return markup

def is_admin(user_id):
    try:
        cursor = db.connection.cursor()
        cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        return result and result[0] == 1
    except:
        return user_id == MAIN_ADMIN_ID

def is_main_admin(user_id):
    return user_id == MAIN_ADMIN_ID

# ============================================
# ОТЗЫВЫ
# ============================================
@bot.callback_query_handler(func=lambda call: call.data == "write_review")
def ask_review(call: CallbackQuery):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "📝 **Напишите текст отзыва:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_review_text)

def process_review_text(message: Message):
    user_states[message.from_user.id] = {"review_text": message.text}
    bot.send_message(message.chat.id, "⭐ **Оцените сервис от 1 до 5:**", parse_mode="Markdown", reply_markup=review_rating())

@bot.callback_query_handler(func=lambda call: call.data.startswith("rate_"))
def process_review_rating(call: CallbackQuery):
    rating = int(call.data.split("_")[1])
    user_data = user_states.get(call.from_user.id, {})
    review_text = user_data.get("review_text", "Без текста")
    db.add_review(call.from_user.id, review_text, rating)
    bot.answer_callback_query(call.id, "✅ Спасибо!")
    bot.send_message(call.message.chat.id, "✅ **Отзыв отправлен на модерацию!**", parse_mode="Markdown")
    if call.from_user.id in user_states:
        del user_states[call.from_user.id]

# ============================================
# ДОНАТЫ (БЕЗ КОМИССИИ)
# ============================================
@bot.message_handler(func=lambda message: message.text == "❤️ Пожертвовать")
def donate_menu(message: Message):
    text = (
        "❤️ **ПОДДЕРЖАТЬ ПРОЕКТ**\n\n"
        "Вы можете помочь развитию проекта.\n\n"
        "💰 Минимальная сумма: 10₽\n"
        "✨ **Комиссия не взимается**\n\n"
        "Выберите способ оплаты:"
    )
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("💳 Platega (СБП/Карта)", callback_data="donate_platega"),
        InlineKeyboardButton("🪙 Криптовалюта USDT", callback_data="donate_crypto")
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "donate_platega")
def donate_platega(call: CallbackQuery):
    msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму (в рублях):**\n\nМинимальная: 10₽", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_donate_platega)

def process_donate_platega(message: Message):
    try:
        amount = float(message.text.strip())
        if amount < 10:
            bot.send_message(message.chat.id, "❌ Минимальная сумма 10₽")
            return
        result = create_platega_payment(amount, message.from_user.id, "donate")
        if result["success"]:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=result["payment_url"]))
            bot.send_message(message.chat.id, f"❤️ **Спасибо!**\n💰 {amount}₽\n👇 Оплатите", parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, f"❌ Ошибка: {result.get('error')}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")

@bot.callback_query_handler(func=lambda call: call.data == "donate_crypto")
def donate_crypto(call: CallbackQuery):
    msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму (в рублях):**\n\nМинимальная: 10₽\n✨ Без комиссии", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_donate_crypto)

def process_donate_crypto(message: Message):
    try:
        rub_amount = float(message.text.strip())
        if rub_amount < 10:
            bot.send_message(message.chat.id, "❌ Минимальная сумма 10₽")
            return
        
        usdt_amount, usdt_rate = calculate_crypto_amount_no_markup(rub_amount)
        result = create_cryptobot_payment(usdt_amount, message.from_user.id, f"Пожертвование {rub_amount}₽", f"donate_{message.from_user.id}")
        
        if result["success"]:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🪙 ОПЛАТИТЬ USDT", url=result["payment_url"]))
            bot.send_message(
                message.chat.id,
                f"❤️ **Спасибо за поддержку!**\n\n"
                f"💰 Сумма: {rub_amount}₽\n"
                f"🪙 К оплате: {usdt_amount} USDT\n"
                f"💱 Курс: {usdt_rate}₽/USDT\n"
                f"✨ Комиссия: 0%\n\n"
                f"👇 Нажмите для оплаты",
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            bot.send_message(message.chat.id, f"❌ Ошибка: {result.get('error')}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")

# ============================================
# ОСНОВНЫЕ ОБРАБОТЧИКИ
# ============================================
@bot.message_handler(commands=['start'])
def start_command(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    db.add_user(user_id, username)
    bot.send_message(user_id, "🤖 Добро пожаловать!\n\n🌟 Бот для продажи подписок LITE и VIP.\n💳 Оплата через Platega или криптовалютой USDT", reply_markup=main_menu(is_admin(user_id)))

@bot.message_handler(func=lambda message: message.text == "👤 Мой профиль")
def profile(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "❌ Ошибка!")
        return
    sub_type, end_date = db.check_subscription(message.from_user.id)
    text = f"👤 **Ваш профиль**\n\n🆔 ID: {user[0]}\n"
    if sub_type:
        days_left = (end_date - datetime.now()).days
        text += f"📅 Подписка: {sub_type.upper()}\n⏰ Действует до: {end_date.strftime('%d.%m.%Y %H:%M')}\n⌛ Осталось: {days_left} д.\n"
    else:
        text += "❌ Нет активной подписки\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🌟 Купить подписку")
def buy_subscription(message: Message):
    bot.send_message(message.chat.id, "🌟 **Выберите тип подписки:**", parse_mode="Markdown", reply_markup=choose_subscription_type())

@bot.callback_query_handler(func=lambda call: call.data == "choose_lite")
def choose_lite(call: CallbackQuery):
    bot.edit_message_text("🌟 **LITE подписка**\n(количество ключей в скобках)", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=lite_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data == "choose_vip")
def choose_vip(call: CallbackQuery):
    bot.edit_message_text("👑 **VIP подписка**\n(количество ключей в скобках)", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=vip_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_lite_"))
def select_lite_duration(call: CallbackQuery):
    days = 1 if call.data == "select_lite_1day" else 7
    amount = PRICES[f"lite_{days}day"]
    bot.edit_message_text(f"🌟 LITE {days} д.\n💰 {amount}₽\nВыберите способ оплаты:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=choose_payment_method("lite", days, amount))

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_vip_"))
def select_vip_duration(call: CallbackQuery):
    days = int(call.data.split("_")[2].replace("day", ""))
    amount = PRICES[f"vip_{days}day"]
    bot.edit_message_text(f"👑 VIP {days} д.\n💰 {amount}₽\nВыберите способ оплаты:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=choose_payment_method("vip", days, amount))

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_platega_"))
def process_platega_payment(call: CallbackQuery):
    _, _, sub_type, days, amount = call.data.split("_")
    days = int(days)
    amount = float(amount)
    
    reserved_key = reserve_key(sub_type, days, call.from_user.id)
    if not reserved_key:
        bot.answer_callback_query(call.id, "❌ Ключи закончились!", show_alert=True)
        return
    
    result = create_platega_payment(amount, call.from_user.id, f"{sub_type}_{days}day")
    if result["success"]:
        user_states[f"payment_{result['transaction_id']}"] = {"user_id": call.from_user.id, "sub_type": sub_type, "days": days, "key": reserved_key}
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=result["payment_url"]))
        markup.add(InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data=f"check_platega_{result['transaction_id']}"))
        markup.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data=f"cancel_platega_{result['transaction_id']}"))
        bot.edit_message_text(f"💳 Счет на {amount}₽\n📦 {sub_type.upper()} {days} д.\n⏰ Ключ зарезервирован на 30 минут", call.message.chat.id, call.message.message_id, reply_markup=markup)
    else:
        release_key(call.from_user.id)
        bot.edit_message_text(f"❌ Ошибка: {result.get('error')}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_crypto_"))
def process_crypto_payment(call: CallbackQuery):
    _, _, sub_type, days, rub_amount = call.data.split("_")
    days = int(days)
    rub_amount = float(rub_amount)
    
    reserved_key = reserve_key(sub_type, days, call.from_user.id)
    if not reserved_key:
        bot.answer_callback_query(call.id, "❌ Ключи закончились!", show_alert=True)
        return
    
    usdt_amount, usdt_rate, markup_percent, final_rub = calculate_crypto_amount_with_markup(rub_amount)
    result = create_cryptobot_payment(usdt_amount, call.from_user.id, f"Подписка {sub_type} {days}д (цена {rub_amount}₽ + комиссия {markup_percent}% = {final_rub:.2f}₽)", f"user_{call.from_user.id}_{sub_type}_{days}day")
    
    if result["success"]:
        user_states[f"crypto_{result['transaction_id']}"] = {"user_id": call.from_user.id, "sub_type": sub_type, "days": days, "key": reserved_key}
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🪙 ОПЛАТИТЬ USDT", url=result["payment_url"]))
        markup.add(InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data=f"check_crypto_{result['transaction_id']}"))
        markup.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data=f"cancel_crypto_{result['transaction_id']}"))
        bot.edit_message_text(
            f"🪙 **Крипто-счет**\n\n💰 Цена: {rub_amount}₽\n📈 Комиссия {markup_percent}%: {rub_amount * markup_percent / 100:.2f}₽\n💵 Итого: {final_rub:.2f}₽\n🪙 {usdt_amount} USDT\n💱 Курс: {usdt_rate}₽\n📦 {sub_type.upper()} {days} д.\n⏰ Ключ зарезервирован на 30 минут",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup
        )
    else:
        release_key(call.from_user.id)
        bot.edit_message_text(f"❌ Ошибка криптоплатежа", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_platega_"))
def check_platega(call: CallbackQuery):
    transaction_id = call.data.split("_")[2]
    status = check_platega_payment(transaction_id)
    if status == "CONFIRMED":
        data = user_states.get(f"payment_{transaction_id}", {})
        if data.get("key") and data.get("user_id"):
            db.activate_subscription(data["user_id"], data["sub_type"], data["days"])
            group_link = create_group_link(data["sub_type"])
            bot.send_message(data["user_id"], f"✅ Оплата подтверждена!\n🔑 Ключ: `{data['key']}`\n📦 Подписка: {data['sub_type'].upper()} {data['days']} д.\n📦 Ссылка на группу: {group_link}" if group_link else "")
        bot.answer_callback_query(call.id, "✅ Оплата подтверждена!")
        bot.send_message(call.message.chat.id, "✅ Подписка активирована!")
        release_key(data.get("user_id"))
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "⏳ Еще не оплачено", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_crypto_"))
def check_crypto(call: CallbackQuery):
    invoice_id = call.data.split("_")[2]
    status = check_cryptobot_payment(invoice_id)
    if status == "paid":
        data = user_states.get(f"crypto_{invoice_id}", {})
        if data.get("key") and data.get("user_id"):
            db.activate_subscription(data["user_id"], data["sub_type"], data["days"])
            group_link = create_group_link(data["sub_type"])
            bot.send_message(data["user_id"], f"✅ Оплата подтверждена!\n🔑 Ключ: `{data['key']}`\n📦 Подписка: {data['sub_type'].upper()} {data['days']} д.\n📦 Ссылка на группу: {group_link}" if group_link else "")
        bot.answer_callback_query(call.id, "✅ Оплата подтверждена!")
        bot.send_message(call.message.chat.id, "✅ Подписка активирована!")
        release_key(data.get("user_id"))
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "⏳ Еще не оплачено", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_platega_"))
def cancel_platega(call: CallbackQuery):
    transaction_id = call.data.split("_")[2]
    release_key(call.from_user.id)
    bot.answer_callback_query(call.id, "❌ Оплата отменена")
    bot.edit_message_text("❌ Оплата отменена", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_crypto_"))
def cancel_crypto(call: CallbackQuery):
    invoice_id = call.data.split("_")[2]
    release_key(call.from_user.id)
    bot.answer_callback_query(call.id, "❌ Оплата отменена")
    bot.edit_message_text("❌ Оплата отменена", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_choice")
def back_to_choice(call: CallbackQuery):
    bot.edit_message_text("🌟 Выберите тип подписки:", call.message.chat.id, call.message.message_id, reply_markup=choose_subscription_type())

@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация")
def info_menu(message: Message):
    markup_percent = get_markup_percent()
    usdt_rate = get_usdt_rate()
    text = f"ℹ️ **ИНФОРМАЦИЯ**\n\n🤖 Бот для продажи подписок LITE и VIP\n\n💳 **Способы оплаты:**\n• Platega (СБП/карты) - без комиссии\n• Криптовалюта USDT - комиссия {markup_percent}% (только на подписки)\n\n💱 Курс USDT: {usdt_rate}₽\n\n📞 **КОНТАКТЫ:**\n• Поддержка: @{SUPPORT_USERNAME}\n• Канал: {MAIN_CHANNEL}\n• Отзывы: {REVIEWS_CHANNEL}"
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=info_buttons())

# ============================================
# АДМИН-ПАНЕЛЬ
# ============================================
@bot.message_handler(func=lambda message: message.text == "⚙️ Админ-панель" and is_admin(message.from_user.id))
def admin_panel(message: Message):
    bot.send_message(message.chat.id, "⚙️ **Админ-панель**", parse_mode="Markdown", reply_markup=admin_menu())

@bot.message_handler(commands=['addadmin'])
def add_admin_command(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /addadmin 123456789")
            return
        new_admin_id = int(parts[1])
        cursor = db.connection.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (new_admin_id,))
        db.connection.commit()
        bot.send_message(message.chat.id, f"✅ Админ {new_admin_id} добавлен")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /removeadmin 123456789")
            return
        remove_id = int(parts[1])
        if remove_id == MAIN_ADMIN_ID:
            bot.send_message(message.chat.id, "❌ Нельзя удалить главного админа")
            return
        cursor = db.connection.cursor()
        cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (remove_id,))
        db.connection.commit()
        bot.send_message(message.chat.id, f"✅ Админ {remove_id} удален")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(func=lambda message: message.text == "👥 Управление админами" and is_admin(message.from_user.id))
def manage_admins_menu(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Только главный админ")
        return
    cursor = db.connection.cursor()
    cursor.execute("SELECT user_id, username FROM users WHERE is_admin = 1")
    admins = cursor.fetchall()
    text = "👥 **Администраторы:**\n\n"
    for admin in admins:
        mark = "⭐" if admin[0] == MAIN_ADMIN_ID else ""
        text += f"• `{admin[0]}` - @{admin[1] or 'без username'} {mark}\n"
    text += "\n/addadmin ID - добавить\n/removeadmin ID - удалить"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📊 Крипто-настройки" and is_admin(message.from_user.id))
def crypto_settings_menu(message: Message):
    markup_percent = get_markup_percent()
    usdt_rate = get_usdt_rate()
    text = f"🪙 **Крипто-настройки**\n\n📈 Комиссия: {markup_percent}%\n💱 Курс USDT: {usdt_rate}₽\n\nИзменить комиссию: `/set_markup 35`"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['set_markup'])
def set_markup_command(message: Message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /set_markup 35")
            return
        new_markup = int(parts[1])
        if new_markup < 0 or new_markup > 100:
            bot.send_message(message.chat.id, "❌ Комиссия от 0 до 100%")
            return
        set_markup_percent(new_markup)
        bot.send_message(message.chat.id, f"✅ Комиссия изменена на {new_markup}%")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(func=lambda message: message.text == "➕ Добавить ключи (массово)" and is_admin(message.from_user.id))
def add_keys_batch(message: Message):
    text = "📝 **Массовое добавление**\n\nФормат:\n`+l1d` - LITE 1д\n`+l7d` - LITE 7д\n`+v1d` - VIP 1д\n`+v7d` - VIP 7д\n`+v14d` - VIP 14д\n\nПример:\n`+v1d`\n`KEY1`\n`KEY2`"
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_add_keys)

def process_add_keys(message: Message):
    lines = message.text.strip().split('\n')
    current_type, current_days = None, None
    added, stats = 0, {"lite_1d": 0, "lite_7d": 0, "vip_1d": 0, "vip_7d": 0, "vip_14d": 0}
    type_map = {
        "+l1d": ("lite", 1, "lite_1d"), "+l7d": ("lite", 7, "lite_7d"),
        "+v1d": ("vip", 1, "vip_1d"), "+v7d": ("vip", 7, "vip_7d"), "+v14d": ("vip", 14, "vip_14d")
    }
    for line in lines:
        line = line.strip().lower()
        if line in type_map:
            current_type, current_days, stat_key = type_map[line]
            continue
        if line and current_type:
            if db.add_key(line, current_type, current_days):
                added += 1
                stats[stat_key] += 1
    result = f"✅ Добавлено: {added}\n📊 LITE 1д: {stats['lite_1d']}, LITE 7д: {stats['lite_7d']}\nVIP 1д: {stats['vip_1d']}, VIP 7д: {stats['vip_7d']}, VIP 14д: {stats['vip_14d']}"
    bot.send_message(message.chat.id, result, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🗑 Удалить ключи (массово)" and is_admin(message.from_user.id))
def delete_keys_batch(message: Message):
    text = "🗑 **Массовое удаление**\n\nВариант 1 - удалить все ключи типа:\n`-l1d` - LITE 1д\n`-l7d` - LITE 7д\n`-v1d` - VIP 1д\n`-v7d` - VIP 7д\n`-v14d` - VIP 14д\n\nВариант 2 - удалить конкретные:\n`KEY1`\n`KEY2`"
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_delete_keys)

def process_delete_keys(message: Message):
    lines = message.text.strip().split('\n')
    type_map = {
        "-l1d": ("lite", 1), "-l7d": ("lite", 7),
        "-v1d": ("vip", 1), "-v7d": ("vip", 7), "-v14d": ("vip", 14)
    }
    first_line = lines[0].strip().lower()
    if first_line in type_map:
        target_type, target_days = type_map[first_line]
        deleted = 0
        all_keys = db.get_all_keys()
        for key in all_keys:
            if key[2] == target_type and key[3] == target_days and key[4] == 0:
                db.delete_key(key[0])
                deleted += 1
        bot.send_message(message.chat.id, f"✅ Удалено {deleted} ключей типа {target_type.upper()} {target_days}д")
        return
    keys_to_delete = set(lines)
    deleted = 0
    for key in db.get_all_keys():
        if key[1] in keys_to_delete and key[4] == 0:
            db.delete_key(key[0])
            deleted += 1
    bot.send_message(message.chat.id, f"✅ Удалено {deleted} ключей")

@bot.message_handler(func=lambda message: message.text == "💰 Изменить цены" and is_admin(message.from_user.id))
def change_prices_menu(message: Message):
    text = f"💰 **Текущие цены:**\n\nLITE 1д: {PRICES['lite_1day']}₽\nLITE 7д: {PRICES['lite_7day']}₽\nVIP 1д: {PRICES['vip_1day']}₽\nVIP 7д: {PRICES['vip_7day']}₽\nVIP 14д: {PRICES['vip_14day']}₽\n\nИзменить: `lite_1day 150`"
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, update_price)

def update_price(message: Message):
    try:
        key, new_price = message.text.strip().split()
        new_price = int(new_price)
        if key in PRICES:
            PRICES[key] = new_price
            set_price(key, new_price)
            bot.send_message(message.chat.id, f"✅ Цена {key} = {new_price}₽")
        else:
            bot.send_message(message.chat.id, "❌ Неверный ключ")
    except:
        bot.send_message(message.chat.id, "❌ Формат: `lite_1day 150`")

@bot.message_handler(func=lambda message: message.text == "📋 Список ключей" and is_admin(message.from_user.id))
def list_keys(message: Message):
    all_keys = db.get_all_keys()
    if not all_keys:
        bot.send_message(message.chat.id, "📭 Нет ключей")
        return
    lite_1d = [k for k in all_keys if k[2] == "lite" and k[3] == 1 and k[4] == 0]
    lite_7d = [k for k in all_keys if k[2] == "lite" and k[3] == 7 and k[4] == 0]
    vip_1d = [k for k in all_keys if k[2] == "vip" and k[3] == 1 and k[4] == 0]
    vip_7d = [k for k in all_keys if k[2] == "vip" and k[3] == 7 and k[4] == 0]
    vip_14d = [k for k in all_keys if k[2] == "vip" and k[3] == 14 and k[4] == 0]
    used = [k for k in all_keys if k[4] == 1]
    text = f"🔑 **Статистика:**\n\nLITE 1д: {len(lite_1d)}\nLITE 7д: {len(lite_7d)}\nVIP 1д: {len(vip_1d)}\nVIP 7д: {len(vip_7d)}\nVIP 14д: {len(vip_14d)}\nИспользовано: {len(used)}\nВсего: {len(all_keys)}"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📊 Статистика" and is_admin(message.from_user.id))
def show_stats(message: Message):
    stats = db.get_stats()
    cursor = db.connection.cursor()
    cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'confirmed'")
    total_income = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'confirmed'")
    total_success = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
    total_pending = cursor.fetchone()[0] or 0
    text = f"📊 **Статистика**\n\n💰 Доход: {total_income}₽\n✅ Успешно: {total_success}\n⏳ В ожидании: {total_pending}\n👥 Пользователей: {stats['total_users']}\n✅ Активных: {stats['active_subs']}"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "◀️ Назад в меню")
def back_to_main(message: Message):
    bot.send_message(message.chat.id, "🏠 Главное меню", reply_markup=main_menu(is_admin(message.from_user.id)))

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call: CallbackQuery):
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🏠 Главное меню", reply_markup=main_menu(is_admin(call.from_user.id)))

# ============================================
# FLASK ПРИЛОЖЕНИЕ
# ============================================
@app.route('/', methods=['GET'])
def index():
    return "Бот работает!", 200

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    try:
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return "OK", 200
    except:
        return "Error", 200

@app.route('/webhook', methods=['POST'])
def platega_webhook():
    try:
        data = request.json
        if data.get('status') == "CONFIRMED" and data.get('payload', '').startswith('user'):
            parts = data['payload'].split('_')
            if len(parts) >= 3:
                user_id = int(parts[1])
                order_parts = parts[2].split('_')
                sub_type = order_parts[0]
                days = int(order_parts[1].replace('day', ''))
                db.activate_subscription(user_id, sub_type, days)
                bot.send_message(user_id, f"✅ Оплата подтверждена!\n📦 {sub_type.upper()} {days} д.\n📦 Ссылка на группу: {create_group_link(sub_type)}")
        return jsonify({"status": "ok"}), 200
    except:
        return jsonify({"status": "error"}), 500

@app.route('/crypto_webhook', methods=['POST'])
def crypto_webhook():
    try:
        data = request.json
        if data.get('payload', '').startswith('user'):
            parts = data['payload'].split('_')
            if len(parts) >= 4:
                user_id = int(parts[1])
                sub_type = parts[2]
                days = int(parts[3].replace('day', ''))
                db.activate_subscription(user_id, sub_type, days)
                bot.send_message(user_id, f"✅ Оплата подтверждена!\n📦 {sub_type.upper()} {days} д.\n📦 Ссылка на группу: {create_group_link(sub_type)}")
        return jsonify({"ok": True}), 200
    except:
        return jsonify({"ok": False}), 200

@app.route('/payment_success', methods=['GET'])
def payment_success():
    return "Оплата успешно проведена!", 200

@app.route('/payment_cancel', methods=['GET'])
def payment_cancel():
    return "Оплата отменена.", 200

# ============================================
# ЗАПУСК
# ============================================
if __name__ == '__main__':
    get_usdt_rate()
    print("=" * 60)
    print("🚀 БОТ ЗАПУЩЕН")
    print(f"🤖 Бот: @KeeperMag_bot")
    print(f"📡 Platega: {RAILWAY_URL}/webhook")
    print(f"🪙 CryptoBot: {RAILWAY_URL}/crypto_webhook")
    print(f"💰 Комиссия: {get_markup_percent()}% (только подписки)")
    print(f"💱 Курс USDT: {get_usdt_rate()}₽")
    print("=" * 60)
    
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": f"{RAILWAY_URL}/telegram_webhook"})
        print("✅ Webhook установлен")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
    
    app.run(host='0.0.0.0', port=5000)
