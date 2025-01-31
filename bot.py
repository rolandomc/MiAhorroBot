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
        logging.info("✅ Conectado a la base de datos correctamente.")
        return conn
    except Exception as e:
        logging.error(f"❌ Error al conectar a la base de datos: {e}")
        return None

# Inicializar la base de datos
def init_db():
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS savings (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    date DATE NOT NULL,
                    amount INTEGER NOT NULL
                )
            ''')
            conn.commit()
            conn.close()
            logging.info("✅ Base de datos inicializada correctamente.")
    except Exception as e:
        logging.error(f"❌ Error al inicializar la base de datos: {e}")

# Obtener total ahorrado y número de días ahorrados
def get_savings_summary(user_id):
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM savings WHERE user_id = %s", (user_id,))
            total, days_saved = cursor.fetchone()
            conn.close()
            return total, days_saved
    except Exception as e:
        logging.error(f"❌ Error al obtener ahorros: {e}")
        return 0, 0

# Obtener números guardados por usuario
def get_savings(user_id):
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT amount FROM savings WHERE user_id = %s ORDER BY date DESC", (user_id,))
            data = cursor.fetchall()
            conn.close()
            return [x[0] for x in data]
    except Exception as e:
        logging.error(f"❌ Error al obtener ahorros del usuario {user_id}: {e}")
        return []

# Generar un número aleatorio único
def get_unique_random_number(user_id):
    saved_numbers = get_savings(user_id)
    available_numbers = [x for x in range(1, 366) if x not in saved_numbers]
    return random.choice(available_numbers) if available_numbers else None

# Guardar número en la base de datos
def save_savings(user_id, amount):
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO savings (user_id, date, amount) VALUES (%s, %s, %s)", 
                           (user_id, datetime.now().date(), amount))
            conn.commit()
            conn.close()
            logging.info(f"✅ Ahorro de {amount} guardado correctamente para el usuario {user_id}.")
    except Exception as e:
        logging.error(f"❌ Error al guardar el ahorro: {e}")

# Comando /start
async def start(update: Update, context: CallbackContext):
    user_id = update.message.chat.id
    keyboard = [
        [InlineKeyboardButton("Ingresar número manualmente", callback_data="ingresar_numero")],
        [InlineKeyboardButton("Ver total ahorrado", callback_data="ver_historial")],
        [InlineKeyboardButton("Generar número aleatorio", callback_data="generar_numero")],
        [InlineKeyboardButton("Programar mensajes diarios", callback_data="programar_mensajes")],
        [InlineKeyboardButton("🗑️ Borrar mis ahorros", callback_data="borrar_datos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"📌 Bienvenido al Bot de Ahorro 💰\n\nUsuario ID: `{user_id}`", reply_markup=reply_markup)

# Manejo de botones del menú
async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    if query.data == "ingresar_numero":
        await query.message.reply_text("✍ Ingresa uno o varios números separados por comas:")
        context.user_data["esperando_numeros"] = True

    elif query.data == "ver_historial":
        total, days_saved = get_savings_summary(chat_id)
        await query.message.reply_text(f"📜 Total acumulado: {total} pesos.\n📅 Días ahorrados: {days_saved} días.")

    elif query.data == "generar_numero":
        amount = get_unique_random_number(chat_id)
        if amount:
            save_savings(chat_id, amount)
            total, days_saved = get_savings_summary(chat_id)
            await query.message.reply_text(f"🎲 Se generó el número {amount} y se ha guardado.\n📜 Total acumulado: {total} pesos.\n📅 Días ahorrados: {days_saved} días.")
        else:
            await query.message.reply_text("⚠️ Ya se han guardado todos los números entre 1 y 365.")

# Programar mensajes diarios
def schedule_daily_savings(hour="08:00"):
    schedule.every().day.at(hour).do(lambda: asyncio.create_task(daily_savings()))
    logging.info(f"✅ Mensajes programados a las {hour}.")

# Capturar números ingresados manualmente
async def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    text = update.message.text.strip()

    if context.user_data.get("esperando_numeros", False):
        numbers = [int(num) for num in text.split(",") if num.strip().isdigit()]
        for amount in numbers:
            save_savings(chat_id, amount)

        total, days_saved = get_savings_summary(chat_id)
        await update.message.reply_text(f"✅ Números guardados.\n📜 Total acumulado: {total} pesos.\n📅 Días ahorrados: {days_saved} días.")
        context.user_data["esperando_numeros"] = False

# Iniciar el bot
if __name__ == "__main__":
    logging.info("🚀 Iniciando el bot de ahorro...")
    init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    schedule_daily_savings()

    app.run_polling()
