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

# НАЦЕНКА НА КРИПТОПЛАТЕЖИ (30%)
CRYPTO_MARKUP_PERCENT = 30
USDT_RATE = 100  # 1 USDT = 100 RUB

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
        if sub_type == "vip":
            group_id = VIP_GROUP_ID
        else:
            group_id = LITE_GROUP_ID
        
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
# ФУНКЦИЯ ДЛЯ РАСЧЕТА СУММЫ С НАЦЕНКОЙ (КРИПТА)
# ============================================
def calculate_crypto_amount(rub_amount):
    """Расчет суммы в USDT с наценкой 30%"""
    rub_with_markup = rub_amount * (1 + CRYPTO_MARKUP_PERCENT / 100)
    usdt_amount = rub_with_markup / USDT_RATE
    return round(usdt_amount, 2)

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
        "paymentDetails": {
            "amount": float(amount),
            "currency": "RUB"
        },
        "description": f"Подписка {order_id} для {user_id}",
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
        else:
            return {"success": False, "error": f"Ошибка {response.status_code}: {response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def check_platega_payment(transaction_id):
    headers = {
        "X-MerchantId": PLATEGA_MERCHANT_ID,
        "X-Secret": PLATEGA_API_SECRET
    }
    
    try:
        response = requests.get(f"{PLATEGA_API_URL}/transaction/{transaction_id}", headers=headers, timeout=30)
        
        if response.status_code == 200:
            return response.json().get("status")
        return None
    except:
        return None

# ============================================
# ПЛАТЕЖИ ЧЕРЕЗ CRYPTOBOT (С НАЦЕНКОЙ 30%)
# ============================================
def create_cryptobot_payment(rub_amount, user_id, order_id):
    """Создает счет в USDT с наценкой 30%"""
    
    usdt_amount = calculate_crypto_amount(rub_amount)
    
    headers = {
        "Content-Type": "application/json",
        "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN
    }
    
    data = {
        "asset": "USDT",
        "amount": usdt_amount,
        "description": f"Подписка {order_id} (включая комиссию {CRYPTO_MARKUP_PERCENT}%)",
        "paid_btn_name": "callback",
        "paid_btn_url": f"{RAILWAY_URL}/payment_success",
        "payload": f"user_{user_id}_{order_id}"
    }
    
    try:
        response = requests.post(f"{CRYPTOBOT_API_URL}/createInvoice", headers=headers, json=data, timeout=30)
        print(f"Ответ CryptoBot: {response.status_code} - {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                invoice = result.get("result")
                return {
                    "success": True,
                    "payment_url": invoice.get("pay_url"),
                    "transaction_id": str(invoice.get("invoice_id")),
                    "usdt_amount": usdt_amount,
                    "rub_original": rub_amount,
                    "rub_with_markup": rub_amount * (1 + CRYPTO_MARKUP_PERCENT / 100)
                }
        return {"success": False, "error": f"Ошибка {response.status_code}: {response.text}"}
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
                    if status == "paid":
                        return "paid"
                    elif status == "active":
                        return "pending"
        return None
    except Exception as e:
        print(f"Ошибка проверки: {e}")
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
    crypto_usdt = calculate_crypto_amount(amount)
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💳 Platega (СБП/Карта)", callback_data=f"pay_platega_{sub_type}_{days}_{amount}"),
        InlineKeyboardButton(f"🪙 Криптовалюта USDT ({crypto_usdt} USDT)", callback_data=f"pay_crypto_{sub_type}_{days}_{amount}"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_to_choice")
    )
    return markup

def lite_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    lite_1day_count = get_key_count("lite", 1)
    lite_7day_count = get_key_count("lite", 7)
    
    markup.add(
        InlineKeyboardButton(f"1 день - {PRICES['lite_1day']}₽ ({lite_1day_count} шт)", callback_data="select_lite_1day"),
        InlineKeyboardButton(f"7 дней - {PRICES['lite_7day']}₽ ({lite_7day_count} шт)", callback_data="select_lite_7day")
    )
    return markup

def vip_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    vip_1day_count = get_key_count("vip", 1)
    vip_7day_count = get_key_count("vip", 7)
    vip_14day_count = get_key_count("vip", 14)
    
    markup.add(
        InlineKeyboardButton(f"1 день - {PRICES['vip_1day']}₽ ({vip_1day_count} шт)", callback_data="select_vip_1day"),
        InlineKeyboardButton(f"7 дней - {PRICES['vip_7day']}₽ ({vip_7day_count} шт)", callback_data="select_vip_7day"),
        InlineKeyboardButton(f"14 дней - {PRICES['vip_14day']}₽ ({vip_14day_count} шт)", callback_data="select_vip_14day")
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
# ДОНАТЫ
# ============================================
@bot.message_handler(func=lambda message: message.text == "❤️ Пожертвовать")
def donate_menu(message: Message):
    text = (
        "❤️ **ПОДДЕРЖАТЬ ПРОЕКТ**\n\n"
        "Вы можете помочь развитию проекта.\n\n"
        "💰 Минимальная сумма: 10₽\n\n"
        "Выберите способ оплаты:"
    )
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("💳 Platega", callback_data="donate_platega"),
        InlineKeyboardButton("🪙 Криптовалюта USDT", callback_data="donate_crypto")
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "donate_platega")
def donate_platega(call: CallbackQuery):
    msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму пожертвования (в рублях):**\n\nМинимальная сумма: 10₽", parse_mode="Markdown")
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
            bot.send_message(
                message.chat.id,
                f"❤️ **Спасибо за поддержку!**\n\n💰 Сумма: {amount}₽\n\n👇 Нажмите для оплаты",
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            bot.send_message(message.chat.id, f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")

@bot.callback_query_handler(func=lambda call: call.data == "donate_crypto")
def donate_crypto(call: CallbackQuery):
    msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму пожертвования (в рублях):**\n\nМинимальная сумма: 10₽\n\n(Сумма будет автоматически сконвертирована в USDT с наценкой 30%)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_donate_crypto)

def process_donate_crypto(message: Message):
    try:
        rub_amount = float(message.text.strip())
        if rub_amount < 10:
            bot.send_message(message.chat.id, "❌ Минимальная сумма 10₽")
            return
        
        usdt_amount = calculate_crypto_amount(rub_amount)
        
        result = create_cryptobot_payment(rub_amount, message.from_user.id, "donate")
        
        if result["success"]:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🪙 ОПЛАТИТЬ USDT", url=result["payment_url"]))
            bot.send_message(
                message.chat.id,
                f"❤️ **Спасибо за поддержку!**\n\n"
                f"💰 Исходная сумма: {rub_amount}₽\n"
                f"🪙 К оплате: {result['usdt_amount']} USDT\n"
                f"📈 Включая комиссию {CRYPTO_MARKUP_PERCENT}%\n\n"
                f"👇 Нажмите для оплаты криптовалютой",
                parse_mode="Markdown",
                reply_markup=markup
            )
        else:
            bot.send_message(message.chat.id, f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
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
    bot.send_message(user_id, "🤖 Добро пожаловать!\n\n🌟 Бот для продажи подписок LITE и VIP.\n💳 Оплата через Platega или криптовалютой USDT (с комиссией 30%)", reply_markup=main_menu(is_admin(user_id)))

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
    bot.edit_message_text("🌟 **LITE подписка**\n\n(количество ключей указано в скобках)", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=lite_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data == "choose_vip")
def choose_vip(call: CallbackQuery):
    bot.edit_message_text("👑 **VIP подписка**\n\n(количество ключей указано в скобках)", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=vip_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_lite_"))
def select_lite_duration(call: CallbackQuery):
    days = 1 if call.data == "select_lite_1day" else 7
    amount = PRICES[f"lite_{days}day"]
    bot.edit_message_text(
        f"🌟 **LITE подписка {days} день/дней**\n\n💰 Сумма: {amount}₽\n\nВыберите способ оплаты:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=choose_payment_method("lite", days, amount)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_vip_"))
def select_vip_duration(call: CallbackQuery):
    days = int(call.data.split("_")[2].replace("day", ""))
    amount = PRICES[f"vip_{days}day"]
    bot.edit_message_text(
        f"👑 **VIP подписка {days} день/дней**\n\n💰 Сумма: {amount}₽\n\nВыберите способ оплаты:",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=choose_payment_method("vip", days, amount)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_platega_"))
def process_platega_payment(call: CallbackQuery):
    _, _, sub_type, days, amount = call.data.split("_")
    days = int(days)
    amount = float(amount)
    
    reserved_key = reserve_key(sub_type, days, call.from_user.id)
    if not reserved_key:
        bot.answer_callback_query(call.id, "❌ Ключи закончились!", show_alert=True)
        return
    
    order_id = f"{sub_type}_{days}day"
    result = create_platega_payment(amount, call.from_user.id, order_id)
    
    if result["success"]:
        user_states[f"payment_{result['transaction_id']}"] = {
            "user_id": call.from_user.id,
            "sub_type": sub_type,
            "days": days,
            "key": reserved_key,
            "amount": amount,
            "method": "platega"
        }
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=result["payment_url"]))
        markup.add(InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data=f"check_platega_{result['transaction_id']}"))
        markup.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data=f"cancel_platega_{result['transaction_id']}"))
        
        bot.edit_message_text(
            f"💳 **Счет на {amount}₽**\n\n"
            f"📦 {sub_type.upper()} {days} д.\n"
            f"⏰ Ключ зарезервирован на 30 минут\n\n"
            f"👇 Нажмите для оплаты",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    else:
        release_key(call.from_user.id)
        bot.edit_message_text(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_crypto_"))
def process_crypto_payment(call: CallbackQuery):
    _, _, sub_type, days, rub_amount = call.data.split("_")
    days = int(days)
    rub_amount = float(rub_amount)
    
    reserved_key = reserve_key(sub_type, days, call.from_user.id)
    if not reserved_key:
        bot.answer_callback_query(call.id, "❌ Ключи закончились!", show_alert=True)
        return
    
    result = create_cryptobot_payment(rub_amount, call.from_user.id, f"{sub_type}_{days}day")
    
    if result["success"]:
        user_states[f"crypto_{result['transaction_id']}"] = {
            "user_id": call.from_user.id,
            "sub_type": sub_type,
            "days": days,
            "key": reserved_key,
            "rub_amount": rub_amount,
            "usdt_amount": result['usdt_amount'],
            "method": "crypto"
        }
        
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🪙 ОПЛАТИТЬ USDT", url=result["payment_url"]))
        markup.add(InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data=f"check_crypto_{result['transaction_id']}"))
        markup.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data=f"cancel_crypto_{result['transaction_id']}"))
        
        bot.edit_message_text(
            f"🪙 **Крипто-счет**\n\n"
            f"💰 Исходная сумма: {rub_amount}₽\n"
            f"🪙 К оплате: {result['usdt_amount']} USDT\n"
            f"📈 Включая комиссию {CRYPTO_MARKUP_PERCENT}%\n"
            f"📦 {sub_type.upper()} {days} д.\n"
            f"⏰ Ключ зарезервирован на 30 минут\n\n"
            f"👇 Нажмите для оплаты",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    else:
        release_key(call.from_user.id)
        bot.edit_message_text(f"❌ Ошибка криптоплатежа: {result.get('error', 'Попробуйте Platega')}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_platega_"))
