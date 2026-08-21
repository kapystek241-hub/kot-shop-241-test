# bothost_bot.py — запускается на BotHost
import asyncio
import os
import json
import logging
import traceback
import time

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, StateFilter
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
REVIEW_CHAT_ID = os.getenv("REVIEW_CHAT_ID", "")

if not all([BOT_TOKEN, VPS_API_URL]):
    raise ValueError("Не заданы переменные окружения: BOT_TOKEN, VPS_API_URL")

logger.info(f"VPS_API_URL = {VPS_API_URL}")
logger.info(f"API_SECRET задан: {'да' if API_SECRET != 'change-me' else 'НЕТ (значение по умолчанию!)'}")
logger.info(f"REVIEW_CHAT_ID задан: {'да' if REVIEW_CHAT_ID else 'НЕТ'}")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ─── Каталог товаров ───
PRODUCTS = {
    "60uc":  {"name": "60 UC",  "price": 82,  "amount_kopecks": 8200,  "orders": 1},
    "120uc": {"name": "120 UC", "price": 164, "amount_kopecks": 8200,  "orders": 2},
}


# ─── FSM ───
class OrderFlow(StatesGroup):
    waiting_for_id = State()
    waiting_for_rating = State()
    waiting_for_review_text = State()


# ─── Тексты ───
WELCOME_TEXT = (
    "Добро пожаловать в Telegram-бот KotShop241! Мы работаем официально через Т-Банк "
    "и даём возможность быстро и с гарантией пополнить любой сервис из нашего каталога. "
    "Также помогаем находить недоступные игры в Steam для пользователей из РФ."
)

MENU_TEXT = (
    "Магазин работает круглосуточно, за исключением технических работ. "
    "О проведении технических работ сообщается в группе @KotShop241 — "
    "подпишитесь, чтобы получать актуальную информацию."
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

SUPPORT_TEXT = (
    "Поддержка отвечает в течение 24 часов. Пожалуйста, не дублируйте сообщения — "
    "вместо этого следуйте инструкции ниже.\n\n"
    "1) Если бот не отправил товар, перешлите переписку с ботом в чат поддержки.\n"
    "2) Дождитесь ответа. Если подтвердится, что товар не был отправлен на указанный "
    "вами способ доставки, средства вернут.\n"
    "3) Не нервничайте и не ищите виноватых — просто опишите, что произошло, и укажите "
    "причину, которую вам назвали.\n"
    "4) Объясните ситуацию развёрнуто: что заказывали, когда, каким способом должны были "
    "получить товар и что ответил бот."
)

REVIEW_PROMPT_TEXT = (
    "Оплата прошла успешно, спасибо! 🎉 "
    "Если вам понравился сервис, будем рады вашему отзыву — он помогает нам становиться лучше.💙"
)

REVIEW_RATING_TEXT = (
    "Каждый отзыв — от реального покупателя, который уже получил товар, "
    "и для меня это очень ценно 💛\n\n"
    "Пожалуйста, перед тем как написать отзыв, оцените качество сервиса "
    "от 1 до 10. Просто отправьте число — это поможет мне стать лучше! 🙏"
)

REVIEW_WRITE_TEXT = (
    "Вы можете написать о нашем сервисе всё, что думаете — даже если "
    "хочется позлиться, мы готовы выслушать 🤬 В любом случае каждое "
    "сообщение помогает нам стать лучше, и мы благодарны за любую "
    "обратную связь! 💬"
)

DELIVERY_TEXT = "UC были доставлены на ваш аккаунт ✅"


# ─── Файл для сохранения ожидающих платежей ───
PENDING_FILE = os.getenv("PENDING_FILE", "pending_payments.json")
PAYMENT_TIMEOUT = 600
DELIVERY_TIMEOUT = 1800
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
    b.button(text="Купить UC по ID", callback_data="pubg_buy_uc")
    b.button(text="Другие товары", callback_data="pubg_other")
    b.button(text="Назад", callback_data="back_buy")
    b.adjust(1)
    return b.as_markup()


def kb_pubg_products():
    b = InlineKeyboardBuilder()
    b.button(text="60 UC — 82 ₽", callback_data="pubg_60uc")
    b.button(text="120 UC — 164 ₽", callback_data="pubg_120uc")
    b.button(text="Назад", callback_data="back_pubg")
    b.adjust(1)
    return b.as_markup()


def kb_pubg_other():
    b = InlineKeyboardBuilder()
    b.button(text="Назад", callback_data="back_pubg")
    b.adjust(1)
    return b.as_markup()


def kb_confirm(game_id: str, product_key: str):
    b = InlineKeyboardBuilder()
    b.button(text="Все верно", callback_data=f"confirm_yes:{game_id}:{product_key}")
    b.button(text="Неверный ID", callback_data=f"confirm_noid:{product_key}")
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


def kb_support():
    b = InlineKeyboardBuilder()
    b.button(text="Поддержка", url="https://t.me/KotShop2415")
    b.button(text="Назад", callback_data="back_menu")
    b.adjust(1)
    return b.as_markup()


def kb_review():
    b = InlineKeyboardBuilder()
    b.button(text="Оценить", callback_data="review_start")
    b.button(text="В меню", callback_data="menu")
    b.adjust(1)
    return b.as_markup()


def kb_review_rating():
    b = InlineKeyboardBuilder()
    b.button(text="Написать отзыв", callback_data="review_write")
    b.button(text="Отправить без текста", callback_data="review_send_stars_only")
    b.button(text="Отменить", callback_data="review_cancel")
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


# ─── Запрос статуса доставки к VPS ───
async def vps_check_delivery(order_id: str) -> bool | None:
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{VPS_API_URL}/check-delivery",
                json={
                    "secret": API_SECRET,
                    "order_id": order_id,
                },
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"VPS /check-delivery вернул HTTP {resp.status}: {text[:200]}")
                    return None
                data = await resp.json()
                return bool(data.get("delivered", False))
    except Exception as e:
        logger.error(f"Ошибка запроса статуса доставки {order_id} к VPS: {e}")
        return None


