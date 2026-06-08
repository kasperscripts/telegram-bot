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

# НАЦЕНКА НА КРИПТОПЛАТЕЖИ (ТОЛЬКО ДЛЯ ПОПОЛНЕНИЯ БАЛАНСА)
CRYPTO_MARKUP_PERCENT = 30

# ГРУППЫ ДЛЯ ПОДПИСЧИКОВ
VIP_GROUP_ID = -1003709565134
LITE_GROUP_ID = -1003709565134

MAIN_ADMIN_ID = 1302493787
ADMIN_IDS = [1302493787, 6784034490]  # Добавьте сюда всех админов

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

# Цены на подписки
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
# ФУНКЦИИ ДЛЯ РАБОТЫ С БАЛАНСОМ И ПОДПИСКАМИ
# ============================================
def get_user_balance(user_id):
    user = db.get_user(user_id)
    if user:
        return user[2]  # balance
    return 0

def update_user_balance(user_id, amount):
    db.update_balance(user_id, amount)

def activate_subscription_from_balance(user_id, sub_type, days):
    price_key = f"{sub_type}_{days}day"
    price = PRICES.get(price_key, 0)
    
    balance = get_user_balance(user_id)
    if balance >= price:
        # Списываем деньги
        update_user_balance(user_id, -price)
        # Активируем подписку
        end_date = db.activate_subscription(user_id, sub_type, days)
        return True, end_date
    return False, None

def get_subscription_info(user_id):
    return db.check_subscription(user_id)

def is_admin(user_id):
    return user_id in ADMIN_IDS

def is_main_admin(user_id):
    return user_id == MAIN_ADMIN_ID

# ============================================
# ФУНКЦИИ ДЛЯ РАСЧЕТА СУММ (С НАЦЕНКОЙ ДЛЯ ПОПОЛНЕНИЯ)
# ============================================
def calculate_crypto_amount_with_markup(rub_amount):
    usdt_rate = get_usdt_rate()
    markup_percent = get_markup_percent()
    final_rub = rub_amount * (1 + markup_percent / 100)
    usdt_amount = final_rub / usdt_rate
    return round(usdt_amount, 2), usdt_rate, markup_percent, final_rub

# ============================================
# ПЛАТЕЖИ ЧЕРЕЗ PLATEGA (ПОПОЛНЕНИЕ БАЛАНСА)
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
        "description": f"Пополнение баланса {user_id}",
        "return": "https://t.me/KeeperMag_bot",
        "failedUrl": "https://t.me/KeeperMag_bot",
        "payload": f"balance_{user_id}_{order_id}",
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

# ============================================
# ПЛАТЕЖИ ЧЕРЕЗ CRYPTOBOT (ПОПОЛНЕНИЕ БАЛАНСА С НАЦЕНКОЙ)
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

# ============================================
# КЛАВИАТУРЫ
# ============================================
def main_menu(user_is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("🌟 Купить подписку"),
        KeyboardButton("💰 Пополнить баланс"),
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
        InlineKeyboardButton("🌟 LITE подписка", callback_data="buy_lite"),
        InlineKeyboardButton("👑 VIP подписка", callback_data="buy_vip")
    )
    return markup

def buy_subscription_buttons(sub_type):
    markup = InlineKeyboardMarkup(row_width=2)
    if sub_type == "lite":
        markup.add(
            InlineKeyboardButton(f"1 день - {PRICES['lite_1day']}₽", callback_data="subscribe_lite_1day"),
            InlineKeyboardButton(f"7 дней - {PRICES['lite_7day']}₽", callback_data="subscribe_lite_7day")
        )
    else:
        markup.add(
            InlineKeyboardButton(f"1 день - {PRICES['vip_1day']}₽", callback_data="subscribe_vip_1day"),
            InlineKeyboardButton(f"7 дней - {PRICES['vip_7day']}₽", callback_data="subscribe_vip_7day"),
            InlineKeyboardButton(f"14 дней - {PRICES['vip_14day']}₽", callback_data="subscribe_vip_14day")
        )
    markup.add(InlineKeyboardButton("◀️ Назад", callback_data="back_to_choice"))
    return markup

