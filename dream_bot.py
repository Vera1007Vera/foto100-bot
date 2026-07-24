import asyncio
import os
import time
import requests
import base64
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import Message, CallbackQuery
from aiohttp import web

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

# ===== СТАРТ =====
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
        "👨‍👧 Совмещать два фото в одну сцену\n\n"
        "Выбери услугу в меню ниже:",
        reply_markup=menu_keyboard
    )

# ===== ВЫБОР УСЛУГИ =====
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

# ===== ОБРАБОТКА ФОТО =====
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

    # ===== СОВМЕЩЕНИЕ 2 ФОТО =====
    if action == "👨‍👧 Совместить 2 фото":
        if len(user_data[user_id]["photos"]) == 1:
            await message.answer("✅ Первое фото сохранено! Теперь отправь **второе фото** (взрослого):")
            return
        elif len(user_data[user_id]["photos"]) == 2:
            await message.answer("⏳ Объединяю два фото в одну сцену... (30–60 секунд)")
            result = call_replicate_merge(
                user_data[user_id]["photos"][0],
                user_data[user_id]["photos"][1]
            )
            user_data[user_id]["photos"] = []
            user_data[user_id]["action"] = None
            if result:
                await message.answer_photo(result, caption="✅ Готово! 👨‍👧")
            else:
                await message.answer("❌ Ошибка объединения. Попробуй ещё раз.")
            return

    # ===== АНИМЕ / ПЛЁНКА =====
    if action in ["🎨 Аниме", "🎞️ Плёнка"]:
        await message.answer("⏳ Генерирую... (20–40 секунд)")
        prompt_map = {
            "🎨 Аниме": "anime style, studio ghibli, vibrant colors, detailed line art, beautiful portrait, keep the person's face exactly the same, identity preservation",
            "🎞️ Плёнка": "film photo style, kodak portra 400, vintage colors, film grain, nostalgic, warm tones, retro aesthetic, keep the person's face exactly the same, identity preservation"
        }
        prompt = prompt_map.get(action, "beautiful portrait")
        result = call_replicate(file_path, prompt)
        if result:
            await message.answer_photo(result, caption="✅ Готово!")
            await check_free_and_offer_subscription(message)
        else:
            await message.answer("❌ Ошибка генерации. Попробуй другой промт.")
    
    # ===== РЕТУШЬ =====
    elif action == "✨ Ретушь лица":
        await message.answer("Выбери уровень ретуши:", reply_markup=get_retouch_keyboard())

# ===== КНОПКИ РЕТУШИ =====
def get_retouch_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👶 30%", callback_data="retouch_30")],
        [InlineKeyboardButton(text="🌟 50%", callback_data="retouch_50")],
        [InlineKeyboardButton(text="🔥 80%", callback_data="retouch_80")],
        [InlineKeyboardButton(text="💎 100%", callback_data="retouch_100")]
    ])

@dp.callback_query(lambda call: call.data.startswith("retouch_"))
async def handle_retouch(call: CallbackQuery):
    user_id = call.from_user.id
    level = call.data.split("_")[1]
    file_path = user_data[user_id]["photos"][-1]
    
    await call.message.answer(f"⏳ Ретушь {level}%... (20–40 секунд)")
    result = call_replicate_retouch(file_path, level)
    
    if result:
        await call.message.answer_photo(result, caption=f"✅ Ретушь {level}% готова!")
    else:
        await call.message.answer("❌ Ошибка ретуши. Попробуй другое фото.")
    
    user_data[user_id]["photos"] = []
    user_data[user_id]["action"] = None

# ===== БЕСПЛАТНО / ПЛАТНО =====
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

# ===== ТАРИФЫ =====
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

# ===== ПОМОЩЬ =====
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

