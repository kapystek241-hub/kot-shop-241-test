import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Не задан BOT_TOKEN в .env")

CHANNEL_LINK = os.getenv("CHANNEL_LINK", "https://t.me/KotShop241")
SUPPORT_TG = os.getenv("SUPPORT_TG", "t.me/KotShop2415")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "kotshop241@gmail.com")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ТЕКСТЫ ---

TEXT_MAIN_MENU = (
    "Здравствуйте!\n\n"
    "Сейчас бот принимает заявки на пополнение баланса, но автоматическая выдача товара временно недоступна — "
    "мы активно работаем над устранением этой проблемы.\n\n"
    "На данный момент время пополнения в среднем занимает 15 минут.\n"
    "Магазин работает с 7:00 до 23:00 по МСК, просим прощения за неудобства.\n\n"
    f"Актуальную информацию о ходе работ публикуем в нашем Telegram‑канале: {CHANNEL_LINK}\n\n"
    "Благодарим за ваше понимание!"
)

TEXT_OFFER_PART1 = (
    "Все документы, написанные ниже, являются настоящими и могут быть проверены на официальных сайтах РФ.\n\n"
    "ИНН Предпринимателя: 661912653571\n"
    "Оферта заключена с банком Т‑Банк, вся оплата проходит через банк‑посредник Т‑Банк.\n"
    "Комиссии не взимаются при возврате средств на тот же счёт, с которого была произведена оплата, "
    "за исключением комиссии, которую взимает банк в случае перевода (она не учитывается в оплате).\n\n"
)

TEXT_OFFER_PART2 = (
    "Все переводы, оплата и прочие списания, связанные с магазином, являются официальными, "
    "с предоставлением чека в случае, если клиент потребует его предоставить.\n\n"
    "При неверных параметрах, отмене получения товара в случае, когда товар доставлен, "
    "но покупатель требует возврата, магазин может отказаться предоставлять возврат, такое может произойти:\n"
    "- Если товар был доставлен на итоговый аккаунт, предоставленный клиентом.\n"
    "- Если товар частично доставлен или был отправлен с задержкой.\n"
    "- В случае странных транзакций, обходов системы безопасности, взлома или прочих незаконных действий. "
    "Также в этом случае возможна отправка данных в госорганы для обеспечения безопасности магазина "
    "и невиновных клиентов.\n\n"
    "Оскорбления, угрозы жизни прямого характера будут также направлены в госорганы. "
    "Попытки обойти закон РФ, обмануть систему Telegram‑бота для получения выгоды будут рассматриваться как правонарушения.\n\n"
    "В случае неверно указанных данных для предоставления товара, при их отправке на указанные данные "
    "невозможно вернуть средства.\n\n"
    "Вся личная информация не передаётся третьим лицам и не является общедоступной.\n\n"
    f"Официальный аккаунт поддержки магазина KotShop241: {SUPPORT_TG}\n"
    f"Почта: {SUPPORT_EMAIL}"
)

TEXT_CATEGORIES = "На данный момент доступны следующие категории товаров, но список постоянно расширяется:"
TEXT_SUPPORT_WAYS = "Выберите удобный способ связи с нашей поддержкой:"
TEXT_TOURNAMENT = "На данный момент первый турнир от магазина KotShop241 по игре PUBG Mobile откладывается на неопределённый срок."
TEXT_RAFFLE = f"На данный момент не проводится коллаборации. Новости по коллаборациям можно будет найти у нас в Telegram‑канале:\n{CHANNEL_LINK}"
TEXT_PUBG_CHOICE = "Выберите интересующий раздел:"
TEXT_STEAM_CHOICE = "Выберите интересующий раздел:"
TEXT_EMAIL_CONTACT = f"Отправьте форму обращения на почту по адресу: {SUPPORT_EMAIL}"

# --- КЛАВИАТУРЫ ---

def kb_main():
    builder = InlineKeyboardBuilder()
    builder.button(text="Меню", callback_data="menu_main")
    builder.button(text="Оферта", callback_data="offer_part1")
    return builder.as_markup()

