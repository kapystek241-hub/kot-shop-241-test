# bothost_bot.py — запускается на BotHost
import asyncio
import os
import json
import logging
import traceback
import time

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv

load_dotenv()

# ─── Логирование ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kotshop-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
VPS_API_URL = os.getenv("VPS_API_URL")  # например: http://123.45.67.89:8080
API_SECRET = os.getenv("API_SECRET", "change-me")

if not all([BOT_TOKEN, VPS_API_URL]):
    raise ValueError("Не заданы переменные окружения: BOT_TOKEN, VPS_API_URL")

logger.info(f"VPS_API_URL = {VPS_API_URL}")
logger.info(f"API_SECRET задан: {'да' if API_SECRET != 'change-me' else 'НЕТ (значение по умолчанию!)'}")

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

POLICY_TEXT = (
    "Магазин KotShop241 является официальным продавцом виртуальных товаров и осуществляет "
    "все расчёты в строгом соответствии с действующим законодательством Российской Федерации, "
    "включая требования Федерального закона «О национальной платёжной системе» и иные "
    "нормативно‑правовые акты, регулирующие оборот цифровых товаров и проведение платежей.\n\n"
    "Реализация товаров осуществляется исключительно в рамках заключённого публичного "
    "договора‑оферты, размещённого на официальном ресурсе магазина. Приобретение игровой "
    "валюты, игр и иных виртуальных товаров подтверждает согласие покупателя с условиями "
    "оферты и правилами работы магазина.\n\n"
    "Любые действия, направленные на нарушение установленных правил, в том числе попытки "
    "неправомерного получения выгоды, обхода платёжных механизмов, использования "
    "мошеннических схем либо иного злоупотребления условиями предоставления услуг, "
    "расцениваются как существенное нарушение договорных обязательств и могут "
    "квалифицироваться как противоправные деяния. Такие действия могут служить основанием "
    "для обращения в правоохранительные органы, а собранные материалы — быть использованы "
    "в качестве доказательной базы в рамках административного или уголовного производства "
    "в соответствии с Уголовным кодексом Российской Федерации и Кодексом Российской "
    "Федерации об административных правонарушениях.\n\n"
    "Магазин KotShop241 реализует игровую валюту, игровые аккаунты, внутриигровые предметы, "
    "ключи активации игр и иные виртуальные товары для популярных игровых платформ и "
    "сервисов. Ассортимент и условия реализации товаров определяются действующими правилами "
    "магазина и положениями оферты, обязательными для ознакомления перед совершением покупки."
)


# ─── Файл для сохранения ожидающих платежей ───
PENDING_FILE = os.getenv("PENDING_FILE", "pending_payments.json")
PAYMENT_TIMEOUT = 600
STARTUP_LOAD_WINDOW = 900

pending_payments: dict[str, dict] = {}


