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
    get_setting, update_setting, create_manual_order, get_manual_order, update_manual_order_status, get_pending_manual_orders,
    get_crypto_fee, set_crypto_fee
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
        "payload": f"user_{user_id}_{order_id}"
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
        amount_to_pay = int(desired_amount * 100 / (100 - crypto_fee))
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
    
    result = create_crypto_invoice(usdt_amount, order_id, user_id)
    
    if result.get("success"):
        pending_payments[user_id] = {
            "amount": desired_amount,
            "order_id": order_id,
            "invoice_id": result["invoice_id"],
            "status": "pending"
        }
        return result["payment_url"]
    else:
        print(f"[CryptoBot] Ошибка: {result.get('error')}")
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
        f"• <a href='https://telegra.ph/Polzovatelskoe-soglashenie-04-01-19'>Пользовательское соглашение</a>"
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
    
    text = f"{emoji(EMOJI['folder'], '📋')} <b>История заказов</b>\n\n"
    for p in purchases:
        text += f"• {p['product_name']} - {p['price']}₽\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "profile_deposit")
async def profile_deposit(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DepositStates.waiting_amount)
    await callback.message.edit_text(
        f"{emoji(EMOJI['dollar'], '💰')} <b>Пополнение баланса</b>\n\n"
        f"Введите сумму пополнения (от 1 ₽):\n"
        f"<i>Минимальная сумма: 1 ₽</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.answer()

@dp.message(DepositStates.waiting_amount)
async def deposit_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount < 1:
            await message.answer("❌ Сумма должна быть не меньше 1 ₽. Попробуйте снова:")
            return
    except:
        await message.answer("❌ Введите корректное число. Попробуйте снова:")
        return
    
    await state.update_data(amount=amount)
    await state.set_state(DepositStates.waiting_method)
    
    shop_mode = await get_setting("shop_mode")
    
    if shop_mode == "auto":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=f"{emoji(EMOJI['crypto'], '🪙')} Crypto Pay", callback_data="deposit_method_crypto"),
                InlineKeyboardButton(text=f"{emoji(EMOJI['sbp'], '💳')} Platega (СБП)", callback_data="deposit_method_platega")
            ],
            [
                InlineKeyboardButton(text="Назад", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])
            ]
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Ручной способ", callback_data="deposit_method_manual")
            ],
            [
                InlineKeyboardButton(text="Назад", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])
            ]
        ])
    
    await message.answer(
        f"{emoji(EMOJI['dollar'], '💰')} <b>Выберите способ оплаты</b>\n\n"
        f"Сумма: <code>{amount} ₽</code>",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(lambda c: c.data == "deposit_method_crypto")
async def deposit_method_crypto(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get("amount")
    user_id = callback.from_user.id
    order_id = str(uuid.uuid4())[:8]
    
    payment_url = await create_crypto_payment(amount, order_id, user_id)
    
    if payment_url:
        await callback.message.edit_text(
            f"{emoji(EMOJI['crypto'], '🪙')} <b>Оплата через Crypto Pay</b>\n\n"
            f"Сумма: <code>{amount} ₽</code>\n\n"
            f"<b>Инструкция:</b>\n"
            f"1. Нажмите на кнопку ниже\n"
            f"2. Оплатите счет в USDT\n"
            f"3. После оплаты баланс начислится автоматически\n\n"
            f"<i>Счет действителен 1 час</i>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💸 Оплатить", url=payment_url)],
                [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_payment_{order_id}_{amount}")],
                [InlineKeyboardButton(text="Назад", callback_data="profile_deposit")]
            ])
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка создания платежа. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="profile_deposit")]])
        )
    
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("check_payment_"))
async def check_payment(callback: CallbackQuery):
    _, order_id, amount = callback.data.split("_")
    amount = int(amount)
    user_id = callback.from_user.id
    
    if user_id in pending_payments:
        payment = pending_payments.get(user_id)
        
        if payment and payment.get("status") == "confirmed":
            await update_user_balance(user_id, payment["amount"])
            await callback.message.edit_text(
                f"✅ Баланс успешно пополнен на {payment['amount']} ₽!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В профиль", callback_data="menu_profile")]])
            )
            pending_payments.pop(user_id, None)
            await callback.answer()
            return
    
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{CRYPTOBOT_API_URL}/getInvoices", headers=headers, json={"asset": "USDT"}) as resp:
                result = await resp.json()
                
                if result.get("ok"):
                    invoices = result.get("result", {}).get("items", [])
                    for invoice in invoices:
                        if invoice.get("payload") == f"user_{user_id}_{order_id}" and invoice.get("status") == "paid":
                            if user_id in pending_payments:
                                pending_payments[user_id]["status"] = "confirmed"
                            
                            await update_user_balance(user_id, amount)
                            await callback.message.edit_text(
                                f"✅ Баланс успешно пополнен на {amount} ₽!",
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В профиль", callback_data="menu_profile")]])
                            )
                            await callback.answer()
                            return
    except Exception as e:
        print(f"Ошибка проверки: {e}")
    
    await callback.answer("❌ Платеж еще не найден. Подождите 1-2 минуты и попробуйте снова.", show_alert=True)

