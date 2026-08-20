import asyncio
import os
import hashlib
import hmac
import uuid
import sqlite3
from datetime import datetime

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TBANK_TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY")
TBANK_PASSWORD = os.getenv("TBANK_PASSWORD")
FAZER_API_KEY = os.getenv("FAZER_API_KEY")
DB_PATH = os.getenv("DB_PATH", "kotshop.db")

if not all([BOT_TOKEN, TBANK_TERMINAL_KEY, TBANK_PASSWORD]):
    raise ValueError("Не заданы переменные окружения")

API_URL = "https://securepay.tinkoff.ru/v2"
FAZER_API_URL = "https://api.fzr.cards/api/v2"

PUBG_CATEGORY_ID = "pubg_mobile_fast"
PUBG_60UC_OFFER_ID = "60_uc"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class OrderFlow(StatesGroup):
    waiting_for_id = State()


def _db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db_sync():
    conn = _db_connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            payment_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            amount_kopecks INTEGER NOT NULL,
            game_id TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            fazer_order_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS user_game_ids (
            user_id INTEGER PRIMARY KEY,
            game_id TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def _save_order_sync(payment_id, order_id, user_id, amount_kopecks, game_id=None):
    now = datetime.utcnow().isoformat()
    conn = _db_connect()
    try:
        conn.execute(
            "INSERT INTO orders (payment_id, order_id, user_id, amount_kopecks, game_id, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (payment_id, order_id, user_id, amount_kopecks, game_id, "new", now, now)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def _get_pending_orders_sync():
    conn = _db_connect()
    rows = conn.execute("SELECT * FROM orders WHERE status IN ('new', 'waiting') ORDER BY created_at ASC").fetchall()
    conn.close()
    return rows


def _update_order_status_sync(payment_id, status):
    now = datetime.utcnow().isoformat()
    conn = _db_connect()
    conn.execute("UPDATE orders SET status = ?, updated_at = ? WHERE payment_id = ?", (status, now, payment_id))
    conn.commit()
    conn.close()


def _update_fazer_order_id_sync(payment_id, fazer_order_id):
    now = datetime.utcnow().isoformat()
    conn = _db_connect()
    conn.execute("UPDATE orders SET fazer_order_id = ?, updated_at = ? WHERE payment_id = ?", (fazer_order_id, now, payment_id))
    conn.commit()
    conn.close()


def _get_delivering_orders_sync():
    conn = _db_connect()
    rows = conn.execute("SELECT * FROM orders WHERE status = 'delivering' AND fazer_order_id IS NOT NULL").fetchall()
    conn.close()
    return rows


def _save_game_id_sync(user_id, game_id):
    now = datetime.utcnow().isoformat()
    conn = _db_connect()
    conn.execute("INSERT OR REPLACE INTO user_game_ids (user_id, game_id, updated_at) VALUES (?, ?, ?)", (user_id, game_id, now))
    conn.commit()
    conn.close()


async def init_db():
    await asyncio.to_thread(_init_db_sync)

async def save_order(payment_id, order_id, user_id, amount_kopecks, game_id=None):
    await asyncio.to_thread(_save_order_sync, payment_id, order_id, user_id, amount_kopecks, game_id)

async def get_pending_orders():
    return await asyncio.to_thread(_get_pending_orders_sync)

async def update_order_status(payment_id, status):
    await asyncio.to_thread(_update_order_status_sync, payment_id, status)

async def update_fazer_order_id(payment_id, fazer_order_id):
    await asyncio.to_thread(_update_fazer_order_id_sync, payment_id, fazer_order_id)

async def get_delivering_orders():
    return await asyncio.to_thread(_get_delivering_orders_sync)

async def save_game_id(user_id, game_id):
    await asyncio.to_thread(_save_game_id_sync, user_id, game_id)


def sign_payload(payload: dict, secret: str) -> str:
    keys = sorted(k for k in payload.keys() if payload[k] is not None)
    pairs = [f"{k}={payload[k]}" for k in keys]
    base_string = "&".join(pairs)
    return hmac.new(secret.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha256).hexdigest()


async def create_payment(order_id: str, amount_kopecks: int, description: str = None) -> dict | None:
    payload = {
        "TerminalKey": TBANK_TERMINAL_KEY,
        "Amount": amount_kopecks,
        "OrderId": order_id,
        "Description": description or f"Покупка: {order_id}",
    }
    token = sign_payload(payload, TBANK_PASSWORD)
    payload["Token"] = token

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_URL}/Init", json=payload) as resp:
            data = await resp.json()
            print(f"[DEBUG] T-Bank Init: {data}")
            if data.get("Success") is True and "PaymentId" in data and "PaymentURL" in data:
                return {"payment_id": str(data["PaymentId"]), "payment_url": data["PaymentURL"]}
            else:
                print("Init error:", data)
                return None


async def check_payment_state(payment_id: str) -> str | None:
    payload = {"TerminalKey": TBANK_TERMINAL_KEY, "PaymentId": payment_id}
    token = sign_payload(payload, TBANK_PASSWORD)
    payload["Token"] = token

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_URL}/GetState", json=payload) as resp:
            data = await resp.json()
            if not data.get("Success"):
                return None
            status = data.get("Status")
            if status in ("NEW", "AUTHORIZED", "WAITING"):
                return "WAITING"
            elif status == "CONFIRMED":
                return "SUCCESS"
            elif status in ("REJECTED", "CANCELED", "DEADLINE_EXPIRED"):
                return "REJECTED"
            return "WAITING"


