# bothost_bot.py — запускается на BotHost
import asyncio
import os

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
VPS_API_URL = os.getenv("VPS_API_URL")  # например: http://123.45.67.89:8080
API_SECRET = os.getenv("API_SECRET", "change-me")

if not all([BOT_TOKEN, VPS_API_URL]):
    raise ValueError("Не заданы переменные окружения: BOT_TOKEN, VPS_API_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ─── FSM ───
class OrderFlow(StatesGroup):
    waiting_for_id = State()


# ─── Тексты ───
WELCOME_TEXT = (
    "Добро пожаловать в Telegram-бот KotShop241! Мы работаем официально через Т-Банк "
    "и даём возможность быстро и с гарантией пополнить любой сервис из нашего каталога. "
    "Также помогаем находить недоступные игры в Steam для пользователей из РФ."
)


# ─── Клавиатуры ───
def kb_start():
    b = InlineKeyboardBuilder()
    b.button(text="Меню", callback_data="menu")
    b.button(text="Оферта", callback_data="oferta")
    b.adjust(2)
    return b.as_markup()


def kb_menu():
    b = InlineKeyboardBuilder()
    b.button(text="Купить", callback_data="buy")
    b.button(text="Поддержка", callback_data="support")
    b.button(text="Турнир", callback_data="tournament")
    b.button(text="Назад", callback_data="back_start")
    b.adjust(2, 1, 1)
    return b.as_markup()


def kb_buy():
    b = InlineKeyboardBuilder()
    b.button(text="PUBG Mobile", callback_data="pubg")
    b.button(text="Назад", callback_data="back_menu")
    b.adjust(1)
    return b.as_markup()


def kb_pubg():
    b = InlineKeyboardBuilder()
    b.button(text="Выбор определенного кол-во валюты", callback_data="pubg_fixed")
    b.button(text="Уникальное кол-во валюты", callback_data="pubg_custom")
    b.button(text="Назад", callback_data="back_buy")
    b.adjust(1)
    return b.as_markup()


def kb_pubg_fixed():
    b = InlineKeyboardBuilder()
    b.button(text="60 UC", callback_data="pubg_60uc")
    b.button(text="Назад", callback_data="back_pubg")
    b.adjust(1)
    return b.as_markup()


def kb_confirm(game_id: str):
    b = InlineKeyboardBuilder()
    b.button(text="Все верно", callback_data=f"confirm_yes:{game_id}")
    b.button(text="Неверный ID", callback_data="confirm_noid")
    b.button(text="Я передумал", callback_data="confirm_cancel")
    b.adjust(1)
    return b.as_markup()


# ─── Хендлеры ───
@dp.message(Command("start"))
async def cmd_start(message):
    await message.answer(WELCOME_TEXT, reply_markup=kb_start())


@dp.callback_query(F.data == "menu")
async def cb_menu(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите нужный раздел", reply_markup=kb_menu())
    await callback.answer()


@dp.callback_query(F.data == "oferta")
async def cb_oferta(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "📄 Политика компании\n\n(Текст в написании)",
        reply_markup=kb_start()
    )
    await callback.answer()


@dp.callback_query(F.data == "back_start")
async def cb_back_start(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=kb_start())
    await callback.answer()


@dp.callback_query(F.data == "buy")
async def cb_buy(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите нужную игру или напишите название игры для получения раздела покупки",
        reply_markup=kb_buy()
    )
    await callback.answer()


@dp.callback_query(F.data == "support")
async def cb_support(callback, state: FSMContext):
    await state.clear()
    await callback.message.answer("Связь с поддержкой: @kotshop241_support")
    await callback.answer()


@dp.callback_query(F.data == "tournament")
async def cb_tournament(callback, state: FSMContext):
    await state.clear()
    await callback.message.answer("🏆 Турнирный раздел в разработке")
    await callback.answer()


@dp.callback_query(F.data == "back_menu")
async def cb_back_menu(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите нужный раздел", reply_markup=kb_menu())
    await callback.answer()


@dp.callback_query(F.data == "pubg")
async def cb_pubg(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите удобный способ получения игровой валюты",
        reply_markup=kb_pubg()
    )
    await callback.answer()


@dp.callback_query(F.data == "back_buy")
async def cb_back_buy(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите нужную игру или напишите название игры для получения раздела покупки",
        reply_markup=kb_buy()
    )
    await callback.answer()


@dp.callback_query(F.data == "pubg_fixed")
async def cb_pubg_fixed(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите нужное количество игровой валюты на ваш аккаунт с фиксированной суммой, "
        "если не найдёте нужное количество, попробуйте создать заказ (Уникальное кол-во валюты)",
        reply_markup=kb_pubg_fixed()
    )
    await callback.answer()


@dp.callback_query(F.data == "pubg_custom")
async def cb_pubg_custom(callback, state: FSMContext):
    await state.clear()
    await callback.message.answer("Раздел «Уникальное кол-во валюты» в разработке")
    await callback.answer()


@dp.callback_query(F.data == "back_pubg")
async def cb_back_pubg(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите удобный способ получения игровой валюты",
        reply_markup=kb_pubg()
    )
    await callback.answer()


@dp.callback_query(F.data == "pubg_60uc")
async def cb_pubg_60uc(callback, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_id)
    await callback.message.edit_text("Укажите ваш ID который должен начинаться на 5")
    await callback.answer()


@dp.message(OrderFlow.waiting_for_id)
async def process_game_id(message, state: FSMContext):
    game_id = message.text.strip()

    if not game_id.isdigit() or not game_id.startswith("5"):
        await message.answer(
            "❌ ID должен состоять только из цифр и начинаться на 5. Попробуйте ещё раз."
        )
        return

    await state.clear()
    await message.answer(
        f"Вы выбрали товар 60 UC стоимостью в 79 рублей\n"
        f"Ваш ID: {game_id}",
        reply_markup=kb_confirm(game_id)
    )


@dp.callback_query(F.data.startswith("confirm_yes"))
async def cb_confirm_yes(callback, state: FSMContext):
    await state.clear()
    game_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    order_id = f"order-{user_id}-{int(asyncio.get_event_loop().time())}"
    amount_kopecks = 7900

    # Запрос к VPS-бэкенду на создание платежа
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{VPS_API_URL}/create-payment",
                json={
                    "secret": API_SECRET,
                    "order_id": order_id,
                    "amount_kopecks": amount_kopecks,
                    "game_id": game_id,
                    "user_id": user_id,
                    "description": f"Покупка 60 UC для PUBG Mobile. Игровой ID: {game_id}",
                    "email": "noreply@kotshop241.ru",
                }
            ) as resp:
                data = await resp.json()

        if not data.get("success"):
            err = data.get("error", "неизвестная ошибка")
            print(f"Ошибка создания платежа: {data}")
            await callback.message.edit_text(
                f"Не удалось создать платёж: {err}. Попробуйте позже."
            )
            await callback.answer()
            return

        pay_url = data["payment_url"]

    except Exception as e:
        print(f"Ошибка запроса к VPS: {e}")
        await callback.message.edit_text(
            "Сервер временно недоступен. Попробуйте позже."
        )
        await callback.answer()
        return

    b = InlineKeyboardBuilder()
    b.button(text="Оплатить 79 ₽", url=pay_url)
    b.adjust(1)

    await callback.message.edit_text(
        f"Заказ #{order_id}\n"
        f"Товар: 60 UC\n"
        f"Ваш ID: {game_id}\n"
        f"Сумма: 79 ₽\n\n"
        f"Нажмите «Оплатить», чтобы завершить покупку.",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@dp.callback_query(F.data == "confirm_noid")
async def cb_confirm_noid(callback, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_id)
    await callback.message.edit_text("Укажите ваш ID который должен начинаться на 5")
    await callback.answer()


@dp.callback_query(F.data == "confirm_cancel")
async def cb_confirm_cancel(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите удобный способ получения игровой валюты",
        reply_markup=kb_pubg()
    )
    await callback.answer()


# ─── Main ───
async def main():
    print("BotHost бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