def deposit_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("100 ₽", callback_data="deposit_100"),
        InlineKeyboardButton("250 ₽", callback_data="deposit_250"),
        InlineKeyboardButton("500 ₽", callback_data="deposit_500"),
        InlineKeyboardButton("1000 ₽", callback_data="deposit_1000"),
        InlineKeyboardButton("Другая сумма", callback_data="deposit_custom")
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
        KeyboardButton("➕ Добавить ключи"),
        KeyboardButton("📋 Список ключей"),
        KeyboardButton("💰 Изменить цены"),
        KeyboardButton("📊 Статистика"),
        KeyboardButton("👥 Управление админами"),
        KeyboardButton("⚙️ Крипто-настройки"),
        KeyboardButton("◀️ Назад в меню")
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
    bot.send_message(call.message.chat.id, "✅ **Отзыв отправлен на модерацию!**", parse_mode="Markdown")
    if call.from_user.id in user_states:
        del user_states[call.from_user.id]

# ============================================
# ПОПОЛНЕНИЕ БАЛАНСА
# ============================================
@bot.message_handler(func=lambda message: message.text == "💰 Пополнить баланс")
def deposit_menu(message: Message):
    bot.send_message(message.chat.id, "💰 **Выберите сумму пополнения:**", parse_mode="Markdown", reply_markup=deposit_buttons())

@bot.callback_query_handler(func=lambda call: call.data.startswith("deposit_"))
def process_deposit(call: CallbackQuery):
    amount = call.data.split("_")[1]
    if amount == "custom":
        msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму пополнения (в рублях):**\nМинимальная сумма: 100₽", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_custom_deposit)
    else:
        amount = int(amount)
        ask_payment_method(call.message.chat.id, call.from_user.id, amount)

def process_custom_deposit(message: Message):
    try:
        amount = int(message.text.strip())
        if amount < 100:
            bot.send_message(message.chat.id, "❌ Минимальная сумма пополнения 100₽")
            return
        ask_payment_method(message.chat.id, message.from_user.id, amount)
    except:
        bot.send_message(message.chat.id, "❌ Введите число!")

def ask_payment_method(chat_id, user_id, amount):
    usdt_amount, usdt_rate, markup_percent, final_rub = calculate_crypto_amount_with_markup(amount)
    text = f"💰 **Пополнение на {amount}₽**\n\nВыберите способ оплаты:"
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💳 Platega (СБП/Карта)", callback_data=f"deposit_platega_{amount}"),
        InlineKeyboardButton(f"🪙 Криптовалюта USDT ({usdt_amount} USDT)", callback_data=f"deposit_crypto_{amount}"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_to_deposit")
    )
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("deposit_platega_"))
def deposit_platega(call: CallbackQuery):
    amount = int(call.data.split("_")[2])
    result = create_platega_payment(amount, call.from_user.id, f"deposit_{int(datetime.now().timestamp())}")
    if result["success"]:
        user_states[f"deposit_{result['transaction_id']}"] = {"user_id": call.from_user.id, "amount": amount}
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=result["payment_url"]))
        markup.add(InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data=f"check_deposit_{result['transaction_id']}"))
        bot.edit_message_text(f"💳 **Счет на {amount}₽**\n👇 Оплатите", call.message.chat.id, call.message.message_id, reply_markup=markup)
    else:
        bot.edit_message_text(f"❌ Ошибка: {result.get('error')}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("deposit_crypto_"))
def deposit_crypto(call: CallbackQuery):
    rub_amount = int(call.data.split("_")[2])
    usdt_amount, usdt_rate, markup_percent, final_rub = calculate_crypto_amount_with_markup(rub_amount)
    
    result = create_cryptobot_payment(usdt_amount, call.from_user.id, f"Пополнение баланса {rub_amount}₽ (с комиссией {markup_percent}%)", f"deposit_{call.from_user.id}_{rub_amount}")
    
    if result["success"]:
        user_states[f"deposit_crypto_{result['transaction_id']}"] = {"user_id": call.from_user.id, "amount": rub_amount}
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🪙 ОПЛАТИТЬ USDT", url=result["payment_url"]))
        markup.add(InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data=f"check_deposit_crypto_{result['transaction_id']}"))
        bot.edit_message_text(
            f"🪙 **Крипто-счет**\n\n"
            f"💰 Сумма пополнения: {rub_amount}₽\n"
            f"📈 Комиссия {markup_percent}%: {rub_amount * markup_percent / 100:.2f}₽\n"
            f"💵 Итого: {final_rub:.2f}₽\n"
            f"🪙 {usdt_amount} USDT\n"
            f"💱 Курс: {usdt_rate}₽\n\n"
            f"👇 Оплатите",
            call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup
        )
    else:
        bot.edit_message_text(f"❌ Ошибка: {result.get('error')}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_deposit_"))