def check_platega(call: CallbackQuery):
    transaction_id = call.data.split("_")[2]
    status = check_platega_payment(transaction_id)
    
    if status == "CONFIRMED":
        payment_data = user_states.get(f"payment_{transaction_id}", {})
        key = payment_data.get("key")
        sub_type = payment_data.get("sub_type")
        days = payment_data.get("days")
        user_id = payment_data.get("user_id")
        
        if key and user_id:
            db.activate_subscription(user_id, sub_type, days)
            group_link = create_group_link(sub_type)
            group_text = f"\n\n📦 **Ссылка для входа в группу:**\n{group_link}\n⚠️ Ссылка одноразовая!" if group_link else ""
            
            bot.send_message(
                user_id,
                f"✅ **Оплата подтверждена!**\n\n"
                f"🔑 Ваш ключ: `{key}`\n"
                f"📦 Подписка: {sub_type.upper()} {days} д.\n"
                f"{group_text}\n\n"
                f"Сохраните ключ!",
                parse_mode="Markdown"
            )
        
        bot.answer_callback_query(call.id, "✅ Оплата подтверждена!")
        bot.send_message(call.message.chat.id, "✅ Подписка активирована!")
        release_key(user_id)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        if f"payment_{transaction_id}" in user_states:
            del user_states[f"payment_{transaction_id}"]
    else:
        bot.answer_callback_query(call.id, "⏳ Еще не оплачено", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_crypto_"))
def check_crypto(call: CallbackQuery):
    invoice_id = call.data.split("_")[2]
    status = check_cryptobot_payment(invoice_id)
    
    if status == "paid":
        payment_data = user_states.get(f"crypto_{invoice_id}", {})
        key = payment_data.get("key")
        sub_type = payment_data.get("sub_type")
        days = payment_data.get("days")
        user_id = payment_data.get("user_id")
        
        if key and user_id:
            db.activate_subscription(user_id, sub_type, days)
            group_link = create_group_link(sub_type)
            group_text = f"\n\n📦 **Ссылка для входа в группу:**\n{group_link}\n⚠️ Ссылка одноразовая!" if group_link else ""
            
            bot.send_message(
                user_id,
                f"✅ **Оплата подтверждена!**\n\n"
                f"🔑 Ваш ключ: `{key}`\n"
                f"📦 Подписка: {sub_type.upper()} {days} д.\n"
                f"{group_text}\n\n"
                f"Сохраните ключ!",
                parse_mode="Markdown"
            )
        
        bot.answer_callback_query(call.id, "✅ Оплата подтверждена!")
        bot.send_message(call.message.chat.id, "✅ Подписка активирована!")
        release_key(user_id)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        if f"crypto_{invoice_id}" in user_states:
            del user_states[f"crypto_{invoice_id}"]
    else:
        bot.answer_callback_query(call.id, "⏳ Еще не оплачено", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_platega_"))
def cancel_platega(call: CallbackQuery):
    transaction_id = call.data.split("_")[2]
    release_key(call.from_user.id)
    bot.answer_callback_query(call.id, "❌ Оплата отменена")
    bot.edit_message_text("❌ Оплата отменена", call.message.chat.id, call.message.message_id)
    if f"payment_{transaction_id}" in user_states:
        del user_states[f"payment_{transaction_id}"]

@bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_crypto_"))
def cancel_crypto(call: CallbackQuery):
    invoice_id = call.data.split("_")[2]
    release_key(call.from_user.id)
    bot.answer_callback_query(call.id, "❌ Оплата отменена")
    bot.edit_message_text("❌ Оплата отменена", call.message.chat.id, call.message.message_id)
    if f"crypto_{invoice_id}" in user_states:
        del user_states[f"crypto_{invoice_id}"]

@bot.callback_query_handler(func=lambda call: call.data == "back_to_choice")
def back_to_choice(call: CallbackQuery):
    bot.edit_message_text("🌟 **Выберите тип подписки:**", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=choose_subscription_type())

@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация")
def info_menu(message: Message):
    text = (
        "ℹ️ **ИНФОРМАЦИЯ**\n\n"
        "🤖 **Бот для продажи подписок LITE и VIP**\n\n"
        "💳 **Способы оплаты:**\n"
        "• Platega (СБП, банковские карты) - без комиссии\n"
        f"• Криптовалюта USDT (через CryptoBot) - комиссия {CRYPTO_MARKUP_PERCENT}%\n\n"
        "📌 **Как пользоваться:**\n"
        "• Купите подписку через меню\n"
        "• Выберите удобный способ оплаты\n"
        "• После оплаты вы получите ключ и ссылку на группу\n\n"
        "📞 **КОНТАКТЫ:**\n"
        f"• Техподдержка: @{SUPPORT_USERNAME}\n"
        f"• Основной канал: {MAIN_CHANNEL}\n"
        f"• Отзывы: {REVIEWS_CHANNEL}\n\n"
        "⚖️ **ДОКУМЕНТЫ:**\n"
        "• Политика конфиденциальности\n"
        "• Пользовательское соглашение\n\n"
        "📄 Нажмите на кнопки ниже для просмотра"
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
        bot.send_message(message.chat.id, "❌ У вас нет прав!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ Используйте: `/addadmin 123456789`", parse_mode="Markdown")
            return
        new_admin_id = int(parts[1])
        cursor = db.connection.cursor()
        cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (new_admin_id,))
        db.connection.commit()
        bot.send_message(message.chat.id, f"✅ Пользователь `{new_admin_id}` назначен администратором!", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_command(message: Message):
    if not is_main_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ У вас нет прав!")
        return
    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ Используйте: `/removeadmin 123456789`", parse_mode="Markdown")
            return
        remove_id = int(parts[1])
        if remove_id == MAIN_ADMIN_ID:
            bot.send_message(message.chat.id, "❌ Нельзя удалить главного администратора!")
            return
        cursor = db.connection.cursor()
        cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (remove_id,))
        db.connection.commit()
        bot.send_message(message.chat.id, f"✅ Пользователь `{remove_id}` удален из администраторов!", parse_mode="Markdown")
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
    text = "👥 **Список администраторов:**\n\n"
    for admin in admins:
        admin_id, username = admin
        mark = "⭐" if admin_id == MAIN_ADMIN_ID else ""
        text += f"• `{admin_id}` - @{username or 'без username'} {mark}\n"
    text += "\n**Команды:**\n`/addadmin ID` - добавить\n`/removeadmin ID` - удалить"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "➕ Добавить ключи (массово)" and is_admin(message.from_user.id))
def add_keys_batch(message: Message):
    text = (
        "📝 **Массовое добавление ключей**\n\n"
        "Формат:\n`+l1d` - LITE 1 день\n`+l7d` - LITE 7 дней\n"
        "`+v1d` - VIP 1 день\n`+v7d` - VIP 7 дней\n`+v14d` - VIP 14 дней\n\n"
        "Пример:\n`+v1d`\n`KEY1`\n`KEY2`\n`KEY3`"
    )
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_add_keys)