@dp.callback_query(lambda c: c.data == "deposit_method_platega")
async def deposit_method_platega(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get("amount")
    user_id = callback.from_user.id
    order_id = str(uuid.uuid4())[:8]
    
    payment_url = await create_platega_payment(amount, order_id, user_id)
    
    if payment_url:
        await callback.message.edit_text(
            f"{emoji(EMOJI['sbp'], '💳')} <b>Оплата через Platega (СБП)</b>\n\n"
            f"Сумма: <code>{amount} ₽</code>\n\n"
            f"<b>Инструкция:</b>\n"
            f"1. Нажмите на кнопку ниже\n"
            f"2. Оплатите по QR-коду или через СБП\n"
            f"3. После оплаты баланс начислится автоматически",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
                [InlineKeyboardButton(text="Назад", callback_data="profile_deposit")]
            ])
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка создания платежа. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="profile_deposit")]])
        )
    
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "deposit_method_manual")
async def deposit_method_manual(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get("amount")
    
    custom_text = await get_setting("custom_payment_text")
    if not custom_text:
        custom_text = "Переведите сумму на карту и отправьте скриншот чека"
    
    await state.update_data(amount=amount)
    await state.set_state(ManualDepositStates.waiting_screenshot)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="profile_deposit", icon_custom_emoji_id=EMOJI["arrow_back"])]
    ])
    
    await callback.message.edit_text(
        f"{emoji(EMOJI['document'], '📝')} <b>Ручное пополнение</b>\n\n"
        f"{custom_text}\n\n"
        f"Сумма: <code>{amount} ₽</code>\n\n"
        f"<i>После оплаты отправьте скриншот чека в этот чат. Администратор проверит оплату и начислит баланс.</i>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.message(ManualDepositStates.waiting_screenshot)
async def manual_deposit_screenshot(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer(
            "❌ Пожалуйста, отправьте скриншот чека (фото).\n\n"
            "Или нажмите /cancel для отмены."
        )
        return
    
    data = await state.get_data()
    amount = data.get("amount")
    user_id = message.from_user.id
    
    order_id = await create_manual_order(user_id, amount, "pending")
    
    user_text = (
        f"✅ <b>Заявка на пополнение отправлена!</b>\n\n"
        f"Сумма: <code>{amount} ₽</code>\n"
        f"Номер заявки: <code>#{order_id}</code>\n\n"
        f"Администратор проверит платеж и начислит баланс в ближайшее время.\n"
        f"Ожидайте уведомление."
    )
    await message.answer(user_text, parse_mode="HTML", reply_markup=get_main_keyboard())
    
    photo_file_id = message.photo[-1].file_id
    
    admin_text = (
        f"🆕 <b>НОВАЯ ЗАЯВКА НА ПОПОЛНЕНИЕ</b>\n\n"
        f"👤 Пользователь: <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"💰 Сумма: <code>{amount} ₽</code>\n"
        f"📝 Номер заявки: <code>#{order_id}</code>\n\n"
        f"<i>Для подтверждения нажмите кнопку ниже</i>"
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                photo=photo_file_id,
                caption=admin_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"manual_confirm_{order_id}"),
                        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"manual_reject_{order_id}")
                    ]
                ])
            )
        except Exception as e:
            print(f"Не удалось отправить уведомление админу {admin_id}: {e}")
    
    await state.clear()

@dp.callback_query(lambda c: c.data and c.data.startswith("manual_confirm_"))
async def manual_confirm_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ У вас нет прав администратора", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    
    order = await get_manual_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    
    if order["status"] != "pending":
        await callback.answer("✅ Этот заказ уже обработан", show_alert=True)
        return
    
    if await update_manual_order_status(order_id, "confirmed"):
        await update_user_balance(order["user_id"], order["amount"])
        await add_purchase(order["user_id"], f"Пополнение баланса (ручной способ)", order["amount"])
        
        try:
            user_text = (
                f"✅ <b>Платеж подтвержден!</b>\n\n"
                f"Сумма: <code>{order['amount']} ₽</code>\n"
                f"Ваш баланс успешно пополнен!\n\n"
                f"💰 Текущий баланс: <code>{await get_balance(order['user_id'])} ₽</code>"
            )
            await bot.send_message(order["user_id"], user_text, parse_mode="HTML")
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {order['user_id']}: {e}")
        
        await callback.answer("✅ Платеж подтвержден и баланс начислен!", show_alert=True)
        
        await callback.message.edit_caption(
            caption=f"{callback.message.caption}\n\n✅ <b>ПОДТВЕРЖДЕН</b> ({callback.from_user.first_name})",
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Ошибка при подтверждении платежа", show_alert=True)

@dp.callback_query(lambda c: c.data and c.data.startswith("manual_reject_"))
async def manual_reject_payment(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ У вас нет прав администратора", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    
    order = await get_manual_order(order_id)
    if not order:
        await callback.answer("❌ Заказ не найден", show_alert=True)
        return
    
    if order["status"] != "pending":
        await callback.answer("✅ Этот заказ уже обработан", show_alert=True)
        return
    
    if await update_manual_order_status(order_id, "rejected"):
        try:
            user_text = (
                f"❌ <b>Платеж отклонен!</b>\n\n"
                f"Сумма: <code>{order['amount']} ₽</code>\n"
                f"Номер заявки: <code>#{order_id}</code>\n\n"
                f"Пожалуйста, свяжитесь с администратором: @nikita1055"
            )
            await bot.send_message(order["user_id"], user_text, parse_mode="HTML")
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {order['user_id']}: {e}")
        
        await callback.answer("❌ Платеж отклонен", show_alert=True)
        
        await callback.message.edit_caption(
            caption=f"{callback.message.caption}\n\n❌ <b>ОТКЛОНЕН</b> ({callback.from_user.first_name})",
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Ошибка при отклонении платежа", show_alert=True)

@dp.callback_query(lambda c: c.data == "profile_activate_promocode")
async def profile_activate_promocode(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileActivatePromocodeStates.waiting_code)
    await callback.message.edit_text(
        f"{emoji(EMOJI['discount'], '🎫')} <b>Активация промокода</b>\n\n"
        f"Введите промокод:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu_profile", icon_custom_emoji_id=EMOJI["arrow_back"])]])
    )
    await callback.answer()