# ===== ГЕНЕРАЦИЯ ЧЕРЕЗ REPLICATE (АНИМЕ / ПЛЁНКА) =====
def call_replicate(image_path, prompt):
    try:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        url = "https://api.replicate.com/v1/predictions"
        headers = {
            "Authorization": f"Bearer {REPLICATE_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "version": "black-forest-labs/flux-dev",
            "input": {
                "prompt": prompt,
                "image": f"data:image/jpeg;base64,{image_data}",
                "num_outputs": 1,
                "strength": 0.5
            }
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 201:
            print("Ошибка Replicate:", response.status_code, response.text)
            return None
        
        prediction_id = response.json()["id"]
        while True:
            time.sleep(3)
            res = requests.get(f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers)
            result = res.json()
            if result.get("status") == "succeeded":
                return result["output"][0]
            if result.get("status") == "failed":
                print("Ошибка генерации:", result.get("error"))
                return None
    except Exception as e:
        print("Исключение:", e)
        return None

# ===== РЕТУШЬ ЧЕРЕЗ CODEFORMER =====
def call_replicate_retouch(image_path, level):
    try:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        url = "https://api.replicate.com/v1/predictions"
        headers = {
            "Authorization": f"Bearer {REPLICATE_TOKEN}",
            "Content-Type": "application/json"
        }
        
        strength = int(level) / 100
        
        data = {
            "version": "sczhou/codeformer:7de2ea26c616d5a6f7a2bd8be49d12d2c7a602e2d4ff1c06dfd96e9231f12d5e",
            "input": {
                "image": f"data:image/jpeg;base64,{image_data}",
                "codeformer_fidelity": strength,
                "face_upsample": True,
                "background_upsample": True
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 201:
            print("Ошибка CodeFormer:", response.status_code, response.text)
            return None
        
        prediction_id = response.json()["id"]
        while True:
            time.sleep(3)
            res = requests.get(f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers)
            result = res.json()
            if result.get("status") == "succeeded":
                return result["output"]
            if result.get("status") == "failed":
                print("Ошибка ретуши:", result.get("error"))
                return None
    except Exception as e:
        print("Исключение в ретуши:", e)
        return None

# ===== СОВМЕЩЕНИЕ 2 ФОТО В ОДНУ СЦЕНУ =====
def call_replicate_merge(image1_path, image2_path):
    try:
        with open(image1_path, "rb") as f:
            img1_data = base64.b64encode(f.read()).decode("utf-8")
        with open(image2_path, "rb") as f:
            img2_data = base64.b64encode(f.read()).decode("utf-8")
        
        url = "https://api.replicate.com/v1/predictions"
        headers = {
            "Authorization": f"Bearer {REPLICATE_TOKEN}",
            "Content-Type": "application/json"
        }
        
        prompt = (
            "A heartwarming scene where an adult is squatting and holding a birthday cake, "
            "and a young child is blowing out the candles. Both are looking at each other with love. "
            "The adult is smiling, the child is happy. The atmosphere is warm and festive. "
            "Realistic, high quality, 8k, emotional moment. "
            "The adult has the same face as in the first image. "
            "The child has the same face as in the second image. "
            "Accurate facial features, identity preservation."
        )
        
        data = {
            "version": "black-forest-labs/flux-dev",
            "input": {
                "prompt": prompt,
                "image": f"data:image/jpeg;base64,{img1_data}",
                "image2": f"data:image/jpeg;base64,{img2_data}",
                "num_outputs": 1,
                "strength": 0.6
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 201:
            print("Ошибка Replicate:", response.status_code, response.text)
            return None
        
        prediction_id = response.json()["id"]
        while True:
            time.sleep(3)
            res = requests.get(f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers)
            result = res.json()
            if result.get("status") == "succeeded":
                return result["output"][0]
            if result.get("status") == "failed":
                print("Ошибка генерации:", result.get("error"))
                return None
    except Exception as e:
        print("Исключение в объединении:", e)
        return None

# ===== ВЕБ-СЕРВЕР ДЛЯ RENDER =====
async def health_check(request):
    return web.Response(text="OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print("🌐 Веб-сервер запущен на порту 8080")

# ===== ЗАПУСК =====
async def main():
    print("🚀 DreamBot с реальной генерацией запущен!")
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())
