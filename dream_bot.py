import asyncio
import os
import time
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import Message, CallbackQuery
from dotenv import load_dotenv
from aiohttp import web

load_dotenv()

TOKEN = os.getenv("TOKEN")
REPLICATE_TOKEN = os.getenv("REPLICATE_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

os.makedirs("downloads", exist_ok=True)

# Храним состояния пользователей
user_state = {}  # {user_id: "waiting_photo" / "waiting_prompt" / "processing"}
user_photo = {}  # {user_id: file_path}
user_free = {}   # {user_id: True/False}  True = уже использовал бесплатное фото

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    user_state[user_id] = "waiting_photo"
    await message.answer(
        "👋  Привет! Я умею изменять фото по твоему описанию.\n\n"
        "Отправь мне фото, а затем напиши, что хочешь сделать:\n"
        "— убери фон\n"
        "— добавь закат\n"
        "— преврати в аниме\n"
        "— убери предмет\n"
        "…и многое другое!\n\n"
        "Первое фото — БЕСПЛАТНО! 🎁 "
    )

@dp.message(lambda msg: msg.photo is not None and user_state.get(msg.from_user.id) == "waiting_photo")
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = f"downloads/{user_id}_{int(time.time())}.jpg"
    await bot.download_file(file.file_path, file_path)

    user_photo[user_id] = file_path
    user_state[user_id] = "waiting_prompt"

    await message.answer(
        "📸  Фото сохранено!\n"
        "Теперь напиши текстом, что с ним сделать:"
    )

@dp.message(lambda msg: user_state.get(msg.from_user.id) == "waiting_prompt")
async def handle_prompt(message: types.Message):
    user_id = message.from_user.id
    prompt = message.text

    # Проверяем, бесплатное ли это фото
    is_free = not user_free.get(user_id, False)

    await message.answer("⏳ Генерирую... это займёт 20–40 секунд...")

    # Отправляем запрос в Replicate
    result_url = generate_with_replicate(user_photo[user_id], prompt)

    if result_url:
        await message.answer_photo(result_url, caption="✅ Готово!")
        if is_free:
            user_free[user_id] = True
            await message.answer(
                "🎁  Это было твоё бесплатное фото!\n"
                "Дальше — подписка:\n"
                "🔹  15 фото — 599 ₽/неделя\n"
                "🔹  20 фото — 799 ₽/неделя\n"
                "🔹  Безлимит — 1599 ₽/неделя"
            )
        else:
            # Здесь позже будет списание из подписки
            await message.answer("✅ Фото сгенерировано!")
    else:
        await message.answer("❌ Ошибка генерации. Попробуй другой промт.")

    # Сброс состояния
    user_state[user_id] = "waiting_photo"

def generate_with_replicate(image_path, prompt):
    """Отправляет фото + промт в Replicate, возвращает ссылку на результат"""
    import base64
    
    # Читаем фото и кодируем в base64
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    
    url = "https://api.replicate.com/v1/predictions"
    headers = {
        "Authorization": f"Bearer {REPLICATE_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Используем модель FLUX для редактирования по промпту
    data = {
        "version": "black-forest-labs/flux-dev",
        "input": {
            "prompt": prompt,
            "image": f"data:image/jpeg;base64,{image_data}",
            "num_outputs": 1
        }
    }
    
    response = requests.post(url, headers=headers, json=data)
    
    # Показываем ошибку, если она есть
    if response.status_code != 201:
        print("❌ Ошибка от Replicate:", response.status_code, response.text)
        return None
    
    prediction_id = response.json()["id"]
    print(f"✅ Задача отправлена, ID: {prediction_id}")

    # Ждём результат
    while True:
        time.sleep(3)
        res = requests.get(f"https://api.replicate.com/v1/predictions/{prediction_id}", headers=headers)
        result = res.json()
        status = result.get("status")
        print(f"Статус: {status}")
        
        if status == "succeeded":
            return result["output"][0]
        if status == "failed":
            print("❌ Ошибка:", result.get("error", "Неизвестная ошибка"))
            return None
# -------- НОВЫЙ ВЕБ-СЕРВЕР ДЛЯ ПИНГА --------
async def health_check(request):
    """Просто отвечает 'OK', чтобы Render знал, что бот жив."""
    return web.Response(text="OK")

async def start_web_server():
    """Запускает веб-сервер на порту 8080."""
    app = web.Application()
    app.router.add_get("/", health_check)  # По адресу / будет висеть health_check
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)  # Слушаем все адреса на 8080 порту
    await site.start()
    print("🌐  Веб-сервер для пинга запущен на порту 8080")

async def main():
    print("🚀  DreamBot запущен!")
    # Запускаем бота и веб-сервер одновременно
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())
