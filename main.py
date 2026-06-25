import asyncio
import os
import ssl
import uuid
import hashlib
import http.client
import hmac
import socket        
import json        
import subprocess
import urllib.request  
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import aiohttp
import requests  
import re

from config import BOT_TOKEN, ADMIN_IDS, RAILWAY_URL, CHANNEL_ID, CRYPTOBOT_TOKEN, PLATEGA_MERCHANT_ID, PLATEGA_API_SECRET
from database import (
    connect_db, add_user, get_balance, get_all_products,
    add_product, add_keys_to_product, get_unused_key,
    mark_key_as_used, update_user_balance, add_purchase, get_user_purchases, get_stats,
    get_all_users, create_promocode, get_promocode, use_promocode, check_promocode_used,
    get_all_promocodes, delete_promocode, get_referrer, get_referrals_count, get_paid_referrals_count,
    get_referral_config, update_referral_config, add_balance, get_product_by_id,
    delete_product, get_keys_by_product, delete_key, mark_purchased, has_user_purchased,
    get_setting, update_setting, get_crypto_fee, set_crypto_fee,
    update_order_status, get_pending_order, save_pending_order, pool
)

EMOJI = {
    "crypto": "5361914370068613491",
    "sbp": "5363972466857252756",
    "wallet": "5310191758255099001",
    "shop": "5361781191722699867",
    "lamp": "5362084755716214813",
    "arrow_down": "5899757765743615694",
    "arrow_back": "5875082500023258804",
    "key": "6005570495603282482",
    "check": "5825794181183836432",
    "document": "5875206779196935950",
    "folder": "5877332341331857066",
    "discount": "5843843420468024653",
    "person": "5879770735999717115",
    "clock": "5985616167740379273",
    "repeat": "5845943483382110702",
    "important": "5775887550262546277",
    "verified": "5931409969613116639",
    "phone": "5897488197650223178",
    "smile": "5942913498349571809",
    "gift": "5985472565508838112",
    "store": "5983399041197675256",
    "dollar": "5992430854909989581",
    "almaz": "5807465992363710697",
    "android": "5819078828017849357",
    "calendar": "5967412305338568701",
    "game": "5298938939644590718",
    "welcome": "5388795032775968174",
    "joy": "5199552932558683107",
    "heart": "5199427253225667842",
    "magic": "5474144592817318927",
    "cat_surprised": "5242261773817492813",
    "cat_wink": "5199427253225667842",
    "cat_dance": "5359444458930718519",
    "joystick": "5870717606364713020",
    "notification": "5870886806601338791",
    "pin": "5870930744116776638",
    "crown": "5807868868886009920",
    "new": "5886306834410640699",
    "edit": "5985774024968379294",
    "camera": "5870856037455630084",
    "cat": "5359444458930718519",
    "trash": "5871053528743158021",
}

def emoji(sticker_id: str, fallback: str = "") -> str:
    return f'<tg-emoji emoji-id="{sticker_id}">{fallback}</tg-emoji>'

_orig_getaddrinfo = socket.getaddrinfo

def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == "pay.cryptobot.net":
        try:
            req = urllib.request.Request(
                "https://1.1.1.1/dns-query?name=pay.cryptobot.net",
                headers={"Accept": "application/dns-json"}
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                dns_data = json.loads(response.read().decode())
                if "Answer" in dns_data:
                    ips = [item["data"] for item in dns_data["Answer"] if item["type"] == 1]
                    if ips:
                        return _orig_getaddrinfo(ips[0], port, family, type, proto, flags)
        except Exception as e:
            print(f"[DNS Патч] Ошибка: {e}", flush=True)
            return _orig_getaddrinfo("172.67.73.187", port, family, type, proto, flags)
            
    return _orig_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = _patched_getaddrinfo

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
flask_app = Flask(__name__)

pending_payments = {}
main_loop = None
processed_payments = set()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

class AddProductStates(StatesGroup):
    waiting_name = State()
    waiting_price = State()
    waiting_keys = State()

class AddKeysStates(StatesGroup):
    waiting_product_id = State()
    waiting_keys = State()

class DepositStates(StatesGroup):
    waiting_amount = State()
    waiting_method = State() 

class AdminAddBalanceStates(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()

class AdminBroadcastStates(StatesGroup):
    waiting_message = State()

class AdminCreatePromocodeStates(StatesGroup):
    waiting_code = State()
    waiting_type = State()
    waiting_value = State()
    waiting_max_uses = State()

class ProfileActivatePromocodeStates(StatesGroup):
    waiting_code = State()

class AdminRefBonusStates(StatesGroup):
    waiting_type = State()
    waiting_value = State()

class AdminCustomTextStates(StatesGroup):
    waiting_text = State()

class ManualDepositStates(StatesGroup):
    waiting_amount = State()
    waiting_screenshot = State()

class AdminCryptoFeeStates(StatesGroup):
    waiting_fee = State()

async def get_usdt_rate() -> float:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=rub") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rate = float(data["tether"]["rub"])
                    print(f"[Курс] USDT/RUB: {rate}")
                    return rate
    except:
        pass
    print("[Курс] Запасной курс: 72 RUB за USDT")
    return 72.0

CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"

def create_crypto_invoice(amount_usd, order_id, user_id):
    headers = {
        "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN,
        "Content-Type": "application/json"
    }
    
    data = {
        "asset": "USDT",
        "amount": str(amount_usd),
        "description": f"Пополнение баланса #{order_id}",
        "payload": f"{user_id}_{order_id}"
    }
    
    try:
        response = requests.post(
            f"{CRYPTOBOT_API_URL}/createInvoice",
            headers=headers,
            json=data,
            timeout=30
        )
        
        print(f"[CryptoBot] Статус: {response.status_code}")
        print(f"[CryptoBot] Ответ: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                invoice = result.get("result")
                return {
                    "success": True,
                    "payment_url": invoice.get("pay_url"),
                    "invoice_id": str(invoice.get("invoice_id")),
                    "status": invoice.get("status")
                }
        return {"success": False, "error": f"Ошибка {response.status_code}: {response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def create_vip_link(user_id: int, days: int = 30):
    try:
        invite_link = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=datetime.now() + timedelta(days=days)
        )
        return invite_link.invite_link
    except:
        return None

async def create_platega_payment(amount: int, order_id: str, user_id: int) -> str:
    if not PLATEGA_MERCHANT_ID or not PLATEGA_API_SECRET:
        print("[Platega] Не настроен магазин")
        return None
    
    url = "https://app.platega.io/v2/transaction/process"
    
    headers = {
        "Content-Type": "application/json",
        "X-MerchantId": PLATEGA_MERCHANT_ID,
        "X-Secret": PLATEGA_API_SECRET
    }
    
    bot_username = (await bot.get_me()).username
    
    data = {
        "command": "create",
        "paymentDetails": {
            "amount": float(amount),
            "currency": "RUB"
        },
        "description": f"Заказ {order_id} для пользователя {user_id}",
        "return": f"https://t.me/{bot_username}",
        "failedUrl": f"https://t.me/{bot_username}",
        "payload": f"order_{user_id}_{order_id}",
        "paymentMethod": ["SBP", "CRYPTO"]
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as resp:
                result = await resp.json()
                print(f"[Platega] Ответ: {result}")
                if result.get("url"):
                    return result.get("url")
                return None
        except Exception as e:
            print(f"[Platega] Ошибка: {e}")
            return None

async def create_crypto_payment(desired_amount: int, order_id: str, user_id: int) -> str:
    if not CRYPTOBOT_TOKEN:
        print("[CryptoBot] Нет токена")
        return None
    
    crypto_fee = await get_crypto_fee()
    
    if crypto_fee > 0:
        amount_to_pay = round(desired_amount / (1 - crypto_fee / 100))
    else:
        amount_to_pay = desired_amount
    
    usdt_rate = await get_usdt_rate()
    usdt_amount = round(amount_to_pay / usdt_rate, 2)
    
    print(f"[CryptoBot] ==================================")
    print(f"[CryptoBot] КУРС: 1 USDT = {usdt_rate} RUB")
    print(f"[CryptoBot] Желаемая сумма на баланс: {desired_amount} RUB")
    print(f"[CryptoBot] Комиссия: {crypto_fee}%")
    print(f"[CryptoBot] Сумма к оплате: {amount_to_pay} RUB")
    print(f"[CryptoBot] Сумма в USDT: {usdt_amount}")
    print(f"[CryptoBot] ==================================")
    
    pending_payments[user_id] = {
        "amount": desired_amount,
        "order_id": order_id,
        "invoice_id": None,
        "status": "pending"
    }
    
    result = create_crypto_invoice(usdt_amount, order_id, user_id)
    
    if result.get("success"):
        pending_payments[user_id]["invoice_id"] = result["invoice_id"]
        return result["payment_url"]
    else:
        print(f"[CryptoBot] Ошибка: {result.get('error')}")
        if user_id in pending_payments:
            del pending_payments[user_id]
        return None

def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Магазин", callback_data="menu_shop", icon_custom_emoji_id=EMOJI["store"]),
            InlineKeyboardButton(text="Профиль", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["person"])
        ],
        [
            InlineKeyboardButton(text="Информация", callback_data="menu_info", icon_custom_emoji_id=EMOJI["document"])
        ]
    ])

def get_profile_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Пополнить баланс", callback_data="profile_deposit", icon_custom_emoji_id=EMOJI["dollar"]),
            InlineKeyboardButton(text="История заказов", callback_data="profile_history", icon_custom_emoji_id=EMOJI["folder"])
        ],
        [
            InlineKeyboardButton(text="Активировать промокод", callback_data="profile_activate_promocode", icon_custom_emoji_id=EMOJI["discount"]),
            InlineKeyboardButton(text="Реферальная система", callback_data="profile_referral", icon_custom_emoji_id=EMOJI["repeat"])
        ],
        [
            InlineKeyboardButton(text="Главное меню", callback_data="menu_main", icon_custom_emoji_id=EMOJI["arrow_back"])
        ]
    ])

