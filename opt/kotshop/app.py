# app.py (на VPS, FastAPI)
import os
import hmac
import hashlib
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
import psycopg2
from psycopg2.extras import RealDictCursor
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Переменные окружения
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
TBANK_TERMINAL_SECRET = os.getenv("TBANK_TERMINAL_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")  # токен бота, чтобы слать уведомления в Telegram

def get_db_conn():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST
    )

def verify_tinkoff_signature(body_str: str, headers: Dict[str, str]) -> bool:
    """
    Проверка подписи вебхука от Т-Банка.
    X-Tinkoff-Signature — это HMAC-SHA256 от тела запроса (raw bytes).
    """
    expected_signature = headers.get("X-Tinkoff-Signature")
    if not expected_signature:
        return False

    computed_signature = hmac.new(
        TBANK_TERMINAL_SECRET.encode("utf-8"),
        body_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_signature, expected_signature)

@app.post("/webhook")
async def tinkoff_webhook(request: Request):
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    headers = dict(request.headers)

    if not verify_tinkoff_signature(body_str, headers):
        logger.warning("Неверная подпись вебхука")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")

    try:
        import json
        data = json.loads(body_str)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    order_id = data.get("OrderId")
    status_val = data.get("Status")  # WAITING_FOR_PAYMENT, AUTHORIZED, REJECTED и т.д.
    payment_id = data.get("PaymentId")
    amount = data.get("Amount")
    message = data.get("Message")

    logger.info(f"Webhook: OrderId={order_id}, Status={status_val}")

    # Обновляем заказ в PostgreSQL
    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Пример таблицы orders: id, order_id, chat_id, status, payment_id, amount, created_at
        cur.execute("""
            UPDATE orders
            SET status = %s, payment_id = %s, amount = %s, updated_at = NOW()
            WHERE order_id = %s
            RETURNING chat_id, status AS old_status
        """, (status_val, payment_id, amount, order_id))
        row = cur.fetchone()
        conn.commit()

        if not row:
            # Заказ не найден — логируем, но не ломаем вебхук (Т-Банк должен получить 200)
            logger.warning(f"OrderId {order_id} не найден в БД")
            return JSONResponse(status_code=200, content={"status": "ok", "note": "order_not_found"})

        chat_id = row["chat_id"]
        old_status = row["old_status"]

        # Если статус изменился на AUTHORIZED — отправляем подтверждение в Telegram
        if status_val == "AUTHORIZED" and old_status != "AUTHORIZED":
            logger.info(f"Оплата подтверждена для chat_id={chat_id}")
            await send_telegram_confirmation(chat_id, order_id, amount)

        return JSONResponse(status_code=200, content={"status": "ok"})
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка обработки вебхука: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})
    finally:
        cur.close()
        conn.close()

async def send_telegram_confirmation(chat_id: int, order_id: str, amount: int):
    """Отправляет сообщение покупателю об успешной оплате"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан — не могу отправить подтверждение в Telegram")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    text = (
        f"✅ Оплата заказа #{order_id} прошла успешно!\n"
        f"Сумма: {amount / 100:.2f} ₽\n\n"
        "Спасибо за покупку! Ваш заказ уже обрабатывается."
    )
    payload = {"chat_id": chat_id, "text": text}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                logger.error(f"Telegram API вернул {resp.status}")
