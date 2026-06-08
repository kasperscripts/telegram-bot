import telebot
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from database import Database
import requests
import json
import traceback
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import random

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

# Наценка на криптоплатежи
CRYPTO_MARKUP_PERCENT = 30

# Администраторы
MAIN_ADMIN_ID = 1302493787
ADMIN_IDS = [1302493787, 6784034490]

# Стикеры для премиум
PREMIUM_STICKERS = [
    "CAACAgIAAxkBAAEB",  # Замените на реальные ID стикеров
    "CAACAgIAAxkBAAEB",
]

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

# Цены на ключи
PRICES = {
    "lite_1day": 140,
    "lite_7day": 700,
    "vip_1day": 270,
    "vip_7day": 1200,
    "vip_14day": 2200
}

# Кэш для курса USDT
usdt_rate_cache = {"rate": 73, "timestamp": 0}

# ============================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С НАСТРОЙКАМИ
# ============================================
def get_markup_percent():
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
    try:
        cursor = db.connection.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("crypto_markup_percent", str(value)))
        db.connection.commit()
        return True
    except:
        return False

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
# ФУНКЦИИ ДЛЯ РАБОТЫ С БАЛАНСОМ И КЛЮЧАМИ
# ============================================
def get_user_balance(user_id):
    user = db.get_user(user_id)
    if user:
        return user[2]
    return 0

def update_user_balance(user_id, amount):
    db.update_balance(user_id, amount)

def get_available_keys_count(sub_type, days):
    keys = db.get_all_keys()
    count = 0
    for key in keys:
        if key[2] == sub_type and key[3] == days and key[4] == 0:
            count += 1
    return count

def get_key_from_balance(user_id, sub_type, days):
    price_key = f"{sub_type}_{days}day"
    price = PRICES.get(price_key, 0)
    
    balance = get_user_balance(user_id)
    if balance >= price:
        # Ищем свободный ключ
        keys = db.get_all_keys()
        for key in keys:
            if key[2] == sub_type and key[3] == days and key[4] == 0:
                # Активируем ключ
                db.use_key(key[1], user_id)
                # Списываем деньги
                update_user_balance(user_id, -price)
                return True, key[1]
        return False, "Ключи закончились!"
    return False, f"Недостаточно средств! Нужно {price}₽, у вас {balance}₽"

def is_admin(user_id):
    return user_id in ADMIN_IDS

def is_main_admin(user_id):
    return user_id == MAIN_ADMIN_ID

# ============================================
# ФУНКЦИИ ДЛЯ ПЛАТЕЖЕЙ
# ============================================
def calculate_crypto_amount_with_markup(rub_amount):
    usdt_rate = get_usdt_rate()
    markup_percent = get_markup_percent()
    final_rub = rub_amount * (1 + markup_percent / 100)
    usdt_amount = final_rub / usdt_rate
    return round(usdt_amount, 2), usdt_rate, markup_percent, final_rub

