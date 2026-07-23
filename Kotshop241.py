import os
import logging
import hmac
import hashlib
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()  # читает .env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TBANK_TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY")
TBANK_TERMINAL_SECRET = os.getenv("TBANK_TERMINAL_SECRET")
TBANK_BASE_URL = os.getenv("TBANK_BASE_URL", "https://securepay.tinkoff.ru")
VPS_WEBHOOK_URL = os.getenv("VPS_WEBHOOK_URL")  # например https://shop.kotshop241.ru/webhook
ADMIN_ID = os.getenv("ADMIN_ID")

if not all([BOT_TOKEN, TBANK_TERMINAL_KEY, TBANK_TERMINAL_SECRET]):
    raise RuntimeError("Не хватает переменных окружения в .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def generate_order_id(chat_id: int) -> str:
    """Уникальный OrderId: chat_id-timestamp-random"""
    rand = os.urandom(4).hex()
    return f"{chat_id}-{int(datetime.utcnow().timestamp())}-{rand}"

def tinkoff_sign_payload(payload: Dict[str, Any]) -> str:
    """
    Правильная подпись для Т-Банка: HMAC-SHA256 от строки параметров.
    1. Сортируем ключи по алфавиту.
    2. Собираем key=value&key=value...
    3. Добавляем &TerminalKey={TERMINAL_KEY}
    4. HMAC-SHA256(secret, строка)
    """
    sorted_keys = sorted(payload.keys())
    parts = []
    for k in sorted_keys:
        v = payload[k]
        if v is None:
            v = ""
        parts.append(f"{k}={v}")
    base_string = "&".join(parts)
    full_string = f"{base_string}&TerminalKey={TBANK_TERMINAL_KEY}"

    signature = hmac.new(
        TBANK_TERMINAL_SECRET.encode("utf-8"),
        full_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return signature

async def create_tinkoff_payment(amount_kopecks: int, chat_id: int, description: str) -> Optional[Dict[str, Any]]:
    order_id = generate_order_id(chat_id)

    payload = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "Amount": amount_kopecks,
        "OrderId": order_id,
        "Description": description,
        "Language": "ru",
        # CustomerKey можно использовать для привязки к клиенту, если нужно
        # "CustomerKey": str(chat_id),
    }

    # Подписываем
    signature = tinkoff_sign_payload(payload)
    payload["Signature"] = signature

    url = f"{TBANK_BASE_URL}/v2/Init"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                return data
        except Exception as e:
            logger.error(f"Ошибка запроса к Т-Банку: {e}")
            return None

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    chat_id = user.id
    user_name = user.full_name or "Покупатель"
    logger.info(f"/start от {chat_id} ({user_name})")

    amount_kopecks = 10000  # 100 рублей
    description = f"Заказ в KotShop241 от {user_name}"

    payment_data = await create_tinkoff_payment(amount_kopecks, chat_id, description)
    if not payment_data:
        await message.answer("Ошибка при создании платежа. Попробуйте позже.")
        if ADMIN_ID:
            await bot.send_message(int(ADMIN_ID), "Ошибка создания платежа: нет ответа от Т-Банка")
        return

    status = payment_data.get("Status")
    pay_url = payment_data.get("PaymentURL")
    order_id = payment_data.get("OrderId")
    message_text = payment_data.get("Message")

    if status != "WAITING_FOR_PAYMENT" or not pay_url:
        err = message_text or "Неизвестный статус оплаты"
        logger.error(f"Платёж не создан: {status}, {err}")
        await message.answer(f"Не удалось создать платёж: {err}")
        if ADMIN_ID:
            await bot.send_message(int(ADMIN_ID), f"Платёж не создан: {payment_data}")
        return

    # Кнопка «Оплатить»
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить 100 ₽", url=pay_url)
    keyboard = builder.as_markup()

    await message.answer(
        f"Привет, {user_name}!\n\n"
        f"Для заказа нужно оплатить 100 ₽. Нажми кнопку ниже, чтобы перейти к оплате.",
        reply_markup=keyboard
    )

    logger.info(f"Заказ {order_id} создан, URL: {pay_url}")

    # Отправляем админу уведомление о новом заказе (опционально)
    if ADMIN_ID:
        await bot.send_message(
            int(ADMIN_ID),
            f"Новый заказ #{order_id}\nПользователь: {user_name} ({chat_id})\nСумма: 100 ₽\nURL: {pay_url}"
        )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
