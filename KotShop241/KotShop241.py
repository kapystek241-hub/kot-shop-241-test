import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_menu_keyboard():
    kb = [
        [InlineKeyboardButton(text="���ню", callback_data="menu")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

@dp.message()
async def echo_handler(message: types.Message):
    await message.answer(
        "Всё работает корректно!",
        reply_markup=get_menu_keyboard()
    )

@dp.callback_query()
async def callback_handler(callback: types.CallbackQuery):
    text = "Всё работает корректно!"
    if callback.data == "menu":
        text = "Это главное меню бота."
    elif callback.data == "help":
        text = "Нажми на кнопку или просто напиши любое сообщение — я отвечу."

    await callback.answer()
    await callback.message.edit_text(
        text,
        reply_markup=get_menu_keyboard()
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    await message.answer(
        "Чек получен. Теперь отправьте логин Steam, на который нужно пополнить данную сумму.\n"
        "Регион должен быть РФ, другие не обслуживаются."
    )
    user_data[user_id]["state"] = "await_login"


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