def kb_menu_main():
    builder = InlineKeyboardBuilder()
    builder.button(text="Раздел с товаром", callback_data="cat_main")
    builder.button(text="Поддержка", callback_data="support_main")
    builder.button(text="Турнир", callback_data="tournament")
    builder.button(text="Розыгрыш", callback_data="raffle")
    builder.button(text="Назад", callback_data="back_to_start")
    return builder.as_markup()

def kb_categories():
    builder = InlineKeyboardBuilder()
    builder.button(text="PUBG Mobile", callback_data="cat_pubg")
    builder.button(text="Steam РФ", callback_data="cat_steam")
    builder.button(text="Назад", callback_data="back_to_menu")
    return builder.as_markup()

def kb_support_main():
    builder = InlineKeyboardBuilder()
    builder.button(text="Поддержка (Telegram)", url=SUPPORT_TG)
    builder.button(text="Почта", callback_data="support_email")
    builder.button(text="Назад", callback_data="back_to_menu")
    return builder.as_markup()

def kb_back_only():
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data="back_to_cat")
    return builder.as_markup()

def kb_offer_navigation(part: int):
    builder = InlineKeyboardBuilder()
    if part == 1:
        builder.button(text="Далее", callback_data="offer_part2")
    else:
        builder.button(text="Назад", callback_data="offer_part1")
    builder.button(text="В главное меню", callback_data="back_to_start")
    return builder.as_markup()

def kb_email_contact():
    builder = InlineKeyboardBuilder()
    builder.button(text="Назад", callback_data="back_to_support")
    return builder.as_markup()

# --- ХЕНДЛЕРЫ ---

async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None):
    """
    Пытается отредактировать сообщение. Если не получается (например, сообщение слишком старое),
    отправляет новое. Это решает проблему, когда Telegram запрещает редактирование.
    """
    try:
        await callback.message.edit_text(text=text, reply_markup=reply_markup)
    except Exception:
        # Если редактирование невозможно — отправляем новое сообщение
        await callback.message.answer(text=text, reply_markup=reply_markup)

@dp.message(Command("start"))
async def cmd_start(message):
    await message.answer(TEXT_MAIN_MENU, reply_markup=kb_main())

@dp.message(F.text == "Меню")
async def text_menu(message):
    await message.answer(TEXT_MAIN_MENU, reply_markup=kb_menu_main())

@dp.callback_query(F.data == "menu_main")
async def cb_menu_main(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_MAIN_MENU, kb_menu_main())

@dp.callback_query(F.data == "cat_main")
async def cb_cat_main(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_CATEGORIES, kb_categories())

@dp.callback_query(F.data == "cat_pubg")
async def cb_cat_pubg(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_PUBG_CHOICE, kb_back_only())

@dp.callback_query(F.data == "cat_steam")
async def cb_cat_steam(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_STEAM_CHOICE, kb_back_only())

@dp.callback_query(F.data == "support_main")
async def cb_support_main(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_SUPPORT_WAYS, kb_support_main())

@dp.callback_query(F.data == "support_email")
async def cb_support_email(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_EMAIL_CONTACT, kb_email_contact())

@dp.callback_query(F.data == "tournament")
async def cb_tournament(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_TOURNAMENT, kb_back_only())

@dp.callback_query(F.data == "raffle")
async def cb_raffle(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_RAFFLE, kb_back_only())

# Навигация «Назад»
@dp.callback_query(F.data == "back_to_start")
async def cb_back_to_start(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_MAIN_MENU, kb_main())

@dp.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_MAIN_MENU, kb_menu_main())

@dp.callback_query(F.data == "back_to_cat")
async def cb_back_to_cat(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_CATEGORIES, kb_categories())

@dp.callback_query(F.data == "back_to_support")
async def cb_back_to_support(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_SUPPORT_WAYS, kb_support_main())

# Оферта (2 части)
@dp.callback_query(F.data == "offer_part1")
async def cb_offer_part1(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_OFFER_PART1, kb_offer_navigation(1))

@dp.callback_query(F.data == "offer_part2")
async def cb_offer_part2(callback: CallbackQuery):
    await safe_edit_message(callback, TEXT_OFFER_PART2, kb_offer_navigation(2))

# Запуск
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