def check_deposit(call: CallbackQuery):
    transaction_id = call.data.split("_")[2]
    status = check_platega_payment(transaction_id)
    if status == "CONFIRMED":
        data = user_states.get(f"deposit_{transaction_id}", {})
        if data.get("user_id") and data.get("amount"):
            update_user_balance(data["user_id"], data["amount"])
            bot.send_message(data["user_id"], f"✅ **Баланс пополнен на {data['amount']}₽!**")
        bot.answer_callback_query(call.id, "✅ Оплата подтверждена!")
        bot.send_message(call.message.chat.id, "✅ Баланс пополнен!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "⏳ Еще не оплачено", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_deposit_crypto_"))
def check_deposit_crypto(call: CallbackQuery):
    invoice_id = call.data.split("_")[3]
    status = check_cryptobot_payment(invoice_id)
    if status == "paid":
        data = user_states.get(f"deposit_crypto_{invoice_id}", {})
        if data.get("user_id") and data.get("amount"):
            update_user_balance(data["user_id"], data["amount"])
            bot.send_message(data["user_id"], f"✅ **Баланс пополнен на {data['amount']}₽!**")
        bot.answer_callback_query(call.id, "✅ Оплата подтверждена!")
        bot.send_message(call.message.chat.id, "✅ Баланс пополнен!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "⏳ Еще не оплачено", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_deposit")
def back_to_deposit(call: CallbackQuery):
    bot.edit_message_text("💰 **Выберите сумму пополнения:**", call.message.chat.id, call.message.message_id, reply_markup=deposit_buttons())

# ============================================
# ПОКУПКА ПОДПИСКИ (С БАЛАНСА)
# ============================================
@bot.message_handler(func=lambda message: message.text == "🌟 Купить подписку")
def buy_subscription_menu(message: Message):
    bot.send_message(message.chat.id, "🌟 **Выберите тип подписки:**", parse_mode="Markdown", reply_markup=choose_subscription_type())

