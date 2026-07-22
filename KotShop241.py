import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from db import create_order
from app import generate_external_id  # или продублируй функцию

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Это магазин KotShop241.\nНажми /buy, чтобы купить UC‑1000.")

@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    external_id = generate_external_id()
    # Создаём заказ в БД
    create_order(
        telegram_user_id=message.from_user.id,
        product_name="UC-1000",
        amount_rub=100.00,
        external_order_id=external_id,
    )

    # Здесь можно сделать запрос к FastAPI /payments/create, но для простоты — заглушка
    # В проде лучше вызывать FastAPI эндпоинт через httpx, а не дублировать логику
    await message.answer(
        f"Заказ #{external_id} создан.\n"
        "Скоро добавим кнопку «Оплатить» с ссылкой на Т‑Банк."
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
