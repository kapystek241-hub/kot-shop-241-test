import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()

def get_conn():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 5432)),
        cursor_factory=RealDictCursor
    )

def create_order(user_id, product, amount):
    import uuid
    ext_id = f"ord-{uuid.uuid4().hex[:10]}"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO orders (telegram_user_id, product_name, amount_rub, external_order_id, status)
                VALUES (%s, %s, %s, %s, 'pending')
                RETURNING *
            """, (user_id, product, amount, ext_id))
            row = cur.fetchone()
            conn.commit()
            return row
    finally:
        conn.close()

def update_payment_info(ext_id, tinkoff_id, status, paid_at=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            if paid_at:
                cur.execute("""
                    UPDATE orders SET status = %s, tinkoff_payment_id = %s, paid_at = %s 
                    WHERE external_order_id = %s
                """, (status, tinkoff_id, paid_at, ext_id))
            else:
                cur.execute("""
                    UPDATE orders SET status = %s, tinkoff_payment_id = %s 
                    WHERE external_order_id = %s
                """, (status, tinkoff_id, ext_id))
            conn.commit()
            return cur.rowcount
    finally:
        conn.close()

def get_order_by_ext(ext_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM orders WHERE external_order_id = %s", (ext_id,))
            return cur.fetchone()
    finally:
        conn.close()