def create_platega_payment(amount, user_id, order_id):
    headers = {
        "Content-Type": "application/json",
        "X-MerchantId": PLATEGA_MERCHANT_ID,
        "X-Secret": PLATEGA_API_SECRET
    }
    data = {
        "command": "create",
        "paymentDetails": {"amount": float(amount), "currency": "RUB"},
        "description": f"Пополнение баланса {user_id}",
        "return": "https://t.me/KeeperMag_bot",
        "failedUrl": "https://t.me/KeeperMag_bot",
        "payload": f"balance_{user_id}_{amount}",
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

def check_platega_payment(transaction_id):
    headers = {"X-MerchantId": PLATEGA_MERCHANT_ID, "X-Secret": PLATEGA_API_SECRET}
    try:
        response = requests.get(f"{PLATEGA_API_URL}/transaction/{transaction_id}", headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get("status")
        return None
    except:
        return None

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

def create_group_link(sub_type):
    try:
        VIP_GROUP_ID = -1003709565134
        LITE_GROUP_ID = -1003709565134
        group_id = VIP_GROUP_ID if sub_type == "vip" else LITE_GROUP_ID
        invite_link = bot.create_chat_invite_link(
            chat_id=group_id,
            member_limit=1,
            expire_date=datetime.now() + timedelta(days=7)
        )
        return invite_link.invite_link
    except:
        return None

# Создаем таблицу settings
try:
    cursor = db.connection.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    db.connection.commit()
except:
    pass

# ============================================
# КЛАВИАТУРЫ (ПРЕМИУМ ДИЗАЙН)
# ============================================
def main_menu(user_is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("🛍️ КУПИТЬ КЛЮЧ"),
        KeyboardButton("💰 БАЛАНС"),
        KeyboardButton("👤 ПРОФИЛЬ"),
        KeyboardButton("❤️ ПОДДЕРЖАТЬ"),
        KeyboardButton("ℹ️ ИНФОРМАЦИЯ")
    ]
    if user_is_admin:
        buttons.append(KeyboardButton("⚙️ АДМИН-ПАНЕЛЬ"))
    markup.add(*buttons)
    return markup

def buy_key_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🌟 LITE КЛЮЧИ", callback_data="buy_lite"),
        InlineKeyboardButton("👑 VIP КЛЮЧИ", callback_data="buy_vip"),
        InlineKeyboardButton("◀️ НАЗАД", callback_data="back_to_menu")
    )
    return markup

def lite_keys_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    lite_1day_count = get_available_keys_count("lite", 1)
    lite_7day_count = get_available_keys_count("lite", 7)
    markup.add(
        InlineKeyboardButton(f"🎫 LITE 1 день - {PRICES['lite_1day']}₽ ({lite_1day_count} шт)", callback_data="buy_lite_1day" if lite_1day_count > 0 else "no_keys"),
        InlineKeyboardButton(f"🎫 LITE 7 дней - {PRICES['lite_7day']}₽ ({lite_7day_count} шт)", callback_data="buy_lite_7day" if lite_7day_count > 0 else "no_keys"),
        InlineKeyboardButton("◀️ НАЗАД", callback_data="back_to_buy")
    )
    return markup

def vip_keys_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    vip_1day_count = get_available_keys_count("vip", 1)
    vip_7day_count = get_available_keys_count("vip", 7)
    vip_14day_count = get_available_keys_count("vip", 14)
    markup.add(
        InlineKeyboardButton(f"👑 VIP 1 день - {PRICES['vip_1day']}₽ ({vip_1day_count} шт)", callback_data="buy_vip_1day" if vip_1day_count > 0 else "no_keys"),
        InlineKeyboardButton(f"👑 VIP 7 дней - {PRICES['vip_7day']}₽ ({vip_7day_count} шт)", callback_data="buy_vip_7day" if vip_7day_count > 0 else "no_keys"),
        InlineKeyboardButton(f"👑 VIP 14 дней - {PRICES['vip_14day']}₽ ({vip_14day_count} шт)", callback_data="buy_vip_14day" if vip_14day_count > 0 else "no_keys"),
        InlineKeyboardButton("◀️ НАЗАД", callback_data="back_to_buy")
    )
    return markup

def deposit_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("100 ₽", callback_data="deposit_100"),
        InlineKeyboardButton("250 ₽", callback_data="deposit_250"),
        InlineKeyboardButton("500 ₽", callback_data="deposit_500"),
        InlineKeyboardButton("1000 ₽", callback_data="deposit_1000"),
        InlineKeyboardButton("💎 ДРУГАЯ СУММА", callback_data="deposit_custom"),
        InlineKeyboardButton("◀️ НАЗАД", callback_data="back_to_menu")
    )
    return markup

def payment_method_buttons(amount):
    usdt_amount, usdt_rate, markup_percent, final_rub = calculate_crypto_amount_with_markup(amount)
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💳 Platega (СБП/КАРТА)", callback_data=f"pay_platega_{amount}"),
        InlineKeyboardButton(f"🪙 USDT ({usdt_amount} USDT)", callback_data=f"pay_crypto_{amount}"),
        InlineKeyboardButton("◀️ НАЗАД", callback_data="back_to_deposit")
    )
    return markup

def info_buttons():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💬 ТЕХПОДДЕРЖКА", url=f"https://t.me/{SUPPORT_USERNAME}"),
        InlineKeyboardButton("📢 ОСНОВНОЙ КАНАЛ", url=f"https://t.me/{MAIN_CHANNEL.lstrip('@')}"),
        InlineKeyboardButton("⭐ ОТЗЫВЫ", url=REVIEWS_CHANNEL),
        InlineKeyboardButton("✍️ ОСТАВИТЬ ОТЗЫВ", callback_data="write_review"),
        InlineKeyboardButton("📄 ПОЛИТИКА", url=PRIVACY_POLICY_URL),
        InlineKeyboardButton("📑 СОГЛАШЕНИЕ", url=TERMS_OF_USE_URL)
    )
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("➕ ДОБАВИТЬ КЛЮЧИ"),
        KeyboardButton("🗑 УДАЛИТЬ КЛЮЧ"),
        KeyboardButton("📋 ВСЕ КЛЮЧИ"),
        KeyboardButton("💰 ВЫДАТЬ БАЛАНС"),
        KeyboardButton("💎 ИЗМЕНИТЬ ЦЕНЫ"),
        KeyboardButton("📊 СТАТИСТИКА"),
        KeyboardButton("👥 УПРАВЛЕНИЕ АДМИНАМИ"),
        KeyboardButton("⚙️ КРИПТО-НАСТРОЙКИ"),
        KeyboardButton("◀️ НАЗАД В МЕНЮ")
    ]
    markup.add(*buttons)
    return markup

def review_rating():
    markup = InlineKeyboardMarkup(row_width=5)
    buttons = [InlineKeyboardButton(str(i), callback_data=f"rate_{i}") for i in range(1, 6)]
    markup.add(*buttons)
    return markup

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
    bot.send_message(call.message.chat.id, "✅ Отзыв отправлен на модерацию!")
    if call.from_user.id in user_states:
        del user_states[call.from_user.id]

