import telebot
from telebot.types import Message, CallbackQuery
import config
from database import Database
from keyboards import *
import uuid
from datetime import datetime

bot = telebot.TeleBot(config.BOT_TOKEN)
db = Database()
user_states = {}

def is_admin(user_id):
    return user_id in config.ADMIN_IDS

# ---------- СТАРТ ----------
@bot.message_handler(commands=['start'])
def start_command(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    db.add_user(user_id, username)
    
    welcome_text = (
        f"🤖 Добро пожаловать, {message.from_user.first_name}!\n\n"
        "🌟 Здесь вы можете приобрести подписки LITE и VIP.\n\n"
        "📌 Вся информация в разделе ℹ️ Информация"
    )
    
    bot.send_message(user_id, welcome_text, reply_markup=main_menu(is_admin(user_id)))

# ---------- ПРОФИЛЬ ----------
@bot.message_handler(func=lambda message: message.text == "👤 Мой профиль")
def profile(message: Message):
    user = db.get_user(message.from_user.id)
    
    if user is None:
        bot.send_message(message.chat.id, "❌ Ошибка! Попробуйте позже.")
        return
    
    sub_type, end_date = db.check_subscription(message.from_user.id)
    
    text = f"👤 **Ваш профиль**\n\n"
    text += f"🆔 ID: {user[0]}\n"
    
    if sub_type:
        days_left = (end_date - datetime.now()).days
        hours_left = (end_date - datetime.now()).seconds // 3600
        text += f"📅 Подписка: {sub_type.upper()}\n"
        text += f"⏰ Действует до: {end_date.strftime('%d.%m.%Y %H:%M')}\n"
        text += f"⌛ Осталось: {days_left} д. {hours_left} ч.\n"
    else:
        text += f"❌ Нет активной подписки\n"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ---------- ПОКУПКА ПОДПИСКИ (ЗАГЛУШКА - НЕ ДАЕТ ОПЛАТИТЬ) ----------
@bot.message_handler(func=lambda message: message.text == "🌟 Купить подписку")
def buy_subscription(message: Message):
    bot.send_message(
        message.chat.id, 
        "🌟 **Выберите тип подписки:**", 
        parse_mode="Markdown",
        reply_markup=choose_subscription_type()
    )

@bot.callback_query_handler(func=lambda call: call.data == "choose_lite")
def choose_lite(call: CallbackQuery):
    text = (
        "🌟 **LITE подписка**\n\n"
        "✅ Базовые возможности\n"
        f"💰 1 день - {config.PRICES['lite_1day']}₽\n"
        f"💰 7 дней - {config.PRICES['lite_7day']}₽\n\n"
        "📅 **Выберите период:**"
    )
    bot.edit_message_text(
        text, 
        call.message.chat.id, 
        call.message.message_id, 
        parse_mode="Markdown"
    )
    bot.edit_message_reply_markup(
        call.message.chat.id, 
        call.message.message_id, 
        reply_markup=lite_duration_buttons()
    )

@bot.callback_query_handler(func=lambda call: call.data == "choose_vip")
def choose_vip(call: CallbackQuery):
    text = (
        "👑 **VIP подписка**\n\n"
        "✅ Все возможности LITE\n"
        "✅ Приоритетная поддержка\n"
        "✅ Эксклюзивный контент\n"
        f"💰 1 день - {config.PRICES['vip_1day']}₽\n"
        f"💰 7 дней - {config.PRICES['vip_7day']}₽\n"
        f"💰 14 дней - {config.PRICES['vip_14day']}₽\n\n"
        "📅 **Выберите период:**"
    )
    bot.edit_message_text(
        text, 
        call.message.chat.id, 
        call.message.message_id, 
        parse_mode="Markdown"
    )
    bot.edit_message_reply_markup(
        call.message.chat.id, 
        call.message.message_id, 
        reply_markup=vip_duration_buttons()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def process_buy(call: CallbackQuery):
    _, sub_type, duration = call.data.split("_")
    key = f"{sub_type}_{duration}"
    
    if key not in config.PRICES:
        bot.answer_callback_query(call.id, "❌ Ошибка!")
        return
    
    price = config.PRICES[key]
    days = int(duration.replace("day", ""))
    
    # ЗАГЛУШКА - ПОКАЗЫВАЕМ, ЧТО ОПЛАТА НЕ РАБОТАЕТ
    text = (
        "⏳ **Оплата временно недоступна**\n\n"
        "💳 Платежная система в разработке.\n\n"
        "🔜 Скоро здесь появится возможность оплаты.\n\n"
        "📞 По всем вопросам:\n"
        f"@nikita1055"
    )
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("💬 Поддержка", url="https://t.me/nikita1055"),
        InlineKeyboardButton("◀️ Назад", callback_data="back_to_choice")
    )
    
    bot.edit_message_text(
        text, 
        call.message.chat.id, 
        call.message.message_id, 
        parse_mode="Markdown",
        reply_markup=markup
    )
    bot.answer_callback_query(call.id, "⏳ Оплата в разработке")

# ---------- АКТИВАЦИЯ КЛЮЧА (ДЛЯ АДМИНОВ) ----------
@bot.message_handler(func=lambda message: message.text == "🔑 Активировать ключ" and is_admin(message.from_user.id))
def activate_key_prompt(message: Message):
    msg = bot.send_message(message.chat.id, "🔑 **Введите ключ активации:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_activation)

def process_activation(message: Message):
    key_code = message.text.strip()
    success, sub_type, days = db.use_key(key_code, message.from_user.id)
    
    if success:
        end_date = db.check_subscription(message.from_user.id)[1]
        bot.send_message(
            message.chat.id,
            f"✅ **Ключ активирован!**\n\n"
            f"📦 Подписка: {sub_type.upper()}\n"
            f"📅 Период: {days} д.\n"
            f"⏰ Действует до: {end_date.strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )
    else:
        bot.send_message(message.chat.id, "❌ **Неверный или использованный ключ!**", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_choice")
def back_to_choice(call: CallbackQuery):
    text = "🌟 **Выберите тип подписки:**"
    bot.edit_message_text(
        text, 
        call.message.chat.id, 
        call.message.message_id, 
        parse_mode="Markdown",
        reply_markup=choose_subscription_type()
    )

# ---------- ОТЗЫВЫ ----------
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

# ---------- ИНФОРМАЦИЯ ----------
@bot.message_handler(func=lambda message: message.text == "ℹ️ Информация")
def info_menu(message: Message):
    text = (
        "ℹ️ **ИНФОРМАЦИЯ**\n\n"
        "🤖 **Бот для продажи подписок LITE и VIP**\n\n"
        "📌 **Как пользоваться:**\n"
        "• Купите подписку через меню\n"
        "• После оплаты ключ придет в чат\n\n"
        "💳 **Оплата:**\n"
        "• Временно недоступна\n"
        "• Ведутся технические работы\n\n"
        "📞 **КОНТАКТЫ:**\n"
        f"• Техподдержка: @{config.SUPPORT_USERNAME}\n"
        f"• Основной канал: {config.MAIN_CHANNEL}\n"
        f"• Отзывы: {config.REVIEWS_CHANNEL}\n\n"
        "⚖️ **ДОКУМЕНТЫ:**\n"
        "• Политика конфиденциальности\n"
        "• Пользовательское соглашение"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True, reply_markup=info_buttons())

# ---------- АДМИН-ПАНЕЛЬ ----------
@bot.message_handler(func=lambda message: message.text == "⚙️ Админ-панель" and is_admin(message.from_user.id))
def admin_panel(message: Message):
    bot.send_message(message.chat.id, "⚙️ **Админ-панель**", parse_mode="Markdown", reply_markup=admin_menu())

# Добавление ключей
@bot.message_handler(func=lambda message: message.text == "➕ Добавить ключи" and is_admin(message.from_user.id))
def add_keys_menu(message: Message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🌟 LITE 1 день", callback_data="addkey_lite_1"),
        InlineKeyboardButton("🌟 LITE 7 дней", callback_data="addkey_lite_7"),
        InlineKeyboardButton("👑 VIP 1 день", callback_data="addkey_vip_1"),
        InlineKeyboardButton("👑 VIP 7 дней", callback_data="addkey_vip_7"),
        InlineKeyboardButton("👑 VIP 14 дней", callback_data="addkey_vip_14")
    )
    bot.send_message(message.chat.id, "🔑 **Выберите тип ключа:**", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("addkey_"))
def ask_for_keys(call: CallbackQuery):
    _, sub_type, days = call.data.split("_")
    user_states[call.from_user.id] = {"sub_type": sub_type, "days": int(days)}
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, f"📝 **Введите ключи для {sub_type.upper()} на {days} д.**\n\nКаждый ключ с новой строки:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, save_keys)

def save_keys(message: Message):
    keys = message.text.strip().split('\n')
    data = user_states.get(message.from_user.id, {})
    sub_type = data.get("sub_type")
    days = data.get("days")
    
    added = 0
    for key in keys:
        key = key.strip()
        if key:
            if db.add_key(key, sub_type, days):
                added += 1
    
    bot.send_message(message.chat.id, f"✅ **Добавлено ключей: {added}**", parse_mode="Markdown")
    if message.from_user.id in user_states:
        del user_states[message.from_user.id]

# Список ключей
@bot.message_handler(func=lambda message: message.text == "📋 Список ключей" and is_admin(message.from_user.id))
def list_keys(message: Message):
    keys = db.get_all_keys()
    if not keys:
        bot.send_message(message.chat.id, "📭 **Нет ключей.**", parse_mode="Markdown")
        return
    
    text = "🔑 **ВСЕ КЛЮЧИ:**\n\n"
    for key in keys:
        key_id, key_code, sub_type, days, is_used, used_by = key
        status = "❌ ИСПОЛЬЗОВАН" if is_used else "✅ АКТИВЕН"
        text += f"`{key_code}` - {sub_type.upper()} {days}д. - {status}\n"
    
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            bot.send_message(message.chat.id, text[i:i+4000], parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

# Удаление ключа
@bot.message_handler(func=lambda message: message.text == "🗑 Удалить ключ" and is_admin(message.from_user.id))
def delete_key_prompt(message: Message):
    msg = bot.send_message(message.chat.id, "🗑 **Введите ключ для удаления:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, delete_key)

def delete_key(message: Message):
    key_code = message.text.strip()
    keys = db.get_all_keys()
    for key in keys:
        if key[1] == key_code:
            db.delete_key(key[0])
            bot.send_message(message.chat.id, f"✅ **Ключ {key_code} удален!**", parse_mode="Markdown")
            return
    bot.send_message(message.chat.id, f"❌ **Ключ не найден!**", parse_mode="Markdown")

# Изменение цен
@bot.message_handler(func=lambda message: message.text == "💰 Изменить цены" and is_admin(message.from_user.id))
def change_prices_menu(message: Message):
    text = "**💰 ТЕКУЩИЕ ЦЕНЫ:**\n\n"
    for key, price in config.PRICES.items():
        sub_type, days = key.split("_")
        days_num = days.replace("day", "")
        text += f"• {sub_type.upper()} {days_num} д.: {price}₽\n"
    
    text += "\n**Изменить цену:**\nОтправьте: `lite_1day:150`"
    
    msg = bot.send_message(message.chat.id, text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, update_price)

def update_price(message: Message):
    try:
        key, new_price = message.text.split(":")
        new_price = int(new_price)
        if key in config.PRICES:
            config.PRICES[key] = new_price
            bot.send_message(message.chat.id, f"✅ **Цена изменена!**", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ **Неверный ключ!**", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "❌ **Неверный формат!**", parse_mode="Markdown")

# Статистика
@bot.message_handler(func=lambda message: message.text == "📊 Статистика" and is_admin(message.from_user.id))
def show_stats(message: Message):
    stats = db.get_stats()
    text = (
        "📊 **СТАТИСТИКА**\n\n"
        f"👥 Пользователей: {stats['total_users']}\n"
        f"✅ Активных: {stats['active_subs']}\n"
        f"🔑 Активаций: {stats['total_activations']}\n"
        f"💰 Доход: {stats['total_income']}₽\n"
        f"🆓 Ключей: {stats['unused_keys']}"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# Управление отзывами
@bot.message_handler(func=lambda message: message.text == "⭐ Управление отзывами" and is_admin(message.from_user.id))
def manage_reviews(message: Message):
    pending = db.get_pending_reviews()
    if not pending:
        bot.send_message(message.chat.id, "✅ **Нет отзывов на модерации.**", parse_mode="Markdown")
        return
    
    for review in pending:
        rev_id, user_id, text, rating, created_at = review
        user = db.get_user(user_id)
        username = user[1] if user else str(user_id)
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_review_{rev_id}"),
            InlineKeyboardButton("❌ Удалить", callback_data=f"delete_review_{rev_id}")
        )
        
        bot.send_message(
            message.chat.id,
            f"⭐ **Отзыв**\n\n👤 @{username}\n⭐ {rating}/5\n📝 {text}",
            parse_mode="Markdown",
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_review_"))
def approve_review(call: CallbackQuery):
    review_id = int(call.data.split("_")[2])
    db.approve_review(review_id)
    bot.answer_callback_query(call.id, "✅ Одобрено!")
    bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_review_"))
def delete_review(call: CallbackQuery):
    review_id = int(call.data.split("_")[2])
    db.delete_review(review_id)
    bot.answer_callback_query(call.id, "❌ Удалено!")
    bot.delete_message(call.message.chat.id, call.message.message_id)

# ---------- НАВИГАЦИЯ ----------
@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call: CallbackQuery):
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, "🏠 **Главное меню**", parse_mode="Markdown", reply_markup=main_menu(is_admin(call.from_user.id)))

@bot.message_handler(func=lambda message: message.text == "◀️ Назад в меню")
def back_to_main(message: Message):
    bot.send_message(message.chat.id, "🏠 **Главное меню**", parse_mode="Markdown", reply_markup=main_menu(is_admin(message.from_user.id)))

# ---------- ЗАПУСК ----------
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН!")
    print(f"👑 Администраторы: {config.ADMIN_IDS}")
    print(f"💬 Поддержка: @{config.SUPPORT_USERNAME}")
    print("=" * 50)
    print("РЕЖИМ: ЗАГЛУШКА ОПЛАТЫ")
    print("Оплата временно недоступна")
    print("=" * 50)
    bot.infinity_polling()