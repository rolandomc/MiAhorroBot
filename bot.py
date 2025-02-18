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
    """ Genera un número aleatorio que no haya sido guardado previamente """
    saved_numbers = get_savings(user_id)
    available_numbers = [x for x in range(1, 366) if x not in saved_numbers]

    return random.choice(available_numbers) if available_numbers else None

async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    if query.data == "generar_numero":
        amount = get_unique_random_number(chat_id)
        if amount:
            if save_savings(chat_id, amount):
                total, days_saved = get_savings_summary(chat_id)
                await query.message.reply_text(f"🎲 Se generó el número {amount} \n📜 Total acumulado: {total} pesos.\n📅 Días ahorrados: {days_saved} días.")
            else:
                await query.message.reply_text(f"⚠️ El número {amount} ya estaba guardado. Intentando otro...")
        else:
            await query.message.reply_text("⚠️ Ya se han guardado todos los números entre 1 y 365.")


# Guardar número en la base de datos
def is_number_saved(user_id, amount):
    """ Verifica si un número ya ha sido guardado por el usuario """
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM savings WHERE user_id = %s AND amount = %s", (user_id, amount))
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0  # Devuelve True si el número ya está guardado
    except Exception as e:
        logging.error(f"❌ Error al verificar número guardado: {e}")
        return False

def save_savings(user_id, amount):
    """ Guarda el número solo si no está duplicado """
    if is_number_saved(user_id, amount):
        logging.info(f"⚠️ El número {amount} ya ha sido guardado previamente para el usuario {user_id}.")
        return False  # Indica que el número no se guardó por ser duplicado
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO savings (user_id, date, amount) VALUES (%s, %s, %s)", 
                           (user_id, datetime.now().date(), amount))
            conn.commit()
            conn.close()
            logging.info(f"✅ Ahorro de {amount} guardado correctamente para el usuario {user_id}.")
            return True  # Indica que el número se guardó correctamente
    except Exception as e:
        logging.error(f"❌ Error al guardar el ahorro: {e}")
        return False


# Borrar todos los ahorros de un usuario
def delete_savings(user_id):
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM savings WHERE user_id = %s", (user_id,))
            conn.commit()
            conn.close()
            logging.info(f"🗑️ Ahorros eliminados para el usuario {user_id}.")
    except Exception as e:
        logging.error(f"❌ Error al borrar los ahorros: {e}")

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

# Comando /gennerar
async def generate_random_number(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    amount = get_unique_random_number(chat_id)  # Genera un número único

    if amount:
        if save_savings(chat_id, amount):  # Guarda solo si no está repetido
            total, days_saved = get_savings_summary(chat_id)
            await update.message.reply_text(f"🎲 Se generó el número {amount} y se ha guardado.\n📜 Total acumulado: {total} pesos.\n📅 Días ahorrados: {days_saved} días.")
        else:
            await update.message.reply_text(f"⚠️ El número {amount} ya estaba guardado. Intentando otro...")
    else:
        await update.message.reply_text("⚠️ Ya se han guardado todos los números entre 1 y 365.")


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

    elif query.data == "borrar_datos":
        await query.message.reply_text("⚠️ Escribe `CONFIRMAR` para borrar todos tus ahorros.")

    elif query.data == "programar_mensajes":
        await query.message.reply_text("⏰ Ingresa la hora en formato 24H (ejemplo: 08:00 o 18:30):")
        context.user_data["esperando_hora"] = True

# Capturar números ingresados manualmente y confirmar borrado
async def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    text = update.message.text.strip()

    if context.user_data.get("esperando_numeros", False):
        numbers = [int(num) for num in text.split(",") if num.strip().isdigit()]
        saved_any = False
        duplicate_numbers = []

        for amount in numbers:
            if save_savings(chat_id, amount):
                saved_any = True
            else:
                duplicate_numbers.append(amount)

        total, days_saved = get_savings_summary(chat_id)

        if saved_any:
            await update.message.reply_text(f"✅ Números guardados.\n📜 Total acumulado: {total} pesos.\n📅 Días ahorrados: {days_saved} días.")
        
        if duplicate_numbers:
            await update.message.reply_text(f"⚠️ Los siguientes números ya estaban guardados y no fueron ingresados nuevamente: {', '.join(map(str, duplicate_numbers))}")

        context.user_data["esperando_numeros"] = False

    elif context.user_data.get("esperando_hora", False):
        schedule.every().day.at(text).do(lambda: asyncio.create_task(daily_savings()))
        await update.message.reply_text(f"✅ Mensajes programados a las {text} diariamente.")
        context.user_data["esperando_hora"] = False

    elif text == "CONFIRMAR":
        delete_savings(chat_id)
        await update.message.reply_text("✅ Se han eliminado todos tus ahorros.")

# Iniciar el bot
if __name__ == "__main__":
    logging.info("🚀 Iniciando el bot de ahorro...")
    init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    CommandHandler("generar", generate_random_number)
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    app.run_polling() 