@dp.message(ProfileActivatePromocodeStates.waiting_code)
async def activate_promocode(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    user_id = message.from_user.id
    
    promocode = await get_promocode(code)
    
    if not promocode:
        await message.answer(
            "❌ Промокод не найден.\n\nПроверьте правильность ввода или попробуйте другой промокод.",
            reply_markup=get_profile_keyboard()
        )
        await state.clear()
        return
    
    if await check_promocode_used(user_id, code):
        await message.answer(
            "❌ Вы уже использовали этот промокод.\n\nКаждый промокод можно активировать только один раз.",
            reply_markup=get_profile_keyboard()
        )
        await state.clear()
        return
    
    if promocode["max_uses"] is not None and promocode["used_count"] >= promocode["max_uses"]:
        await message.answer(
            "❌ Этот промокод больше недействителен (достигнут лимит использований).",
            reply_markup=get_profile_keyboard()
        )
        await state.clear()
        return
    
    if promocode["expires_at"] and datetime.now() > datetime.fromisoformat(promocode["expires_at"]):
        await message.answer(
            "❌ Срок действия промокода истек.",
            reply_markup=get_profile_keyboard()
        )
        await state.clear()
        return
    
    await use_promocode(user_id, code)
    
    bonus = promocode["value"]
    
    if promocode["type"] == "percent":
        await message.answer(
            f"✅ Промокод <b>{code}</b> активирован!\n\n"
            f"Вы получили скидку <b>{bonus}%</b> на следующую покупку!\n"
            f"Скидка применится автоматически при оформлении заказа.",
            parse_mode="HTML",
            reply_markup=get_profile_keyboard()
        )
    else:
        await update_user_balance(user_id, bonus)
        await add_purchase(user_id, f"Активация промокода {code}", bonus)
        await message.answer(
            f"✅ Промокод <b>{code}</b> активирован!\n\n"
            f"На ваш баланс начислено <b>{bonus} ₽</b>!\n"
            f"💰 Текущий баланс: <code>{await get_balance(user_id)} ₽</code>",
            parse_mode="HTML",
            reply_markup=get_profile_keyboard()
        )
    
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])
    product = await get_product_by_id(product_id)
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    shop_mode = await get_setting("shop_mode")
    
    if shop_mode == "auto":
        key = await get_unused_key(product_id)
        
        if not key:
            await callback.message.edit_text(
                f"{emoji(EMOJI['important'], '❌')} <b>Товар временно недоступен</b>\n\n"
                f"К сожалению, все ключи {product['name']} закончились.\n"
                f"Ожидайте пополнения.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад в магазин", callback_data="menu_shop")]])
            )
            await callback.answer()
            return
        
        balance = await get_balance(callback.from_user.id)
        
        if balance < product["price"]:
            await callback.message.edit_text(
                f"{emoji(EMOJI['important'], '❌')} <b>Недостаточно средств</b>\n\n"
                f"Цена: <code>{product['price']} ₽</code>\n"
                f"Ваш баланс: <code>{balance} ₽</code>\n\n"
                f"Пополните баланс в разделе <b>Профиль</b> → <b>Пополнить баланс</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пополнить", callback_data="profile_deposit"), InlineKeyboardButton(text="Назад", callback_data="menu_shop")]])
            )
            await callback.answer()
            return
        
        new_balance = balance - product["price"]
        await update_user_balance(callback.from_user.id, -product["price"])
        await mark_key_as_used(key["id"], callback.from_user.id)
        await mark_purchased(callback.from_user.id, product_id)
        await add_purchase(callback.from_user.id, product["name"], product["price"])
        
        referrer = await get_referrer(callback.from_user.id)
        if referrer:
            config = await get_referral_config()
            if not await has_user_purchased(callback.from_user.id):
                if config["bonus_type"] == "rubles":
                    bonus = config["bonus_value"]
                    await update_user_balance(referrer, bonus)
                    await add_purchase(referrer, f"Реферальный бонус за приглашение {callback.from_user.id}", bonus)
        
        invite_link = await create_vip_link(callback.from_user.id, 30)
        vip_text = f"\n\n{emoji(EMOJI['verified'], '🔓')} <b>Доступ в VIP канал:</b> <a href='{invite_link}'>Нажмите для входа</a>" if invite_link else ""
        
        await callback.message.edit_text(
            f"{emoji(EMOJI['check'], '✅')} <b>Поздравляем с покупкой!</b>\n\n"
            f"Товар: <b>{product['name']}</b>\n"
            f"Цена: <code>{product['price']} ₽</code>\n\n"
            f"{emoji(EMOJI['key'], '🔑')} <b>Ваш ключ:</b>\n"
            f"<code>{key['key_value']}</code>\n\n"
            f"{emoji(EMOJI['lamp'], '💡')} <b>Инструкция:</b>\n"
            f"Перейдите в чат @MagicChatSupport и активируйте ключ через бота @MagicBot\n"
            f"<i>Ключ действует 24 часа с момента активации в боте</i>{vip_text}\n\n"
            f"💰 <b>Остаток на балансе:</b> <code>{new_balance} ₽</code>",
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В магазин", callback_data="menu_shop"), InlineKeyboardButton(text="В профиль", callback_data="menu_profile")]])
        )
        await callback.answer()
    else:
        if await has_user_purchased(callback.from_user.id, product_id):
            await callback.message.edit_text(
                f"{emoji(EMOJI['important'], '❌')} <b>Товар уже куплен</b>\n\n"
                f"Вы уже приобретали товар <b>{product['name']}</b>.\n"
                f"В ручном режиме магазина каждый товар можно купить только один раз.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад в магазин", callback_data="menu_shop")]])
            )
            await callback.answer()
            return
        
        balance = await get_balance(callback.from_user.id)
        
        if balance < product["price"]:
            await callback.message.edit_text(
                f"{emoji(EMOJI['important'], '❌')} <b>Недостаточно средств</b>\n\n"
                f"Цена: <code>{product['price']} ₽</code>\n"
                f"Ваш баланс: <code>{balance} ₽</code>\n\n"
                f"Пополните баланс в разделе <b>Профиль</b> → <b>Пополнить баланс</b>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пополнить", callback_data="profile_deposit"), InlineKeyboardButton(text="Назад", callback_data="menu_shop")]])
            )
            await callback.answer()
            return
        
        new_balance = balance - product["price"]
        await update_user_balance(callback.from_user.id, -product["price"])
        await mark_purchased(callback.from_user.id, product_id)
        await add_purchase(callback.from_user.id, product["name"], product["price"])
        
        await callback.message.edit_text(
            f"{emoji(EMOJI['check'], '✅')} <b>Покупка оформлена!</b>\n\n"
            f"Товар: <b>{product['name']}</b>\n"
            f"Цена: <code>{product['price']} ₽</code>\n\n"
            f"{emoji(EMOJI['clock'], '⏳')} <b>Ожидайте выдачи ключа</b>\n"
            f"Ключ будет выдан администратором в ближайшее время.\n\n"
            f"💰 <b>Остаток на балансе:</b> <code>{new_balance} ₽</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В магазин", callback_data="menu_shop"), InlineKeyboardButton(text="В профиль", callback_data="menu_profile")]])
        )
        await callback.answer()