async def fazer_topup_order(category_id: str, offer_id: str, player_id: str) -> dict | None:
    headers = {"X-API-Key": FAZER_API_KEY, "Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}
    body = {"category_id": category_id, "offer_id": offer_id, "fields": {"player_id": player_id}}
    print(f"[DEBUG] FazerCards request: {body}")
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{FAZER_API_URL}/topups/order", json=body, headers=headers) as resp:
            data = await resp.json()
            print(f"[DEBUG] FazerCards response: {data}")
            if data.get("ok") and "order" in data:
                return data["order"]
            print("FazerCards error:", data)
            return None


async def fazer_check_order(fazer_order_id: str) -> str | None:
    headers = {"X-API-Key": FAZER_API_KEY}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{FAZER_API_URL}/orders/{fazer_order_id}", headers=headers) as resp:
            data = await resp.json()
            if data.get("ok") and "order" in data:
                return data["order"].get("status")
            return None


async def deliver_item(order_id: str, user_id: int, game_id: str, bot: Bot, payment_id: str):
    print(f"[DELIVER] Order {order_id}, user={user_id}, game_id={game_id}")
    print(f"[DEBUG] FAZER_API_KEY={'есть' if FAZER_API_KEY else 'НЕТ!'}")

    order = await fazer_topup_order(PUBG_CATEGORY_ID, PUBG_60UC_OFFER_ID, game_id)
    if not order:
        await bot.send_message(user_id, "❌ Не удалось начислить UC. Свяжитесь с поддержкой: @kotshop241_support")
        return

    fazer_order_id = order.get("id")
    fazer_status = order.get("status", "processing")

    if fazer_order_id:
        await update_fazer_order_id(payment_id, fazer_order_id)

    if fazer_status == "completed":
        await update_order_status(payment_id, "delivered")
        await bot.send_message(user_id, f"✅ 60 UC зачислены!\nID: {game_id}\nЗаказ: {fazer_order_id}")
    elif fazer_status == "processing":
        await update_order_status(payment_id, "delivering")
        await bot.send_message(user_id, f"⏳ Заказ в обработке. UC будут зачислены в течение нескольких минут.\nID: {game_id}\nЗаказ: {fazer_order_id}")
    else:
        await update_order_status(payment_id, "delivering")
        await bot.send_message(user_id, f"📦 Статус: {fazer_status}\nID: {game_id}\nЗаказ: {fazer_order_id}")


async def poll_payments(bot: Bot):
    while True:
        try:
            rows = await get_pending_orders()
            for row in rows:
                payment_id = row["payment_id"]
                order_id = row["order_id"]
                user_id = row["user_id"]
                game_id = row["game_id"]

                status = await check_payment_state(payment_id)
                if status is None:
                    continue

                if status == "SUCCESS":
                    await update_order_status(payment_id, "success")
                    if game_id:
                        await deliver_item(order_id, user_id, game_id, bot, payment_id)
                    else:
                        await bot.send_message(user_id, "✅ Оплата получена, но не удалось определить игровой ID. Свяжитесь с поддержкой.")
                elif status == "REJECTED":
                    await update_order_status(payment_id, "rejected")
                    await bot.send_message(user_id, "❌ Оплата отклонена. Свяжитесь с поддержкой.")
        except Exception as e:
            print("Polling error:", e)
        await asyncio.sleep(10)


async def poll_fazer_orders(bot: Bot):
    while True:
        try:
            rows = await get_delivering_orders()
            for row in rows:
                fazer_status = await fazer_check_order(row["fazer_order_id"])
                if fazer_status == "completed":
                    await update_order_status(row["payment_id"], "delivered")
                    await bot.send_message(row["user_id"], f"✅ 60 UC зачислены!\nID: {row['game_id']}\nЗаказ: {row['fazer_order_id']}")
                elif fazer_status == "failed":
                    await update_order_status(row["payment_id"], "deliver_failed")
                    await bot.send_message(row["user_id"], "❌ Не удалось зачислить UC. Свяжитесь с поддержкой.")
        except Exception as e:
            print("FazerCards polling error:", e)
        await asyncio.sleep(30)


WELCOME_TEXT = (
    "Добро пожаловать в Telegram-бот KotShop241! Мы работаем официально через Т-Банк "
    "и даём возможность быстро и с гарантией пополнить любой сервис из нашего каталога. "
    "Также помогаем находить недоступные игры в Steam для пользователей из РФ."
)

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
    await callback.message.edit_text("📄 Политика компании\n\n(Текст в написании)", reply_markup=kb_start())
    await callback.answer()

@dp.callback_query(F.data == "back_start")
async def cb_back_start(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=kb_start())
    await callback.answer()

@dp.callback_query(F.data == "buy")
async def cb_buy(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите нужную игру или напишите название игры для получения раздела покупки", reply_markup=kb_buy())
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
    await callback.message.edit_text("Выберите удобный способ получения игровой валюты", reply_markup=kb_pubg())
    await callback.answer()

@dp.callback_query(F.data == "back_buy")
async def cb_back_buy(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите нужную игру или напишите название игры для получения раздела покупки", reply_markup=kb_buy())
    await callback.answer()

@dp.callback_query(F.data == "pubg_fixed")
async def cb_pubg_fixed(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите нужное количество игровой валюты на ваш аккаунт с фиксированной суммой, "
        "если не найдёте нужное количество, попробуйте создать заказ (Уникальное кол-во валюты)",
        reply_markup=kb_pubg_fixed())
    await callback.answer()

@dp.callback_query(F.data == "pubg_custom")
async def cb_pubg_custom(callback, state: FSMContext):
    await state.clear()
    await callback.message.answer("Раздел «Уникальное кол-во валюты» в разработке")
    await callback.answer()

@dp.callback_query(F.data == "back_pubg")
async def cb_back_pubg(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите удобный способ получения игровой валюты", reply_markup=kb_pubg())
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
        await message.answer("❌ ID должен состоять только из цифр и начинаться на 5. Попробуйте ещё раз.")
        return
    await save_game_id(message.from_user.id, game_id)
    await state.clear()
    await message.answer(f"Вы выбрали товар 60 UC стоимостью в 79 рублей\nВаш ID: {game_id}", reply_markup=kb_confirm(game_id))

@dp.callback_query(F.data.startswith("confirm_yes"))
async def cb_confirm_yes(callback, state: FSMContext):
    await state.clear()
    game_id = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id
    order_id = f"order-{user_id}-{int(asyncio.get_event_loop().time())}"
    amount_kopecks = 7900

    result = await create_payment(order_id, amount_kopecks, description=f"Покупка 60 UC. ID: {game_id}")
    if not result:
        await callback.message.edit_text("Не удалось создать платёж. Попробуйте позже.")
        await callback.answer()
        return

    payment_id = result["payment_id"]
    pay_url = result["payment_url"]
    await save_order(payment_id, order_id, user_id, amount_kopecks, game_id=game_id)

    b = InlineKeyboardBuilder()
    b.button(text="Оплатить 79 ₽", url=pay_url)
    b.adjust(1)
    await callback.message.edit_text(
        f"Заказ #{order_id}\nТовар: 60 UC\nВаш ID: {game_id}\nСумма: 79 ₽\n\nНажмите «Оплатить».",
        reply_markup=b.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "confirm_noid")
async def cb_confirm_noid(callback, state: FSMContext):
    await state.set_state(OrderFlow.waiting_for_id)
    await callback.message.edit_text("Укажите ваш ID который должен начинаться на 5")
    await callback.answer()

@dp.callback_query(F.data == "confirm_cancel")
async def cb_confirm_cancel(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите удобный способ получения игровой валюты", reply_markup=kb_pubg())
    await callback.answer()

async def main():
    await init_db()
    asyncio.create_task(poll_payments(bot))
    asyncio.create_task(poll_fazer_orders(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
