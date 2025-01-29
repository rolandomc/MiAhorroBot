import os
import logging
import psycopg2
import schedule
import time
import threading
import random
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    raise ValueError("⚠️ ERROR: La variable de entorno DATABASE_URL no está configurada correctamente.")

print(f"🌐 URL de conexión a PostgreSQL: {DB_URL}")


# Configuración de Logging
logging.basicConfig(level=logging.INFO)

# Variables de entorno (Railway las manejará)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

# Conectar a PostgreSQL
def connect_db():
    return psycopg2.connect(DB_URL, sslmode="require")

# Crear la tabla si no existe
def init_db():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS savings (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            amount INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Guardar el monto del día
def save_savings(amount):
    conn = connect_db()
    cursor = conn.cursor()
    date_today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("INSERT INTO savings (date, amount) VALUES (%s, %s)", (date_today, amount))
    conn.commit()
    conn.close()

# Obtener historial de ahorros
def get_savings():
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT date, amount FROM savings ORDER BY date DESC")
    data = cursor.fetchall()
    conn.close()
    return data

# Comando /start
def start(update: Update, context: CallbackContext):
    update.message.reply_text("¡Hola! Soy tu bot de ahorro. Te enviaré un número diario para ahorrar.")

# Comando /historial
def history(update: Update, context: CallbackContext):
    savings = get_savings()
    message = "Historial de ahorro:\n"
    for date, amount in savings:
        message += f"📅 {date}: 💰 {amount}\n"
    update.message.reply_text(message if savings else "Aún no has ahorrado nada.")

# Generar ahorro diario
def daily_savings():
    amount = random.randint(10, 500)
    save_savings(amount)
    updater.bot.send_message(chat_id=os.getenv("TELEGRAM_CHAT_ID"), text=f"💰 Hoy debes ahorrar: {amount} pesos")

# Programar tarea diaria
def schedule_daily_savings():
    schedule.every().day.at("08:00").do(daily_savings)

# Hilo para ejecutar el schedule
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Iniciar el bot
if __name__ == "__main__":
    init_db()
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("historial", history))

    thread = threading.Thread(target=run_scheduler)
    thread.start()

    updater.start_polling()
    updater.idle()
