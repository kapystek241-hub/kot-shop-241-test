import os
import hashlib
import hmac
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
import requests

# Если на BotHost нет файла .env — уберите load_dotenv и берите из os.environ
try:
    load_dotenv(".env")
except Exception:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN")
TBANK_TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY")
TBANK_TERMINAL_SECRET = os.getenv("TBANK_TERMINAL_SECRET")
TBANK_BASE_URL = os.getenv("TBANK_BASE_URL", "https://securepay.tinkoff.ru")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def generate_order_id(chat_id: int) -> str:
    # Уникальность: chat_id + случайное число
    return f"{chat_id}_{random.randint(10000, 99999)}"

def create_token(payload: dict, secret: str) -> str:
    # Сортируем ключи по алфавиту, склеиваем значения, считаем HMAC-SHA256
    sorted_keys = sorted(payload.keys())
    concatenated = "".join(str(payload[k]) for k in sorted_keys if k != "Token")
    digest = hmac.new(secret.encode("utf-8"), concatenated.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    amount_kopecks = 10000  # 100 рублей
    order_id = generate_order_id(message.chat.id)

    payload = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "Amount": amount_kopecks,
        "OrderId": order_id,
        "Description": f"Оплата заказа {order_id} в KotShop241",
    }
    token = create_token(payload, TBANK_TERMINAL_SECRET)
    payload["Token"] = token

    try:
        resp = requests.post(f"{TBANK_BASE_URL}/v2/Init", json=payload, timeout=10)
        data = resp.json()
    except Exception as e:
        await message.answer(f"❌ Ошибка при создании платежа: {e}")
        return

    if data.get("Success") and "PaymentURL" in data:
        payment_url = data["PaymentURL"]
        await message.answer(
            f"💳 Оплата заказа {order_id}\n"
            f"Сумма: 100 ₽\n"
            f"Нажмите на кнопку ниже, чтобы оплатить:",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="Оплатить", url=payment_url)]
            ])
        )
    else:
        error_msg = data.get("Message", "Неизвестная ошибка при создании платежа")
        await message.answer(f"❌ Не удалось создать платёж: {error_msg}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
