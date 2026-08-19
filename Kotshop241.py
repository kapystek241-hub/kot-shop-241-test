import asyncio
import logging
import aiohttp
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder  # <-- исправлено
from dotenv import load_dotenv
import sqlite3
import os

DB_PATH = "orders.db"
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
# Проверь, что это актуальный IP твоего VPS, где крутится FastAPI на порту 8000
VPS_IP = "157.22.252.246"
API_BASE_URL = f"http://{VPS_IP}:8000"
DB_PATH = "orders.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kotshop_bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_id TEXT NOT NULL,
            payment_url TEXT NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'WAITING'
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized.")

def save_order(user_id: int, order_id: str, payment_url: str, amount: float):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO orders (user_id, order_id, payment_url, amount) VALUES (?, ?, ?, ?)",
            (user_id, order_id, payment_url, amount)
        )
        conn.commit()
        logger.info(f"Order saved: user_id={user_id}, order_id={order_id}")
    except Exception as e:
        logger.error(f"Failed to save order: {e}")
    finally:
        conn.close()

def get_pay_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Купить товар (100 ₽)", callback_data="buy_100")
    return builder.as_markup()

def get_payment_link_keyboard(payment_url: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="Перейти к оплате", url=payment_url)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Добро пожаловать в KotShop241!\nВыберите товар для покупки:",
        reply_markup=get_pay_keyboard()
    )

@dp.callback_query(F.data == "buy_100")
async def cb_buy_100(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    amount = 100

    logger.info(f"User {user_id} clicked 'buy_100', initiating payment...")

    payload = {
        "user_id": user_id,
        "amount": amount
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE_URL}/pay/init",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    logger.error(f"API returned status {resp.status}")
                    await callback.answer("Ошибка сервера. Попробуйте позже.", show_alert=True)
                    return

                data = await resp.json()

        success = data.get("success")
        message_text = data.get("message", "")
        order_data = data.get("data", {})
        payment_url = order_data.get("PaymentURL")
        order_id = order_data.get("OrderId")

        if not success:
            logger.warning(f"Payment init failed: {message_text}")
            await callback.answer(f"Ошибка: {message_text}", show_alert=True)
            return

        save_order(user_id, order_id, payment_url, amount)

        logger.info(f"Payment created: order_id={order_id}, url={payment_url}")

        await callback.message.edit_text(
            f"✅ Заказ создан!\n\n"
            f"Сумма: {amount} ₽\n"
            f"OrderId: {order_id}\n\n"
            f"{message_text}",
            reply_markup=get_payment_link_keyboard(payment_url)
        )
        await callback.answer()

    except asyncio.TimeoutError:
        logger.error("Request to FastAPI timed out")
        await callback.answer("Сервер оплаты не ответил вовремя. Попробуйте позже.", show_alert=True)
    except Exception as e:
        logger.exception(f"Unexpected error during payment init: {e}")
        await callback.answer("Произошла непредвиденная ошибка. Попробуйте позже.", show_alert=True)
def get_orders_by_user(user_id: int):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, order_id, amount, status, created_at FROM orders WHERE user_id = ?",
            (user_id,)
        )
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"Error reading orders: {e}")
        return []

@dp.message(Command("myorders"))
async def cmd_myorders(message: types.Message):
    rows = get_orders_by_user(message.from_user.id)
    if not rows:
        await message.answer("У вас пока нет заказов.")
        return
    text = "Ваши заказы:\n"
    for r in rows:
        # r = (id, user_id, order_id, amount, status, created_at)
        text += f"- №{r[0]}: {r[2]} | {r[3]} ₽ | статус: {r[4]} | {r[5]}\n"
    await message.answer(text)
    
async def main():
    init_db()
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