def get_admin_keyboard(shop_mode="auto"):
    mode_text = "Режим: Авто" if shop_mode == "auto" else "Режим: Ручной"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Добавить товар", callback_data="admin_add_product", icon_custom_emoji_id=EMOJI["shop"]),
            InlineKeyboardButton(text="Добавить ключи", callback_data="admin_add_keys", icon_custom_emoji_id=EMOJI["key"])
        ],
        [
            InlineKeyboardButton(text="Выдать баланс", callback_data="admin_add_balance", icon_custom_emoji_id=EMOJI["dollar"]),
            InlineKeyboardButton(text="Сделать рассылку", callback_data="admin_broadcast", icon_custom_emoji_id=EMOJI["notification"])
        ],
        [
            InlineKeyboardButton(text="Создать промокод", callback_data="admin_create_promocode", icon_custom_emoji_id=EMOJI["discount"]),
            InlineKeyboardButton(text="Список промокодов", callback_data="admin_list_promocodes", icon_custom_emoji_id=EMOJI["folder"])
        ],
        [
            InlineKeyboardButton(text="Настройка рефералов", callback_data="admin_ref_config", icon_custom_emoji_id=EMOJI["repeat"]),
            InlineKeyboardButton(text="Комиссия крипты", callback_data="admin_crypto_fee", icon_custom_emoji_id=EMOJI["crypto"])
        ],
        [
            InlineKeyboardButton(text=mode_text, callback_data="admin_toggle_mode"),
            InlineKeyboardButton(text="Текст кастома", callback_data="admin_change_custom_text", icon_custom_emoji_id=EMOJI["edit"])
        ],
        [
            InlineKeyboardButton(text="Управление товарами", callback_data="admin_manage_products", icon_custom_emoji_id=EMOJI["store"]),
            InlineKeyboardButton(text="Управление ключами", callback_data="admin_manage_keys", icon_custom_emoji_id=EMOJI["key"])
        ],
        [
            InlineKeyboardButton(text="Статистика", callback_data="admin_stats", icon_custom_emoji_id=EMOJI["crown"]),
            InlineKeyboardButton(text="Главное меню", callback_data="menu_main", icon_custom_emoji_id=EMOJI["arrow_back"])
        ]
    ])