# ─── Отправка отзыва в группу ───
async def send_review_to_group(text: str):
    if not REVIEW_CHAT_ID:
        logger.warning("REVIEW_CHAT_ID не задан — отзыв не отправлен в группу")
        return
    try:
        await bot.send_message(REVIEW_CHAT_ID, text)
        logger.info("Отзыв отправлен в группу отзывов")
    except Exception as e:
        logger.error(f"Не удалось отправить отзыв в группу: {e}")


# ─── Фоновая задача: проверка статуса платежей и доставки ───
async def check_payments_loop():
    logger.info("Запущен цикл проверки платежей (интервал 15 сек, таймаут 600 сек)")
    while True:
        await asyncio.sleep(15)
        now = time.time()
        to_remove = []
        status_changed = False

        for order_id, info in list(pending_payments.items()):
            try:
                status = info.get("status", "paying")

                # ── Проверка оплаты ──
                if status == "paying":
                    if now - info["created_at"] > PAYMENT_TIMEOUT:
                        logger.info(f"Платёж {order_id} истёк по таймауту (10 мин)")
                        await bot.send_message(
                            info["chat_id"],
                            "Похоже, платёж прервался. Ничего страшного — "
                            "просто создайте заказ ещё раз, и сможете оплатить.",
                            reply_markup=kb_back_to_menu(),
                        )
                        await asyncio.sleep(1)
                        try:
                            await bot.delete_message(info["chat_id"], info["message_id"])
                        except Exception as e:
                            logger.warning(f"Не удалось удалить сообщение {info['message_id']}: {e}")
                        to_remove.append(order_id)
                        continue

                    paid = await vps_check_payment(order_id)
                    if paid is None or not paid:
                        continue

                    logger.info(f"Платёж {order_id} подтверждён (VPS: paid=true)")

                    notify_msg = await bot.send_message(info["chat_id"], "Оплата выполнена")
                    await asyncio.sleep(2)
                    try:
                        await notify_msg.delete()
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение «Оплата выполнена»: {e}")

                    await asyncio.sleep(1)
                    try:
                        await bot.delete_message(info["chat_id"], info["message_id"])
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение с ссылкой на оплату: {e}")

                    if "UC" in info.get("product_name", ""):
                        # UC — переводим в режим проверки доставки
                        await bot.send_message(
                            info["chat_id"],
                            "UC поступят на аккаунт в течении 5 минут",
                            reply_markup=kb_back_to_menu(),
                        )
                        info["status"] = "delivering"
                        info["paid_at"] = time.time()
                        status_changed = True
                        logger.info(f"Заказ {order_id} переведён в статус delivering")
                    else:
                        # Не UC — завершаем
                        await bot.send_message(
                            info["chat_id"],
                            "Оплата успешно выполнена.",
                            reply_markup=kb_back_to_menu(),
                        )
                        to_remove.append(order_id)

                # ── Проверка доставки ──
                elif status == "delivering":
                    paid_at = info.get("paid_at", info["created_at"])
                    if now - paid_at > DELIVERY_TIMEOUT:
                        logger.info(f"Доставка {order_id} истекла по таймауту ({DELIVERY_TIMEOUT} сек)")
                        await bot.send_message(
                            info["chat_id"],
                            DELIVERY_TEXT,
                            reply_markup=kb_review(),
                        )
                        to_remove.append(order_id)
                        continue

                    delivered = await vps_check_delivery(order_id)
                    if delivered is None or not delivered:
                        continue

                    logger.info(f"Доставка {order_id} подтверждена (VPS: delivered=true)")
                    await bot.send_message(
                        info["chat_id"],
                        DELIVERY_TEXT,
                        reply_markup=kb_review(),
                    )
                    to_remove.append(order_id)

            except Exception as e:
                logger.error(f"Непредвиденная ошибка при обработке платежа {order_id}: {e}")
                logger.error(traceback.format_exc())
                continue

        if to_remove:
            for order_id in to_remove:
                pending_payments.pop(order_id, None)
        if to_remove or status_changed:
            save_pending_to_file()


