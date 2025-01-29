import os
import logging
import psycopg2
import schedule
import time
import threading
import random
from datetime import datetime
from urllib.parse import urlparse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext

# Configuración de Logging
logging.basicConfig(level=logging.INFO)

# Obtener las variables de entorno
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

# Verificar que las variables estén configuradas
if not TOKEN:
    raise ValueError("⚠️ ERROR: La variable TELEGRAM_BOT_TOKEN no está configurada.")
if not DB_URL:
    raise ValueError("⚠️ ERROR: La variable DATABASE_URL no está configurada.")

print(f"🌐 URL de conexión a PostgreSQL: {DB_URL}")

# Función para conectar a PostgreSQL
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

# Inicializar la base de datos con user_id
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

# Guardar número en la base de datos para un usuario específico
def save_savings(user_id, amount):
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO savings (user_id, date, amount) VALUES (%s, %s, %s)", 
                           (user_id, datetime.now().date(), amount))
            conn.commit()
            cursor.close()
            conn.close()
            logging.info(f"✅ Ahorro de {amount} guardado correctamente para el usuario {user_id}.")
    except Exception as e:
        logging.error(f"❌ Error al guardar el ahorro para el usuario {user_id}: {e}")

# Obtener el total ahorrado por usuario
def get_total_savings(user_id):
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM savings WHERE user_id = %s", (user_id,))
            total = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            return total
    except Exception as e:
        logging.error(f"❌ Error al obtener el total ahorrado para el usuario {user_id}: {e}")
        return 0

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
        logging.error(f"❌ Error al obtener el historial de ahorros para el usuario {user_id}: {e}")
        return []

# Eliminar todos los registros de ahorro de un usuario
def delete_user_savings(user_id):
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM savings WHERE user_id = %s", (user_id,))
            conn.commit()
            cursor.close()
            conn.close()
            logging.info(f"🗑️ Se eliminaron todos los ahorros del usuario {user_id}.")
    except Exception as e:
        logging.error(f"❌ Error al eliminar los ahorros del usuario {user_id}: {e}")

# Generar un número aleatorio que no se repita por usuario
def get_unique_random_number(user_id):
    saved_numbers = get_savings(user_id)
    available_numbers = [x for x in range(1, 366) if x not in saved_numbers]
    return random.choice(available_numbers) if available_numbers else None

# Capturar números ingresados manualmente y verificar si ya existen
async def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.chat.id
    text = update.message.text.strip()

    # Dividir los números ingresados por comas y eliminar espacios
    numbers = text.split(",")
    numbers = [num.strip() for num in numbers if num.strip().isdigit()]

    if not numbers:
        await update.message.reply_text("⚠️ Ingresa uno o varios números válidos separados por comas.")
        return

    existing_numbers = get_savings(user_id)
    saved_numbers = []
    ignored_numbers = []

    for num in numbers:
        amount = int(num)
        if 1 <= amount <= 365:
            if amount not in existing_numbers:
                save_savings(user_id, amount)
                saved_numbers.append(amount)
            else:
                ignored_numbers.append(amount)
        else:
            ignored_numbers.append(amount)

    # Mensajes de respuesta
    response = ""
    if saved_numbers:
        total = get_total_savings(user_id)
        response += f"✅ Se han guardado: {', '.join(map(str, saved_numbers))} pesos. Total acumulado: {total} pesos.\n"
    if ignored_numbers:
        response += f"⚠️ Estos números ya estaban guardados o no son válidos: {', '.join(map(str, ignored_numbers))}."

    await update.message.reply_text(response)

# Iniciar el bot
if __name__ == "__main__":
    logging.info("🚀 Iniciando el bot de ahorro...")
    init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))  # <-- Se corrige el filtro aquí

    app.run_polling()