@dp.message(CommandStart())
async def start_cmd(message: Message):
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].split("_")[1])
            if referrer_id == message.from_user.id:
                referrer_id = None
        except:
            pass
    
    await add_user(message.from_user.id, referrer_id)
    
    text = (
        f"{emoji(EMOJI['welcome'], '✨')} <b>Добро пожаловать в KeeperShop</b>\n\n"
        f"{emoji(EMOJI['magic'], '✨')} <b>Официальный магазин ключей Magic</b>\n\n"
        f"{emoji(EMOJI['arrow_down'], '👇')} <b>Для покупки товаров используйте кнопки ниже</b>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.callback_query(lambda c: c.data == "menu_main")
async def menu_main(callback: CallbackQuery):
    text = f"{emoji(EMOJI['magic'], '✨')} <b>Главное меню</b>\n\nВыберите действие:"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_info")
async def menu_info(callback: CallbackQuery):
    info_text = (
        f"{emoji(EMOJI['document'], 'ℹ')} <b>ИНФОРМАЦИЯ</b> {emoji(EMOJI['document'], 'ℹ')}\n\n"
        f"{emoji(EMOJI['cat'], '🐱')} <b>Официальный бот по продаже ключей для чит клиента Magic</b>\n\n"
        f"{emoji(EMOJI['sbp'], '💳')} <b>Оплата:</b> Platega (СБП), {emoji(EMOJI['crypto'], '🪙')} Crypto Pay (Криптовалюта)\n\n"
        f"{emoji(EMOJI['important'], '📌')} <b>Как пользоваться:</b>\n"
        f"• Приобретите ключ через меню\n"
        f"• После оплаты вы получите ключ и доступ в VIP канал\n\n"
        f"{emoji(EMOJI['phone'], '📞')} <b>КОНТАКТЫ:</b>\n"
        f"• Техподдержка: @nikita1055\n"
        f"• Основной канал: @keepersell\n"
        f"• Отзывы: https://t.me/KeeperOtzivi\n\n"
        f"{emoji(EMOJI['important'], '⚖')} <b>ДОКУМЕНТЫ:</b>\n"
        f"• <a href='https://telegra.ph/Politika-konfidencialnosti-04-01-26'>Политика конфиденциальности</a>\n"
        f"• <a href='https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19'>Пользовательское соглашение</a>\n\n"
        f"{emoji('5199942808214976824', '🤖')} <b>Похожего бота можно заказать у @ZOJlOTOY</b>"
    )
    await callback.message.edit_text(info_text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_main", icon_custom_emoji_id=EMOJI["arrow_back"])]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_shop")
async def menu_shop(callback: CallbackQuery):
    products = await get_all_products()
    if not products:
        await callback.message.edit_text(
            f"{emoji(EMOJI['key'], '📭')} <b>Товаров пока нет</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_main", icon_custom_emoji_id=EMOJI["arrow_back"])]])
        )
        await callback.answer()
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{p['name']} | {p['price']}₽", callback_data=f"buy_{p['id']}", icon_custom_emoji_id=EMOJI["joystick"])]
        for p in products
    ] + [[InlineKeyboardButton(text="Назад", callback_data="menu_main", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    
    await callback.message.edit_text(
        f"{emoji(EMOJI['store'], '🛍')} <b>Выберите интересующий вас товар</b>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    balance = await get_balance(callback.from_user.id)
    text = (
        f"{emoji(EMOJI['person'], '👤')} <b>Профиль</b>\n\n"
        f"{emoji(EMOJI['verified'], '🆔')} ID: <code>{callback.from_user.id}</code>\n"
        f"{emoji(EMOJI['almaz'], '💰')} Баланс: <code>{balance} ₽</code>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_profile_keyboard())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile_referral")
async def profile_referral(callback: CallbackQuery):
    user_id = callback.from_user.id
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    total_referrals = await get_referrals_count(user_id)
    paid_referrals = await get_paid_referrals_count(user_id)
    config = await get_referral_config()
    
    if config["bonus_type"] == "rubles":
        bonus_text = f"{config['bonus_value']} ₽"
    else:
        bonus_text = f"{config['bonus_value']}% от покупки"
    
    text = (
        f"{emoji(EMOJI['repeat'], '👥')} <b>Реферальная система</b>\n\n"
        f"{emoji(EMOJI['key'], '🔗')} <b>Ваша ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"{emoji(EMOJI['person'], '👥')} Приглашено друзей: <code>{total_referrals}</code>\n"
        f"{emoji(EMOJI['check'], '✅')} Из них купили: <code>{paid_referrals}</code>\n"
        f"{emoji(EMOJI['gift'], '🎁')} <b>Награда за покупку друга:</b> {bonus_text}\n\n"
        f"{emoji(EMOJI['lamp'], '💡')} Награда начисляется после первой покупки вашего друга!\n\n"
        f"{emoji(EMOJI['cat_wink'], '😉')} <i>Приглашайте друзей и получайте бонусы!</i>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile_history")
async def profile_history(callback: CallbackQuery):
    purchases = await get_user_purchases(callback.from_user.id)
    
    if not purchases:
        await callback.message.edit_text(
            f"{emoji(EMOJI['folder'], '📋')} <b>История заказов</b>\n\nУ вас пока нет покупок.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]])
        )
        await callback.answer()
        return
    
    history_text = f"{emoji(EMOJI['gift'], '🎉')} <b>История заказов</b>\n\n"
    for p in purchases[:10]:
        history_text += f"{emoji(EMOJI['verified'], '🆔')} Заказ #{p['id']}\n"
        history_text += f"{emoji(EMOJI['joystick'], '🎮')} Товар: {p['name']}\n"
        history_text += f"{emoji(EMOJI['dollar'], '💰')} Цена: {p['price']} ₽\n"
        history_text += f"{emoji(EMOJI['calendar'], '📅')} Дата: {p['created_at'].strftime('%d.%m.%Y %H:%M')}\n"
        history_text += "─" * 15 + "\n"
    
    await callback.message.edit_text(history_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile_deposit")
async def profile_deposit(callback: CallbackQuery, state: FSMContext):
    shop_mode = await get_setting("shop_mode")
    
    if shop_mode == "custom":
        await state.set_state(ManualDepositStates.waiting_amount)
        await callback.message.edit_text(
            f"{emoji(EMOJI['dollar'], '💰')} <b>Ручное пополнение баланса</b>\n\n"
            f"Введите сумму пополнения (от 10 до 50000 ₽):\n\n"
            f"Пример: <code>500</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]])
        )
    else:
        await state.set_state(DepositStates.waiting_amount)
        await callback.message.edit_text(
            f"{emoji(EMOJI['dollar'], '💰')} <b>Укажите сумму пополнения баланса</b>\n\n"
            f"Введите сумму от 10 до 50000 ₽\n\nПример: <code>500</code>\n\n"
            f"Отправьте число в этот чат",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]])
        )
    
    await callback.answer()

@dp.message(ManualDepositStates.waiting_amount)
async def process_manual_deposit_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount < 10 or amount > 50000:
            await message.answer(f"{emoji(EMOJI['key'], '❌')} Сумма должна быть от 10 до 50000 ₽", parse_mode="HTML")
            return
        
        await state.update_data(amount=amount)
        await state.set_state(ManualDepositStates.waiting_screenshot)
        
        custom_text = await get_setting("custom_text")
        
        await message.answer(
            f"{emoji(EMOJI['phone'], '💳')} <b>Реквизиты для оплаты:</b>\n\n"
            f"{custom_text}\n\n"
            f"{emoji(EMOJI['important'], '⚠️')} <b>ВАЖНО:</b> В комментарии к переводу укажите ваш ID: <code>{message.from_user.id}</code>\n\n"
            f"{emoji(EMOJI['camera'], '📷')} После оплаты отправьте СКРИНШОТ чека в этот чат:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]
            ])
        )
        try:
            await message.delete()
        except:
            pass
    except ValueError:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Введите число", parse_mode="HTML")

@dp.message(ManualDepositStates.waiting_screenshot)
async def process_manual_deposit_screenshot(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Пожалуйста, отправьте скриншот чека", parse_mode="HTML")
        return
    
    data = await state.get_data()
    amount = data.get("amount")
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    order_id = str(uuid.uuid4())[:8]
    
    try:
        from database import save_pending_order
        await save_pending_order(user_id, order_id, amount)
        print(f"[ManualDeposit] Создан заказ {order_id} для user_id={user_id} на сумму {amount}")
    except Exception as e:
        print(f"[ManualDeposit] Ошибка сохранения в БД: {e}")
        await message.answer("Произошла ошибка при создании заявки. Пожалуйста, попробуйте позже.")
        await state.clear()
        return
    
    photo = message.photo[-1]
    file_id = photo.file_id
    
    admin_text = (
        f"{emoji(EMOJI['notification'], '🔔')} <b>НОВЫЙ ЗАПРОС НА ПОПОЛНЕНИЕ</b>\n\n"
        f"{emoji(EMOJI['person'], '👤')} Пользователь: @{username}\n"
        f"{emoji(EMOJI['verified'], '🆔')} ID: <code>{user_id}</code>\n"
        f"{emoji(EMOJI['dollar'], '💰')} Сумма: <code>{amount} ₽</code>\n\n"
        f"{emoji(EMOJI['clock'], '⏳')} Статус: Ожидает проверки\n"
        f"ID Заявки: <code>{order_id}</code>"
    )
    
    # Короткий префикс чтобы избежать проблем с лимитом callback_data
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"ok_{order_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"no_{order_id}")
        ]
    ])
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                photo=file_id,
                caption=admin_text,
                parse_mode="HTML",
                reply_markup=admin_kb
            )
        except Exception as e:
            print(f"[ManualDeposit] Ошибка отправки админу {admin_id}: {e}")
    
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Скриншот отправлен на проверку!</b>\n\n"
        f"Сумма: <code>{amount} ₽</code>\n\n"
        f"{emoji(EMOJI['clock'], '⏳')} Администратор проверит оплату в ближайшее время.\n"
        f"После подтверждения баланс будет автоматически пополнен.",
        parse_mode="HTML",
        reply_markup=get_profile_keyboard()
    )
    
    try:
        await message.delete()
    except:
        pass
    
    await state.clear()

@dp.callback_query(lambda c: c.data and c.data.startswith("ok_"))
async def admin_confirm_deposit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    order_id = callback.data.replace("ok_", "")
    
    try:
        order = await get_pending_order(order_id)
            
        if not order:
            await callback.answer("❌ Заявка не найдена или уже обработана.", show_alert=True)
            return
        
        user_id = order['user_id']
        amount = order['amount']
        
        current_balance = await get_balance(user_id)
        await update_user_balance(user_id, current_balance + amount)
        await update_order_status(order_id, "confirmed")
        
        # Безопасно получаем caption (может быть None)
        original_caption = callback.message.caption or ""
        new_caption = original_caption + f"\n\n✅ <b>Статус: ПОДТВЕРЖДЕНО</b>\nАдминистратор: @{callback.from_user.username or callback.from_user.first_name}"
        
        await callback.message.edit_caption(
            caption=new_caption,
            parse_mode="HTML",
            reply_markup=None
        )
        
        await callback.answer(f"✅ Баланс пользователя {user_id} пополнен на {amount} ₽", show_alert=True)
        
        await bot.send_message(
            user_id,
            f"✅ <b>Ваше пополнение подтверждено!</b>\n\n"
            f"💰 Сумма: <code>{amount} ₽</code>\n"
            f"📊 Новый баланс: <code>{current_balance + amount} ₽</code>",
            parse_mode="HTML"
        )
        
    except Exception as e:
        print(f"[AdminConfirm] Ошибка при обработке заказа {order_id}: {e}")
        await callback.answer(f"❌ Произошла внутренняя ошибка: {str(e)}", show_alert=True)