def process_add_keys(message: Message):
    lines = message.text.strip().split('\n')
    current_type = None
    current_days = None
    added = 0
    stats = {"lite_1d": 0, "lite_7d": 0, "vip_1d": 0, "vip_7d": 0, "vip_14d": 0}
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
    result = f"✅ **Добавлено ключей: {added}**\n\n📊 Статистика:\n"
    result += f"• LITE 1д: {stats['lite_1d']}\n• LITE 7д: {stats['lite_7d']}\n"
    result += f"• VIP 1д: {stats['vip_1d']}\n• VIP 7д: {stats['vip_7d']}\n• VIP 14д: {stats['vip_14d']}"
    bot.send_message(message.chat.id, result, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🗑 Удалить ключи (массово)" and is_admin(message.from_user.id))
def delete_keys_batch(message: Message):
    text = (
        "🗑 **Массовое удаление ключей**\n\n"
        "Вариант 1 - удалить все ключи типа:\n`-l1d` - LITE 1д\n`-l7d` - LITE 7д\n"
        "`-v1d` - VIP 1д\n`-v7d` - VIP 7д\n`-v14d` - VIP 14д\n\n"
        "Вариант 2 - удалить конкретные ключи:\n`KEY1`\n`KEY2`\n`KEY3`"
    )
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_delete_keys)

