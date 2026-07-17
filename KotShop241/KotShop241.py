import os
import logging
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------------------------
# Конфигурация
# -------------------------
load_dotenv()  # Если BotHost сам подтягивает .env — можно убрать
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в переменных окружения BotHost")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kotshop-bot")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# -------------------------
# Хендлер /buy: только генерация ссылки
# -------------------------
@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    user = message.from_user
    user_id = user.id
    amount = 600  # фиксированная сумма для теста

    # Генерируем уникальный order_id
    order_id = f"ORD-{user_id}-{int(datetime.now(timezone.utc).timestamp())}"

    logger.info(f"Пользователь {user_id} запросил оплату. order_id={order_id}")

    # Ссылка ведёт на твой VPS: он запишет в БД и сделает редирект на Т‑Банк
    vps_url = f"https://kotshop241.ru/start-payment?oid={order_id}&uid={user_id}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить заказ", url=vps_url)]
    ])

    await message.answer(
        f"💰 Заказ #{order_id}\n"
        f"Сумма: {amount} ₽\n\n"
        "Нажмите кнопку ниже, чтобы перейти к оплате.",
        reply_markup=kb
    )


# -------------------------
# Хендлер /start
# -------------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот KotShop241.\n"
        "Нажми /buy, чтобы оформить заказ."
    )


# -------------------------
# Запуск
# -------------------------
async def main():
    logger.info("Бот запущен на BotHost...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