async def send_admin_panel(message_or_callback, user_id):
    shop_mode = await get_setting("shop_mode")
    kb = get_admin_keyboard(shop_mode)
    
    text = (
        f"{emoji(EMOJI['crown'], '👑')} <b>АДМИН-ПАНЕЛЬ</b> {emoji(EMOJI['crown'], '👑')}\n\n"
        f"Добро пожаловать в админ-панель, <b>{message_or_callback.from_user.first_name}</b>!\n\n"
        f"Выберите действие:"
    )
    
    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text, parse_mode="HTML", reply_markup=kb)

@dp.message(Command("admin"))
async def admin_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к админ-панели")
        return
    
    await send_admin_panel(message, message.from_user.id)

@dp.callback_query(lambda c: c.data == "admin_add_product")
async def admin_add_product(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    await state.set_state(AddProductStates.waiting_name)
    await callback.message.edit_text(
        f"{emoji(EMOJI['shop'], '➕')} <b>Добавление товара</b>\n\n"
        f"Введите название товара:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_cancel")]])
    )
    await callback.answer()

@dp.message(AddProductStates.waiting_name)
async def add_product_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProductStates.waiting_price)
    await message.answer(
        f"{emoji(EMOJI['shop'], '💰')} <b>Добавление товара</b>\n\n"
        f"Товар: <b>{message.text.strip()}</b>\n\n"
        f"Введите цену товара (в рублях):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_cancel")]])
    )

@dp.message(AddProductStates.waiting_price)
async def add_product_price(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        if price <= 0:
            await message.answer("❌ Цена должна быть положительным числом. Попробуйте снова:")
            return
    except:
        await message.answer("❌ Введите корректное число. Попробуйте снова:")
        return
    
    data = await state.get_data()
    name = data.get("name")
    
    await state.update_data(price=price)
    await state.set_state(AddProductStates.waiting_keys)
    
    await message.answer(
        f"{emoji(EMOJI['key'], '🔑')} <b>Добавление товара</b>\n\n"
        f"Товар: <b>{name}</b>\n"
        f"Цена: <code>{price} ₽</code>\n\n"
        f"Введите ключи (по одному на строку):\n"
        f"<i>Пример:\n"
        f"KEY-XXXX-XXXX-XXXX\n"
        f"KEY-YYYY-YYYY-YYYY</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить (добавить ключи позже)", callback_data="admin_skip_keys")]])
    )