def process_delete_keys(message: Message):
    lines = message.text.strip().split('\n')
    deleted = 0
    stats = {"lite_1d": 0, "lite_7d": 0, "vip_1d": 0, "vip_7d": 0, "vip_14d": 0}
    type_map = {
        "-l1d": ("lite", 1, "lite_1d"), "-l7d": ("lite", 7, "lite_7d"),
        "-v1d": ("vip", 1, "vip_1d"), "-v7d": ("vip", 7, "vip_7d"), "-v14d": ("vip", 14, "vip_14d")
    }
    first_line = lines[0].strip().lower()
    if first_line in type_map:
        target_type, target_days, stat_key = type_map[first_line]
        all_keys = db.get_all_keys()
        for key in all_keys:
            if key[2] == target_type and key[3] == target_days and key[4] == 0:
                db.delete_key(key[0])
                deleted += 1
                stats[stat_key] += 1
        result = f"✅ **Удалено ключей типа {target_type.upper()} {target_days}д: {deleted}**"
        bot.send_message(message.chat.id, result, parse_mode="Markdown")
        return
    keys_to_delete = set(lines)
    all_keys = db.get_all_keys()
    for key in all_keys:
        if key[1] in keys_to_delete and key[4] == 0:
            db.delete_key(key[0])
            deleted += 1
            stat_key = f"{key[2]}_{key[3]}d".replace("lite", "lite").replace("vip", "vip")
            stats[stat_key] = stats.get(stat_key, 0) + 1
            keys_to_delete.discard(key[1])
    result = f"✅ **Удалено ключей: {deleted}**\n\n📊 Статистика:\n"
    for k, v in stats.items():
        if v > 0:
            result += f"• {k}: {v}\n"
    bot.send_message(message.chat.id, result, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "💰 Изменить цены" and is_admin(message.from_user.id))