@bot.callback_query_handler(func=lambda call: call.data == "buy_lite")
def buy_lite(call: CallbackQuery):
    bot.edit_message_text("🌟 **LITE подписка**\nВыберите период:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=buy_subscription_buttons("lite"))

@bot.callback_query_handler(func=lambda call: call.data == "buy_vip")
def buy_vip(call: CallbackQuery):
    bot.edit_message_text("👑 **VIP подписка**\nВыберите период:", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=buy_subscription_buttons("vip"))

@bot.callback_query_handler(func=lambda call: call.data.startswith("subscribe_"))
def process_subscription(call: CallbackQuery):
    _, sub_type, days = call.data.split("_")
    days = int(days.replace("day", ""))
    price = PRICES[f"{sub_type}_{days}day"]
    
    balance = get_user_balance(call.from_user.id)
    if balance >= price:
        success, end_date = activate_subscription_from_balance(call.from_user.id, sub_type, days)
        if success:
            group_link = create_group_link(sub_type)
            group_text = f"\n\n📦 **Ссылка на группу:**\n{group_link}\n⚠️ Одноразовая!" if group_link else ""
            bot.send_message(
                call.from_user.id,
                f"✅ **Подписка активирована!**\n\n"
                f"📦 {sub_type.upper()} {days} д.\n"
                f"⏰ Действует до: {end_date.strftime('%d.%m.%Y %H:%M')}\n"
                f"💰 Остаток на балансе: {get_user_balance(call.from_user.id)}₽"
                f"{group_text}",
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id, "✅ Подписка активирована!")
            bot.delete_message(call.message.chat.id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка активации", show_alert=True)
    else:
        bot.answer_callback_query(call.id, f"❌ Недостаточно средств! Нужно {price}₽, у вас {balance}₽", show_alert=True)

# ============================================
# ПРОФИЛЬ
# ============================================
@bot.message_handler(func=lambda message: message.text == "👤 Мой профиль")
def profile(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "❌ Ошибка! Пользователь не найден.")
        return
    
    balance = user[2]
    sub_type, end_date = db.check_subscription(message.from_user.id)
    
    text = f"👤 **Ваш профиль**\n\n"
    text += f"🆔 ID: {user[0]}\n"
    text += f"💰 Баланс: {balance}₽\n\n"
    
    if sub_type:
        days_left = (end_date - datetime.now()).days
        hours_left = (end_date - datetime.now()).seconds // 3600
        text += f"📅 **Подписка:** {sub_type.upper()}\n"
        text += f"⏰ Действует до: {end_date.strftime('%d.%m.%Y %H:%M')}\n"
        text += f"⌛ Осталось: {days_left} д. {hours_left} ч.\n"
    else:
        text += "❌ Нет активной подписки\n"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ============================================
# ДОНАТЫ (БЕЗ КОМИССИИ)
# ============================================
@bot.message_handler(func=lambda message: message.text == "❤️ Пожертвовать")
def donate_menu(message: Message):
    text = (
        "❤️ **ПОДДЕРЖАТЬ ПРОЕКТ**\n\n"
        "💰 Минимальная сумма: 10₽\n"
        "✨ Комиссия не взимается\n\n"
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
    msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму (в рублях):**\nМинимальная: 10₽", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_donate_platega)

def process_donate_platega(message: Message):
    try:
        amount = float(message.text.strip())
        if amount < 10:
            bot.send_message(message.chat.id, "❌ Минимальная сумма 10₽")
            return
        result = create_platega_payment(amount, message.from_user.id, f"donate_{int(datetime.now().timestamp())}")
        if result["success"]:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=result["payment_url"]))
            bot.send_message(message.chat.id, f"❤️ **Спасибо!**\n💰 {amount}₽", parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, f"❌ Ошибка: {result.get('error')}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")

@bot.callback_query_handler(func=lambda call: call.data == "donate_crypto")
def donate_crypto(call: CallbackQuery):
    msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму (в рублях):**\nМинимальная: 10₽\n✨ Без комиссии", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_donate_crypto)

def process_donate_crypto(message: Message):
    try:
        rub_amount = float(message.text.strip())
        if rub_amount < 10:
            bot.send_message(message.chat.id, "❌ Минимальная сумма 10₽")
            return
        
        usdt_amount, usdt_rate = rub_amount / get_usdt_rate(), get_usdt_rate()
        usdt_amount = round(usdt_amount, 2)
        
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
                f"👇 Оплатите",
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            bot.send_message(message.chat.id, f"❌ Ошибка: {result.get('error')}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")

# ============================================
# ИНФОРМАЦИЯ
# ============================================
@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация")
def info_menu(message: Message):
    markup_percent = get_markup_percent()
    usdt_rate = get_usdt_rate()
    text = (
        "ℹ️ **ИНФОРМАЦИЯ**\n\n"
        "🤖 **Бот для продажи подписок LITE и VIP**\n\n"
        "💳 **Пополнение баланса:**\n"
        "• Platega (СБП/карты) - без комиссии\n"
        f"• Криптовалюта USDT - комиссия {markup_percent}%\n\n"
        "💱 **Курс USDT:** {usdt_rate}₽\n\n"
        "📌 **Как пользоваться:**\n"
        "1. Пополните баланс\n"
        "2. Купите подписку\n"
        "3. Получите ключ и доступ в группу\n\n"
        "📞 **КОНТАКТЫ:**\n"
        f"• Поддержка: @{SUPPORT_USERNAME}\n"
        f"• Канал: {MAIN_CHANNEL}\n"
        f"• Отзывы: {REVIEWS_CHANNEL}\n\n"
        "⚖️ **ДОКУМЕНТЫ:**\n"
        "• Политика конфиденциальности\n"
        "• Пользовательское соглашение"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=info_buttons())

# ============================================
# АДМИН-ПАНЕЛЬ
# ============================================
@bot.message_handler(func=lambda message: message.text == "⚙️ Админ-панель" and is_admin(message.from_user.id))
def admin_panel(message: Message):
    bot.send_message(message.chat.id, "⚙️ **Админ-панель**", parse_mode="Markdown", reply_markup=admin_menu())

@bot.message_handler(commands=['addadmin'])
def add_admin_command(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Только главный администратор!")
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
        global ADMIN_IDS
        if new_admin_id not in ADMIN_IDS:
            ADMIN_IDS.append(new_admin_id)
        bot.send_message(message.chat.id, f"✅ Администратор {new_admin_id} добавлен!")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Только главный администратор!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ /removeadmin 123456789")
            return
        remove_id = int(parts[1])
        if remove_id == MAIN_ADMIN_ID:
            bot.send_message(message.chat.id, "❌ Нельзя удалить главного администратора!")
            return
        cursor = db.connection.cursor()
        cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (remove_id,))
        db.connection.commit()
        global ADMIN_IDS
        if remove_id in ADMIN_IDS:
            ADMIN_IDS.remove(remove_id)
        bot.send_message(message.chat.id, f"✅ Администратор {remove_id} удален!")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(func=lambda message: message.text == "👥 Управление админами" and is_admin(message.from_user.id))
def manage_admins_menu(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Только главный администратор!")
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

@bot.message_handler(func=lambda message: message.text == "⚙️ Крипто-настройки" and is_admin(message.from_user.id))
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

@bot.message_handler(func=lambda message: message.text == "➕ Добавить ключи" and is_admin(message.from_user.id))
def add_keys(message: Message):
    msg = bot.send_message(message.chat.id, "📝 **Введите ключи**\n\nФормат: `КЛЮЧ lite 1`\nКаждый ключ с новой строки:\n\nПример:\n`ABC123 lite 1`\n`DEF456 vip 7`", parse_mode="Markdown")
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
    bot.send_message(message.chat.id, f"✅ **Добавлено ключей: {added}**", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📋 Список ключей" and is_admin(message.from_user.id))
def list_keys(message: Message):
    keys = db.get_all_keys()
    if not keys:
        bot.send_message(message.chat.id, "📭 **Нет ключей**", parse_mode="Markdown")
        return
    
    text = "🔑 **СПИСОК КЛЮЧЕЙ:**\n\n"
    for key in keys:
        key_id, key_code, sub_type, days, is_used, used_by = key
        status = "✅ АКТИВЕН" if not is_used else f"❌ ИСПОЛЬЗОВАН (пользователь {used_by})"
        text += f"`{key_code}` - {sub_type.upper()} {days}д. - {status}\n"
    
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            bot.send_message(message.chat.id, text[i:i+4000], parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "💰 Изменить цены" and is_admin(message.from_user.id))
def change_prices_menu(message: Message):
    text = "💰 **Текущие цены:**\n\n"
    for key, price in PRICES.items():
        sub_type, days = key.split("_")
        days_num = days.replace("day", "")
        text += f"• {sub_type.upper()} {days_num} д.: {price}₽\n"
    text += "\n**Изменить цену:**\nОтправьте: `lite_1day:150`"
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, update_price)

def update_price(message: Message):
    try:
        if ' ' in message.text:
            key, new_price = message.text.split(' ')
        elif ':' in message.text:
            key, new_price = message.text.split(':')
        else:
            bot.send_message(message.chat.id, "❌ Формат: `lite_1day 150` или `lite_1day:150`")
            return
        new_price = int(new_price)
        if key in PRICES:
            PRICES[key] = new_price
            cursor = db.connection.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (f"price_{key}", str(new_price)))
            db.connection.commit()
            bot.send_message(message.chat.id, f"✅ Цена {key} = {new_price}₽")
        else:
            bot.send_message(message.chat.id, f"❌ Неверный ключ! Доступны: {', '.join(PRICES.keys())}")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(func=lambda message: message.text == "📊 Статистика" and is_admin(message.from_user.id))
def show_stats(message: Message):
    stats = db.get_stats()
    cursor = db.connection.cursor()
    cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'confirmed'")
    total_income = cursor.fetchone()[0] or 0
    total_users = stats.get('total_users', 0)
    active_subs = stats.get('active_subs', 0)
    
    text = f"📊 **СТАТИСТИКА**\n\n💰 Доход: {total_income}₽\n👥 Пользователей: {total_users}\n✅ Активных подписок: {active_subs}"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "◀️ Назад в меню")
