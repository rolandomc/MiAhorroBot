import os
import logging
import psycopg2
import time
import threading
import random
import asyncio
from datetime import datetime
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext

# Configuración de Logging
logging.basicConfig(level=logging.INFO)

# Obtener las variables de entorno
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

if not TOKEN or not DB_URL:
    raise ValueError("⚠️ ERROR: Las variables de entorno TELEGRAM_BOT_TOKEN o DATABASE_URL no están configuradas.")

# Conectar a PostgreSQL
def connect_db():
    try:
        result = urlparse(DB_URL)
        conn = psycopg2.connect(
            database=result.path[1:],  
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port,
            sslmode="require"
        )
        return conn
    except Exception as e:
        logging.error(f"❌ Error al conectar a la base de datos: {e}")
        return None

# Inicializar la base de datos
def init_db():
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS savings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                date DATE NOT NULL,
                amount INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                user_id BIGINT PRIMARY KEY,
                schedule_time TIME NOT NULL
            );
        ''')
        conn.commit()
        conn.close()
        logging.info("✅ Base de datos inicializada correctamente.")

# Guardar la hora programada en la base de datos en formato TIME
def save_schedule(user_id, schedule_time):
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            formatted_time = datetime.strptime(schedule_time, "%H:%M").time()
            cursor.execute(
                "INSERT INTO scheduled_messages (user_id, schedule_time) VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET schedule_time = EXCLUDED.schedule_time",
                (user_id, formatted_time)
            )
            conn.commit()
            conn.close()
            logging.info(f"✅ Mensajes programados para {user_id} a las {formatted_time}.")
    except Exception as e:
        logging.error(f"❌ Error al guardar la hora programada: {e}")

# Obtener usuarios con horarios programados
def get_scheduled_users():
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, schedule_time FROM scheduled_messages")
        data = cursor.fetchall()
        conn.close()
        return data
    return []

# Obtener número único para ahorro
def get_unique_random_number(user_id):
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT amount FROM savings WHERE user_id = %s ORDER BY date DESC", (user_id,))
        saved_numbers = [x[0] for x in cursor.fetchall()]
        available_numbers = [x for x in range(1, 366) if x not in saved_numbers]
        conn.close()
        return random.choice(available_numbers) if available_numbers else None
    return None

# Guardar ahorro
def save_savings(user_id, amount):
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO savings (user_id, date, amount) VALUES (%s, %s, %s)", 
                       (user_id, datetime.now().date(), amount))
        conn.commit()
        conn.close()
        logging.info(f"✅ Ahorro de {amount} guardado correctamente para el usuario {user_id}.")

# Enviar mensajes automáticos
async def send_daily_savings(application):
    scheduled_users = get_scheduled_users()
    now = datetime.now().strftime("%H:%M")

    logging.info(f"🕒 Verificando mensajes programados... Hora actual: {now}")

    for user_id, schedule_time in scheduled_users:
        if now == schedule_time.strftime("%H:%M"):
            amount = get_unique_random_number(user_id)
            if amount:
                save_savings(user_id, amount)
                await application.bot.send_message(
                    chat_id=user_id,
                    text=f"📢 ¡Hola! Tu número de ahorro de hoy es: *{amount}*\n¡Sigue ahorrando! 💰",
                    parse_mode="Markdown"
                )
                logging.info(f"📤 Mensaje enviado a {user_id} con el número {amount}.")

# Comando /start con el menú original
async def start(update: Update, context: CallbackContext):
    user_id = update.message.chat.id
    keyboard = [
        [InlineKeyboardButton("Programar mensajes diarios", callback_data="programar_mensajes")],
        [InlineKeyboardButton("Generar número ahora", callback_data="generar_numero")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🤖 ¡Bienvenido al Bot de Ahorro!\n\nConfigura tu horario y comienza a recibir números de ahorro diarios.", reply_markup=reply_markup)

# Manejo de botones
async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    if query.data == "programar_mensajes":
        await query.message.reply_text("⏰ Ingresa la hora en formato 24H (ejemplo: 08:00 o 18:30):")
        context.user_data["esperando_hora"] = True

# Capturar horario ingresado por el usuario
async def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    text = update.message.text.strip()

    if context.user_data.get("esperando_hora", False):
        try:
            horario = text.strip()
            save_schedule(chat_id, horario)
            await update.message.reply_text(f"✅ Has programado los mensajes diarios a las {horario}.")
        except ValueError:
            await update.message.reply_text("⚠️ Formato incorrecto. Ingresa la hora en formato HH:MM (ejemplo: 08:00).")
        
        context.user_data["esperando_hora"] = False

# Corrección del scheduler
def start_scheduler(application):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        future = asyncio.run_coroutine_threadsafe(send_daily_savings(application), loop)
        try:
            future.result()  
        except Exception as e:
            logging.error(f"❌ Error en el scheduler: {e}")
        time.sleep(60)

# Iniciar el bot
if __name__ == "__main__":
    logging.info("🚀 Iniciando el bot de ahorro...")
    init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    scheduler_thread = threading.Thread(target=start_scheduler, args=(app,))
    scheduler_thread.daemon = True
    scheduler_thread.start()

    app.run_polling()