def change_prices_menu(message: Message):
    text = "💰 **Текущие цены:**\n\n"
    text += f"• LITE 1д: {PRICES['lite_1day']}₽\n• LITE 7д: {PRICES['lite_7day']}₽\n"
    text += f"• VIP 1д: {PRICES['vip_1day']}₽\n• VIP 7д: {PRICES['vip_7day']}₽\n• VIP 14д: {PRICES['vip_14day']}₽\n\n"
    text += "**Изменить цену:**\n`lite_1day 150`"
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, update_price)

def update_price(message: Message):
    try:
        text = message.text.strip()
        if ' ' in text:
            key, new_price = text.split(' ')
        else:
            bot.send_message(message.chat.id, "❌ Формат: `lite_1day 150`", parse_mode="Markdown")
            return
        new_price = int(new_price)
        if key in PRICES:
            PRICES[key] = new_price
            set_price(key, new_price)
            bot.send_message(message.chat.id, f"✅ Цена {key} = {new_price}₽", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ Неверный ключ!", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка!", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📋 Список ключей" and is_admin(message.from_user.id))
def list_keys(message: Message):
    all_keys = db.get_all_keys()
    if not all_keys:
        bot.send_message(message.chat.id, "📭 **Нет ключей**", parse_mode="Markdown")
        return
    lite_1d = [k for k in all_keys if k[2] == "lite" and k[3] == 1 and k[4] == 0]
    lite_7d = [k for k in all_keys if k[2] == "lite" and k[3] == 7 and k[4] == 0]
    vip_1d = [k for k in all_keys if k[2] == "vip" and k[3] == 1 and k[4] == 0]
    vip_7d = [k for k in all_keys if k[2] == "vip" and k[3] == 7 and k[4] == 0]
    vip_14d = [k for k in all_keys if k[2] == "vip" and k[3] == 14 and k[4] == 0]
    used = [k for k in all_keys if k[4] == 1]
    text = "🔑 **СТАТИСТИКА КЛЮЧЕЙ:**\n\n"
    text += f"🌟 LITE 1д: {len(lite_1d)}\n🌟 LITE 7д: {len(lite_7d)}\n"
    text += f"👑 VIP 1д: {len(vip_1d)}\n👑 VIP 7д: {len(vip_7d)}\n👑 VIP 14д: {len(vip_14d)}\n"
    text += f"❌ Использовано: {len(used)}\n📊 Всего: {len(all_keys)}"
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
    text = f"📊 **СТАТИСТИКА**\n\n💰 Доход: {total_income}₽\n✅ Успешно: {total_success}\n⏳ В ожидании: {total_pending}\n👥 Пользователей: {stats['total_users']}\n✅ Активных: {stats['active_subs']}"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "◀️ Назад в меню")