def back_to_main(message: Message):
    bot.send_message(message.chat.id, "🏠 **Главное меню**", parse_mode="Markdown", reply_markup=main_menu(is_admin(message.from_user.id)))

@bot.callback_query_handler(func=lambda call: call.data == "back_to_choice")
def back_to_choice(call: CallbackQuery):
    bot.edit_message_text("🌟 **Выберите тип подписки:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=choose_subscription_type())

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call: CallbackQuery):
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🏠 **Главное меню**", parse_mode="Markdown", reply_markup=main_menu(is_admin(call.from_user.id)))

# ============================================
# ФУНКЦИЯ ДЛЯ ВЫДАЧИ ССЫЛКИ НА ГРУППУ
# ============================================
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
# FLASK ПРИЛОЖЕНИЕ ДЛЯ ВЕБХУКОВ
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
        if data.get('status') == "CONFIRMED":
            payload = data.get('payload', '')
            if payload.startswith('balance_'):
                parts = payload.split('_')
                if len(parts) >= 3:
                    user_id = int(parts[1])
                    amount = float(parts[2]) if parts[2].isdigit() else 0
                    if amount > 0:
                        update_user_balance(user_id, amount)
                        bot.send_message(user_id, f"✅ **Баланс пополнен на {amount}₽!**")
            elif payload.startswith('donate_'):
                parts = payload.split('_')
                if len(parts) >= 2:
                    user_id = int(parts[1])
                    bot.send_message(user_id, "❤️ **Спасибо за поддержку!**")
            elif payload.startswith('user_'):
                parts = payload.split('_')
                if len(parts) >= 4:
                    user_id = int(parts[1])
                    sub_type = parts[2]
                    days = int(parts[3].replace('day', ''))
                    db.activate_subscription(user_id, sub_type, days)
                    group_link = create_group_link(sub_type)
                    group_text = f"\n\n📦 **Ссылка на группу:**\n{group_link}\n⚠️ Одноразовая!" if group_link else ""
                    bot.send_message(user_id, f"✅ **Подписка активирована!**\n📦 {sub_type.upper()} {days} д.{group_text}")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Ошибка вебхука: {e}")
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
                bot.send_message(user_id, f"✅ **Баланс пополнен на {amount}₽!**")
        elif data.get('payload', '').startswith('donate_'):
            parts = data['payload'].split('_')
            if len(parts) >= 2:
                user_id = int(parts[1])
                bot.send_message(user_id, "❤️ **Спасибо за поддержку!**")
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
    print(f"🤖 Бот: @KeeperMag_bot")
    print(f"👑 Главный админ: {MAIN_ADMIN_ID}")
    print(f"👥 Администраторы: {ADMIN_IDS}")
    print(f"📡 Platega webhook: {RAILWAY_URL}/webhook")
    print(f"🪙 CryptoBot webhook: {RAILWAY_URL}/crypto_webhook")
    print(f"💰 Комиссия: {get_markup_percent()}%")
    print(f"💱 Курс USDT: {get_usdt_rate()}₽")
    print("=" * 60)
    
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": f"{RAILWAY_URL}/telegram_webhook"})
        print("✅ Webhook установлен")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
    
    app.run(host='0.0.0.0', port=5000)
