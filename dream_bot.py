import asyncio
import os
import time
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import Message, CallbackQuery

TOKEN = os.getenv("TOKEN")
REPLICATE_TOKEN = os.getenv("REPLICATE_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

os.makedirs("downloads", exist_ok=True)

user_data = {}

menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🎨 Аниме"), KeyboardButton(text="🎞️ Плёнка")],
        [KeyboardButton(text="✨ Ретушь лица"), KeyboardButton(text="👨‍👧 Совместить 2 фото")],
        [KeyboardButton(text="💎 Тарифы"), KeyboardButton(text="📞 Помощь")]
    ],
    resize_keyboard=True
)

@dp.message(Command("start"))
async def start_cmd(message: Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        user_data[user_id] = {"free_used": False, "balance": 0, "action": None, "photos": []}
    await message.answer(
        "👋 Привет! Я — AI-фотограф.\n\n"
        "Я умею:\n"
        "🎨 Превращать фото в аниме\n"
        "🎞️ Добавлять эффект плёнки\n"
        "✨ Ретушировать лицо (30–100%)\n"
        "👨‍👧 Совмещать два фото\n\n"
        "Выбери услугу в меню ниже:",
        reply_markup=menu_keyboard
    )

@dp.message(lambda msg: msg.text in ["🎨 Аниме", "🎞️ Плёнка", "✨ Ретушь лица", "👨‍👧 Совместить 2 фото"])
async def handle_service_selection(message: Message):
    user_id = message.from_user.id
    action = message.text
    if user_id not in user_data:
        user_data[user_id] = {"free_used": False, "balance": 0, "action": None, "photos": []}
    user_data[user_id]["action"] = action
    user_data[user_id]["photos"] = []
    if action == "👨‍👧 Совместить 2 фото":
        await message.answer("📸 Отправь **первое фото** (например, детское):")
    else:
        await message.answer("📸 Отправь фото, которое нужно обработать:")

@dp.message(lambda msg: msg.photo is not None)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    if user_id not in user_data or user_data[user_id].get("action") is None:
        await message.answer("❌ Сначала выбери услугу в меню!")
        return
    action = user_data[user_id]["action"]
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = f"downloads/{user_id}_{int(time.time())}.jpg"
    await bot.download_file(file.file_path, file_path)
    user_data[user_id]["photos"].append(file_path)

    if action == "👨‍👧 Совместить 2 фото":
        if len(user_data[user_id]["photos"]) == 1:
            await message.answer("✅ Первое фото сохранено! Теперь отправь **второе фото** (взрослого):")
            return
        elif len(user_data[user_id]["photos"]) == 2:
            await message.answer("⏳ Объединяю два фото...")
            await message.answer("✅ Готово! (здесь будет результат)")
            user_data[user_id]["photos"] = []
            user_data[user_id]["action"] = None
            return

    if action in ["🎨 Аниме", "🎞️ Плёнка"]:
        await message.answer("⏳ Генерирую...")
        await message.answer("✅ Готово! (здесь будет фото)")
        await check_free_and_offer_subscription(message)
    elif action == "✨ Ретушь лица":
        await message.answer("Выбери уровень ретуши:", reply_markup=get_retouch_keyboard())

def get_retouch_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👶 30%", callback_data="retouch_30")],
        [InlineKeyboardButton(text="🌟 50%", callback_data="retouch_50")],
        [InlineKeyboardButton(text="🔥 80%", callback_data="retouch_80")],
        [InlineKeyboardButton(text="💎 100%", callback_data="retouch_100")]
    ])

@dp.callback_query(lambda call: call.data.startswith("retouch_"))
async def handle_retouch(call: CallbackQuery):
    level = call.data.split("_")[1]
    await call.message.answer(f"⏳ Ретушь {level}%...")
    await call.message.answer(f"✅ Ретушь {level}% готова!")
    user_data[call.from_user.id]["photos"] = []
    user_data[call.from_user.id]["action"] = None

async def check_free_and_offer_subscription(message: Message):
    user_id = message.from_user.id
    if not user_data[user_id].get("free_used", False):
        user_data[user_id]["free_used"] = True
        await message.answer(
            "🎁 Это было твоё бесплатное фото!\n\n"
            "💎 Наши тарифы:\n"
            "🎨 Аниме / 🎞️ Плёнка — 15 фото: 499 ₽\n"
            "✨ Ретушь — 5 фото: 399 ₽\n"
            "👨‍👧 Совместить — 3 фото: 499 ₽\n"
            "🔥 Комбо (всё сразу) — 15 фото: 899 ₽"
        )
    else:
        await message.answer("💎 Это платное фото. Купи тариф в меню 💎 Тарифы!")

@dp.message(lambda msg: msg.text == "💎 Тарифы")
async def show_tariffs(message: Message):
    await message.answer(
        "💎 Наши тарифы:\n\n"
        "🎨 Аниме / 🎞️ Плёнка\n"
        "15 фото — 499 ₽\n\n"
        "✨ Ретушь лица\n"
        "5 фото — 399 ₽\n\n"
        "👨‍👧 Совместить 2 фото\n"
        "3 фото — 499 ₽\n\n"
        "🔥 Комбо (все услуги)\n"
        "15 фото — 899 ₽\n\n"
        "💳 Оплата будет доступна после 25 июля"
    )

@dp.message(lambda msg: msg.text == "📞 Помощь")
async def help_cmd(message: Message):
    await message.answer(
        "📞 Помощь\n\n"
        "1. Выбери услугу в меню\n"
        "2. Отправь фото\n"
        "3. Для ретуши выбери процент\n"
        "4. Для совмещения — отправь два фото\n\n"
        "Первое фото для Аниме и Плёнки — бесплатно!"
    )

async def main():
    print("🚀 DreamBot (без оплаты) запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