def back_to_main(message: Message):
    bot.send_message(message.chat.id, "🏠 **Главное меню**", parse_mode="Markdown", reply_markup=main_menu(is_admin(message.from_user.id)))

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call: CallbackQuery):
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🏠 **Главное меню**", parse_mode="Markdown", reply_markup=main_menu(is_admin(call.from_user.id)))

# ============================================
# FLASK ПРИЛОЖЕНИЕ ДЛЯ ВЕБХУКОВ
# ============================================
@app.route('/', methods=['GET'])
def index():
    return "Бот работает!", 200

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        print(f"Ошибка: {e}")
        return "Error", 200

@app.route('/webhook', methods=['POST'])
def platega_webhook():
    try:
        data = request.json
        status = data.get('status')
        payload = data.get('payload')
        if status == "CONFIRMED" and payload and payload.startswith('user'):
            parts = payload.split('_')
            if len(parts) >= 3:
                user_id = int(parts[1])
                order_parts = parts[2].split('_')
                sub_type = order_parts[0]
                days = int(order_parts[1].replace('day', ''))
                db.activate_subscription(user_id, sub_type, days)
                group_link = create_group_link(sub_type)
                group_text = f"\n\n📦 Ссылка на группу: {group_link}" if group_link else ""
                bot.send_message(user_id, f"✅ Оплата подтверждена!\n🔑 Подписка: {sub_type.upper()} {days} д.{group_text}")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error"}), 500

