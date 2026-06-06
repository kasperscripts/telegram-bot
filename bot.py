import telebot
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from database import Database
import requests
from datetime import datetime
from flask import Flask, request, jsonify

BOT_TOKEN = "8664140220:AAH9fRMhiDj6USmjG005FNglEBGhVSQamgw"
MERCHANT_ID = "709e8d20-e5f9-4ad0-8bae-311460ff7991"
API_SECRET = "YZwWK4Kqpaaqhb8R5yxcOLKzUoljHmFABf3arpCTSColGlHIuYkVnP9BrHxulkDZJRh33ApHMCxlxbQHLBFmKIQJ8hBiQVxvj4uM"
PLATEGA_API_URL = "https://app.platega.io"
RAILWAY_URL = "https://telegram-bot-production-2773.up.railway.app"

bot = telebot.TeleBot(BOT_TOKEN)
db = Database()
app = Flask(__name__)

def main_menu(user_is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [KeyboardButton("🌟 Купить подписку"), KeyboardButton("👤 Мой профиль"), KeyboardButton("ℹ️ Информация")]
    if user_is_admin:
        buttons.append(KeyboardButton("⚙️ Админ-панель"))
    markup.add(*buttons)
    return markup

def choose_subscription_type():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🌟 LITE", callback_data="choose_lite"), InlineKeyboardButton("👑 VIP", callback_data="choose_vip"))
    return markup

def lite_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("1 день - 140₽", callback_data="buy_lite_1day"), InlineKeyboardButton("7 дней - 700₽", callback_data="buy_lite_7day"))
    return markup

def vip_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("1 день - 270₽", callback_data="buy_vip_1day"), InlineKeyboardButton("7 дней - 1200₽", callback_data="buy_vip_7day"), InlineKeyboardButton("14 дней - 2200₽", callback_data="buy_vip_14day"))
    return markup

def info_buttons():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("💬 Поддержка", url="https://t.me/nikita1055"), InlineKeyboardButton("📢 Канал", url="https://t.me/keepersell"))
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [KeyboardButton("➕ Добавить ключи"), KeyboardButton("📋 Список ключей"), KeyboardButton("📊 Статистика"), KeyboardButton("◀️ Назад")]
    markup.add(*buttons)
    return markup

def is_admin(user_id):
    return user_id in [1302493787, 6784034490]

@bot.message_handler(commands=['start'])
def start_command(message):
    db.add_user(message.from_user.id, message.from_user.username or f"user_{message.from_user.id}")
    bot.send_message(message.chat.id, "🤖 Добро пожаловать!\n💰 Оплата через Platega", reply_markup=main_menu(is_admin(message.from_user.id)))

@bot.message_handler(func=lambda m: m.text == "👤 Мой профиль")
def profile(m):
    user = db.get_user(m.from_user.id)
    sub_type, end_date = db.check_subscription(m.from_user.id)
    text = f"👤 ID: {user[0]}\n"
    if sub_type:
        days_left = (end_date - datetime.now()).days
        text += f"📅 Подписка: {sub_type.upper()}\n⏰ До: {end_date.strftime('%d.%m.%Y')}\n⌛ Осталось: {days_left} д."
    else:
        text += "❌ Нет подписки"
    bot.send_message(m.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "🌟 Купить подписку")
def buy_subscription(m):
    bot.send_message(m.chat.id, "Выберите тип:", reply_markup=choose_subscription_type())

@bot.callback_query_handler(func=lambda call: call.data == "choose_lite")
def choose_lite(call):
    bot.edit_message_text("LITE подписка\n140₽ - 1 день\n700₽ - 7 дней", call.message.chat.id, call.message.message_id, reply_markup=lite_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data == "choose_vip")
def choose_vip(call):
    bot.edit_message_text("VIP подписка\n270₽ - 1 день\n1200₽ - 7 дней\n2200₽ - 14 дней", call.message.chat.id, call.message.message_id, reply_markup=vip_duration_buttons())

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call):
    _, sub_type, duration = call.data.split("_")
    days = int(duration.replace("day", ""))
    prices = {"lite_1day": 140, "lite_7day": 700, "vip_1day": 270, "vip_7day": 1200, "vip_14day": 2200}
    amount = prices.get(f"{sub_type}_{duration}")
    
    headers = {"Content-Type": "application/json", "X-MerchantId": MERCHANT_ID, "X-Secret": API_SECRET}
    payment_data = {
        "paymentDetails": {"amount": float(amount), "currency": "RUB"},
        "description": f"Подписка {sub_type.upper()} на {days} дней",
        "return": "https://t.me/KeeperMag_bot",
        "failedUrl": "https://t.me/KeeperMag_bot",
        "payload": f"user_{call.from_user.id}_{sub_type}_{duration}"
    }
    
    try:
        response = requests.post(f"{PLATEGA_API_URL}/transaction/process", headers=headers, json=payment_data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("💳 ОПЛАТИТЬ", url=result.get("redirect")))
            markup.add(InlineKeyboardButton("🔄 Проверить", callback_data=f"check_{result.get('transactionId')}"))
            bot.edit_message_text(f"💳 Счет на {amount}₽\n👇 Нажмите ОПЛАТИТЬ", call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            bot.edit_message_text(f"❌ Ошибка {response.status_code}", call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {str(e)[:100]}", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_"))