@dp.callback_query(lambda c: c.data and c.data.startswith("no_"))
async def admin_reject_deposit(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return

    order_id = callback.data.replace("no_", "")
    
    try:
        order = await get_pending_order(order_id)
            
        if not order:
            await callback.answer("❌ Заявка не найдена или уже обработана.", show_alert=True)
            return
        
        user_id = order['user_id']
        amount = order['amount']
        
        await update_order_status(order_id, "rejected")
        
        original_caption = callback.message.caption or ""
        new_caption = original_caption + f"\n\n❌ <b>Статус: ОТКЛОНЕНО</b>\nАдминистратор: @{callback.from_user.username or callback.from_user.first_name}"
        
        await callback.message.edit_caption(
            caption=new_caption,
            parse_mode="HTML",
            reply_markup=None
        )
        
        await callback.answer(f"❌ Запрос пользователя {user_id} отклонен", show_alert=True)
        
        await bot.send_message(
            user_id,
            f"❌ <b>Ваше пополнение отклонено!</b>\n\n"
            f"💰 Сумма: <code>{amount} ₽</code>\n\n"
            f"Пожалуйста, попробуйте снова или свяжитесь с поддержкой.",
            parse_mode="HTML"
        )
        
    except Exception as e:
        print(f"[AdminReject] Ошибка при обработке заказа {order_id}: {e}")
        await callback.answer(f"❌ Произошла внутренняя ошибка: {str(e)}", show_alert=True)

@dp.message(DepositStates.waiting_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    shop_mode = await get_setting("shop_mode")
    if shop_mode == "custom":
        await state.clear()
        return

    try:
        amount = int(message.text.strip())
        if amount < 10 or amount > 50000:
            await message.answer(
                f"{emoji(EMOJI['key'], '❌')} Сумма должна быть от 10 до 50000 ₽\n\nПопробуйте снова:",
                parse_mode="HTML"
            )
            return
        
        await state.update_data(amount=amount)
        await state.set_state(DepositStates.waiting_method)
        
        crypto_fee = await get_crypto_fee()
        fee_text = ""
        if crypto_fee > 0:
            amount_to_pay = round(amount / (1 - crypto_fee / 100))
            fee_text = f"\n\n{emoji(EMOJI['important'], 'ℹ️')} <b>Комиссия:</b> {crypto_fee}%\nК оплате: <code>{amount_to_pay} ₽</code>\nНа баланс поступит: <code>{amount} ₽</code>"
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="СБП (Platega)", callback_data="pay_method_platega", icon_custom_emoji_id=EMOJI["sbp"]),
                InlineKeyboardButton(text="Криптовалюта (CryptoPay)", callback_data="pay_method_crypto", icon_custom_emoji_id=EMOJI["crypto"])
            ],
            [InlineKeyboardButton(text="Отмена", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]
        ])
        
        await message.answer(
            f"{emoji(EMOJI['magic'], '✨')} <b>Сумма пополнения: {amount} ₽</b>{fee_text}\n\nВыберите предпочтительный метод оплаты:",
            parse_mode="HTML",
            reply_markup=kb
        )
        try:
            await message.delete()
        except:
            pass
        
    except ValueError:
        await message.answer(
            f"{emoji(EMOJI['key'], '❌')} Введите число!\n\nПример: <code>500</code>",
            parse_mode="HTML"
        )

