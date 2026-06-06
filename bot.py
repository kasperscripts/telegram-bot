import telebot
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from database import Database
import requests
import json
import traceback
from datetime import datetime
from flask import Flask, request, jsonify

# ============================================
# НАСТРОЙКИ
# ============================================
BOT_TOKEN = "8664140220:AAGDF8R4pQM31nd_ZMOFgCK69MMReNxWEOA"
MERCHANT_ID = "709e8d20-e5f9-4ad0-8bae-311460ff7991"
API_SECRET = "b4gxyG1yLHYrz3AvG0QEOjxw5BuKaWie3JkP3p25ExhEX6AFLbf2ZqPMWGFWgpSXtgsrGYTjsXh7KEF8tDHdxLAvFW6XCNqG7xJ2"
PLATEGA_API_URL = "https://app.platega.io"
RAILWAY_URL = "https://telegram-bot-production-4bcc.up.railway.app"

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

# ============================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ЦЕНАМИ
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
    """Проверяет есть ли неиспользованные ключи для подписки"""
    keys = db.get_all_keys()
    for key in keys:
        if key[2] == sub_type and key[3] == days and key[4] == 0:
            return True
    return False

def get_and_activate_key(sub_type, days, user_id):
    """Находит и активирует ключ, возвращает ключ"""
    keys = db.get_all_keys()
    for key in keys:
        if key[2] == sub_type and key[3] == days and key[4] == 0:
            # Активируем ключ
            db.use_key(key[1], user_id)
            return key[1]
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

def lite_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    lite_1day_available = check_keys_available("lite", 1)
    lite_7day_available = check_keys_available("lite", 7)
    
    markup.add(
        InlineKeyboardButton(f"1 день - {PRICES['lite_1day']}₽" + (" ✅" if lite_1day_available else " ❌"), callback_data="buy_lite_1day" if lite_1day_available else "no_keys"),
        InlineKeyboardButton(f"7 дней - {PRICES['lite_7day']}₽" + (" ✅" if lite_7day_available else " ❌"), callback_data="buy_lite_7day" if lite_7day_available else "no_keys")
    )
    return markup

