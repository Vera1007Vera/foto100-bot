import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import ssl

TOKEN = "8906564302:AAFMPnXvenSWnXwOa-UJFBgU_9e2V2e2FcU"

bot = Bot(token=TOKEN, timeout=60)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привет! Я твой бот! Я работаю! 😊")

async def main():
    print("Бот запущен! Жду команду /start...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