@dp.message(AddProductStates.waiting_keys)
async def add_product_keys(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("name")
    price = data.get("price")
    keys_text = message.text.strip()
    
    keys = [k.strip() for k in keys_text.split('\n') if k.strip()]
    
    if not keys:
        await message.answer("❌ Не найдено ни одного ключа. Введите ключи или нажмите 'Пропустить'")
        return
    
    product_id = await add_product(name, price)
    
    if product_id:
        await add_keys_to_product(product_id, keys)
        await message.answer(
            f"{emoji(EMOJI['check'], '✅')} <b>Товар успешно добавлен!</b>\n\n"
            f"Название: <b>{name}</b>\n"
            f"Цена: <code>{price} ₽</code>\n"
            f"Добавлено ключей: <code>{len(keys)}</code>\n\n"
            f"ID товара: <code>{product_id}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel")]])
        )
    else:
        await message.answer("❌ Ошибка при добавлении товара")
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_skip_keys")
async def admin_skip_keys(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    name = data.get("name")
    price = data.get("price")
    
    product_id = await add_product(name, price)
    
    if product_id:
        await callback.message.edit_text(
            f"{emoji(EMOJI['check'], '✅')} <b>Товар успешно добавлен!</b>\n\n"
            f"Название: <b>{name}</b>\n"
            f"Цена: <code>{price} ₽</code>\n"
            f"Ключи не добавлены (можно добавить позже)\n\n"
            f"ID товара: <code>{product_id}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel")]])
        )
    else:
        await callback.message.edit_text("❌ Ошибка при добавлении товара", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]]))
    
    await state.clear()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_add_keys")
async def admin_add_keys(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    products = await get_all_products()
    
    if not products:
        await callback.message.edit_text(
            "❌ Сначала добавьте товар",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Добавить товар", callback_data="admin_add_product")]])
        )
        await callback.answer()
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{p['name']} (ID: {p['id']})", callback_data=f"select_product_{p['id']}")]
        for p in products
    ] + [[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]])
    
    await callback.message.edit_text(
        f"{emoji(EMOJI['key'], '🔑')} <b>Выберите товар для добавления ключей</b>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("select_product_"))
async def select_product_for_keys(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[2])
    await state.update_data(product_id=product_id)
    await state.set_state(AddKeysStates.waiting_keys)
    
    await callback.message.edit_text(
        f"{emoji(EMOJI['key'], '🔑')} <b>Добавление ключей</b>\n\n"
        f"Введите ключи (по одному на строку):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_add_keys")]])
    )
    await callback.answer()

@dp.message(AddKeysStates.waiting_keys)
async def add_keys_to_product_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    product_id = data.get("product_id")
    keys_text = message.text.strip()
    
    keys = [k.strip() for k in keys_text.split('\n') if k.strip()]
    
    if not keys:
        await message.answer("❌ Не найдено ни одного ключа. Попробуйте снова:")
        return
    
    await add_keys_to_product(product_id, keys)
    
    product = await get_product_by_id(product_id)
    
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Ключи успешно добавлены!</b>\n\n"
        f"Товар: <b>{product['name']}</b>\n"
        f"Добавлено ключей: <code>{len(keys)}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel")]])
    )
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_add_balance")
async def admin_add_balance(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    await state.set_state(AdminAddBalanceStates.waiting_user_id)
    await callback.message.edit_text(
        f"{emoji(EMOJI['dollar'], '💰')} <b>Выдача баланса</b>\n\n"
        f"Введите ID пользователя:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]])
    )
    await callback.answer()

@dp.message(AdminAddBalanceStates.waiting_user_id)
async def admin_add_balance_user_id(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        await state.update_data(target_user_id=user_id)
        await state.set_state(AdminAddBalanceStates.waiting_amount)
        await message.answer(
            f"💰 Введите сумму для начисления (в рублях):\n\n"
            f"Пользователь: <code>{user_id}</code>",
            parse_mode="HTML"
        )
    except:
        await message.answer("❌ Введите корректный ID пользователя (число):")

@dp.message(AdminAddBalanceStates.waiting_amount)
async def admin_add_balance_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительной")
            return
    except:
        await message.answer("❌ Введите корректную сумму")
        return
    
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    
    await add_balance(target_user_id, amount)
    new_balance = await get_balance(target_user_id)
    
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Баланс успешно выдан!</b>\n\n"
        f"Пользователь: <code>{target_user_id}</code>\n"
        f"Сумма: <code>{amount} ₽</code>\n"
        f"Новый баланс: <code>{new_balance} ₽</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel")]])
    )
    
    try:
        await bot.send_message(
            target_user_id,
            f"{emoji(EMOJI['gift'], '🎁')} <b>Вам начислен бонус!</b>\n\n"
            f"Сумма: <code>{amount} ₽</code>\n"
            f"💰 Текущий баланс: <code>{new_balance} ₽</code>",
            parse_mode="HTML"
        )
    except:
        pass
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    await state.set_state(AdminBroadcastStates.waiting_message)
    await callback.message.edit_text(
        f"{emoji(EMOJI['notification'], '📢')} <b>Рассылка</b>\n\n"
        f"Введите текст сообщения для рассылки:\n"
        f"<i>Поддерживается HTML-разметка</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]])
    )
    await callback.answer()

@dp.message(AdminBroadcastStates.waiting_message)
async def admin_broadcast_send(message: Message, state: FSMContext):
    text = message.text
    
    users = await get_all_users()
    success = 0
    fail = 0
    
    status_msg = await message.answer("⏳ Начинаю рассылку...")
    
    for user in users:
        try:
            await bot.send_message(user["user_id"], text, parse_mode="HTML")
            success += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(
        f"{emoji(EMOJI['check'], '✅')} <b>Рассылка завершена!</b>\n\n"
        f"✅ Отправлено: <code>{success}</code>\n"
        f"❌ Ошибок: <code>{fail}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel")]])
    )
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_create_promocode")
async def admin_create_promocode(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    await state.set_state(AdminCreatePromocodeStates.waiting_code)
    await callback.message.edit_text(
        f"{emoji(EMOJI['discount'], '🎫')} <b>Создание промокода</b>\n\n"
        f"Введите название промокода (латиницей, цифры):\n"
        f"<i>Например: SUMMER2024</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin_panel")]])
    )
    await callback.answer()

