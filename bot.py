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
# КЛАВИАТУРЫ
# ============================================
def main_menu(user_is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("🌟 Купить подписку"),
        KeyboardButton("👤 Мой профиль"),
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
    markup.add(
        InlineKeyboardButton("1 день - 140₽", callback_data="buy_lite_1day"),
        InlineKeyboardButton("7 дней - 700₽", callback_data="buy_lite_7day")
    )
    return markup

def vip_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("1 день - 270₽", callback_data="buy_vip_1day"),
        InlineKeyboardButton("7 дней - 1200₽", callback_data="buy_vip_7day"),
        InlineKeyboardButton("14 дней - 2200₽", callback_data="buy_vip_14day")
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
    bot.edit_message_text("🌟 **LITE подписка**\n\n💰 1 день - 140₽\n💰 7 дней - 700₽\n\n💳 После оплаты подписка активируется автоматически", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=lite_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data == "choose_vip")
def choose_vip(call: CallbackQuery):
    bot.edit_message_text("👑 **VIP подписка**\n\n💰 1 день - 270₽\n💰 7 дней - 1200₽\n💰 14 дней - 2200₽\n\n💳 После оплаты подписка активируется автоматически", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=vip_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call: CallbackQuery):
    try:
        _, sub_type, duration = call.data.split("_")
        days = int(duration.replace("day", ""))
        prices = {"lite_1day": 140, "lite_7day": 700, "vip_1day": 270, "vip_7day": 1200, "vip_14day": 2200}
        amount = prices.get(f"{sub_type}_{duration}")
        
        user_id = call.from_user.id
        payload = f"user_{user_id}_{sub_type}_{duration}"
        
        headers = {
            "Content-Type": "application/json",
            "X-MerchantId": MERCHANT_ID,
            "X-Secret": API_SECRET
        }
        
        payment_data = {
            "paymentDetails": {
                "amount": float(amount),
                "currency": "RUB"
            },
            "description": f"Подписка {sub_type.upper()} на {days} дней",
            "return": "https://t.me/KeeperMag_bot",
            "failedUrl": "https://t.me/KeeperMag_bot",
            "payload": payload
        }
        
        # Отправляем запрос к Platega
        response = requests.post(
            f"{PLATEGA_API_URL}/v2/transaction/process",
            headers=headers,
            json=payment_data,
            timeout=30
        )
        
        # Детальное логирование в консоль Railway
        print("=" * 50)
        print(f"ЗАПРОС К PLATEGA:")
        print(f"URL: {PLATEGA_API_URL}/v2/transaction/process")
        print(f"HEADERS: {headers}")
        print(f"PAYLOAD: {json.dumps(payment_data, indent=2)}")
        print(f"ОТВЕТ КОД: {response.status_code}")
        print(f"ОТВЕТ ТЕЛО: {response.text}")
        print("=" * 50)
        
        if response.status_code == 200:
            result = response.json()
            payment_url = result.get("redirect") or result.get("payment_url")
            transaction_id = result.get("transactionId") or result.get("id")
            
            if payment_url and transaction_id:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=payment_url))
                markup.add(InlineKeyboardButton("🔄 Проверить статус", callback_data=f"check_{transaction_id}"))
                
                bot.edit_message_text(
                    f"💳 **Счет на оплату**\n\n"
                    f"💰 Сумма: {amount}₽\n"
                    f"📦 Подписка: {sub_type.upper()} {days} д.\n\n"
                    f"👇 Нажмите для оплаты",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=markup
                )
            else:
                bot.edit_message_text(
                    f"❌ Ошибка: Не получен URL оплаты\nОтвет: {response.text[:200]}",
                    call.message.chat.id,
                    call.message.message_id
                )
        else:
            # Показываем подробную ошибку пользователю
            error_msg = f"❌ Ошибка создания платежа\n\nКод: {response.status_code}\n\nДля техподдержки:\n```\n{response.text[:300]}\n```"
            bot.edit_message_text(error_msg, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"ИСКЛЮЧЕНИЕ: {error_details}")
        bot.edit_message_text(
            f"❌ Критическая ошибка:\n```\n{str(e)[:200]}\n```\nОбратитесь к @nikita1055",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_"))
def check_payment(call: CallbackQuery):
    transaction_id = call.data.split("_")[1]
    headers = {
        "X-MerchantId": MERCHANT_ID,
        "X-Secret": API_SECRET
    }
    
    try:
        response = requests.get(f"{PLATEGA_API_URL}/transaction/{transaction_id}", headers=headers, timeout=30)
        
        print(f"ПРОВЕРКА ПЛАТЕЖА: {transaction_id} -> {response.status_code} {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "CONFIRMED":
                bot.answer_callback_query(call.id, "✅ Оплата подтверждена!")
                bot.send_message(call.message.chat.id, "✅ Подписка активирована!")
            else:
                bot.answer_callback_query(call.id, "⏳ Еще не оплачено", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {response.status_code}", show_alert=True)
    except Exception as e:
        print(f"Ошибка проверки: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка соединения", show_alert=True)

@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация")
def info_menu(message: Message):
    text = (
        "ℹ️ **ИНФОРМАЦИЯ**\n\n"
        "🤖 **Бот для продажи подписок LITE и VIP**\n\n"
        "💳 **Оплата:** Platega (СБП, Криптовалюта)\n\n"
        "📌 **Как пользоваться:**\n"
        "• Купите подписку через меню\n"
        "• После оплаты подписка активируется автоматически\n\n"
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

@bot.message_handler(func=lambda message: message.text == "📋 Список ключей" and is_admin(message.from_user.id))
def list_keys(message: Message):
    keys = db.get_all_keys()
    if not keys:
        bot.send_message(message.chat.id, "📭 **Нет ключей**", parse_mode="Markdown")
        return
    
    text = "🔑 **СПИСОК КЛЮЧЕЙ:**\n\n"
    for key in keys[-30:]:
        _, key_code, sub_type, days, is_used, _ = key
        status = "✅ АКТИВЕН" if not is_used else "❌ ИСПОЛЬЗОВАН"
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
@app.route('/')
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
        print(f"Ошибка вебхука Telegram: {e}")
        return "Error", 200

@app.route('/webhook', methods=['POST'])
def platega_webhook():
    try:
        data = request.json
        print(f"📡 Получен вебхук от Platega: {json.dumps(data, indent=2)}")
        status = data.get('status')
        payload = data.get('payload')
        
        if status == "CONFIRMED" and payload:
            parts = payload.split('_')
            if len(parts) >= 4 and parts[0] == 'user':
                user_id = int(parts[1])
                sub_type = parts[2]
                days = int(parts[3].replace('day', ''))
                db.activate_subscription(user_id, sub_type, days)
                try:
                    bot.send_message(user_id, f"✅ Оплата подтверждена! Подписка {sub_type.upper()} на {days} дней активирована!")
                except:
                    pass
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Ошибка вебхука Platega: {e}")
        return jsonify({"status": "error"}), 500

# ============================================
# ЗАПУСК
# ============================================
if __name__ == '__main__':
    print("=" * 60)
    print("🚀 ЗАПУСК БОТА")
    print(f"🤖 Бот: @KeeperMag_bot")
    print(f"📡 Callback URL: {RAILWAY_URL}/webhook")
    print("=" * 60)
    
    # Устанавливаем вебхук Telegram
    try:
        resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
        print(f"Удаление вебхука: {resp.status_code}")
        resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", json={"url": f"{RAILWAY_URL}/telegram_webhook"})
        print(f"Установка вебхука: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"Ошибка установки вебхука: {e}")
    
    print("✅ Бот готов к работе!")
    app.run(host='0.0.0.0', port=5000)