@app.route('/crypto_webhook', methods=['POST'])
def crypto_webhook():
    try:
        data = request.json
        print(f"CryptoBot webhook: {data}")
        if data.get("payload"):
            payload = data.get("payload")
            if payload.startswith('user'):
                parts = payload.split('_')
                if len(parts) >= 3:
                    user_id = int(parts[1])
                    order_parts = parts[2].split('_')
                    sub_type = order_parts[0]
                    days = int(order_parts[1].replace('day', ''))
                    db.activate_subscription(user_id, sub_type, days)
                    group_link = create_group_link(sub_type)
                    group_text = f"\n\n📦 Ссылка на группу: {group_link}" if group_link else ""
                    bot.send_message(user_id, f"✅ Оплата подтверждена!\n🔑 Подписка: {sub_type.upper()} {days} д.{group_text}")
        return jsonify({"ok": True}), 200
    except Exception as e:
        return jsonify({"ok": False}), 200

@app.route('/payment_success', methods=['GET'])
def payment_success():
    return "Оплата успешно проведена! Можете вернуться в бота.", 200

@app.route('/payment_cancel', methods=['GET'])
def payment_cancel():
    return "Оплата отменена.", 200

# ============================================
# ЗАПУСК
# ============================================
if __name__ == '__main__':
    print("=" * 60)
    print("🚀 БОТ ЗАПУЩЕН")
    print(f"🤖 Бот: @KeeperMag_bot")
    print(f"📡 Callback URL: {RAILWAY_URL}/webhook")
    print(f"🪙 CryptoBot URL: {RAILWAY_URL}/crypto_webhook")
    print(f"💰 Комиссия за криптоплатежи: {CRYPTO_MARKUP_PERCENT}%")
    print("=" * 60)
    
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": f"{RAILWAY_URL}/telegram_webhook"})
        print("✅ Webhook установлен")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
    
    app.run(host='0.0.0.0', port=5000)