@dp.message(AdminCreatePromocodeStates.waiting_code)
async def admin_create_promocode_code(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    
    existing = await get_promocode(code)
    if existing:
        await message.answer("❌ Промокод с таким названием уже существует. Введите другое название:")
        return
    
    await state.update_data(code=code)
    await state.set_state(AdminCreatePromocodeStates.waiting_type)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Фиксированная сумма (₽)", callback_data="promocode_type_rubles")],
        [InlineKeyboardButton(text="Процент скидки (%)", callback_data="promocode_type_percent")]
    ])
    
    await message.answer(
        f"🎫 <b>Создание промокода</b>\n\n"
        f"Название: <b>{code}</b>\n\n"
        f"Выберите тип бонуса:",
        parse_mode="HTML",
        reply_markup=kb
    )

@dp.callback_query(lambda c: c.data.startswith("promocode_type_"))
async def admin_create_promocode_type(callback: CallbackQuery, state: FSMContext):
    bonus_type = callback.data.split("_")[2]
    await state.update_data(bonus_type=bonus_type)
    await state.set_state(AdminCreatePromocodeStates.waiting_value)
    
    if bonus_type == "rubles":
        await callback.message.edit_text(
            f"💰 Введите сумму бонуса (в рублях):\n"
            f"<i>Например: 100</i>",
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            f"📊 Введите процент скидки (от 1 до 100):\n"
            f"<i>Например: 10</i>",
            parse_mode="HTML"
        )
    await callback.answer()

@dp.message(AdminCreatePromocodeStates.waiting_value)
async def admin_create_promocode_value(message: Message, state: FSMContext):
    try:
        value = int(message.text.strip())
        data = await state.get_data()
        if data.get("bonus_type") == "percent" and (value < 1 or value > 100):
            await message.answer("❌ Процент скидки должен быть от 1 до 100. Попробуйте снова:")
            return
        if value <= 0:
            await message.answer("❌ Значение должно быть положительным. Попробуйте снова:")
            return
    except:
        await message.answer("❌ Введите корректное число. Попробуйте снова:")
        return
    
    await state.update_data(bonus_value=value)
    await state.set_state(AdminCreatePromocodeStates.waiting_max_uses)
    await message.answer(
        f"🔢 Введите максимальное количество использований:\n"
        f"<i>Например: 100 (или 0 для безлимита)</i>",
        parse_mode="HTML"
    )

@dp.message(AdminCreatePromocodeStates.waiting_max_uses)
async def admin_create_promocode_max_uses(message: Message, state: FSMContext):
    try:
        max_uses = int(message.text.strip())
        if max_uses < 0:
            await message.answer("❌ Количество использований не может быть отрицательным")
            return
        if max_uses == 0:
            max_uses = None
    except:
        await message.answer("❌ Введите корректное число. Попробуйте снова:")
        return
    
    data = await state.get_data()
    code = data.get("code")
    bonus_type = data.get("bonus_type")
    bonus_value = data.get("bonus_value")
    
    await create_promocode(code, bonus_type, bonus_value, max_uses)
    
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Промокод успешно создан!</b>\n\n"
        f"Название: <b>{code}</b>\n"
        f"Тип: {'Фиксированная сумма' if bonus_type == 'rubles' else 'Процент'}\n"
        f"Значение: <code>{bonus_value} {'₽' if bonus_type == 'rubles' else '%'}</code>\n"
        f"Лимит использований: <code>{max_uses if max_uses else 'Безлимит'}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel")]])
    )
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_list_promocodes")
async def admin_list_promocodes(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    promocodes = await get_all_promocodes()
    
    if not promocodes:
        await callback.message.edit_text(
            "📭 Список промокодов пуст.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]])
        )
        await callback.answer()
        return
    
    text = f"{emoji(EMOJI['folder'], '📋')} <b>Список промокодов</b>\n\n"
    
    for p in promocodes:
        text += f"• <b>{p['code']}</b> - {p['value']} {'₽' if p['type'] == 'rubles' else '%'} | Использован: {p['used_count']}/{p['max_uses'] if p['max_uses'] else '∞'}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить промокод", callback_data="admin_delete_promocode")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_delete_promocode")
async def admin_delete_promocode_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    promocodes = await get_all_promocodes()
    
    if not promocodes:
        await callback.answer("Нет промокодов для удаления", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{p['code']}", callback_data=f"delete_promo_{p['code']}")]
        for p in promocodes
    ] + [[InlineKeyboardButton(text="Назад", callback_data="admin_list_promocodes")]])
    
    await callback.message.edit_text(
        "🗑 <b>Выберите промокод для удаления:</b>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_promo_"))
async def admin_delete_promocode_confirm(callback: CallbackQuery):
    code = callback.data.replace("delete_promo_", "")
    
    await delete_promocode(code)
    
    await callback.answer(f"Промокод {code} удален", show_alert=True)
    
    await admin_list_promocodes(callback)