@dp.callback_query(DepositStates.waiting_method, lambda c: c.data in ["pay_method_platega", "pay_method_crypto"])
async def process_deposit_method(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get("amount")
    await state.clear()
    
    order_id = str(uuid.uuid4())[:8]
    user_id = callback.from_user.id
    
    await callback.answer("Генерируем счёт...")
    
    if callback.data == "pay_method_platega":
        await callback.message.edit_text(
            f"{emoji(EMOJI['clock'], '⏳')} <b>Создаем безопасную сессию СБП...</b>\nПожалуйста, подождите.", parse_mode="HTML"
        )
        payment_url = await create_platega_payment(amount, order_id, user_id)
        method_name = "Platega (СБП)"
        pending_payments[user_id] = {
            "amount": amount,
            "order_id": order_id,
            "status": "pending"
        }
        if payment_url:
            await callback.message.edit_text(
                f"{emoji(EMOJI['wallet'], '💳')} <b>Оплата через {method_name}</b>\n\n"
                f"Сумма к оплате: <code>{amount} ₽</code>\n\n"
                f"{emoji(EMOJI['key'], '🔗')} <a href='{payment_url}'>НАЖМИТЕ ТУТ ЧТОБЫ ОПЛАТИТЬ</a>\n\n"
                f"{emoji(EMOJI['verified'], '🆔')} Номер заказа: <code>{order_id}</code>\n\n"
                f"{emoji(EMOJI['magic'], '⚡')} Баланс обновится автоматически после оплаты!",
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=get_profile_keyboard()
            )
    else:
        await callback.message.edit_text(
            f"{emoji(EMOJI['clock'], '⏳')} <b>Связываемся со шлюзом CryptoBot API...</b>\nПожалуйста, подождите пару секунд.", parse_mode="HTML"
        )
        crypto_fee = await get_crypto_fee()
        amount_to_pay = round(amount / (1 - crypto_fee / 100)) if crypto_fee > 0 else amount
        payment_url = await create_crypto_payment(amount, order_id, user_id)
        method_name = "Crypto Pay (Криптовалюта)"
        
        if payment_url:
            await callback.message.edit_text(
                f"{emoji(EMOJI['wallet'], '💳')} <b>Оплата через {method_name}</b>\n\n"
                f"Сумма к оплате: <code>{amount_to_pay} ₽</code>\n"
                f"На баланс поступит: <code>{amount} ₽</code>\n\n"
                f"{emoji(EMOJI['key'], '🔗')} <a href='{payment_url}'>НАЖМИТЕ ТУТ ЧТОБЫ ОПЛАТИТЬ</a>\n\n"
                f"{emoji(EMOJI['verified'], '🆔')} Номер заказа: <code>{order_id}</code>\n\n"
                f"{emoji(EMOJI['magic'], '⚡')} Баланс обновится автоматически после оплаты!",
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=get_profile_keyboard()
            )
    
    if not payment_url:
        await callback.message.edit_text(
            f"{emoji(EMOJI['cat_surprised'], '😲')} <b>Платежная система временно недоступна</b>\n\n"
            f"Свяжитесь с администратором для ручного пополнения баланса.\n\n"
            f"{emoji(EMOJI['person'], '👤')} Админ: @nikita1055",
            parse_mode="HTML",
            reply_markup=get_profile_keyboard()
        )
        return

@dp.callback_query(lambda c: c.data == "profile_activate_promocode")
async def profile_activate_promocode(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileActivatePromocodeStates.waiting_code)
    await callback.message.edit_text(
        f"{emoji(EMOJI['new'], '🎫')} <b>Активация промокода</b>\n\n"
        f"Введите промокод:\n\n"
        f"Пример: <code>SUMMER2024</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.answer()

@dp.message(ProfileActivatePromocodeStates.waiting_code)
async def process_activate_promocode(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    promocode = await get_promocode(code)
    
    if not promocode:
        await message.answer(
            f"{emoji(EMOJI['cat_surprised'], '😲')} <b>Промокод не найден или уже использован</b>",
            parse_mode="HTML",
            reply_markup=get_profile_keyboard()
        )
        await state.clear()
        return
    
    already_used = await check_promocode_used(message.from_user.id, promocode["id"])
    if already_used:
        await message.answer(
            f"{emoji(EMOJI['key'], '❌')} <b>Вы уже активировали этот промокод</b>",
            parse_mode="HTML",
            reply_markup=get_profile_keyboard()
        )
        await state.clear()
        return
    
    current_balance = await get_balance(message.from_user.id)
    discount_type = promocode["discount_type"]
    discount_value = promocode["discount_value"]
    new_balance = current_balance
    
    if discount_type == "percent":
        new_balance = current_balance + int(current_balance * discount_value / 100)
        bonus_text = f"{discount_value}% от текущего баланса"
    elif discount_type == "rubles":
        new_balance = current_balance + discount_value
        bonus_text = f"{discount_value} ₽"
    else:
        new_balance = current_balance + discount_value
        bonus_text = f"{discount_value} ₽ бонусом"
    
    await update_user_balance(message.from_user.id, new_balance)
    await use_promocode(message.from_user.id, promocode["id"])
    
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Промокод успешно активирован!</b>\n\n"
        f"{emoji(EMOJI['discount'], '🎫')} Промокод: <code>{code}</code>\n"
        f"{emoji(EMOJI['dollar'], '💰')} Вы получили: {bonus_text}\n"
        f"{emoji(EMOJI['almaz'], '📊')} Было: <code>{current_balance} ₽</code>\n"
        f"{emoji(EMOJI['almaz'], '📊')} Стало: <code>{new_balance} ₽</code>\n\n"
        f"{emoji(EMOJI['joy'], '😊')} <i>Отличный бонус!</i>",
        parse_mode="HTML",
        reply_markup=get_profile_keyboard()
    )
    await state.clear()
    try:
        await message.delete()
    except:
        pass

@dp.callback_query(lambda c: c.data and c.data.startswith("buy_"))
async def handle_buy(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    products = await get_all_products()
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        await callback.answer("Товар не найден")
        return
    
    balance = await get_balance(user_id)
    if balance < product["price"]:
        await callback.answer(f"Недостаточно средств! Нужно {product['price']} ₽")
        return
    
    key_row = await get_unused_key(product_id)
    if not key_row:
        await callback.answer("Ключи закончились")
        return
    
    await update_user_balance(user_id, balance - product["price"])
    await mark_key_as_used(key_row["id"])
    await add_purchase(user_id, product_id, product["price"])
    
    if not await has_user_purchased(user_id):
        await mark_purchased(user_id)
        
        referrer_id = await get_referrer(user_id)
        if referrer_id:
            config = await get_referral_config()
            if config and config["bonus_value"] > 0:
                if config["bonus_type"] == "rubles":
                    await add_balance(referrer_id, config["bonus_value"])
                    await bot.send_message(
                        referrer_id,
                        f"{emoji(EMOJI['cat_dance'], '💃')} <b>Реферальный бонус!</b>\n\n"
                        f"Ваш друг @{callback.from_user.username or callback.from_user.first_name} совершил первую покупку!\n"
                        f"{emoji(EMOJI['dollar'], '💰')} Вы получили: <code>{config['bonus_value']} ₽</code>\n\n"
                        f"{emoji(EMOJI['joy'], '😊')} Поздравляем!",
                        parse_mode="HTML"
                    )
                elif config["bonus_type"] == "percent":
                    bonus_amount = int(product["price"] * config["bonus_value"] / 100)
                    await add_balance(referrer_id, bonus_amount)
                    await bot.send_message(
                        referrer_id,
                        f"{emoji(EMOJI['cat_dance'], '💃')} <b>Реферальный бонус!</b>\n\n"
                        f"Ваш друг @{callback.from_user.username or callback.from_user.first_name} совершил первую покупку на {product['price']} ₽!\n"
                        f"{emoji(EMOJI['dollar'], '💰')} Вы получили: <code>{bonus_amount} ₽ ({config['bonus_value']}% от покупки)</code>\n\n"
                        f"{emoji(EMOJI['joy'], '😊')} Поздравляем!",
                        parse_mode="HTML"
                    )
    
    async with pool.acquire() as conn:
        keys_left = await conn.fetchval("SELECT COUNT(*) FROM keys_store WHERE product_id = $1 AND used = FALSE", product_id)
    
    vip_link = await create_vip_link(user_id, 30)
    if not vip_link:
        vip_link = "https://t.me/+a5AssXS77w01Yjky"
    
    await callback.message.answer(
        f"{emoji(EMOJI['cat_dance'], '💃')} <b>Покупка успешна!</b>\n\n"
        f"{emoji(EMOJI['key'], '🔑')} <b>Ключей в наличии:</b> {keys_left}\n"
        f"{emoji(EMOJI['dollar'], '💰')} <b>Цена:</b> {product['price']} ₽\n\n"
        f"{emoji(EMOJI['key'], '🔑')} <b>Ваш ключ:</b> <code>{key_row['key_value']}</code>\n\n"
        f"{emoji(EMOJI['key'], '🔗')} <b>Ссылка на VIP канал (одноразовая):</b>\n"
        f"<a href='{vip_link}'>Нажмите для вступления</a>\n\n"
        f"{emoji(EMOJI['important'], '⚠️')} Ссылка действительна 30 дней и только для вас!\n\n"
        f"{emoji(EMOJI['heart'], '❤️')} <i>Спасибо за покупку!</i>",
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В меню", callback_data="menu_main", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.message.delete()
    await callback.answer(f"{emoji(EMOJI['cat_dance'], '💃')} Покупка успешна!")

@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(f"{emoji(EMOJI['key'], '⛔')} Доступ запрещен")
        return
    
    shop_mode = await get_setting("shop_mode")
    await message.answer(
        f"{emoji(EMOJI['crown'], '🔐')} <b>Админ-панель</b>",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(shop_mode)
    )

@dp.callback_query(lambda c: c.data == "admin_toggle_mode")
async def admin_toggle_mode(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')} Доступ запрещен")
        return
    
    current_mode = await get_setting("shop_mode")
    new_mode = "custom" if current_mode == "auto" else "auto"
    await update_setting("shop_mode", new_mode)
    
    status_text = "РУЧНОЙ (Кастомный текст)" if new_mode == "custom" else "АВТО (Автоплатежи)"
    await callback.answer(f"Режим изменен на: {status_text}")
    await callback.message.edit_reply_markup(reply_markup=get_admin_keyboard(new_mode))

@dp.callback_query(lambda c: c.data == "admin_change_custom_text")
async def admin_change_custom_text(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')} Доступ запрещен")
        return
        
    current_text = await get_setting("custom_text")
    await state.set_state(AdminCustomTextStates.waiting_text)
    await callback.message.answer(
        f"{emoji(EMOJI['edit'], '📝')} <b>Текущий текст с реквизитами:</b>\n\n{current_text}\n\n"
        f"Введите новый текст с реквизитами для ручной оплаты (поддерживается HTML):",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(AdminCustomTextStates.waiting_text)
async def process_custom_text_save(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
        
    new_text = message.text.strip()
    await update_setting("custom_text", new_text)
    await state.clear()
    
    shop_mode = await get_setting("shop_mode")
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Текст для ручной оплаты успешно обновлен!</b>",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(shop_mode)
    )

@dp.callback_query(lambda c: c.data == "admin_crypto_fee")
async def admin_crypto_fee(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')} Доступ запрещен")
        return
    
    current_fee = await get_crypto_fee()
    await state.set_state(AdminCryptoFeeStates.waiting_fee)
    await callback.message.answer(
        f"{emoji(EMOJI['crypto'], '🪙')} <b>Настройка комиссии для крипто-пополнений</b>\n\n"
        f"Текущая комиссия: <code>{current_fee}%</code>\n\n"
        f"Введите размер комиссии (число от 0 до 50):\n\n"
        f"Пример: <code>10</code> - пользователь хочет получить 100₽, платит ~111₽\n"
        f"Пример: <code>0</code> - без комиссии",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="admin_back", icon_custom_emoji_id=EMOJI["arrow_back"])]
        ])
    )
    await callback.answer()

@dp.message(AdminCryptoFeeStates.waiting_fee)
async def process_crypto_fee(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    try:
        fee = int(message.text.strip())
        if fee < 0 or fee > 50:
            await message.answer(f"{emoji(EMOJI['key'], '❌')} Комиссия должна быть от 0 до 50%", parse_mode="HTML")
            return
        
        await set_crypto_fee(fee)
        
        shop_mode = await get_setting("shop_mode")
        await message.answer(
            f"{emoji(EMOJI['check'], '✅')} <b>Комиссия успешно установлена!</b>\n\n"
            f"{emoji(EMOJI['crypto'], '🪙')} Размер комиссии: <code>{fee}%</code>\n\n"
            f"Если пользователь хочет получить на баланс 100 ₽, он заплатит <code>{round(100 / (1 - fee/100))} ₽</code>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(shop_mode)
        )
        await state.clear()
        
    except ValueError:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Введите число", parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "admin_add_product")
async def admin_add_product(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')} Доступ запрещен")
        return
    await state.set_state(AddProductStates.waiting_name)
    await callback.message.edit_text(
        f"{emoji(EMOJI['edit'], '📝')} Введите название товара:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_back", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.answer()

@dp.message(AddProductStates.waiting_name)
async def product_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(name=message.text)
    await state.set_state(AddProductStates.waiting_price)
    await message.answer(f"{emoji(EMOJI['dollar'], '💰')} Введите цену (число):", parse_mode="HTML")

@dp.message(AddProductStates.waiting_price)
async def product_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        price = int(message.text)
        await state.update_data(price=price)
        await state.set_state(AddProductStates.waiting_keys)
        await message.answer(
            f"{emoji(EMOJI['key'], '🔑')} Введите ключи (каждый с новой строки):\n\n"
            f"Пример:\n<code>KEY-123-ABC</code>\n<code>KEY-456-DEF</code>",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Введите число", parse_mode="HTML")

@dp.message(AddProductStates.waiting_keys)
async def product_keys(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    keys = [k.strip() for k in message.text.split("\n") if k.strip()]
    if not keys:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Хотя бы один ключ", parse_mode="HTML")
        return
    
    product_id = await add_product(data["name"], data["price"])
    await add_keys_to_product(product_id, keys)
    
    shop_mode = await get_setting("shop_mode")
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} Товар добавлен! {len(keys)} ключей\n{emoji(EMOJI['verified'], '📦')} ID товара: {product_id}",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(shop_mode)
    )
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_add_keys")
async def admin_add_keys(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')} Доступ запрещен")
        return
    products = await get_all_products()
    if not products:
        shop_mode = await get_setting("shop_mode")
        await callback.message.edit_text(
            f"{emoji(EMOJI['key'], '❌')} Сначала добавьте товар",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(shop_mode)
        )
        await callback.answer()
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{p['name']} (ID: {p['id']})", callback_data=f"addkeys_{p['id']}")]
        for p in products
    ] + [[InlineKeyboardButton(text="Назад", callback_data="admin_back", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    
    await callback.message.edit_text(
        f"{emoji(EMOJI['folder'], '📦')} Выберите товар для добавления ключей:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("addkeys_"))
async def select_for_keys(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')}")
        return
    product_id = int(callback.data.split("_")[1])
    await state.update_data(product_id=product_id)
    await state.set_state(AddKeysStates.waiting_keys)
    await callback.message.edit_text(
        f"{emoji(EMOJI['key'], '🔑')} Введите ключи (по одному на строку):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_back", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.answer()

@dp.message(AddKeysStates.waiting_keys)
async def process_keys_only(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    product_id = data["product_id"]
    keys = [k.strip() for k in message.text.split("\n") if k.strip()]
    await add_keys_to_product(product_id, keys)
    
    shop_mode = await get_setting("shop_mode")
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} Добавлено {len(keys)} ключей для товара ID {product_id}",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(shop_mode)
    )
    await state.clear()

@dp.message(lambda m: m.text and m.text.startswith("/delproduct_"))
async def delete_product_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        product_id = int(message.text.split("_")[1])
        await delete_product(product_id)
        shop_mode = await get_setting("shop_mode")
        await message.answer(
            f"{emoji(EMOJI['check'], '✅')} Товар удален!",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(shop_mode)
        )
    except:
        await message.answer(
            f"{emoji(EMOJI['key'], '❌')} Ошибка при удалении",
            parse_mode="HTML"
        )
@dp.callback_query(lambda c: c.data and c.data.startswith("showkeys_"))
async def show_keys(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен")
        return
    
    product_id = int(callback.data.split("_")[1])
    product = await get_product_by_id(product_id)
    keys = await get_keys_by_product(product_id)
    
    if not keys:
        await callback.message.edit_text(
            f"{emoji(EMOJI['key'], '🔑')} <b>Ключи для товара {product['name']}</b>\n\nСписок пуст",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage_keys")]
            ])
        )
        await callback.answer()
        return
    
    text = f"{emoji(EMOJI['key'], '🔑')} <b>Ключи для товара {product['name']}</b>\n\n"
    for k in keys:
        status = "✅ Использован" if k["used"] else "🟢 Доступен"
        text += f"🆔 ID: {k['id']} | {k['key_value']} | {status}\n🗑️ /delkey_{k['id']} - удалить ключ\n\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage_keys")]
        ])
    )
    await callback.answer()

@dp.message(lambda m: m.text and m.text.startswith("/delkey_"))
async def delete_key_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        key_id = int(message.text.split("_")[1])
        await delete_key(key_id)
        shop_mode = await get_setting("shop_mode")
        await message.answer(
            f"{emoji(EMOJI['check'], '✅')} Ключ удален!",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(shop_mode)
        )
    except:
        await message.answer(
            f"{emoji(EMOJI['key'], '❌')} Ошибка при удалении",
            parse_mode="HTML"
        )

@dp.callback_query(lambda c: c.data == "admin_add_balance")
async def admin_add_balance(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')} Доступ запрещен")
        return
    await state.set_state(AdminAddBalanceStates.waiting_user_id)
    await callback.message.edit_text(
        f"{emoji(EMOJI['dollar'], '💰')} <b>Выдача баланса пользователю</b>\n\n"
        "Введите ID пользователя Telegram:\n\n"
        "Пример: <code>123456789</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_back", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.answer()

@dp.message(AdminAddBalanceStates.waiting_user_id)
async def process_add_balance_user_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.strip())
        await state.update_data(user_id=user_id)
        await state.set_state(AdminAddBalanceStates.waiting_amount)
        await message.answer(
            f"{emoji(EMOJI['dollar'], '💰')} Введите сумму для начисления на баланс:\n\n"
            "Пример: <code>500</code>",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Неверный ID. Введите число.", parse_mode="HTML")

@dp.message(AdminAddBalanceStates.waiting_amount)
async def process_add_balance_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            await message.answer(f"{emoji(EMOJI['key'], '❌')} Сумма должна быть больше 0", parse_mode="HTML")
            return
        
        data = await state.get_data()
        user_id = data["user_id"]
        
        current_balance = await get_balance(user_id)
        await update_user_balance(user_id, current_balance + amount)
        
        shop_mode = await get_setting("shop_mode")
        await message.answer(
            f"{emoji(EMOJI['check'], '✅')} <b>Баланс успешно выдан!</b>\n\n"
            f"{emoji(EMOJI['person'], '👤')} Пользователь: <code>{user_id}</code>\n"
            f"{emoji(EMOJI['dollar'], '💰')} Сумма: <code>{amount} ₽</code>\n"
            f"{emoji(EMOJI['almaz'], '📊')} Новый баланс: <code>{current_balance + amount} ₽</code>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(shop_mode)
        )
        
        await bot.send_message(
            user_id,
            f"{emoji(EMOJI['check'], '✅')} <b>Баланс пополнен администратором!</b>\n\n"
            f"{emoji(EMOJI['dollar'], '💰')} Сумма: <code>{amount} ₽</code>\n"
            f"{emoji(EMOJI['almaz'], '📊')} Новый баланс: <code>{current_balance + amount} ₽</code>",
            parse_mode="HTML"
        )
        
        await state.clear()
        
    except ValueError:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Введите число", parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')} Доступ запрещен")
        return
    await state.set_state(AdminBroadcastStates.waiting_message)
    await callback.message.edit_text(
        f"{emoji(EMOJI['notification'], '📢')} <b>Рассылка сообщения</b>\n\n"
        "Введите текст сообщения для рассылки всем пользователям:\n\n"
        "Поддерживается HTML разметка",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_back", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.answer()

@dp.message(AdminBroadcastStates.waiting_message)
async def process_broadcast(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    broadcast_text = message.text
    users = await get_all_users()
    
    await message.answer(
        f"{emoji(EMOJI['notification'], '📢')} <b>Начинаю рассылку...</b>\n\n"
        f"{emoji(EMOJI['person'], '👥')} Всего пользователей: <code>{len(users)}</code>",
        parse_mode="HTML"
    )
    
    success_count = 0
    fail_count = 0
    
    for user in users:
        try:
            await bot.send_message(
                user["user_id"],
                f"{emoji(EMOJI['notification'], '📢')} <b>РАССЫЛКА ОТ АДМИНИСТРАТОРА</b>\n\n{broadcast_text}",
                parse_mode="HTML"
            )
            success_count += 1
        except:
            fail_count += 1
        await asyncio.sleep(0.05)
    
    shop_mode = await get_setting("shop_mode")
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Рассылка завершена!</b>\n\n"
        f"{emoji(EMOJI['check'], '✅')} Доставлено: <code>{success_count}</code>\n"
        f"{emoji(EMOJI['key'], '❌')} Не доставлено: <code>{fail_count}</code>",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(shop_mode)
    )
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_create_promocode")
async def admin_create_promocode(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')} Доступ запрещен")
        return
    await state.set_state(AdminCreatePromocodeStates.waiting_code)
    await callback.message.edit_text(
        f"{emoji(EMOJI['new'], '🎫')} <b>Создание промокода</b>\n\n"
        "Введите название промокода (только латиница и цифры, без пробелов):\n\n"
        "Пример: <code>SUMMER2024</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_back", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.answer()

@dp.message(AdminCreatePromocodeStates.waiting_code)
async def create_promocode_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    code = message.text.strip().upper()
    await state.update_data(code=code)
    await state.set_state(AdminCreatePromocodeStates.waiting_type)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Скидка в процентах (%)", callback_data="promo_type_percent", icon_custom_emoji_id=EMOJI["discount"])],
        [InlineKeyboardButton(text="Скидка в рублях (₽)", callback_data="promo_type_rubles", icon_custom_emoji_id=EMOJI["dollar"])],
        [InlineKeyboardButton(text="Бонусный баланс (₽)", callback_data="promo_type_bonus", icon_custom_emoji_id=EMOJI["gift"])],
        [InlineKeyboardButton(text="Отмена", callback_data="admin_back", icon_custom_emoji_id=EMOJI["arrow_back"])]
    ])
    
    await message.answer(
        f"{emoji(EMOJI['clock'], '📊')} <b>Выберите тип промокода:</b>",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(lambda c: c.data and c.data.startswith("promo_type_"))
async def create_promocode_type(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')}")
        return
    
    discount_type = callback.data.split("_")[2]
    await state.update_data(discount_type=discount_type)
    await state.set_state(AdminCreatePromocodeStates.waiting_value)
    
    if discount_type == "percent":
        await callback.message.edit_text(
            f"{emoji(EMOJI['clock'], '📊')} Введите размер скидки в процентах (число от 1 до 100):\n\nПример: <code>10</code>",
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"{emoji(EMOJI['dollar'], '💰')} Введите сумму скидки или бонуса в рублях (число):\n\nПример: <code>500</code>",
            parse_mode="HTML"
        )
    await callback.answer()

@dp.message(AdminCreatePromocodeStates.waiting_value)
async def create_promocode_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        value = int(message.text.strip())
        if value <= 0:
            await message.answer(f"{emoji(EMOJI['key'], '❌')} Значение должно быть больше 0", parse_mode="HTML")
            return
        
        await state.update_data(discount_value=value)
        await state.set_state(AdminCreatePromocodeStates.waiting_max_uses)
        await message.answer(
            f"{emoji(EMOJI['repeat'], '🔢')} Введите максимальное количество активаций промокода:\n\nПример: <code>100</code>",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Введите число", parse_mode="HTML")

@dp.message(AdminCreatePromocodeStates.waiting_max_uses)
async def create_promocode_max_uses(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        max_uses = int(message.text.strip())
        if max_uses <= 0:
            await message.answer(f"{emoji(EMOJI['key'], '❌')} Количество активаций должно быть больше 0", parse_mode="HTML")
            return
        
        data = await state.get_data()
        code = data["code"]
        discount_type = data["discount_type"]
        discount_value = data["discount_value"]
        
        await create_promocode(code, discount_type, discount_value, max_uses)
        
        if discount_type == "percent":
            type_text = f"{discount_value}%"
        elif discount_type == "rubles":
            type_text = f"{discount_value} ₽ (скидка)"
        else:
            type_text = f"{discount_value} ₽ (бонус)"
        
        shop_mode = await get_setting("shop_mode")
        await message.answer(
            f"{emoji(EMOJI['check'], '✅')} <b>Промокод успешно создан!</b>\n\n"
            f"{emoji(EMOJI['new'], '🎫')} Код: <code>{code}</code>\n"
            f"{emoji(EMOJI['clock'], '📊')} Тип: {type_text}\n"
            f"{emoji(EMOJI['repeat'], '🔢')} Максимум активаций: <code>{max_uses}</code>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(shop_mode)
        )
        await state.clear()
        
    except ValueError:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Введите число", parse_mode="HTML")
    
@dp.message(lambda m: m.text and m.text.startswith("/del_"))
async def delete_promocode_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        promocode_id = int(message.text.split("_")[1])
        await delete_promocode(promocode_id)
        shop_mode = await get_setting("shop_mode")
        await message.answer(
            f"{emoji(EMOJI['check'], '✅')} Промокод удален!",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(shop_mode)
        )
    except:
        await message.answer(
            f"{emoji(EMOJI['key'], '❌')} Ошибка при удалении",
            parse_mode="HTML"
        )

@dp.callback_query(lambda c: c.data == "admin_ref_config")
async def admin_ref_config(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')}")
        return
    
    await state.set_state(AdminRefBonusStates.waiting_type)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Фиксированная сумма (₽)", callback_data="ref_type_rubles", icon_custom_emoji_id=EMOJI["dollar"])],
        [InlineKeyboardButton(text="Процент от покупки (%)", callback_data="ref_type_percent", icon_custom_emoji_id=EMOJI["discount"])],
        [InlineKeyboardButton(text="Отмена", callback_data="admin_back", icon_custom_emoji_id=EMOJI["arrow_back"])]
    ])
    await callback.message.edit_text(
        f"{emoji(EMOJI['gift'], '🎁')} <b>Настройка реферального бонуса</b>\n\n"
        "Выберите тип бонуса за первую покупку приглашённого друга:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith("ref_type_"))
async def ref_type_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')}")
        return
    
    bonus_type = callback.data.split("_")[2]
    await state.update_data(bonus_type=bonus_type)
    await state.set_state(AdminRefBonusStates.waiting_value)
    
    if bonus_type == "rubles":
        await callback.message.edit_text(
            f"{emoji(EMOJI['dollar'], '💰')} Введите фиксированную сумму бонуса в рублях:\n\nПример: <code>50</code>",
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"{emoji(EMOJI['discount'], '📊')} Введите процент от покупки (число от 1 до 100):\n\nПример: <code>10</code>",
            parse_mode="HTML"
        )
    await callback.answer()

@dp.message(AdminRefBonusStates.waiting_value)
async def ref_value_callback(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        value = int(message.text.strip())
        if value <= 0:
            await message.answer(f"{emoji(EMOJI['key'], '❌')} Значение должно быть больше 0", parse_mode="HTML")
            return
        
        data = await state.get_data()
        bonus_type = data["bonus_type"]
        
        await update_referral_config(bonus_type, value)
        
        bonus_text = f"{value} ₽" if bonus_type == "rubles" else f"{value}% от покупки"
        
        shop_mode = await get_setting("shop_mode")
        await message.answer(
            f"{emoji(EMOJI['check'], '✅')} <b>Настройки реферальной системы обновлены!</b>\n\n"
            f"{emoji(EMOJI['gift'], '🎁')} Тип бонуса: {bonus_text}",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(shop_mode)
        )
        await state.clear()
    except ValueError:
        await message.answer(f"{emoji(EMOJI['key'], '❌')} Введите число", parse_mode="HTML")

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer(f"{emoji(EMOJI['key'], '⛔')}")
        return
    stats = await get_stats()
    shop_mode = await get_setting("shop_mode")
    await callback.message.edit_text(
        f"{emoji(EMOJI['crown'], '📊')} <b>Статистика</b>\n\n"
        f"{emoji(EMOJI['person'], '👥')} Пользователей: <code>{stats['users']}</code>\n"
        f"{emoji(EMOJI['dollar'], '💰')} Продаж на сумму: <code>{stats['total_sales']} ₽</code>\n"
        f"{emoji(EMOJI['key'], '🔑')} Выдано ключей: <code>{stats['keys_sold']}</code>\n"
        f"{emoji(EMOJI['key'], '🔑')} Осталось ключей: <code>{stats['keys_left']}</code>\n"
        f"{emoji(EMOJI['store'], '📦')} Товаров в продаже: <code>{stats['products_count']}</code>",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(shop_mode)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    shop_mode = await get_setting("shop_mode")
    await callback.message.edit_text(
        f"{emoji(EMOJI['crown'], '🔐')} <b>Админ-панель</b>",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(shop_mode)
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_manage_products")
async def admin_manage_products(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    products = await get_all_products()
    if not products:
        await callback.message.edit_text(
            f"{emoji(EMOJI['folder'], '📭')} <b>Список товаров пуст</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
        await callback.answer()
        return
    
    text = f"{emoji(EMOJI['store'], '📦')} <b>Список товаров</b>\n\n"
    for p in products:
        text += f"{emoji(EMOJI['verified'], '🆔')} ID: {p['id']}\n"
        text += f"{emoji(EMOJI['document'], '📛')} Название: {p['name']}\n"
        text += f"{emoji(EMOJI['dollar'], '💰')} Цена: {p['price']} ₽\n"
        text += f"{emoji(EMOJI['trash'], '🗑️')} /delproduct_{p['id']} - удалить товар\n\n"
    
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
        ])
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_manage_products")
async def admin_manage_products(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    products = await get_all_products()
    if not products:
        await callback.message.edit_text(
            f"{emoji(EMOJI['folder'], '📭')} <b>Список товаров пуст</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
        await callback.answer()
        return
    
    text = f"{emoji(EMOJI['store'], '📦')} <b>Список товаров</b>\n\n"
    for p in products:
        text += f"🆔 ID: {p['id']}\n📛 Название: {p['name']}\n💰 Цена: {p['price']} ₽\n🗑️ /delproduct_{p['id']} - удалить товар\n\n"
    
    await callback.message.edit_text(
        text, 
        parse_mode="HTML", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
        ])
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_manage_keys")
async def admin_manage_keys(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    products = await get_all_products()
    if not products:
        await callback.message.edit_text(
            f"{emoji(EMOJI['folder'], '📭')} <b>Сначала добавьте товар</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
            ])
        )
        await callback.answer()
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{p['name']} (ID: {p['id']})", callback_data=f"showkeys_{p['id']}")]
        for p in products
    ] + [[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]])
    
    await callback.message.edit_text(
        f"{emoji(EMOJI['key'], '🔑')} Выберите товар для просмотра ключей:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data == "admin_list_promocodes")
async def admin_list_promocodes(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    promocodes = await get_all_promocodes()
    shop_mode = await get_setting("shop_mode")
    
    if not promocodes:
        await callback.message.edit_text(
            f"{emoji(EMOJI['folder'], '📭')} <b>Список промокодов пуст</b>",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard(shop_mode)
        )
        await callback.answer()
        return
    
    text = f"{emoji(EMOJI['discount'], '🎫')} <b>Список промокодов</b>\n\n"
    for p in promocodes:
        if p["discount_type"] == "percent":
            type_text = f"{p['discount_value']}%"
        elif p["discount_type"] == "rubles":
            type_text = f"{p['discount_value']} ₽ (скидка)"
        else:
            type_text = f"{p['discount_value']} ₽ (бонус)"
        
        text += f"🔹 <code>{p['code']}</code>\n   📊 {type_text}\n   📊 Использован: {p['used_count']}/{p['max_uses']}\n   🗑️ /del_{p['id']} - удалить\n\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(shop_mode)
    )
    await callback.answer()

@flask_app.route("/webhook/platega", methods=["POST"])
def platega_webhook():
    data = request.json
    print(f"[Platega Webhook] Получены данные: {data}")
    
    status = data.get("status")
    payload = data.get("payload")
    
    if status == "CONFIRMED" and payload and payload.startswith("order_"):
        parts = payload.split("_")
        if len(parts) >= 2:
            user_id = int(parts[1])
            order_id = parts[2] if len(parts) > 2 else ""
            
            amount = None
            for uid, info in pending_payments.items():
                if uid == user_id and info.get("order_id") == order_id:
                    amount = info["amount"]
                    break
            
            if amount:
                async def process():
                    current = await get_balance(user_id)
                    await update_user_balance(user_id, current + amount)
                    await bot.send_message(
                        user_id,
                        f"{emoji(EMOJI['check'], '✅')} <b>Оплата успешно получена через Platega!</b>\n\n"
                        f"{emoji(EMOJI['dollar'], '💰')} Сумма: <code>{amount} ₽</code>\n"
                        f"{emoji(EMOJI['almaz'], '📊')} Новый баланс: <code>{current + amount} ₽</code>",
                        parse_mode="HTML"
                    )
                    if user_id in pending_payments:
                        del pending_payments[user_id]
                
                asyncio.run_coroutine_threadsafe(process(), main_loop)
                return jsonify({"status": "ok"}), 200
    
    return jsonify({"status": "error"}), 400

@flask_app.route("/webhook/crypto", methods=["POST"])
def crypto_webhook():
    signature = request.headers.get("crypto-pay-api-signature")
    if not signature:
        return "Unauthorized", 401
        
    body = request.data
    secret = hashlib.sha256(CRYPTOBOT_TOKEN.encode()).digest()
    calc_signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    
    if signature != calc_signature:
        print("[Webhook] Неверная подпись!")
        return "Forbidden", 403
        
    data = request.json
    if data.get("update_type") == "invoice_paid":
        payload_str = data["update_object"].get("payload")
        if payload_str:
            try:
                parts = payload_str.split("_")
                user_id = int(parts[0])
                
                amount = None
                for uid, info in pending_payments.items():
                    if uid == user_id:
                        amount = info["amount"]
                        break
                
                if amount:
                    async def process():
                        current = await get_balance(user_id)
                        await update_user_balance(user_id, current + amount)
                        await bot.send_message(
                            user_id,
                            f"{emoji(EMOJI['check'], '✅')} <b>Оплата успешно получена!</b>\n\n"
                            f"{emoji(EMOJI['dollar'], '💰')} Ваш баланс пополнен на <b>{amount} ₽</b>\n"
                            f"{emoji(EMOJI['almaz'], '📊')} Текущий баланс: <code>{current + amount} ₽</code>\n\n"
                            f"{emoji(EMOJI['joy'], '😊')} Спасибо за оплату!",
                            parse_mode="HTML"
                        )
                        if user_id in pending_payments:
                            del pending_payments[user_id]
                        print(f"[CryptoPay] Выдано {amount} руб пользователю {user_id}")
                    
                    asyncio.run_coroutine_threadsafe(process(), main_loop)
            except Exception as e:
                print(f"[Webhook] Ошибка: {e}")
                
    return jsonify({"status": "ok"}), 200

@flask_app.route("/webhook", methods=["POST"])
def webhook_platega_redirect():
    return platega_webhook()

@flask_app.route("/payment/success", methods=["GET"])
def payment_success():
    return "Оплата прошла успешно! Можете вернуться в бота.", 200

@flask_app.route("/payment/fail", methods=["GET"])
def payment_fail():
    return "Оплата не прошла. Попробуйте снова.", 200

@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "alive"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

async def main():
    global main_loop
    main_loop = asyncio.get_running_loop()
    
    await connect_db()
    
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook удален, использую polling режим")
    
    thread = Thread(target=run_flask, daemon=True)
    thread.start()
    
    print(f"{emoji(EMOJI['cat_dance'], '🤖')} Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
