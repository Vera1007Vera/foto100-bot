import asyncio
import os
import time
import sqlite3
import random
from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiohttp import web
from dotenv import load_dotenv

# ===== ПРОВЕРКА НАЛИЧИЯ INSIGHTFACE =====
try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
    print("✅ InsightFace загружен")
except ImportError:
    INSIGHTFACE_AVAILABLE = False
    print("⚠️ InsightFace не установлен, ретушь в упрощённом режиме")

load_dotenv()

TOKEN = os.getenv("TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ===== БАЗА ДАННЫХ =====
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    free_used INTEGER DEFAULT 0,
    balance INTEGER DEFAULT 0,
    visits INTEGER DEFAULT 0
)
""")
conn.commit()

os.makedirs("downloads", exist_ok=True)

# ===== ХРАНИЛИЩЕ СОСТОЯНИЙ =====
user_states = {}

# ===== МЕНЮ =====
menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="▶️ Старт")],
        [KeyboardButton(text="🎨 Аниме"), KeyboardButton(text="🎞️ Плёнка")],
        [KeyboardButton(text="✨ Ретушь лица"), KeyboardButton(text="👨‍👧 Совместить 2 фото")],
        [KeyboardButton(text="🌄 Заменить фон"), KeyboardButton(text="💎 Тарифы")],
        [KeyboardButton(text="📞 Помощь"), KeyboardButton(text="🏠 Главное меню")]
    ],
    resize_keyboard=True
)

# ===== ИНИЦИАЛИЗАЦИЯ INSIGHTFACE =====
face_app = None

def init_face_app():
    global face_app
    if not INSIGHTFACE_AVAILABLE:
        return None
    if face_app is None:
        face_app = FaceAnalysis(name='buffalo_l')
        face_app.prepare(ctx_id=0, det_size=(640, 640))
    return face_app

# ===== СТАРТ =====
@dp.message(Command("start"))
async def start_cmd(message: Message):
    user_id = message.from_user.id
    
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET visits = visits + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    
    user = message.from_user
    if user.username:
        user_name = f"@{user.username}"
    elif user.first_name:
        user_name = user.first_name
    else:
        user_name = "Друг"
    
    cursor.execute("SELECT visits FROM users WHERE user_id=?", (user_id,))
    visits = cursor.fetchone()[0]
    
    welcome_text = f"👋 Привет, {user_name}! Я — AI-фотограф.\n\n"
    
    if visits == 1:
        welcome_text += "🌟 Рад познакомиться! У тебя есть одно бесплатное фото 🎁\n\n"
    else:
        welcome_text += "✨ Рад снова тебя видеть! Что сегодня будем создавать?\n\n"
    
    welcome_text += (
        "Я умею:\n"
        "🎨 Превращать фото в аниме\n"
        "🎞️ Добавлять эффект плёнки\n"
        "✨ Ретушировать лицо\n"
        "🌄 Заменять фон\n"
        "👨‍👧 Совмещать два фото\n\n"
        "Выбери услугу в меню ниже:"
    )
    
    await message.answer(welcome_text, reply_markup=menu_keyboard)

# ===== СТАРТ (КНОПКА) =====
@dp.message(lambda msg: msg.text == "▶️ Старт")
async def start_button(message: Message):
    await start_cmd(message)

# ===== ГЛАВНОЕ МЕНЮ =====
@dp.message(lambda msg: msg.text == "🏠 Главное меню")
async def back_to_menu(message: Message):
    user_id = message.from_user.id
    user_states[user_id] = {}
    
    user = message.from_user
    user_name = user.first_name or "Друг"
    
    await message.answer(
        f"👋 Привет, {user_name}! Возвращаемся в главное меню.\n\n"
        "Выбери услугу:",
        reply_markup=menu_keyboard
    )

# ===== ВЫБОР УСЛУГИ =====
@dp.message(lambda msg: msg.text in ["🎨 Аниме", "🎞️ Плёнка", "✨ Ретушь лица", "👨‍👧 Совместить 2 фото", "🌄 Заменить фон"])
async def handle_service_selection(message: Message):
    user_id = message.from_user.id
    user_states[user_id] = {"action": message.text, "photos": []}
    
    if message.text == "👨‍👧 Совместить 2 фото":
        await message.answer("📸 Отправь **первое фото** (например, детское):")
    elif message.text == "🌄 Заменить фон":
        await message.answer("📸 Отправь фото, у которого нужно заменить фон:")
    else:
        await message.answer("📸 Отправь фото, которое нужно обработать:")

# ===== ОБРАБОТКА ФОТО =====
@dp.message(lambda msg: msg.photo is not None)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    if user_id not in user_states or user_states[user_id].get("action") is None:
        await message.answer("❌ Сначала выбери услугу в меню!")
        return
    
    action = user_states[user_id]["action"]
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = f"downloads/{user_id}_{int(time.time())}.jpg"
    await bot.download_file(file.file_path, file_path)
    user_states[user_id]["photos"].append(file_path)

    # ===== СОВМЕЩЕНИЕ 2 ФОТО =====
    if action == "👨‍👧 Совместить 2 фото":
        if len(user_states[user_id]["photos"]) == 1:
            await message.answer("✅ Первое фото сохранено! Теперь отправь **второе фото** (взрослого):")
            return
        elif len(user_states[user_id]["photos"]) == 2:
            await message.answer("⏳ Объединяю два фото...")
            result = merge_photos(
                user_states[user_id]["photos"][0],
                user_states[user_id]["photos"][1]
            )
            user_states[user_id]["photos"] = []
            user_states[user_id]["action"] = None
            if result:
                await message.answer_photo(FSInputFile(result), caption="✅ Готово! 👨‍👧")
            else:
                await message.answer("❌ Ошибка объединения. Попробуй ещё раз.")
            return

    # ===== АНИМЕ =====
    if action == "🎨 Аниме":
        await message.answer("⏳ Превращаю в аниме... (это может занять 20-40 секунд)")
        result = apply_anime_style(file_path)
        if result:
            await message.answer_photo(FSInputFile(result), caption="✅ Аниме готово!")
            await check_free_and_offer_subscription(message)
        else:
            await message.answer("❌ Ошибка обработки. Попробуй другое фото.")
    
    # ===== ПЛЁНКА =====
    elif action == "🎞️ Плёнка":
        await message.answer("⏳ Применяю эффект плёнки...")
        result = apply_film_effect(file_path)
        if result:
            await message.answer_photo(FSInputFile(result), caption="✅ Плёнка готова!")
            await check_free_and_offer_subscription(message)
        else:
            await message.answer("❌ Ошибка обработки. Попробуй другое фото.")
    
    # ===== РЕТУШЬ =====
    elif action == "✨ Ретушь лица":
        await message.answer("Выбери тип ретуши:", reply_markup=get_retouch_keyboard())
    
    # ===== ЗАМЕНА ФОНА =====
    elif action == "🌄 Заменить фон":
        await message.answer("Выбери новый фон:", reply_markup=get_background_keyboard())

# ===== КНОПКИ РЕТУШИ =====
def get_retouch_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Комбо", callback_data="retouch_combo")],
        [InlineKeyboardButton(text="👶 Тон кожи", callback_data="retouch_skin")],
        [InlineKeyboardButton(text="✨ Сгладить кожу", callback_data="retouch_smooth")],
        [InlineKeyboardButton(text="👁️ Осветлить глаза", callback_data="retouch_eyes")],
        [InlineKeyboardButton(text="🦷 Отбелить зубы", callback_data="retouch_teeth")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])

@dp.callback_query(lambda call: call.data == "menu")
async def back_to_menu_callback(call: CallbackQuery):
    user_id = call.from_user.id
    user_states[user_id] = {}
    await call.message.delete()
    await call.message.answer("Выбери услугу:", reply_markup=menu_keyboard)

@dp.callback_query(lambda call: call.data.startswith("retouch_"))
async def handle_retouch(call: CallbackQuery):
    user_id = call.from_user.id
    action = call.data.split("_")[1]
    
    if user_id not in user_states or not user_states[user_id].get("photos"):
        await call.message.answer("❌ Не найдено фото для ретуши. Попробуй заново.")
        return
    
    file_path = user_states[user_id]["photos"][-1]
    await call.message.answer("⏳ Обработка...")
    
    if action == "combo":
        result = retouch_combo(file_path)
        caption = "✅ Комбо-ретушь готова! ✨"
    elif action == "skin":
        result = retouch_skin_tone(file_path)
        caption = "✅ Тон кожи выровнен!"
    elif action == "smooth":
        result = retouch_smooth_skin(file_path)
        caption = "✅ Кожа сглажена!"
    elif action == "eyes":
        result = retouch_eyes(file_path)
        caption = "✅ Глаза осветлены!"
    elif action == "teeth":
        result = retouch_teeth(file_path)
        caption = "✅ Зубы отбелены!"
    else:
        await call.message.answer("❌ Неизвестное действие.")
        return
    
    if result:
        await call.message.answer_photo(FSInputFile(result), caption=caption)
    else:
        await call.message.answer("❌ Ошибка обработки. Попробуй другое фото.")
    
    user_states[user_id]["photos"] = []
    user_states[user_id]["action"] = None

# ===== КНОПКИ ЗАМЕНЫ ФОНА =====
def get_background_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬜ Белый", callback_data="bg_white")],
        [InlineKeyboardButton(text="🔄 Прозрачный", callback_data="bg_transparent")],
        [InlineKeyboardButton(text="🌿 Природа", callback_data="bg_nature")],
        [InlineKeyboardButton(text="📸 Студия", callback_data="bg_studio")],
        [InlineKeyboardButton(text="🌈 Градиент", callback_data="bg_gradient")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])

@dp.callback_query(lambda call: call.data.startswith("bg_"))
async def handle_background(call: CallbackQuery):
    user_id = call.from_user.id
    bg_type = call.data.split("_")[1]
    
    if user_id not in user_states or not user_states[user_id].get("photos"):
        await call.message.answer("❌ Сначала отправь фото!")
        return
    
    file_path = user_states[user_id]["photos"][-1]
    await call.message.answer("⏳ Заменяю фон...")
    
    result = change_background(file_path, bg_type)
    
    if result:
        await call.message.answer_photo(FSInputFile(result), caption="✅ Фон заменён!")
    else:
        await call.message.answer("❌ Ошибка. Попробуй другое фото.")
    
    user_states[user_id]["photos"] = []
    user_states[user_id]["action"] = None

# ===== БЕСПЛАТНО / ПЛАТНО =====
async def check_free_and_offer_subscription(message: Message):
    user_id = message.from_user.id
    cursor.execute("SELECT free_used FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    
    if result and not result[0]:
        cursor.execute("UPDATE users SET free_used=1 WHERE user_id=?", (user_id,))
        conn.commit()
        await message.answer(
            "🎁 Это было твоё бесплатное фото!\n\n"
            "💎 Наши тарифы:\n"
            "🎨 Аниме / 🎞️ Плёнка — 15 фото: 499 ₽\n"
            "✨ Ретушь — 5 фото: 399 ₽\n"
            "🌄 Замена фона — 5 фото: 399 ₽\n"
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
        "🌄 Замена фона\n"
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
        "3. Для ретуши выбери тип\n"
        "4. Для замены фона выбери фон\n"
        "5. Для совмещения — отправь два фото\n\n"
        "Первое фото для Аниме и Плёнки — бесплатно!"
    )

# ===== ЛОКАЛЬНЫЕ ФУНКЦИИ =====

def retouch_face(image_path, level):
    """Ретушь лица"""
    if not INSIGHTFACE_AVAILABLE:
        return retouch_face_simple(image_path, level)
    try:
        app = init_face_app()
        img = cv2.imread(image_path)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        faces = app.get(img_rgb)
        if len(faces) == 0:
            return retouch_face_simple(image_path, level)
        face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        x1, y1, x2, y2 = face.bbox.astype(int)
        strength = int(level) / 100
        face_region = img_rgb[y1:y2, x1:x2]
        kernel_size = int(21 * strength) + 1
        if kernel_size % 2 == 0:
            kernel_size += 1
        blurred = cv2.bilateralFilter(face_region, kernel_size, 75, 75)
        result_face = cv2.addWeighted(face_region, 1 - strength * 0.7, blurred, strength * 0.7, 0)
        result = img_rgb.copy()
        result[y1:y2, x1:x2] = result_face
        result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
        output_path = image_path.replace(".jpg", f"_retouched_{level}.jpg")
        cv2.imwrite(output_path, result_bgr)
        return output_path
    except Exception as e:
        print("Ошибка ретуши:", e)
        return retouch_face_simple(image_path, level)

def retouch_face_simple(image_path, level):
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None
        strength = int(level) / 100
        kernel_size = int(21 * strength) + 1
        if kernel_size % 2 == 0:
            kernel_size += 1
        blurred = cv2.GaussianBlur(img, (kernel_size, kernel_size), 0)
        result = cv2.addWeighted(img, 1 - strength * 0.7, blurred, strength * 0.7, 0)
        output_path = image_path.replace(".jpg", f"_retouched_{level}.jpg")
        cv2.imwrite(output_path, result)
        return output_path
    except Exception as e:
        print("Ошибка simple_retouch:", e)
        return None

def retouch_skin_tone(image_path):
    try:
        img = cv2.imread(image_path)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        lab = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        a = cv2.addWeighted(a, 0.7, np.zeros_like(a), 0.3, 0)
        b = cv2.addWeighted(b, 0.8, np.zeros_like(b), 0.2, 0)
        lab = cv2.merge((l, a, b))
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
        output_path = image_path.replace(".jpg", "_skin_toned.jpg")
        cv2.imwrite(output_path, result_bgr)
        return output_path
    except Exception as e:
        print("Ошибка тона кожи:", e)
        return None

def retouch_smooth_skin(image_path):
    try:
        img = cv2.imread(image_path)
        result = cv2.bilateralFilter(img, 9, 75, 75)
        kernel = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]])
        result = cv2.filter2D(result, -1, kernel)
        output_path = image_path.replace(".jpg", "_smoothed.jpg")
        cv2.imwrite(output_path, result)
        return output_path
    except Exception as e:
        print("Ошибка сглаживания:", e)
        return None

def retouch_eyes(image_path):
    try:
        img = cv2.imread(image_path)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        app = init_face_app()
        if app is None:
            return None
        faces = app.get(img_rgb)
        if len(faces) == 0:
            return None
        face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        landmarks = face.landmark_2d_106
        left_eye = landmarks[90:103].mean(axis=0)
        right_eye = landmarks[60:73].mean(axis=0)
        result = img_rgb.copy()
        for eye in [left_eye, right_eye]:
            x, y = int(eye[0]), int(eye[1])
            r = 20
            eye_region = result[y-r:y+r, x-r:x+r]
            eye_region = cv2.convertScaleAbs(eye_region, alpha=1.2, beta=15)
            result[y-r:y+r, x-r:x+r] = eye_region
        result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
        output_path = image_path.replace(".jpg", "_eyes.jpg")
        cv2.imwrite(output_path, result_bgr)
        return output_path
    except Exception as e:
        print("Ошибка глаз:", e)
        return None

def retouch_teeth(image_path):
    try:
        img = cv2.imread(image_path)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hsv[:, :, 2] = cv2.addWeighted(hsv[:, :, 2], 1.1, np.zeros_like(hsv[:, :, 2]), 0, 20)
        result = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        output_path = image_path.replace(".jpg", "_teeth.jpg")
        cv2.imwrite(output_path, result)
        return output_path
    except Exception as e:
        print("Ошибка отбеливания:", e)
        return None

def retouch_combo(image_path):
    try:
        img = cv2.imread(image_path)
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        result = img_rgb.copy()
        lab = cv2.cvtColor(result, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        a = cv2.addWeighted(a, 0.7, np.zeros_like(a), 0.3, 0)
        b = cv2.addWeighted(b, 0.8, np.zeros_like(b), 0.2, 0)
        lab = cv2.merge((l, a, b))
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        result = cv2.bilateralFilter(result, 9, 75, 75)
        app = init_face_app()
        if app is not None:
            faces = app.get(result)
            if len(faces) > 0:
                face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
                landmarks = face.landmark_2d_106
                left_eye = landmarks[90:103].mean(axis=0)
                right_eye = landmarks[60:73].mean(axis=0)
                for eye in [left_eye, right_eye]:
                    x, y = int(eye[0]), int(eye[1])
                    r = 20
                    eye_region = result[y-r:y+r, x-r:x+r]
                    eye_region = cv2.convertScaleAbs(eye_region, alpha=1.2, beta=15)
                    result[y-r:y+r, x-r:x+r] = eye_region
        result_hsv = cv2.cvtColor(result, cv2.COLOR_RGB2HSV)
        result_hsv[:, :, 2] = cv2.addWeighted(result_hsv[:, :, 2], 1.1, np.zeros_like(result_hsv[:, :, 2]), 0, 20)
        result = cv2.cvtColor(result_hsv, cv2.COLOR_HSV2RGB)
        result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)
        output_path = image_path.replace(".jpg", "_combo.jpg")
        cv2.imwrite(output_path, result_bgr)
        return output_path
    except Exception as e:
        print("Ошибка комбо:", e)
        return None

def apply_anime_style(image_path):
    """Улучшенный аниме-стиль через OpenCV"""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 1.3, 0, 255).astype(np.uint8)
        img = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        img = cv2.bilateralFilter(img, 9, 75, 75)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edges = cv2.dilate(edges, None, iterations=1)
        edges = cv2.bitwise_not(edges)
        edges_3ch = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        result = cv2.addWeighted(img, 0.75, edges_3ch, 0.25, 0)
        lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        lab = cv2.merge((l, a, b))
        result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        result = cv2.stylization(result, sigma_s=60, sigma_r=0.6)
        output_path = image_path.replace(".jpg", "_anime.jpg")
        cv2.imwrite(output_path, result)
        return output_path
    except Exception as e:
        print("Ошибка аниме:", e)
        return None

def apply_film_effect(image_path):
    try:
        img = Image.open(image_path).convert("RGB")
        r, g, b = img.split()
        r = r.point(lambda i: i * 1.08)
        g = g.point(lambda i: i * 0.97)
        b = b.point(lambda i: i * 0.88)
        img = Image.merge("RGB", (r, g, b))
        img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.2)
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.15)
        width, height = img.size
        vignette = Image.new("L", (width, height), 0)
        for x in range(width):
            for y in range(height):
                dx = (x - width/2) / (width/2)
                dy = (y - height/2) / (height/2)
                distance = (dx*dx + dy*dy) ** 0.5
                value = max(0, min(255, int(255 * (1 - distance * 0.35))))
                vignette.putpixel((x, y), value)
        img_r, img_g, img_b = img.split()
        img_r = Image.composite(img_r, Image.new("L", (width, height), 0), vignette)
        img_g = Image.composite(img_g, Image.new("L", (width, height), 0), vignette)
        img_b = Image.composite(img_b, Image.new("L", (width, height), 0), vignette)
        img = Image.merge("RGB", (img_r, img_g, img_b))
        pixels = img.load()
        for i in range(width):
            for j in range(height):
                noise = random.randint(-15, 15)
                r, g, b = pixels[i, j]
                pixels[i, j] = (min(255, max(0, r + noise)), min(255, max(0, g + noise)), min(255, max(0, b + noise)))
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(1.02)
        output_path = image_path.replace(".jpg", "_film.jpg")
        img.save(output_path)
        return output_path
    except Exception as e:
        print("Ошибка плёнки:", e)
        return None

def merge_photos(image1_path, image2_path):
    try:
        img1 = Image.open(image1_path)
        img2 = Image.open(image2_path)
        height = min(img1.height, img2.height)
        img1 = img1.resize((int(img1.width * height / img1.height), height))
        img2 = img2.resize((int(img2.width * height / img2.height), height))
        total_width = img1.width + img2.width + 20
        new_img = Image.new('RGB', (total_width, height), (255, 255, 255))
        new_img.paste(img1, (0, 0))
        new_img.paste(img2, (img1.width + 20, 0))
        output_path = image1_path.replace(".jpg", "_merged.jpg")
        new_img.save(output_path)
        return output_path
    except Exception as e:
        print("Ошибка объединения:", e)
        return None

def change_background(image_path, background_type="white"):
    try:
        from rembg import remove
        with open(image_path, "rb") as f:
            input_data = f.read()
        output_data = remove(input_data)
        no_bg_path = image_path.replace(".jpg", "_nobg.png")
        with open(no_bg_path, "wb") as f:
            f.write(output_data)
        obj = Image.open(no_bg_path).convert("RGBA")
        width, height = obj.size
        if background_type == "white":
            bg = Image.new("RGB", (width, height), (255, 255, 255))
        elif background_type == "transparent":
            bg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        elif background_type == "nature":
            bg = Image.new("RGB", (width, height), (120, 200, 80))
            for x in range(width):
                for y in range(height):
                    r = 80 + (y / height) * 100
                    g = 180 + (y / height) * 60
                    b = 60 + (y / height) * 40
                    bg.putpixel((x, y), (int(r), int(g), int(b)))
        elif background_type == "studio":
            bg = Image.new("RGB", (width, height), (200, 200, 200))
            for x in range(width):
                for y in range(height):
                    value = 180 + (x / width) * 60
                    bg.putpixel((x, y), (int(value), int(value), int(value)))
        elif background_type == "gradient":
            bg = Image.new("RGB", (width, height), (200, 200, 200))
            for x in range(width):
                for y in range(height):
                    r = 150 + (x / width) * 100
                    g = 50 + (y / height) * 100
                    b = 200 - (x / width) * 80
                    bg.putpixel((x, y), (int(r), int(g), int(b)))
        else:
            bg = Image.new("RGB", (width, height), (255, 255, 255))
        bg.paste(obj, (0, 0), obj)
        output_path = image_path.replace(".jpg", f"_bg_{background_type}.png")
        bg.save(output_path)
        os.remove(no_bg_path)
        return output_path
    except Exception as e:
        print("Ошибка замены фона:", e)
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
    print("🚀 DreamBot запущен!")
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())