@dp.callback_query(lambda c: c.data == "admin_ref_config")
async def admin_ref_config(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    config = await get_referral_config()
    bonus_text = f"{config['bonus_value']} {'₽' if config['bonus_type'] == 'rubles' else '%'}"
    
    text = (
        f"{emoji(EMOJI['repeat'], '👥')} <b>Настройка реферальной системы</b>\n\n"
        f"Награда: {bonus_text}\n\n"
        f"Выберите действие:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Изменить награду", callback_data="ref_change_bonus")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "ref_change_bonus")
async def ref_change_bonus(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    await state.set_state(AdminRefBonusStates.waiting_type)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Фиксированная сумма (₽)", callback_data="ref_bonus_rubles")],
        [InlineKeyboardButton(text="Процент от покупки (%)", callback_data="ref_bonus_percent")]
    ])
    
    await callback.message.edit_text(
        "🎁 <b>Выберите тип награды:</b>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("ref_bonus_"))
async def ref_bonus_type(callback: CallbackQuery, state: FSMContext):
    bonus_type = callback.data.split("_")[2]
    await state.update_data(bonus_type=bonus_type)
    await state.set_state(AdminRefBonusStates.waiting_value)
    
    if bonus_type == "rubles":
        await callback.message.edit_text(
            "💰 Введите сумму награды (в рублях):\n"
            "<i>Например: 50</i>",
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            "📊 Введите процент от покупки (от 1 до 100):\n"
            "<i>Например: 10</i>",
            parse_mode="HTML"
        )
    await callback.answer()

@dp.message(AdminRefBonusStates.waiting_value)
async def ref_bonus_value(message: Message, state: FSMContext):
    try:
        value = int(message.text.strip())
        data = await state.get_data()
        if data.get("bonus_type") == "percent" and (value < 1 or value > 100):
            await message.answer("❌ Процент должен быть от 1 до 100. Попробуйте снова:")
            return
        if value <= 0:
            await message.answer("❌ Значение должно быть положительным. Попробуйте снова:")
            return
    except:
        await message.answer("❌ Введите корректное число. Попробуйте снова:")
        return
    
    await update_referral_config("bonus_type", data.get("bonus_type"))
    await update_referral_config("bonus_value", value)
    
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Настройки реферальной системы обновлены!</b>\n\n"
        f"Тип награды: {'Фиксированная сумма' if data.get('bonus_type') == 'rubles' else 'Процент'}\n"
        f"Значение: <code>{value} {'₽' if data.get('bonus_type') == 'rubles' else '%'}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel")]])
    )
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_toggle_mode")
async def admin_toggle_mode(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    current_mode = await get_setting("shop_mode")
    new_mode = "manual" if current_mode == "auto" else "auto"
    await update_setting("shop_mode", new_mode)
    
    await callback.answer(f"Режим магазина изменен на {'Автоматический' if new_mode == 'auto' else 'Ручной'}", show_alert=True)
    
    await send_admin_panel(callback, callback.from_user.id)

@dp.callback_query(lambda c: c.data == "admin_change_custom_text")
async def admin_change_custom_text(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    current_text = await get_setting("custom_payment_text")
    if not current_text:
        current_text = "Не установлен"
    
    await state.set_state(AdminCustomTextStates.waiting_text)
    await callback.message.edit_text(
        f"{emoji(EMOJI['edit'], '✏️')} <b>Изменение текста для ручной оплаты</b>\n\n"
        f"Текущий текст:\n<code>{current_text}</code>\n\n"
        f"Введите новый текст (отправьте сообщение):\n"
        f"<i>Пользователь увидит этот текст при выборе ручного способа оплаты</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]])
    )
    await callback.answer()

@dp.message(AdminCustomTextStates.waiting_text)
async def admin_custom_text_save(message: Message, state: FSMContext):
    new_text = message.text.strip()
    
    await update_setting("custom_payment_text", new_text)
    
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Текст для ручной оплаты обновлен!</b>\n\n"
        f"Новый текст:\n<code>{new_text}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel")]])
    )
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_manage_products")
async def admin_manage_products(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    products = await get_all_products()
    
    if not products:
        await callback.message.edit_text(
            "📭 Список товаров пуст.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]])
        )
        await callback.answer()
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🗑 {p['name']} (ID: {p['id']})", callback_data=f"manage_product_del_{p['id']}")]
        for p in products
    ] + [[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]])
    
    await callback.message.edit_text(
        f"{emoji(EMOJI['store'], '🛍')} <b>Управление товарами</b>\n\n"
        f"Нажмите на товар для удаления:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("manage_product_del_"))
async def admin_delete_product(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[3])
    product = await get_product_by_id(product_id)
    
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return
    
    await delete_product(product_id)
    
    await callback.answer(f"Товар '{product['name']}' удален", show_alert=True)
    
    await admin_manage_products(callback)

@dp.callback_query(lambda c: c.data == "admin_manage_keys")
async def admin_manage_keys(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    products = await get_all_products()
    
    if not products:
        await callback.message.edit_text(
            "📭 Сначала добавьте товар.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]])
        )
        await callback.answer()
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔑 {p['name']} (ID: {p['id']})", callback_data=f"manage_keys_show_{p['id']}")]
        for p in products
    ] + [[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]])
    
    await callback.message.edit_text(
        f"{emoji(EMOJI['key'], '🔑')} <b>Управление ключами</b>\n\n"
        f"Выберите товар для просмотра/удаления ключей:",
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("manage_keys_show_"))
async def admin_show_keys(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[3])
    product = await get_product_by_id(product_id)
    keys = await get_keys_by_product(product_id)
    
    if not keys:
        await callback.message.edit_text(
            f"🔑 <b>Ключи товара: {product['name']}</b>\n\n"
            f"Нет ключей для этого товара.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Добавить ключи", callback_data=f"add_keys_to_{product_id}")],
                [InlineKeyboardButton(text="Назад", callback_data="admin_manage_keys")]
            ])
        )
        await callback.answer()
        return
    
    text = f"🔑 <b>Ключи товара: {product['name']}</b>\n\n"
    used_count = sum(1 for k in keys if k["used_by"] is not None)
    text += f"Всего: {len(keys)} | Использовано: {used_count} | Свободно: {len(keys) - used_count}\n\n"
    
    kb_buttons = []
    for k in keys[:20]:
        status = "✅" if k["used_by"] is None else "❌"
        text += f"{status} <code>{k['key_value']}</code>"
        if k["used_by"]:
            text += f" (куплен: {k['used_by']})"
        text += "\n"
        kb_buttons.append([InlineKeyboardButton(f"🗑 Удалить {k['key_value'][:10]}...", callback_data=f"delete_key_{k['id']}")])
    
    if len(keys) > 20:
        text += f"\n<i>... и еще {len(keys) - 20} ключей</i>"
    
    kb_buttons.append([InlineKeyboardButton(text="➕ Добавить ключи", callback_data=f"add_keys_to_{product_id}")])
    kb_buttons.append([InlineKeyboardButton(text="Назад", callback_data="admin_manage_keys")])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons))
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_key_"))
async def admin_delete_key(callback: CallbackQuery):
    key_id = int(callback.data.split("_")[2])
    
    await delete_key(key_id)
    
    await callback.answer("Ключ удален", show_alert=True)
    
    await admin_manage_keys(callback)