def check_payment(call):
    tid = call.data.split("_")[1]
    headers = {"X-MerchantId": MERCHANT_ID, "X-Secret": API_SECRET}
    try:
        r = requests.get(f"{PLATEGA_API_URL}/transaction/{tid}", headers=headers)
        if r.status_code == 200 and r.json().get("status") == "CONFIRMED":
            bot.answer_callback_query(call.id, "✅ Оплачено!")
            bot.send_message(call.message.chat.id, "✅ Подписка активирована!")
        else:
            bot.answer_callback_query(call.id, "⏳ Не оплачено", show_alert=True)
    except:
        bot.answer_callback_query(call.id, "❌ Ошибка")

@bot.message_handler(func=lambda m: m.text == "ℹ️ Информация")
def info_menu(m):
    bot.send_message(m.chat.id, "ℹ️ Бот для продажи подписок\nПоддержка: @nikita1055\nКанал: @keepersell", reply_markup=info_buttons())

@bot.message_handler(func=lambda m: m.text == "⚙️ Админ-панель" and is_admin(m.from_user.id))
def admin_panel(m):
    bot.send_message(m.chat.id, "Админ-панель", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "➕ Добавить ключи" and is_admin(m.from_user.id))
def add_keys(m):
    msg = bot.send_message(m.chat.id, "Введите ключи (каждый с новой строки):\nФормат: КЛЮЧ lite 1")
    bot.register_next_step_handler(msg, save_keys)

def save_keys(m):
    added = 0
    for line in m.text.split('\n'):
        parts = line.strip().split()
        if len(parts) >= 3:
            if db.add_key(parts[0], parts[1].lower(), int(parts[2])):
                added += 1
    bot.send_message(m.chat.id, f"✅ Добавлено: {added}")

@bot.message_handler(func=lambda m: m.text == "📋 Список ключей" and is_admin(m.from_user.id))
def list_keys(m):
    keys = db.get_all_keys()
    if not keys:
        bot.send_message(m.chat.id, "Нет ключей")
        return
    text = "🔑 КЛЮЧИ:\n"
    for k in keys[-20:]:
        text += f"{k[1]} - {k[2].upper()} {k[3]}д. - {'✅' if k[4]==0 else '❌'}\n"
    bot.send_message(m.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "📊 Статистика" and is_admin(m.from_user.id))
def show_stats(m):
    s = db.get_stats()
    bot.send_message(m.chat.id, f"📊 Статистика\n👥 Пользователей: {s['total_users']}\n✅ Активных: {s['active_subs']}\n💰 Доход: {s['total_income']}₽")

@bot.message_handler(func=lambda m: m.text == "◀️ Назад")
def back_to_main(m):
    bot.send_message(m.chat.id, "Главное меню", reply_markup=main_menu(is_admin(m.from_user.id)))

@app.route('/')
def index():
    return "Bot works!", 200

@app.route('/telegram_webhook', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return "OK", 200
    except:
        return "Error", 200

@app.route('/webhook', methods=['POST'])
def platega_wh():
    try:
        data = request.json
        if data.get('status') == "CONFIRMED" and data.get('payload'):
            parts = data['payload'].split('_')
            if len(parts) >= 4:
                db.activate_subscription(int(parts[1]), parts[2], int(parts[3].replace('day', '')))
                bot.send_message(int(parts[1]), "✅ Оплата подтверждена! Подписка активирована.")
        return jsonify({"status": "ok"}), 200
    except:
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    print("🚀 БОТ ЗАПУЩЕН! РЕАЛЬНЫЕ ПЛАТЕЖИ PLATEGA!")
    print(f"📡 Callback URL: {RAILWAY_URL}/webhook")
    app.run(host='0.0.0.0', port=5000)
