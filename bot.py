import os
import logging
import psycopg2
import schedule
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

# Función para ejecutar el proceso de envío automático en un hilo separado
def start_scheduler(application):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        future = asyncio.run_coroutine_threadsafe(send_daily_savings(application), loop)
        try:
            future.result()  # Bloquea hasta que la tarea se complete
        except Exception as e:
            logging.error(f"❌ Error en el scheduler: {e}")
        time.sleep(60)  # Verificar cada minuto

# Iniciar el bot con la automatización agregada
if __name__ == "__main__":
    logging.info("🚀 Iniciando el bot de ahorro...")
    
    app = Application.builder().token(TOKEN).build()
    
    # Iniciar el hilo de programación de tareas
    scheduler_thread = threading.Thread(target=start_scheduler, args=(app,))
    scheduler_thread.daemon = True
    scheduler_thread.start()

    app.run_polling()