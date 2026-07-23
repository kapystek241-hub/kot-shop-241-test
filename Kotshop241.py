import asyncio
import hashlib
import hmac
import logging
import os
import sys
import time
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

import requests
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

load_dotenv()

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
TBANK_TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY")
TBANK_TERMINAL_PASS = os.getenv("TBANK_TERMINAL_PASS")

VPS_ORDERS_URL = "https://shop.kotshop241.ru/orders/create"
TBANK_INIT_URL = "https://securepay.tinkoff.ru/v2/Init"

if not all([BOT_TOKEN, TBANK_TERMINAL_KEY, TBANK_TERMINAL_PASS]):
    missing = [k for k, v in locals().items() if k.startswith("TBANK") or k == "BOT_TOKEN" and not v]
    logging.critical("Не хватает переменных окружения: %s", ", ".join(missing))
    sys.exit(1)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def generate_tbank_token(terminal_key: str, amount: int, order_id: str, password: str) -> str:
    """
    Генерирует подпись Token для Т‑Банка по официальной схеме:
    HMAC-SHA256(TerminalKey + Amount + OrderId + Password)
    Все части конкатенируются подряд, без разделителей.
    """
    payload_string = f"{terminal_key}{amount}{order_id}{password}"
    digest = hmac.new(
        password.encode("utf-8"),
        payload_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest


def create_order_on_vps_sync(order_id: str, chat_id: int, amount: float, description: str) -> Optional[Dict[str, Any]]:
    payload = {
        "order_id": order_id,
        "chat_id": chat_id,
        "amount": amount,
        "description": description,
    }
    try:
        resp = requests.post(VPS_ORDERS_URL, json=payload, timeout=10, verify=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            logger.warning("VPS вернул не JSON: Content-Type=%s", content_type)
            return None
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error("Ошибка запроса к VPS orders/create: %s", e)
        return None
    except ValueError as e:
        logger.error("Не удалось распарсить JSON от VPS: %s", e)
        return None


async def create_order_on_vps(order_id: str, chat_id: int, amount: float, description: str):
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=2) as executor:
        return await loop.run_in_executor(executor, create_order_on_vps_sync, order_id, chat_id, amount, description)


def get_pay_keyboard(url: str) -> InlineKeyboardMarkup:
    kb = [[InlineKeyboardButton(text="💳 Оплатить", url=url)]]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def tbank_init_sync(amount: float, description: str, customer_id: str) -> Optional[Dict[str, Any]]:
    amount_cents = int(round(amount * 100))

    # Лучше генерировать OrderId на бэкенде (FastAPI), а не в боте.
    # Здесь оставляем временную генерацию для теста.
    order_id = f"{customer_id}_{int(time.time())}"

    token = generate_tbank_token(TBANK_TERMINAL_KEY, amount_cents, order_id, TBANK_TERMINAL_PASS)

    headers = {"Content-Type": "application/json"}

    payload = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "Amount": amount_cents,
        "OrderId": order_id,
        "Description": description,
        "CustomerId": customer_id,
        "Token": token,
    }

    try:
        resp = requests.post(TBANK_INIT_URL, headers=headers, json=payload, timeout=15, verify=True)
        data = resp.json()  # Т‑Банк всегда возвращает JSON, даже при ошибках
    except requests.exceptions.RequestException as e:
        logger.error("Ошибка соединения с Т‑Банком: %s", e)
        return None
    except ValueError as e:
        logger.error("Не удалось распарсить JSON от Т‑Банка: %s", e)
        return None

    if resp.status_code != 200:
        logger.warning("Т‑Банк вернул HTTP %s: %s", resp.status_code, data)

    error_code = data.get("ErrorCode")
    if error_code and error_code != "0":
        error_msg = data.get("Message", "Неизвестная ошибка")
        logger.warning("Т‑Банк вернул ошибку: ErrorCode=%s, Message=%s", error_code, error_msg)
        return data

    return data


async def tbank_init(amount: float, description: str, customer_id: str):
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=2) as executor:
        return await loop.run_in_executor(executor, tbank_init_sync, amount, description, customer_id)


# --- РОУТЕР БОТА ---
router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    amount = 100.0
    description = "Оплата товара через Т‑Банк"
    customer_id = str(message.from_user.id)

    tbank_response = await tbank_init(amount, description, customer_id)
    if tbank_response is None:
        await message.answer("😕 Не удалось создать платёж у Т‑Банка. Попробуйте позже.")
        return

    error_code = tbank_response.get("ErrorCode")
    if error_code and error_code != "0":
        err_msg = tbank_response.get("Message", "Ошибка платёжной системы")
        logger.error("Т‑Банк: ErrorCode=%s, Message=%s", error_code, err_msg)
        await message.answer(f"⚠️ Ошибка платёжной системы: {err_msg}")
        return

    order_id_tbank = tbank_response.get("OrderId")
    payment_url = tbank_response.get("PaymentURL")

    if not order_id_tbank or not payment_url:
        logger.warning("Т‑Банк не вернул OrderId или PaymentURL: %s", tbank_response)
        await message.answer("⚠️ Ошибка платёжной системы: нет данных для оплаты.")
        return

    vps_result = await create_order_on_vps(
        order_id=order_id_tbank,
        chat_id=message.from_user.id,
        amount=amount,
        description=description,
    )

    if vps_result is None:
        await message.answer("😕 Техническая ошибка: не удалось сохранить заказ. Попробуйте позже.")
        return

    status = vps_result.get("status")
    order_id_local = vps_result.get("id")

    if status == "created":
        await message.answer(
            f"✅ Заказ #{order_id_local} создан.\n"
            f"Сумма: {vps_result.get('amount', amount)} ₽\n"
            "Нажмите кнопку ниже, чтобы оплатить:",
            reply_markup=get_pay_keyboard(payment_url),
        )
    elif status == "exists":
        await message.answer(
            "⚠️ Заказ уже существует. Вот кнопка для оплаты:",
            reply_markup=get_pay_keyboard(payment_url),
        )
    else:
        await message.answer("⚠️ Неожиданный статус заказа. Обратитесь в поддержку.")


@router.message(F.text == "Купить")
async def handle_buy(message: Message):
    await cmd_start(message)


# --- ТОЧКА ВХОДА ---
def main():
    logger.info("Запуск бота KotShop241...")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    dp.run_polling(bot)


if __name__ == "__main__":
    main()