# ─── Вспомогательная функция: отправить новое сообщение, затем удалить старое через 1 сек ───
async def answer_and_delete(callback, text, reply_markup=None):
    await callback.message.answer(text, reply_markup=reply_markup)
    await asyncio.sleep(1)
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {callback.message.message_id}: {e}")


# ─── Хендлеры ───
@dp.message(Command("start"))
async def cmd_start(message):
    logger.info(f"/start от user_id={message.from_user.id}, username={message.from_user.username}")
    await message.answer(WELCOME_TEXT, reply_markup=kb_start())


# ── Раздел «Отзыв» (вызывается текстом «Отзыв») ──
@dp.message(F.text == "Отзыв", StateFilter(None))
async def cmd_review(message, state: FSMContext):
    await state.clear()
    await message.answer(REVIEW_PROMPT_TEXT, reply_markup=kb_review())


# ── Меню и навигация ──
@dp.callback_query(F.data == "menu")
async def cb_menu(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, MENU_TEXT, kb_menu())
    await callback.answer()


@dp.callback_query(F.data == "oferta")
async def cb_oferta(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, POLICY_TEXT, kb_policy())
    await callback.answer()


@dp.callback_query(F.data == "back_start")
async def cb_back_start(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, WELCOME_TEXT, kb_start())
    await callback.answer()


