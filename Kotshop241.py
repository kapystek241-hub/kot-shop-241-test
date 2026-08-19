import asyncio
import os
import logging
import hashlib
import hmac
from datetime import datetime
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardBuilder, Message
from dotenv import load_dotenv

# -----------------------------
# Настройка логирования
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("KotShop241")

load_dotenv()

# -----------------------------
# Переменные окружения
# -----------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
TBANK_TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY")
TBANK_SECRET_KEY = os.getenv("TBANK_SECRET_KEY")

if not all([BOT_TOKEN, TBANK_TERMINAL_KEY, TBANK_SECRET_KEY]):
    logger.error("Не заданы все необходимые переменные окружения!")
    raise ValueError("Проверьте .env: BOT_TOKEN, TBANK_TERMINAL_KEY, TBANK_SECRET_KEY")

# -----------------------------
# Константы
# -----------------------------
PAYMENT_AMOUNT_RUB = 100  # фиксированная цена товара
PAYMENT_CURRENCY = "RUB"
ORDER_PREFIX = "kotshop_"

# -----------------------------
# HTTP клиент (переиспользуемый)
# -----------------------------
session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    global session
    if session is None:
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
    return session

async def close_session():
    global session
    if session:
        await session.close()
        session = None

# -----------------------------
# API Т-Банка (упрощённо)
# -----------------------------
async def tbank_init_payment(order_id: str, amount: int) -> Optional[dict]:
    """
    Инициализация платежа в Т-Банке.
    Возвращает ответ API или None при ошибке.
    """
    url = "https://securepay.tinkoff.ru/v2/Init"
    payload = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "Amount": amount,
        "Currency": PAYMENT_CURRENCY,
        "OrderId": order_id,
        "Description": "Пополнение игровой валюты и сервисов",
        "Data": {
            "Email": "client@example.com",  # можно брать из данных пользователя при необходимости
            "Phone": "+79990000000"         # можно брать из данных пользователя при необходимости
        }
    }

    # Подпись PayLoad (обязательная для Init)
    # В документации Т-Банка: Signature = HMAC-SHA256(JSON_без_пробелов, SecretKey)
    import json
    json_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    signature = hmac.new(
        TBANK_SECRET_KEY.encode("utf-8"),
        json_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    payload["Token"] = signature

    try:
        sess = await get_session()
        async with sess.post(url, json=payload) as resp:
            data = await resp.json()
            logger.info(f"Tinkoff Init response (status={resp.status}, success={data.get('Success')})")
            if resp.status == 200 and data.get("Success"):
                return data
            else:
                logger.error(f"Tinkoff Init failed: {data}")
                return None
    except Exception as e:
        logger.exception(f"Error calling Tinkoff Init: {e}")
        return None


async def tbank_get_order_status(order_id: str) -> Optional[dict]:
    """
    Проверка статуса заказа.
    """
    url = "https://securepay.tinkoff.ru/v2/GetOrderStatus"
    payload = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "OrderId": order_id
    }
    import json
    json_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    signature = hmac.new(
        TBANK_SECRET_KEY.encode("utf-8"),
        json_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    payload["Token"] = signature

    try:
        sess = await get_session()
        async with sess.post(url, json=payload) as resp:
            data = await resp.json()
            logger.info(f"Tinkoff GetOrderStatus response (status={resp.status}): {data}")
            if resp.status == 200:
                return data
            else:
                logger.error(f"Tinkoff GetOrderStatus failed: {data}")
                return None
    except Exception as e:
        logger.exception(f"Error calling Tinkoff GetOrderStatus: {e}")
        return None


# -----------------------------
# Логика бота
# -----------------------------
router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="Купить товар (100 ₽)", callback_data="buy_item")
    await message.answer(
        "Привет! Это бот KotShop241.\n"
        "Здесь можно безопасно и дёшево купить игровую валюту и пополнить сервисы.\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )


@router.callback_query(F.data == "buy_item")
async def cb_buy_item(callback: CallbackQuery):
    user_id = callback.from_user.id
    order_id = f"{ORDER_PREFIX}{user_id}_{int(datetime.now().timestamp())}"

    logger.info(f"Creating payment for user {user_id}, order_id={order_id}")

    result = await tbank_init_payment(order_id=order_id, amount=PAYMENT_AMOUNT_RUB)

    if not result or not result.get("Success") or "PaymentURL" not in result:
        await callback.answer("Ошибка при создании платежа. Попробуйте позже.", show_alert=True)
        return

    payment_url = result["PaymentURL"]

    builder = InlineKeyboardBuilder()
    builder.button(text="Перейти к оплате", url=payment_url)
    await callback.message.edit_text(
        f"Заказ #{order_id}\n"
        f"Сумма: {PAYMENT_AMOUNT_RUB} ₽\n\n"
        "Перейдите по ссылке для оплаты:",
        reply_markup=builder.as_markup()
    )
    logger.info(f"Payment link sent for order_id={order_id}")


# Простая периодическая проверка статусов (можно сделать умнее, но это базовый вариант)
async def check_pending_payments(bot: Bot):
    """
    В реальном проекте здесь будет очередь заказов и более умная логика.
    Сейчас это заглушка, чтобы показать принцип проверки статуса.
    """
    # Для примера: можно хранить pending_orders в Redis/SQLite.
    # Здесь мы ничего не делаем, но место под логику есть.
    pass


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    logger.info("Starting bot...")
    await dp.start_polling(bot)
    # При остановке корректно закроем HTTP-сессию
    await close_session()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
        asyncio.run(close_session())