@dp.callback_query(lambda c: c.data.startswith("add_keys_to_"))
async def admin_add_keys_to_existing_product(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.split("_")[3])
    await state.update_data(product_id=product_id)
    await state.set_state(AddKeysStates.waiting_keys)
    
    await callback.message.edit_text(
        f"{emoji(EMOJI['key'], '🔑')} <b>Добавление ключей</b>\n\n"
        f"Введите ключи (по одному на строку):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data=f"manage_keys_show_{product_id}")]])
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    stats = await get_stats()
    
    text = (
        f"{emoji(EMOJI['crown'], '📊')} <b>СТАТИСТИКА БОТА</b> {emoji(EMOJI['crown'], '📊')}\n\n"
        f"{emoji(EMOJI['person'], '👥')} Всего пользователей: <code>{stats['total_users']}</code>\n"
        f"{emoji(EMOJI['dollar'], '💰')} Всего продаж: <code>{stats['total_sales']} ₽</code>\n"
        f"{emoji(EMOJI['key'], '🔑')} Продано ключей: <code>{stats['total_keys_sold']}</code>\n\n"
        f"{emoji(EMOJI['gift'], '🎁')} Всего промокодов: <code>{stats['total_promocodes']}</code>\n"
        f"{emoji(EMOJI['repeat'], '👥')} Приглашенных рефералов: <code>{stats['total_referrals']}</code>"
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]]))
    await callback.answer()

@dp.callback_query(lambda c: c.data == "admin_crypto_fee")
async def admin_crypto_fee(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    current_fee = await get_crypto_fee()
    
    await state.set_state(AdminCryptoFeeStates.waiting_fee)
    await callback.message.edit_text(
        f"{emoji(EMOJI['crypto'], '🪙')} <b>Настройка комиссии для крипто-платежей</b>\n\n"
        f"Текущая комиссия: <code>{current_fee}%</code>\n\n"
        f"Введите новый процент комиссии (от 0 до 50):\n"
        f"<i>Комиссия будет добавлена к сумме оплаты.\n"
        f"Пример: при комиссии 5% и желаемом пополнении 100₽, пользователь заплатит ~105₽</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]])
    )
    await callback.answer()

@dp.message(AdminCryptoFeeStates.waiting_fee)
async def admin_crypto_fee_save(message: Message, state: FSMContext):
    try:
        fee = float(message.text.strip().replace(',', '.'))
        if fee < 0 or fee > 50:
            await message.answer("❌ Комиссия должна быть от 0 до 50%. Попробуйте снова:")
            return
    except:
        await message.answer("❌ Введите корректное число. Попробуйте снова:")
        return
    
    await set_crypto_fee(fee)
    
    await message.answer(
        f"{emoji(EMOJI['check'], '✅')} <b>Комиссия для крипто-платежей обновлена!</b>\n\n"
        f"Новая комиссия: <code>{fee}%</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel")]])
    )
    
    await state.clear()

@dp.callback_query(lambda c: c.data == "admin_cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await send_admin_panel(callback, callback.from_user.id)

@dp.callback_query(lambda c: c.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа")
        return
    
    await send_admin_panel(callback, callback.from_user.id)

@flask_app.route('/')
def index():
    return jsonify({"status": "ok", "bot": "KeeperShop"})

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    return jsonify({"status": "ok"})

async def on_startup():
    await connect_db()
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Бот запущен, вебхук удалён")

def run_flask():
    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

async def main():
    await on_startup()
    
    thread = Thread(target=run_flask, daemon=True)
    thread.start()
    print("✅ Flask сервер запущен на порту 8080")
    
    print("🚀 Запуск polling...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