def vip_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    vip_1day_available = check_keys_available("vip", 1)
    vip_7day_available = check_keys_available("vip", 7)
    vip_14day_available = check_keys_available("vip", 14)
    
    markup.add(
        InlineKeyboardButton(f"1 день - {PRICES['vip_1day']}₽" + (" ✅" if vip_1day_available else " ❌"), callback_data="buy_vip_1day" if vip_1day_available else "no_keys"),
        InlineKeyboardButton(f"7 дней - {PRICES['vip_7day']}₽" + (" ✅" if vip_7day_available else " ❌"), callback_data="buy_vip_7day" if vip_7day_available else "no_keys"),
        InlineKeyboardButton(f"14 дней - {PRICES['vip_14day']}₽" + (" ✅" if vip_14day_available else " ❌"), callback_data="buy_vip_14day" if vip_14day_available else "no_keys")
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
        KeyboardButton("💰 Изменить цены"),
        KeyboardButton("📋 Список ключей"),
        KeyboardButton("📊 Статистика"),
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
    return user_id in [1302493787, 6784034490]

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
        "Вы можете помочь развитию проекта любой суммой.\n\n"
        "💳 **Реквизиты для поддержки:**\n"
        "• СБП (по номеру телефона): @nikita1055\n"
        "• USDT (TRC20): TXhXXXXXXXXXXXXXXXXXXXXX\n\n"
        "Или нажмите на кнопку ниже для оплаты через Platega"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💸 Пожертвовать через Platega", callback_data="donate"))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "donate")
def process_donate(call: CallbackQuery):
    msg = bot.send_message(call.message.chat.id, "💰 **Введите сумму пожертвования (в рублях):**\n\nМинимальная сумма: 50₽", parse_mode="Markdown")
    bot.register_next_step_handler(msg, create_donate_payment)

def create_donate_payment(message: Message):
    try:
        amount = float(message.text.strip())
        if amount < 50:
            bot.send_message(message.chat.id, "❌ Минимальная сумма пожертвования 50₽")
            return
        
        user_id = message.from_user.id
        payload = f"donate_{user_id}_{int(datetime.now().timestamp())}"
        
        headers = {
            "Content-Type": "application/json",
            "X-MerchantId": MERCHANT_ID,
            "X-Secret": API_SECRET
        }
        
        payment_data = {
            "command": "create",
            "paymentDetails": {
                "amount": float(amount),
                "currency": "RUB"
            },
            "description": f"Пожертвование от пользователя {user_id}",
            "return": "https://t.me/KeeperMag_bot",
            "failedUrl": "https://t.me/KeeperMag_bot",
            "payload": payload,
            "paymentMethod": ["SBP", "CRYPTO"]
        }
        
        response = requests.post(
            f"{PLATEGA_API_URL}/v2/transaction/process",
            headers=headers,
            json=payment_data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            payment_url = result.get("url") or result.get("payment_url")
            
            if payment_url:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("💳 ПЕРЕЙТИ К ОПЛАТЕ", url=payment_url))
                bot.send_message(
                    message.chat.id,
                    f"❤️ **Спасибо за поддержку!**\n\n"
                    f"💰 Сумма: {amount}₽\n\n"
                    f"👇 Нажмите для оплаты",
                    parse_mode="Markdown",
                    reply_markup=markup
                )
            else:
                bot.send_message(message.chat.id, f"❌ Ошибка создания платежа")
        else:
            bot.send_message(message.chat.id, f"❌ Ошибка {response.status_code}")
            
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

# ============================================
# ОСНОВНЫЕ ОБРАБОТЧИКИ
# ============================================
@bot.message_handler(commands=['start'])
def start_command(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    db.add_user(user_id, username)
    bot.send_message(user_id, "🤖 Добро пожаловать!\n\n🌟 Бот для продажи подписок LITE и VIP.\n💳 Оплата через Platega (СБП, Криптовалюта)", reply_markup=main_menu(is_admin(user_id)))

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
    bot.edit_message_text("🌟 **LITE подписка**\n\n✅ - есть ключи\n❌ - нет ключей", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=lite_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data == "choose_vip")
def choose_vip(call: CallbackQuery):
    bot.edit_message_text("👑 **VIP подписка**\n\n✅ - есть ключи\n❌ - нет ключей", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=vip_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data == "no_keys")
def no_keys_available(call: CallbackQuery):
    bot.answer_callback_query(call.id, "❌ Ключи закончились! Обратитесь к администратору.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call: CallbackQuery):
    try:
        _, sub_type, duration = call.data.split("_")
        days = int(duration.replace("day", ""))
        amount = PRICES.get(f"{sub_type}_{duration}")

        if not amount:
            bot.answer_callback_query(call.id, "❌ Ошибка цены!")
            return

        # Проверяем наличие ключей
        key = get_and_activate_key(sub_type, days, call.from_user.id)
        if not key:
            bot.answer_callback_query(call.id, "❌ Ключи закончились! Обратитесь к администратору.", show_alert=True)
            bot.edit_message_text("❌ **Ключи временно отсутствуют**\n\nПожалуйста, обратитесь к администратору @nikita1055", call.message.chat.id, call.message.message_id)
            return

        user_id = call.from_user.id
        payload = f"user_{user_id}_{sub_type}_{duration}_{key}"
        
        headers = {
            "Content-Type": "application/json",
            "X-MerchantId": MERCHANT_ID,
            "X-Secret": API_SECRET
        }

        payment_data = {
            "command": "create",
            "paymentDetails": {
                "amount": float(amount),
                "currency": "RUB"
            },
            "description": f"Подписка {sub_type.upper()} на {days} дней",
            "return": "https://t.me/KeeperMag_bot",
            "failedUrl": "https://t.me/KeeperMag_bot",
            "payload": payload,
            "paymentMethod": ["SBP", "CRYPTO"]
        }

        response = requests.post(
            f"{PLATEGA_API_URL}/v2/transaction/process",
            headers=headers,
            json=payment_data,
            timeout=30
        )

        print("="*50)
        print(f"КОД ОТВЕТА: {response.status_code}")
        print(f"ТЕЛО ОТВЕТА: {response.text}")
        print("="*50)

        if response.status_code == 200:
            result = response.json()
            payment_url = result.get("url") or result.get("payment_url")
            transaction_id = result.get("transactionId") or result.get("id")

            if payment_url and transaction_id:
                # Сохраняем ключ во временное хранилище
                user_states[f"payment_{transaction_id}"] = {
                    "user_id": user_id,
                    "sub_type": sub_type,
                    "days": days,
                    "key": key,
                    "amount": amount
                }
                
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=payment_url))
                markup.add(InlineKeyboardButton("🔄 ПРОВЕРИТЬ", callback_data=f"check_{transaction_id}"))

                bot.edit_message_text(
                    f"💳 **Счет на {amount}₽**\n\n"
                    f"📦 {sub_type.upper()} {days} д.\n"
                    f"👇 Нажмите для оплаты",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            else:
                # Если ошибка, возвращаем ключ обратно
                bot.edit_message_text(f"❌ Ошибка: не получен URL\n{response.text[:200]}", call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text(f"❌ Ошибка {response.status_code}\n{response.text[:300]}", call.message.chat.id, call.message.message_id)

    except Exception as e:
        print(traceback.format_exc())
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:100]}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_"))
def check_payment(call: CallbackQuery):
    transaction_id = call.data.split("_")[1]
    headers = {"X-MerchantId": MERCHANT_ID, "X-Secret": API_SECRET}
    
    try:
        response = requests.get(f"{PLATEGA_API_URL}/transaction/{transaction_id}", headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "CONFIRMED":
                # Получаем сохраненные данные
                payment_data = user_states.get(f"payment_{transaction_id}", {})
                key = payment_data.get("key")
                sub_type = payment_data.get("sub_type")
                days = payment_data.get("days")
                user_id = payment_data.get("user_id")
                
                if key and user_id:
                    # Активируем подписку (ключ уже активирован при создании платежа)
                    db.activate_subscription(user_id, sub_type, days)
                    bot.send_message(user_id, f"✅ **Оплата подтверждена!**\n\n🔑 Ваш ключ:\n`{key}`\n\n📦 Подписка: {sub_type.upper()} {days} д.\n\nСохраните ключ!", parse_mode="Markdown")
                    
                bot.answer_callback_query(call.id, "✅ Оплата подтверждена!")
                bot.send_message(call.message.chat.id, "✅ Подписка активирована! Ключ отправлен в личные сообщения.")
                # Очищаем временные данные
                if f"payment_{transaction_id}" in user_states:
                    del user_states[f"payment_{transaction_id}"]
            else:
                bot.answer_callback_query(call.id, "⏳ Еще не оплачено", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка проверки", show_alert=True)
    except Exception as e:
        print(f"Ошибка: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация")
def info_menu(message: Message):
    text = (
        "ℹ️ **ИНФОРМАЦИЯ**\n\n"
        "🤖 **Бот для продажи подписок LITE и VIP**\n\n"
        "💳 **Оплата:** Platega (СБП, Криптовалюта)\n\n"
        "📌 **Как пользоваться:**\n"
        "• Купите подписку через меню\n"
        "• После оплаты вы получите ключ активации\n\n"
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

@bot.message_handler(func=lambda message: message.text == "➕ Добавить ключи" and is_admin(message.from_user.id))
def add_keys_menu(message: Message):
    msg = bot.send_message(message.chat.id, "📝 **Введите ключи**\n\nФормат: `КЛЮЧ lite 1`\nКаждый ключ с новой строки:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_keys)

def save_keys(message: Message):
    added = 0
    for line in message.text.strip().split('\n'):
        parts = line.strip().split()
        if len(parts) >= 3:
            key, sub_type, days = parts[0], parts[1].lower(), int(parts[2])
            if db.add_key(key, sub_type, days):
                added += 1
    bot.send_message(message.chat.id, f"✅ **Добавлено ключей: {added}**", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "💰 Изменить цены" and is_admin(message.from_user.id))
def change_prices_menu(message: Message):
    text = "💰 **Текущие цены:**\n\n"
    text += f"• LITE 1 день: {PRICES['lite_1day']}₽\n"
    text += f"• LITE 7 дней: {PRICES['lite_7day']}₽\n"
    text += f"• VIP 1 день: {PRICES['vip_1day']}₽\n"
    text += f"• VIP 7 дней: {PRICES['vip_7day']}₽\n"
    text += f"• VIP 14 дней: {PRICES['vip_14day']}₽\n\n"
    text += "**Изменить цену:**\nОтправьте: `lite_1day 150`"
    
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, update_price)

def update_price(message: Message):
    try:
        text = message.text.strip()
        if ' ' in text:
            key, new_price = text.split(' ')
        elif ':' in text:
            key, new_price = text.split(':')
        else:
            bot.send_message(message.chat.id, "❌ Неверный формат! Используйте: `lite_1day 150`", parse_mode="Markdown")
            return
        
        new_price = int(new_price)
        if key in PRICES:
            PRICES[key] = new_price
            set_price(key, new_price)
            bot.send_message(message.chat.id, f"✅ Цена {key} изменена на {new_price}₽", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, f"❌ Неверный ключ!", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "❌ Ошибка! Пример: `lite_1day 150`", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📋 Список ключей" and is_admin(message.from_user.id))
def list_keys(message: Message):
    keys = db.get_all_keys()
    if not keys:
        bot.send_message(message.chat.id, "📭 **Нет ключей**", parse_mode="Markdown")
        return
    
    text = "🔑 **СПИСОК КЛЮЧЕЙ:**\n\n"
    for key in keys[-30:]:
        _, key_code, sub_type, days, is_used, used_by = key
        status = "✅ АКТИВЕН" if not is_used else f"❌ ИСПОЛЬЗОВАН (пользователь {used_by})"
        text += f"`{key_code}` - {sub_type.upper()} {days}д. - {status}\n"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📊 Статистика" and is_admin(message.from_user.id))
def show_stats(message: Message):
    stats = db.get_stats()
    text = (
        f"📊 **СТАТИСТИКА**\n\n"
        f"👥 Пользователей: {stats['total_users']}\n"
        f"✅ Активных подписок: {stats['active_subs']}\n"
        f"💰 Доход: {stats['total_income']}₽"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "◀️ Назад в меню")
def back_to_main(message: Message):
    bot.send_message(message.chat.id, "🏠 **Главное меню**", parse_mode="Markdown", reply_markup=main_menu(is_admin(message.from_user.id)))

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call: CallbackQuery):
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🏠 **Главное меню**", parse_mode="Markdown", reply_markup=main_menu(is_admin(call.from_user.id)))

# ============================================
# FLASK ПРИЛОЖЕНИЕ
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
        print(f"📡 Вебхук Platega: {json.dumps(data, indent=2)}")
        status = data.get('status')
        payload = data.get('payload')
        
        if status == "CONFIRMED" and payload:
            parts = payload.split('_')
            if len(parts) >= 5 and parts[0] == 'user':
                user_id = int(parts[1])
                sub_type = parts[2]
                days = int(parts[3].replace('day', ''))
                key = parts[4]
                
                # Активируем подписку
                db.activate_subscription(user_id, sub_type, days)
                try:
                    bot.send_message(user_id, f"✅ **Оплата подтверждена!**\n\n🔑 Ваш ключ:\n`{key}`\n\n📦 Подписка: {sub_type.upper()} {days} д.\n\nСохраните ключ!", parse_mode="Markdown")
                except:
                    pass
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Ошибка: {e}")
        return jsonify({"status": "error"}), 500

# ============================================
# ЗАПУСК
# ============================================
if __name__ == '__main__':
    print("=" * 60)
    print("🚀 БОТ ЗАПУЩЕН")
    print(f"🤖 Бот: @KeeperMag_bot")
    print(f"📡 Callback URL: {RAILWAY_URL}/webhook")
    print("=" * 60)
    
    try:
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": f"{RAILWAY_URL}/telegram_webhook"})
        print("✅ Webhook установлен")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
    
    app.run(host='0.0.0.0', port=5000)