# ============================================
# ПРОФИЛЬ
# ============================================
@bot.message_handler(func=lambda message: message.text == "👤 ПРОФИЛЬ" or message.text == "💰 БАЛАНС")
def profile(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        # Создаем пользователя если его нет
        username = message.from_user.username or f"user_{message.from_user.id}"
        db.add_user(message.from_user.id, username)
        user = db.get_user(message.from_user.id)
    
    balance = get_user_balance(message.from_user.id)
    sub_type, end_date = db.check_subscription(message.from_user.id)
    
    text = "┌───────────────────┐\n"
    text += "│   👤 **ПРОФИЛЬ**   │\n"
    text += "└───────────────────┘\n\n"
    text += f"🆔 ID: `{user[0]}`\n"
    text += f"💰 БАЛАНС: **{balance}₽**\n\n"
    
    if sub_type:
        days_left = (end_date - datetime.now()).days
        hours_left = (end_date - datetime.now()).seconds // 3600
        text += "┌───────────────────┐\n"
        text += "│  🔑 **ПОДПИСКА**   │\n"
        text += "└───────────────────┘\n\n"
        text += f"📦 ТИП: **{sub_type.upper()}**\n"
        text += f"⏰ ДЕЙСТВУЕТ ДО: {end_date.strftime('%d.%m.%Y %H:%M')}\n"
        text += f"⌛ ОСТАЛОСЬ: {days_left} д. {hours_left} ч.\n"
    else:
        text += "❌ НЕТ АКТИВНОЙ ПОДПИСКИ\n"
    
    # Отправляем премиум стикер
    try:
        bot.send_sticker(message.chat.id, "CAACAgIAAxkBAAEB" + str(random.randint(1000, 9999)))
    except:
        pass
    
    # Кнопка пополнения
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💰 ПОПОЛНИТЬ БАЛАНС", callback_data="show_deposit"))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "show_deposit")
def show_deposit(call: CallbackQuery):
    bot.edit_message_text("💰 **ВЫБЕРИТЕ СУММУ ПОПОЛНЕНИЯ:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=deposit_buttons())

# ============================================
# ПОПОЛНЕНИЕ БАЛАНСА
# ============================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("deposit_"))
def process_deposit(call: CallbackQuery):
    amount = call.data.split("_")[1]
    if amount == "custom":
        msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму пополнения (в рублях):**\nМИНИМАЛЬНАЯ СУММА: 100₽", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_custom_deposit)
    else:
        amount = int(amount)
        bot.edit_message_text(f"💰 **СУММА: {amount}₽**\n\nВЫБЕРИТЕ СПОСОБ ОПЛАТЫ:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=payment_method_buttons(amount))

def process_custom_deposit(message: Message):
    try:
        amount = int(message.text.strip())
        if amount < 100:
            bot.send_message(message.chat.id, "❌ МИНИМАЛЬНАЯ СУММА 100₽", parse_mode="Markdown")
            return
        bot.send_message(message.chat.id, f"💰 **СУММА: {amount}₽**\n\nВЫБЕРИТЕ СПОСОБ ОПЛАТЫ:", parse_mode="Markdown", reply_markup=payment_method_buttons(amount))
    except:
        bot.send_message(message.chat.id, "❌ ВВЕДИТЕ ЧИСЛО!", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_platega_"))
def pay_platega(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    result = create_platega_payment(amount, call.from_user.id, f"deposit_{int(datetime.now().timestamp())}")
    if result["success"]:
        user_states[f"deposit_{result['transaction_id']}"] = {"user_id": call.from_user.id, "amount": amount}
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=result["payment_url"]))
        markup.add(InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data=f"check_deposit_{result['transaction_id']}"))
        bot.edit_message_text(f"💳 **СЧЕТ НА {amount}₽**\n👇 НАЖМИТЕ ДЛЯ ОПЛАТЫ", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.edit_message_text(f"❌ ОШИБКА: {result.get('error')}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_crypto_"))
def pay_crypto(call: CallbackQuery):
    rub_amount = int(call.data.split("_")[2])
    usdt_amount, usdt_rate, markup_percent, final_rub = calculate_crypto_amount_with_markup(rub_amount)
    
    result = create_cryptobot_payment(usdt_amount, call.from_user.id, f"Пополнение баланса {rub_amount}₽", f"deposit_{call.from_user.id}_{rub_amount}")
    
    if result["success"]:
        user_states[f"deposit_crypto_{result['transaction_id']}"] = {"user_id": call.from_user.id, "amount": rub_amount}
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🪙 ОПЛАТИТЬ USDT", url=result["payment_url"]))
        markup.add(InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data=f"check_deposit_crypto_{result['transaction_id']}"))
        bot.edit_message_text(
            f"🪙 **КРИПТО-СЧЕТ**\n\n"
            f"💰 СУММА: {rub_amount}₽\n"
            f"📈 КОМИССИЯ {markup_percent}%: {rub_amount * markup_percent / 100:.2f}₽\n"
            f"💵 ИТОГО: {final_rub:.2f}₽\n"
            f"🪙 {usdt_amount} USDT\n"
            f"💱 КУРС: {usdt_rate}₽\n\n"
            f"👇 НАЖМИТЕ ДЛЯ ОПЛАТЫ",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup
        )
    else:
        bot.edit_message_text(f"❌ ОШИБКА: {result.get('error')}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_deposit_"))