def save_pending_to_file():
    try:
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(pending_payments, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не удалось сохранить pending_payments в файл: {e}")


def load_pending_from_file():
    global pending_payments
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        now = time.time()
        loaded = {}
        for order_id, info in data.items():
            created_at = info.get("created_at", 0)
            if now - created_at < STARTUP_LOAD_WINDOW:
                loaded[order_id] = info
            else:
                logger.info(f"Платёж {order_id} старше {STARTUP_LOAD_WINDOW} сек — пропущен при загрузке")
        pending_payments = loaded
        logger.info(f"Загружено {len(loaded)} ожидающих платежей из файла {PENDING_FILE}")
    except FileNotFoundError:
        logger.info(f"Файл {PENDING_FILE} не найден — стартуем с пустым списком")
    except Exception as e:
        logger.error(f"Не удалось загрузить pending_payments из файла: {e}")


# ─── Клавиатуры ───
def kb_start():
    b = InlineKeyboardBuilder()
    b.button(text="Меню", callback_data="menu")
    b.button(text="Политика компании", callback_data="oferta")
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


def kb_back_to_menu():
    b = InlineKeyboardBuilder()
    b.button(text="Назад", callback_data="back_menu")
    b.adjust(1)
    return b.as_markup()


def kb_policy():
    b = InlineKeyboardBuilder()
    b.button(text="Меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


# ─── Запрос статуса платежа к VPS ───
async def vps_check_payment(order_id: str) -> bool | None:
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{VPS_API_URL}/check-payment",
                json={
                    "secret": API_SECRET,
                    "order_id": order_id,
                },
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"VPS /check-payment вернул HTTP {resp.status}: {text[:200]}")
                    return None
                data = await resp.json()
                return bool(data.get("paid", False))
    except Exception as e:
        logger.error(f"Ошибка запроса статуса платежа {order_id} к VPS: {e}")
        return None


# ─── Фоновая задача: проверка статуса платежей ───
async def check_payments_loop():
    logger.info("Запущен цикл проверки платежей (интервал 15 сек, таймаут 600 сек)")
    while True:
        await asyncio.sleep(15)
        now = time.time()
        to_remove = []

        for order_id, info in list(pending_payments.items()):
            try:
                if now - info["created_at"] > PAYMENT_TIMEOUT:
                    logger.info(f"Платёж {order_id} истёк по таймауту (10 мин)")
                    try:
                        await bot.delete_message(info["chat_id"], info["message_id"])
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение {info['message_id']}: {e}")

                    await bot.send_message(
                        info["chat_id"],
                        "Похоже, платёж прервался. Ничего страшного — "
                        "просто создайте заказ ещё раз, и сможете оплатить.",
                        reply_markup=kb_back_to_menu(),
                    )
                    to_remove.append(order_id)
                    continue

                paid = await vps_check_payment(order_id)

                if paid is None:
                    continue

                if not paid:
                    continue

                logger.info(f"Платёж {order_id} подтверждён (VPS: paid=true)")

                notify_msg = await bot.send_message(info["chat_id"], "Оплата выполнена")
                await asyncio.sleep(2)

                try:
                    await notify_msg.delete()
                except Exception as e:
                    logger.warning(f"Не удалось удалить сообщение «Оплата выполнена»: {e}")

                try:
                    await bot.delete_message(info["chat_id"], info["message_id"])
                except Exception as e:
                    logger.warning(f"Не удалось удалить сообщение с ссылкой на оплату: {e}")

                if "UC" in info.get("product_name", ""):
                    await bot.send_message(
                        info["chat_id"],
                        "UC поступят на аккаунт в течении 5 минут",
                        reply_markup=kb_back_to_menu(),
                    )
                else:
                    await bot.send_message(
                        info["chat_id"],
                        "Оплата успешно выполнена.",
                        reply_markup=kb_back_to_menu(),
                    )

                to_remove.append(order_id)

            except Exception as e:
                logger.error(f"Непредвиденная ошибка при обработке платежа {order_id}: {e}")
                logger.error(traceback.format_exc())
                continue

        if to_remove:
            for order_id in to_remove:
                pending_payments.pop(order_id, None)
            save_pending_to_file()


# ─── Хендлеры ───
@dp.message(Command("start"))
async def cmd_start(message):
    logger.info(f"/start от user_id={message.from_user.id}, username={message.from_user.username}")
    await message.answer(WELCOME_TEXT, reply_markup=kb_start())


@dp.callback_query(F.data == "menu")
async def cb_menu(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите нужный раздел", reply_markup=kb_menu())
    await callback.answer()


@dp.callback_query(F.data == "oferta")
async def cb_oferta(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(POLICY_TEXT, reply_markup=kb_policy())
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
        logger.warning(f"Неверный game_id от user_id={message.from_user.id}: '{game_id}'")
        await message.answer(
            "❌ ID должен состоять только из цифр и начинаться на 5. Попробуйте ещё раз."
        )
        return

    await state.clear()
    logger.info(f"Получен game_id={game_id} от user_id={message.from_user.id}")
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
    order_id = f"order-{user_id}-{int(time.time())}"
    amount_kopecks = 7900

    logger.info(f"Создание платежа: order_id={order_id}, user_id={user_id}, game_id={game_id}, amount={amount_kopecks}")

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
                logger.info(f"Ответ бэкенда: HTTP {resp.status}")
                try:
                    data = await resp.json()
                except Exception as e:
                    raw_text = await resp.text()
                    logger.error(f"Не удалось распарсить JSON от бэкенда: {e}")
                    logger.error(f"Сырой ответ: {raw_text[:500]}")
                    await callback.message.edit_text(
                        "Сервер вернул некорректный ответ. Попробуйте позже."
                    )
                    await callback.answer()
                    return

        logger.info(f"Тело ответа бэкенда: {data}")

        if not data.get("success"):
            err = data.get("error", "неизвестная ошибка")
            logger.error(f"Бэкенд отклонил платёж: {data}")
            await callback.message.edit_text(
                f"❌ Не удалось создать платёж: {err}\n\n"
                f"Попробуйте позже или обратитесь в поддержку: @kotshop241_support"
            )
            await callback.answer()
            return

        pay_url = data["payment_url"]
        payment_id = data.get("payment_id", "")
        logger.info(f"Платёж создан: payment_id={payment_id}, payment_url={pay_url}")

    except aiohttp.ClientConnectorError as e:
        logger.error(f"Не удалось подключиться к VPS-бэкенду: {e}")
        logger.error(f"Проверьте VPS_API_URL={VPS_API_URL} и открыт ли порт 8080 на VPS")
        await callback.message.edit_text(
            "❌ Не удалось подключиться к серверу оплаты.\n"
            "Проверьте, что VPS запущен и порт 8080 открыт.\n\n"
            "Поддержка: @kotshop241_support"
        )
        await callback.answer()
        return

    except asyncio.TimeoutError:
        logger.error(f"Таймаут при запросе к VPS-бэкенду (15 сек). URL: {VPS_API_URL}")
        await callback.message.edit_text(
            "❌ Сервер оплаты не ответил вовремя. Попробуйте позже."
        )
        await callback.answer()
        return

    except Exception as e:
        logger.error(f"Непредвиденная ошибка при создании платежа: {e}")
        logger.error(traceback.format_exc())
        await callback.message.edit_text(
            "❌ Произошла ошибка. Попробуйте позже или обратитесь в поддержку: @kotshop241_support"
        )
        await callback.answer()
        return

    b = InlineKeyboardBuilder()
    b.button(text="Оплатить 79 ₽", url=pay_url)
    b.adjust(1)

    payment_msg = await callback.message.edit_text(
        f"Заказ #{order_id}\n"
        f"Товар: 60 UC\n"
        f"Ваш ID: {game_id}\n"
        f"Сумма: 79 ₽\n\n"
        f"Нажмите «Оплатить», чтобы завершить покупку.",
        reply_markup=b.as_markup()
    )

    pending_payments[order_id] = {
        "user_id": user_id,
        "chat_id": callback.message.chat.id,
        "message_id": payment_msg.message_id,
        "game_id": game_id,
        "product_name": "60 UC",
        "payment_id": payment_id,
        "amount_kopecks": amount_kopecks,
        "created_at": time.time(),
        "payment_url": pay_url,
    }
    save_pending_to_file()
    logger.info(f"Платёж {order_id} (payment_id={payment_id}) добавлен в очередь мониторинга")

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


# ─── Глобальный обработчик ошибок ───
@dp.error()
async def on_error(event, exception):
    logger.error(f"Необработанная ошибка в хендлере: {exception}")
    logger.error(traceback.format_exc())
    return True


# ─── Main ───
async def main():
    logger.info("BotHost бот запущен")
    logger.info(f"VPS_API_URL = {VPS_API_URL}")

    load_pending_from_file()

    asyncio.create_task(check_payments_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
