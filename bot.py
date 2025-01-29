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

# Guardar número en la base de datos para un usuario específico
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
        else:
            logging.error(f"❌ No se pudo conectar a la base de datos.")
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

# Generar un número aleatorio que no se repita por usuario
def get_unique_random_number(user_id):
    saved_numbers = get_savings(user_id)
    available_numbers = [x for x in range(1, 366) if x not in saved_numbers]
    return random.choice(available_numbers) if available_numbers else None

# Comando /start con menú interactivo
async def start(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    keyboard = [
        [InlineKeyboardButton("Ingresar número manualmente", callback_data=f"ingresar_numero_{user_id}")],
        [InlineKeyboardButton("Ver total ahorrado", callback_data=f"ver_historial_{user_id}")],
        [InlineKeyboardButton("Generar número aleatorio", callback_data=f"generar_numero_{user_id}")],
        [InlineKeyboardButton("Programar mensajes diarios", callback_data=f"programar_mensajes_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"📌 Bienvenido al Bot de Ahorro 💰\n\nUsuario ID: `{user_id}`\nElige una opción:", reply_markup=reply_markup)

# Manejo de botones del menú
async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    user_id = query.message.chat_id  # Obtener ID del usuario

    if "generar_numero" in query.data:
        amount = get_unique_random_number(user_id)
        if amount is not None:
            save_savings(user_id, amount)  # Asegurar que se guarda con user_id
            total = get_total_savings(user_id)
            await query.message.reply_text(f"🎲 Se generó el número {amount} y se ha guardado. Total acumulado: {total} pesos.")
        else:
            await query.message.reply_text("⚠️ Ya se han guardado todos los números entre 1 y 365.")
    elif "ver_historial" in query.data:
        total = get_total_savings(user_id)
        await query.message.reply_text(f"📜 Total acumulado: {total} pesos.")

# Capturar números ingresados manualmente
async def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    text = update.message.text

    try:
        amount = int(text)
        if 1 <= amount <= 365:
            save_savings(user_id, amount)
            total = get_total_savings(user_id)
            await update.message.reply_text(f"✅ Se ha guardado {amount} pesos. Total acumulado: {total} pesos.")
        else:
            await update.message.reply_text("⚠️ Ingresa un número entre 1 y 365.")
    except ValueError:
        await update.message.reply_text("⚠️ Ingresa un número válido.")

# Iniciar el bot
if __name__ == "__main__":
    logging.info("🚀 Iniciando el bot de ahorro...")
    init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()