def check_deposit(call: CallbackQuery):
    transaction_id = call.data.split("_")[2]
    status = check_platega_payment(transaction_id)
    if status == "CONFIRMED":
        data = user_states.get(f"deposit_{transaction_id}", {})
        if data.get("user_id") and data.get("amount"):
            update_user_balance(data["user_id"], data["amount"])
            bot.send_message(data["user_id"], f"✅ **БАЛАНС ПОПОЛНЕН НА {data['amount']}₽!**")
        bot.answer_callback_query(call.id, "✅ ОПЛАТА ПОДТВЕРЖДЕНА!")
        bot.send_message(call.message.chat.id, "✅ БАЛАНС ПОПОЛНЕН!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "⏳ ЕЩЕ НЕ ОПЛАЧЕНО", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_deposit_crypto_"))
def check_deposit_crypto(call: CallbackQuery):
    invoice_id = call.data.split("_")[3]
    status = check_cryptobot_payment(invoice_id)
    if status == "paid":
        data = user_states.get(f"deposit_crypto_{invoice_id}", {})
        if data.get("user_id") and data.get("amount"):
            update_user_balance(data["user_id"], data["amount"])
            bot.send_message(data["user_id"], f"✅ **БАЛАНС ПОПОЛНЕН НА {data['amount']}₽!**")
        bot.answer_callback_query(call.id, "✅ ОПЛАТА ПОДТВЕРЖДЕНА!")
        bot.send_message(call.message.chat.id, "✅ БАЛАНС ПОПОЛНЕН!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "⏳ ЕЩЕ НЕ ОПЛАЧЕНО", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_deposit")
