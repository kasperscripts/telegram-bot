from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import PRICES, SUPPORT_USERNAME, MAIN_CHANNEL, REVIEWS_CHANNEL, PRIVACY_POLICY_URL, TERMS_OF_USE_URL

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
        InlineKeyboardButton("👑 VIP подписка", callback_data="choose_vip"),
        InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")
    )
    return markup

def lite_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(f"🎫 1 день - {PRICES['lite_1day']}₽", callback_data="buy_lite_1day"),
        InlineKeyboardButton(f"🎫 7 дней - {PRICES['lite_7day']}₽", callback_data="buy_lite_7day"),
        InlineKeyboardButton("◀️ Назад к выбору", callback_data="back_to_choice")
    )
    return markup

def vip_duration_buttons():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(f"👑 1 день - {PRICES['vip_1day']}₽", callback_data="buy_vip_1day"),
        InlineKeyboardButton(f"👑 7 дней - {PRICES['vip_7day']}₽", callback_data="buy_vip_7day"),
        InlineKeyboardButton(f"👑 14 дней - {PRICES['vip_14day']}₽", callback_data="buy_vip_14day"),
        InlineKeyboardButton("◀️ Назад к выбору", callback_data="back_to_choice")
    )
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        KeyboardButton("➕ Добавить ключи"),
        KeyboardButton("🔑 Активировать ключ"),
        KeyboardButton("🗑 Удалить ключ"),
        KeyboardButton("📋 Список ключей"),
        KeyboardButton("💰 Изменить цены"),
        KeyboardButton("📊 Статистика"),
        KeyboardButton("⭐ Управление отзывами"),
        KeyboardButton("◀️ Назад в меню")
    ]
    markup.add(*buttons)
    return markup

def info_buttons():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("💬 Техподдержка", url=f"https://t.me/{SUPPORT_USERNAME}"),
        InlineKeyboardButton("📢 Основной канал", url=f"https://t.me/{MAIN_CHANNEL.lstrip('@')}"),
        InlineKeyboardButton("⭐ Отзывы", url=REVIEWS_CHANNEL),
        InlineKeyboardButton("✍️ Оставить отзыв", callback_data="write_review"),
        InlineKeyboardButton("📄 Политика конфиденциальности", url=PRIVACY_POLICY_URL),
        InlineKeyboardButton("📑 Пользовательское соглашение", url=TERMS_OF_USE_URL)
    )
    return markup

def review_rating():
    markup = InlineKeyboardMarkup(row_width=5)
    buttons = [InlineKeyboardButton(str(i), callback_data=f"rate_{i}") for i in range(1, 6)]
    markup.add(*buttons)
    return markup