@dp.callback_query(F.data == "buy")
async def cb_buy(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(
        callback,
        "Выберите нужную игру или напишите название игры для получения раздела покупки",
        kb_buy(),
    )
    await callback.answer()


@dp.callback_query(F.data == "support")
async def cb_support(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, SUPPORT_TEXT, kb_support())
    await callback.answer()


@dp.callback_query(F.data == "tournament")
async def cb_tournament(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, "🏆 Турнирный раздел в разработке", kb_menu())
    await callback.answer()


@dp.callback_query(F.data == "back_menu")
async def cb_back_menu(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, MENU_TEXT, kb_menu())
    await callback.answer()


# ── PUBG Mobile ──
@dp.callback_query(F.data == "pubg")
async def cb_pubg(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, "Выберите нужный раздел", kb_pubg())
    await callback.answer()


@dp.callback_query(F.data == "back_buy")
async def cb_back_buy(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(
        callback,
        "Выберите нужную игру или напишите название игры для получения раздела покупки",
        kb_buy(),
    )
    await callback.answer()


@dp.callback_query(F.data == "pubg_buy_uc")
async def cb_pubg_buy_uc(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(
        callback,
        "Выберите интересующий товар для игры PUBG Mobile",
        kb_pubg_products(),
    )
    await callback.answer()


@dp.callback_query(F.data == "pubg_other")
async def cb_pubg_other(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(
        callback,
        "На данный момент этот раздел в разработке",
        kb_pubg_other(),
    )
    await callback.answer()


@dp.callback_query(F.data == "back_pubg")
async def cb_back_pubg(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, "Выберите нужный раздел", kb_pubg())
    await callback.answer()


@dp.callback_query(F.data == "pubg_60uc")
async def cb_pubg_60uc(callback, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_id)
    await state.set_data({"product": "60uc"})
    await callback.message.answer("Укажите ваш ID который должен начинаться на 5")
    await asyncio.sleep(1)
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {callback.message.message_id}: {e}")
    await callback.answer()


@dp.callback_query(F.data == "pubg_120uc")
async def cb_pubg_120uc(callback, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_id)
    await state.set_data({"product": "120uc"})
    await callback.message.answer("Укажите ваш ID который должен начинаться на 5")
    await asyncio.sleep(1)
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {callback.message.message_id}: {e}")
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

    data = await state.get_data()
    product_key = data.get("product", "60uc")
    product = PRODUCTS.get(product_key, PRODUCTS["60uc"])

    await state.clear()
    logger.info(f"Получен game_id={game_id} от user_id={message.from_user.id}, product={product_key}")
    await message.answer(
        f"Вы выбрали товар {product['name']} стоимостью в {product['price']} рублей\n"
        f"Ваш ID: {game_id}",
        reply_markup=kb_confirm(game_id, product_key)
    )


@dp.callback_query(F.data.startswith("confirm_yes"))
async def cb_confirm_yes(callback, state: FSMContext):
    await state.clear()
    parts = callback.data.split(":")
    game_id = parts[1]
    product_key = parts[2] if len(parts) > 2 else "60uc"
    product = PRODUCTS.get(product_key, PRODUCTS["60uc"])
    user_id = callback.from_user.id
    num_orders = product["orders"]
    amount_kopecks = product["amount_kopecks"]
    total_price = product["price"]

    logger.info(
        f"Создание платежа: user_id={user_id}, game_id={game_id}, "
        f"product={product_key}, orders={num_orders}, amount_per_order={amount_kopecks}"
    )

    created_orders = []

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for i in range(num_orders):
                order_id = f"order-{user_id}-{int(time.time())}-{i+1}"
                logger.info(f"Создание заказа {i+1}/{num_orders}: order_id={order_id}")

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
                    logger.info(f"Ответ бэкенда (заказ {i+1}): HTTP {resp.status}")
                    try:
                        data = await resp.json()
                    except Exception as e:
                        raw_text = await resp.text()
                        logger.error(f"Не удалось распарсить JSON от бэкенда: {e}")
                        logger.error(f"Сырой ответ: {raw_text[:500]}")
                        await callback.message.answer("Сервер вернул некорректный ответ. Попробуйте позже.")
                        await asyncio.sleep(1)
                        try:
                            await callback.message.delete()
                        except Exception:
                            pass
                        await callback.answer()
                        return

                logger.info(f"Тело ответа бэкенда (заказ {i+1}): {data}")

                if not data.get("success"):
                    err = data.get("error", "неизвестная ошибка")
                    logger.error(f"Бэкенд отклонил платёж (заказ {i+1}): {data}")
                    await callback.message.answer(
                        f"❌ Не удалось создать платёж: {err}\n\n"
                        f"Попробуйте позже или обратитесь в поддержку: @kotshop241_support"
                    )
                    await asyncio.sleep(1)
                    try:
                        await callback.message.delete()
                    except Exception:
                        pass
                    await callback.answer()
                    return

                created_orders.append({
                    "order_id": order_id,
                    "pay_url": data["payment_url"],
                    "payment_id": data.get("payment_id", ""),
                })
                logger.info(f"Заказ {i+1} создан: order_id={order_id}, payment_id={data.get('payment_id', '')}")

    except aiohttp.ClientConnectorError as e:
        logger.error(f"Не удалось подключиться к VPS-бэкенду: {e}")
        logger.error(f"Проверьте VPS_API_URL={VPS_API_URL} и открыт ли порт 8080 на VPS")
        await callback.message.answer(
            "❌ Не удалось подключиться к серверу оплаты.\n"
            "Проверьте, что VPS запущен и порт 8080 открыт.\n\n"
            "Поддержка: @kotshop241_support"
        )
        await asyncio.sleep(1)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()
        return

    except asyncio.TimeoutError:
        logger.error(f"Таймаут при запросе к VPS-бэкенду (15 сек). URL: {VPS_API_URL}")
        await callback.message.answer("❌ Сервер оплаты не ответил вовремя. Попробуйте позже.")
        await asyncio.sleep(1)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()
        return

    except Exception as e:
        logger.error(f"Непредвиденная ошибка при создании платежа: {e}")
        logger.error(traceback.format_exc())
        await callback.message.answer(
            "❌ Произошла ошибка. Попробуйте позже или обратитесь в поддержку: @kotshop241_support"
        )
        await asyncio.sleep(1)
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()
        return

    # Клавиатура с кнопками оплаты
    b = InlineKeyboardBuilder()
    if num_orders == 1:
        b.button(text=f"Оплатить {total_price} ₽", url=created_orders[0]["pay_url"])
    else:
        for i, order in enumerate(created_orders):
            b.button(
                text=f"Оплатить {product['price'] // num_orders} ₽ ({i+1}/{num_orders})",
                url=order["pay_url"],
            )
    b.adjust(1)

    # Текст сообщения
    if num_orders == 1:
        payment_text = (
            f"Заказ #{created_orders[0]['order_id']}\n"
            f"Товар: {product['name']}\n"
            f"Ваш ID: {game_id}\n"
            f"Сумма: {total_price} ₽\n\n"
            f"Нажмите «Оплатить», чтобы завершить покупку."
        )
    else:
        order_ids = ", ".join(f"#{o['order_id']}" for o in created_orders)
        payment_text = (
            f"Заказы: {order_ids}\n"
            f"Товар: {product['name']}\n"
            f"Ваш ID: {game_id}\n"
            f"Сумма: {total_price} ₽ ({num_orders} платежа по {product['price'] // num_orders} ₽)\n\n"
            f"Оплатите оба платежа, чтобы завершить покупку."
        )

    payment_msg = await callback.message.answer(payment_text, reply_markup=b.as_markup())
    await asyncio.sleep(1)
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {callback.message.message_id}: {e}")

    # Сохраняем все заказы в pending
    for order in created_orders:
        pending_payments[order["order_id"]] = {
            "user_id": user_id,
            "chat_id": callback.message.chat.id,
            "message_id": payment_msg.message_id,
            "game_id": game_id,
            "product_name": product["name"],
            "payment_id": order["payment_id"],
            "amount_kopecks": amount_kopecks,
            "created_at": time.time(),
            "payment_url": order["pay_url"],
            "status": "paying",
        }
    save_pending_to_file()
    logger.info(f"Добавлено {len(created_orders)} заказов в очередь мониторинга")

    await callback.answer()


@dp.callback_query(F.data.startswith("confirm_noid"))
async def cb_confirm_noid(callback, state: FSMContext):
    parts = callback.data.split(":")
    product_key = parts[1] if len(parts) > 1 else "60uc"
    await state.set_state(OrderFlow.waiting_for_id)
    await state.set_data({"product": product_key})
    await callback.message.answer("Укажите ваш ID который должен начинаться на 5")
    await asyncio.sleep(1)
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {callback.message.message_id}: {e}")
    await callback.answer()


@dp.callback_query(F.data == "confirm_cancel")
async def cb_confirm_cancel(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, "Выберите нужный раздел", kb_pubg())
    await callback.answer()


# ── Раздел отзывов ──
@dp.callback_query(F.data == "review_start")
async def cb_review_start(callback, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_rating)
    await callback.message.answer(REVIEW_RATING_TEXT)
    await asyncio.sleep(1)
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {callback.message.message_id}: {e}")
    await callback.answer()


@dp.message(OrderFlow.waiting_for_rating)
async def process_rating(message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or not (1 <= int(text) <= 10):
        await message.answer("❌ Пожалуйста, отправьте число от 1 до 10.")
        return

    rating = int(text)
    stars = "⭐" * rating
    await state.set_state(None)
    await state.set_data({"rating": rating})
    await message.answer(
        f"{stars}\n\nЗдесь будет ваш отзыв, напишите его",
        reply_markup=kb_review_rating()
    )


@dp.callback_query(F.data == "review_write")
async def cb_review_write(callback, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_review_text)
    await callback.message.answer(REVIEW_WRITE_TEXT)
    await asyncio.sleep(1)
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {callback.message.message_id}: {e}")
    await callback.answer()


@dp.message(OrderFlow.waiting_for_review_text)
async def process_review_text(message, state: FSMContext):
    data = await state.get_data()
    rating = data.get("rating", 5)
    stars = "⭐" * rating
    review_text = message.text.strip()

    full_review = f"{stars}\n\n{review_text}"
    await send_review_to_group(full_review)

    await state.clear()
    await message.answer("Спасибо за ваш отзыв! 💙", reply_markup=kb_menu())


@dp.callback_query(F.data == "review_send_stars_only")
async def cb_review_send_stars_only(callback, state: FSMContext):
    data = await state.get_data()
    rating = data.get("rating", 5)
    stars = "⭐" * rating

    await send_review_to_group(stars)
    await state.clear()
    await callback.message.answer("Спасибо за вашу оценку! 💙", reply_markup=kb_menu())
    await asyncio.sleep(1)
    try:
        await callback.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {callback.message.message_id}: {e}")
    await callback.answer()


@dp.callback_query(F.data == "review_cancel")
async def cb_review_cancel(callback, state: FSMContext):
    await state.clear()
    await answer_and_delete(callback, MENU_TEXT, kb_menu())
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
    logger.info(f"REVIEW_CHAT_ID = {REVIEW_CHAT_ID if REVIEW_CHAT_ID else '(не задан)'}")

    load_pending_from_file()

    asyncio.create_task(check_payments_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