def back_to_deposit(call: CallbackQuery):
    bot.edit_message_text("💰 **ВЫБЕРИТЕ СУММУ ПОПОЛНЕНИЯ:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=deposit_buttons())

# ============================================
# ПОКУПКА КЛЮЧА
# ============================================
@bot.message_handler(func=lambda message: message.text == "🛍️ КУПИТЬ КЛЮЧ")
def buy_key(message: Message):
    bot.send_message(message.chat.id, "🔑 **ВЫБЕРИТЕ ТИП КЛЮЧА:**", parse_mode="Markdown", reply_markup=buy_key_menu())

@bot.callback_query_handler(func=lambda call: call.data == "buy_lite")
def buy_lite(call: CallbackQuery):
    bot.edit_message_text("🌟 **LITE КЛЮЧИ**\n\nВЫБЕРИТЕ ПЕРИОД:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=lite_keys_buttons())

@bot.callback_query_handler(func=lambda call: call.data == "buy_vip")
def buy_vip(call: CallbackQuery):
    bot.edit_message_text("👑 **VIP КЛЮЧИ**\n\nВЫБЕРИТЕ ПЕРИОД:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=vip_keys_buttons())

@bot.callback_query_handler(func=lambda call: call.data == "no_keys")
def no_keys(call: CallbackQuery):
    bot.answer_callback_query(call.id, "❌ КЛЮЧИ ЗАКОНЧИЛИСЬ! ОБРАТИТЕСЬ К АДМИНИСТРАТОРУ.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy_key(call: CallbackQuery):
    _, sub_type, days = call.data.split("_")
    days = int(days.replace("day", ""))
    price = PRICES[f"{sub_type}_{days}day"]
    
    # Отправляем премиум стикер
    try:
        bot.send_sticker(call.message.chat.id, "CAACAgIAAxkBAAEB" + str(random.randint(1000, 9999)))
    except:
        pass
    
    success, result = get_key_from_balance(call.from_user.id, sub_type, days)
    if success:
        group_link = create_group_link(sub_type)
        group_text = f"\n\n📦 **ССЫЛКА НА ГРУППУ:**\n{group_link}\n⚠️ ССЫЛКА ОДНОРАЗОВАЯ!" if group_link else ""
        
        text = (
            f"✅ **КЛЮЧ АКТИВИРОВАН!**\n\n"
            f"🔑 ВАШ КЛЮЧ: `{result}`\n"
            f"📦 ТИП: {sub_type.upper()} {days} д.\n"
            f"💰 ОСТАТОК НА БАЛАНСЕ: {get_user_balance(call.from_user.id)}₽"
            f"{group_text}\n\n"
            f"✨ СОХРАНИТЕ КЛЮЧ!"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.answer_callback_query(call.id, "✅ КЛЮЧ ВЫДАН!")
    else:
        # Недостаточно средств или нет ключей
        if result == "Ключи закончились!":
            text = f"❌ **{result}**\n\nОБРАТИТЕСЬ К АДМИНИСТРАТОРУ @{SUPPORT_USERNAME}"
        else:
            text = f"❌ **{result}**\n\n💰 ВАШ БАЛАНС: {get_user_balance(call.from_user.id)}₽\n💎 НУЖНО: {price}₽\n\n➡️ ПОПОЛНИТЕ БАЛАНС В РАЗДЕЛЕ «💰 БАЛАНС»"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.answer_callback_query(call.id, "❌ ОШИБКА", show_alert=True)

# ============================================
# ПОДДЕРЖКА
# ============================================
@bot.message_handler(func=lambda message: message.text == "❤️ ПОДДЕРЖАТЬ")
def donate_menu(message: Message):
    text = (
        "❤️ **ПОДДЕРЖАТЬ ПРОЕКТ**\n\n"
        "ВЫ МОЖЕТЕ ПОМОЧЬ РАЗВИТИЮ ПРОЕКТА.\n\n"
        "💰 МИНИМАЛЬНАЯ СУММА: 10₽\n"
        "✨ КОМИССИЯ НЕ ВЗИМАЕТСЯ\n\n"
        "ВЫБЕРИТЕ СПОСОБ ОПЛАТЫ:"
    )
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("💳 Platega (СБП/КАРТА)", callback_data="donate_platega"),
        InlineKeyboardButton("🪙 КРИПТОВАЛЮТА USDT", callback_data="donate_crypto")
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "donate_platega")
def donate_platega(call: CallbackQuery):
    msg = bot.send_message(call.message.chat.id, "💰 **ВВЕДИТЕ СУММУ (В РУБЛЯХ):**\nМИНИМАЛЬНАЯ: 10₽", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_donate_platega)

def process_donate_platega(message: Message):
    try:
        amount = float(message.text.strip())
        if amount < 10:
            bot.send_message(message.chat.id, "❌ МИНИМАЛЬНАЯ СУММА 10₽")
            return
        result = create_platega_payment(amount, message.from_user.id, f"donate_{int(datetime.now().timestamp())}")
        if result["success"]:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=result["payment_url"]))
            bot.send_message(message.chat.id, f"❤️ **СПАСИБО ЗА ПОДДЕРЖКУ!**\n💰 СУММА: {amount}₽\n👇 ОПЛАТИТЕ", parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, f"❌ ОШИБКА: {result.get('error')}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ВВЕДИТЕ ЧИСЛО!")

@bot.callback_query_handler(func=lambda call: call.data == "donate_crypto")
def donate_crypto(call: CallbackQuery):
    msg = bot.send_message(call.message.chat.id, "💰 **ВВЕДИТЕ СУММУ (В РУБЛЯХ):**\nМИНИМАЛЬНАЯ: 10₽\n✨ БЕЗ КОМИССИИ", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_donate_crypto)

def process_donate_crypto(message: Message):
    try:
        rub_amount = float(message.text.strip())
        if rub_amount < 10:
            bot.send_message(message.chat.id, "❌ МИНИМАЛЬНАЯ СУММА 10₽")
            return
        usdt_rate = get_usdt_rate()
        usdt_amount = round(rub_amount / usdt_rate, 2)
        result = create_cryptobot_payment(usdt_amount, message.from_user.id, f"Пожертвование {rub_amount}₽", f"donate_{message.from_user.id}")
        if result["success"]:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🪙 ОПЛАТИТЬ USDT", url=result["payment_url"]))
            bot.send_message(
                message.chat.id,
                f"❤️ **СПАСИБО ЗА ПОДДЕРЖКУ!**\n\n"
                f"💰 СУММА: {rub_amount}₽\n"
                f"🪙 К ОПЛАТЕ: {usdt_amount} USDT\n"
                f"💱 КУРС: {usdt_rate}₽/USDT\n"
                f"✨ КОМИССИЯ: 0%\n\n"
                f"👇 ОПЛАТИТЕ",
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            bot.send_message(message.chat.id, f"❌ ОШИБКА: {result.get('error')}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ ВВЕДИТЕ ЧИСЛО!")

# ============================================
# ИНФОРМАЦИЯ
# ============================================
@bot.message_handler(func=lambda message: message.text == "ℹ️ ИНФОРМАЦИЯ")
def info_menu(message: Message):
    markup_percent = get_markup_percent()
    usdt_rate = get_usdt_rate()
    text = (
        "┌─────────────────────────────────┐\n"
        "│         ℹ️ **ИНФОРМАЦИЯ**         │\n"
        "└─────────────────────────────────┘\n\n"
        "🤖 **БОТ ДЛЯ ПРОДАЖИ КЛЮЧЕЙ**\n\n"
        "💳 **СПОСОБЫ ОПЛАТЫ:**\n"
        "• Platega (СБП/КАРТЫ) - БЕЗ КОМИССИИ\n"
        f"• КРИПТОВАЛЮТА USDT - КОМИССИЯ {markup_percent}%\n\n"
        f"💱 **КУРС USDT:** {usdt_rate}₽\n\n"
        "📌 **КАК ПОЛЬЗОВАТЬСЯ:**\n"
        "1️⃣ ПОПОЛНИТЕ БАЛАНС\n"
        "2️⃣ КУПИТЕ КЛЮЧ\n"
        "3️⃣ ПОЛУЧИТЕ КЛЮЧ И ДОСТУП В ГРУППУ\n\n"
        "📞 **КОНТАКТЫ:**\n"
        f"• ПОДДЕРЖКА: @{SUPPORT_USERNAME}\n"
        f"• КАНАЛ: {MAIN_CHANNEL}\n"
        f"• ОТЗЫВЫ: {REVIEWS_CHANNEL}\n\n"
        "⚖️ **ДОКУМЕНТЫ:**\n"
        "• ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ\n"
        "• ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ\n\n"
        "📄 НАЖМИТЕ НА КНОПКИ НИЖЕ ДЛЯ ПРОСМОТРА"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=info_buttons())

# ============================================
# АДМИН-ПАНЕЛЬ
# ============================================
@bot.message_handler(func=lambda message: message.text == "⚙️ АДМИН-ПАНЕЛЬ" and is_admin(message.from_user.id))
def admin_panel(message: Message):
    bot.send_message(message.chat.id, "⚙️ **АДМИН-ПАНЕЛЬ**", parse_mode="Markdown", reply_markup=admin_menu())

# Выдача баланса
@bot.message_handler(func=lambda message: message.text == "💰 ВЫДАТЬ БАЛАНС" and is_admin(message.from_user.id))
def give_balance_menu(message: Message):
    msg = bot.send_message(message.chat.id, "💰 **ВЫДАТЬ БАЛАНС**\n\nФОРМАТ: `ID СУММА`\nПРИМЕР: `1302493787 500`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_give_balance)

def process_give_balance(message: Message):
    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ ФОРМАТ: `ID СУММА`\nПРИМЕР: `1302493787 500`", parse_mode="Markdown")
            return
        user_id = int(parts[0])
        amount = int(parts[1])
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ СУММА ДОЛЖНА БЫТЬ ПОЛОЖИТЕЛЬНОЙ")
            return
        update_user_balance(user_id, amount)
        bot.send_message(message.chat.id, f"✅ **ВЫДАНО {amount}₽ ПОЛЬЗОВАТЕЛЮ `{user_id}`**", parse_mode="Markdown")
        try:
            bot.send_message(user_id, f"💰 **ВАМ НАЧИСЛЕНО {amount}₽ НА БАЛАНС!**", parse_mode="Markdown")
        except:
            pass
    except:
        bot.send_message(message.chat.id, "❌ ОШИБКА! ФОРМАТ: `ID СУММА`")

# Добавление ключей
@bot.message_handler(func=lambda message: message.text == "➕ ДОБАВИТЬ КЛЮЧИ" and is_admin(message.from_user.id))
def add_keys_menu(message: Message):
    msg = bot.send_message(message.chat.id, "📝 **ДОБАВИТЬ КЛЮЧИ**\n\nФОРМАТ: `КЛЮЧ lite 1`\nКАЖДЫЙ КЛЮЧ С НОВОЙ СТРОКИ:\n\nПРИМЕР:\n`ABC123 lite 1`\n`DEF456 vip 7`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_keys)

def save_keys(message: Message):
    lines = message.text.strip().split('\n')
    added = 0
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 3:
            key, sub_type, days = parts[0], parts[1].lower(), int(parts[2])
            if db.add_key(key, sub_type, days):
                added += 1
    bot.send_message(message.chat.id, f"✅ **ДОБАВЛЕНО КЛЮЧЕЙ: {added}**", parse_mode="Markdown")

# Удаление ключа
@bot.message_handler(func=lambda message: message.text == "🗑 УДАЛИТЬ КЛЮЧ" and is_admin(message.from_user.id))
def delete_key_menu(message: Message):
    msg = bot.send_message(message.chat.id, "🗑 **УДАЛИТЬ КЛЮЧ**\n\nВВЕДИТЕ КЛЮЧ ДЛЯ УДАЛЕНИЯ:\nПРИМЕР: `ABC123`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_delete_key)

def process_delete_key(message: Message):
    key_code = message.text.strip()
    keys = db.get_all_keys()
    for key in keys:
        if key[1] == key_code:
            db.delete_key(key[0])
            bot.send_message(message.chat.id, f"✅ **КЛЮЧ {key_code} УДАЛЕН!**", parse_mode="Markdown")
            return
    bot.send_message(message.chat.id, f"❌ **КЛЮЧ {key_code} НЕ НАЙДЕН!**", parse_mode="Markdown")

# Список всех ключей
@bot.message_handler(func=lambda message: message.text == "📋 ВСЕ КЛЮЧИ" and is_admin(message.from_user.id))
def list_all_keys(message: Message):
    keys = db.get_all_keys()
    if not keys:
        bot.send_message(message.chat.id, "📭 **НЕТ КЛЮЧЕЙ**", parse_mode="Markdown")
        return
    
    text = "🔑 **ВСЕ КЛЮЧИ:**\n\n"
    for key in keys:
        key_id, key_code, sub_type, days, is_used, used_by = key
        status = "✅ АКТИВЕН" if not is_used else f"❌ ИСПОЛЬЗОВАН (ПОЛЬЗОВАТЕЛЬ {used_by})"
        text += f"`{key_code}` - {sub_type.upper()} {days}д. - {status}\n"
    
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            bot.send_message(message.chat.id, text[i:i+4000], parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

# Изменение цен
@bot.message_handler(func=lambda message: message.text == "💎 ИЗМЕНИТЬ ЦЕНЫ" and is_admin(message.from_user.id))
def change_prices_menu(message: Message):
    text = "💰 **ТЕКУЩИЕ ЦЕНЫ:**\n\n"
    for key, price in PRICES.items():
        sub_type, days = key.split("_")
        days_num = days.replace("day", "")
        text += f"• {sub_type.upper()} {days_num} д.: {price}₽\n"
    text += "\n**ИЗМЕНИТЬ ЦЕНУ:**\nОТПРАВЬТЕ: `lite_1day:150` ИЛИ `lite_1day 150`"
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, update_price)

def update_price(message: Message):
    try:
        if ' ' in message.text:
            key, new_price = message.text.split(' ')
        elif ':' in message.text:
            key, new_price = message.text.split(':')
        else:
            bot.send_message(message.chat.id, "❌ ФОРМАТ: `lite_1day 150` ИЛИ `lite_1day:150`")
            return
        new_price = int(new_price)
        if key in PRICES:
            PRICES[key] = new_price
            cursor = db.connection.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"price_{key}", str(new_price)))
            db.connection.commit()
            bot.send_message(message.chat.id, f"✅ **ЦЕНА {key} ИЗМЕНЕНА НА {new_price}₽**", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, f"❌ НЕВЕРНЫЙ КЛЮЧ! ДОСТУПНЫ: {', '.join(PRICES.keys())}")
    except:
        bot.send_message(message.chat.id, "❌ ОШИБКА!")

# Статистика
@bot.message_handler(func=lambda message: message.text == "📊 СТАТИСТИКА" and is_admin(message.from_user.id))
def show_admin_stats(message: Message):
    stats = db.get_stats()
    cursor = db.connection.cursor()
    cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'confirmed'")
    total_income = cursor.fetchone()[0] or 0
    total_users = stats.get('total_users', 0)
    active_subs = stats.get('active_subs', 0)
    
    # Подсчет ключей
    all_keys = db.get_all_keys()
    used_keys = sum(1 for k in all_keys if k[4] == 1)
    available_keys = len(all_keys) - used_keys
    
    text = (
        "┌─────────────────────────────────┐\n"
        "│        📊 **СТАТИСТИКА**         │\n"
        "└─────────────────────────────────┘\n\n"
        f"💰 **ДОХОД:** {total_income}₽\n"
        f"👥 **ПОЛЬЗОВАТЕЛЕЙ:** {total_users}\n"
        f"✅ **АКТИВНЫХ ПОДПИСОК:** {active_subs}\n"
        f"🔑 **ДОСТУПНО КЛЮЧЕЙ:** {available_keys}\n"
        f"❌ **ИСПОЛЬЗОВАНО КЛЮЧЕЙ:** {used_keys}\n"
        f"📊 **ВСЕГО КЛЮЧЕЙ:** {len(all_keys)}"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# Управление админами
@bot.message_handler(func=lambda message: message.text == "👥 УПРАВЛЕНИЕ АДМИНАМИ" and is_admin(message.from_user.id))
def manage_admins(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ ТОЛЬКО ГЛАВНЫЙ АДМИНИСТРАТОР!")
        return
    cursor = db.connection.cursor()
    cursor.execute("SELECT user_id, username FROM users WHERE is_admin = 1")
    admins = cursor.fetchall()
    text = "👥 **АДМИНИСТРАТОРЫ:**\n\n"
    for admin in admins:
        mark = "⭐" if admin[0] == MAIN_ADMIN_ID else ""
        text += f"• `{admin[0]}` - @{admin[1] or 'без username'} {mark}\n"
    text += "\n/addadmin ID - ДОБАВИТЬ\n/removeadmin ID - УДАЛИТЬ"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['addadmin'])
def add_admin(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ ТОЛЬКО ГЛАВНЫЙ АДМИНИСТРАТОР!")
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
        if new_admin_id not in ADMIN_IDS:
            ADMIN_IDS.append(new_admin_id)
        bot.send_message(message.chat.id, f"✅ АДМИНИСТРАТОР {new_admin_id} ДОБАВЛЕН!")
    except:
        bot.send_message(message.chat.id, "❌ ОШИБКА!")

@bot.message_handler(commands=['removeadmin'])
def remove_admin(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ ТОЛЬКО ГЛАВНЫЙ АДМИНИСТРАТОР!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /removeadmin 123456789")
            return
        remove_id = int(parts[1])
        if remove_id == MAIN_ADMIN_ID:
            bot.send_message(message.chat.id, "❌ НЕЛЬЗЯ УДАЛИТЬ ГЛАВНОГО АДМИНИСТРАТОРА!")
            return
        cursor = db.connection.cursor()
        cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (remove_id,))
        db.connection.commit()
        if remove_id in ADMIN_IDS:
            ADMIN_IDS.remove(remove_id)
        bot.send_message(message.chat.id, f"✅ АДМИНИСТРАТОР {remove_id} УДАЛЕН!")
    except:
        bot.send_message(message.chat.id, "❌ ОШИБКА!")

# Крипто-настройки
@bot.message_handler(func=lambda message: message.text == "⚙️ КРИПТО-НАСТРОЙКИ" and is_admin(message.from_user.id))
def crypto_settings(message: Message):
    markup_percent = get_markup_percent()
    usdt_rate = get_usdt_rate()
    text = f"🪙 **КРИПТО-НАСТРОЙКИ**\n\n📈 КОМИССИЯ: {markup_percent}%\n💱 КУРС USDT: {usdt_rate}₽\n\nИЗМЕНИТЬ КОМИССИЮ: `/set_markup 35`"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['set_markup'])
def set_markup(message: Message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ НЕТ ПРАВ!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /set_markup 35")
            return
        new_markup = int(parts[1])
        if new_markup < 0 or new_markup > 100:
            bot.send_message(message.chat.id, "❌ КОМИССИЯ ОТ 0 ДО 100%")
            return
        set_markup_percent(new_markup)
        bot.send_message(message.chat.id, f"✅ КОМИССИЯ ИЗМЕНЕНА НА {new_markup}%")
    except:
        bot.send_message(message.chat.id, "❌ ОШИБКА!")

# ============================================
# НАВИГАЦИЯ
# ============================================
@bot.callback_query_handler(func=lambda call: call.data == "back_to_buy")
def back_to_buy(call: CallbackQuery):
    bot.edit_message_text("🔑 **ВЫБЕРИТЕ ТИП КЛЮЧА:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=buy_key_menu())

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call: CallbackQuery):
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🏠 **ГЛАВНОЕ МЕНЮ**", parse_mode="Markdown", reply_markup=main_menu(is_admin(call.from_user.id)))

@bot.message_handler(func=lambda message: message.text == "◀️ НАЗАД В МЕНЮ")
def back_to_main(message: Message):
    bot.send_message(message.chat.id, "🏠 **ГЛАВНОЕ МЕНЮ**", parse_mode="Markdown", reply_markup=main_menu(is_admin(message.from_user.id)))

# ============================================
# FLASK ПРИЛОЖЕНИЕ ДЛЯ ВЕБХУКОВ
# ============================================
@app.route('/', methods=['GET'])
def index():
    return "БОТ РАБОТАЕТ!", 200

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
        if data.get('status') == "CONFIRMED":
            payload = data.get('payload', '')
            if payload.startswith('balance_'):
                parts = payload.split('_')
                if len(parts) >= 3:
                    user_id = int(parts[1])
                    amount = float(parts[2])
                    update_user_balance(user_id, amount)
                    bot.send_message(user_id, f"✅ **БАЛАНС ПОПОЛНЕН НА {amount}₽!**")
            elif payload.startswith('donate_'):
                parts = payload.split('_')
                if len(parts) >= 2:
                    user_id = int(parts[1])
                    bot.send_message(user_id, "❤️ **СПАСИБО ЗА ПОДДЕРЖКУ!**")
        return jsonify({"status": "ok"}), 200
    except:
        return jsonify({"status": "error"}), 500

@app.route('/crypto_webhook', methods=['POST'])
def crypto_webhook():
    try:
        data = request.json
        if data.get('payload', '').startswith('deposit_'):
            parts = data['payload'].split('_')
            if len(parts) >= 3:
                user_id = int(parts[1])
                amount = float(parts[2])
                update_user_balance(user_id, amount)
                bot.send_message(user_id, f"✅ **БАЛАНС ПОПОЛНЕН НА {amount}₽!**")
        return jsonify({"ok": True}), 200
    except:
        return jsonify({"ok": False}), 200

# ============================================
# ЗАПУСК
# ============================================
if __name__ == '__main__':
    get_usdt_rate()
    print("=" * 60)
    print("🚀 БОТ ЗАПУЩЕН")
    print(f"🤖 БОТ: @KeeperMag_bot")
    print(f"👑 ГЛАВНЫЙ АДМИН: {MAIN_ADMIN_ID}")
    print(f"👥 АДМИНИСТРАТОРЫ: {ADMIN_IDS}")
    print(f"📡 PLATEGA WEBHOOK: {RAILWAY_URL}/webhook")
    print(f"🪙 CRYPTOBOT WEBHOOK: {RAILWAY_URL}/crypto_webhook")
    print(f"💰 КОМИССИЯ: {get_markup_percent()}%")
    print(f"💱 КУРС USDT: {get_usdt_rate()}₽")
    print("=" * 60)
    
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": f"{RAILWAY_URL}/telegram_webhook"})
        print("✅ WEBHOOK УСТАНОВЛЕН")
    except Exception as e:
        print(f"⚠️ ОШИБКА: {e}")
    
    app.run(host='0.0.0.0', port=5000)
