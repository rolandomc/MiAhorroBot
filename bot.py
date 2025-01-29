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
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
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
                    date DATE NOT NULL,
                    amount INTEGER NOT NULL
                )
            ''')
            conn.commit()
            conn.close()
            logging.info("✅ Base de datos inicializada correctamente.")
    except Exception as e:
        logging.error(f"❌ Error al inicializar la base de datos: {e}")

# Guardar número en la base de datos
def save_savings(amount):
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO savings (date, amount) VALUES (%s, %s)", (datetime.now().date(), amount))
            conn.commit()
            conn.close()
            logging.info(f"✅ Ahorro de {amount} guardado correctamente.")
    except Exception as e:
        logging.error(f"❌ Error al guardar el ahorro: {e}")

# Obtener el total ahorrado
def get_total_savings():
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM savings")
            total = cursor.fetchone()[0]
            conn.close()
            return total
    except Exception as e:
        logging.error(f"❌ Error al obtener el total ahorrado: {e}")
        return 0

# Obtener números guardados
def get_savings():
    try:
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT amount FROM savings ORDER BY date DESC")
            data = cursor.fetchall()
            conn.close()
            return [x[0] for x in data]
    except Exception as e:
        logging.error(f"❌ Error al obtener el historial de ahorros: {e}")
        return []

# Generar un número aleatorio que no se repita
def get_unique_random_number():
    saved_numbers = get_savings()
    available_numbers = [x for x in range(1, 366) if x not in saved_numbers]
    return random.choice(available_numbers) if available_numbers else None

# Comando /start con menú interactivo
async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Ingresar número manualmente", callback_data="ingresar_numero")],
        [InlineKeyboardButton("Ver total ahorrado", callback_data="ver_historial")],
        [InlineKeyboardButton("Generar número aleatorio", callback_data="generar_numero")],
        [InlineKeyboardButton("Programar mensajes diarios", callback_data="programar_mensajes")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📌 Bienvenido al Bot de Ahorro 💰\n\nElige una opción:", reply_markup=reply_markup)

# Manejo de botones del menú
async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "ingresar_numero":
        await query.message.reply_text("✍ Ingresa un número para guardarlo en el ahorro:")
    elif query.data == "ver_historial":
        total = get_total_savings()
        await query.message.reply_text(f"📜 Total acumulado: {total} pesos.")
    elif query.data == "generar_numero":
        amount = get_unique_random_number()
        if amount is not None:
            save_savings(amount)
            total = get_total_savings()
            await query.message.reply_text(f"🎲 Se generó el número {amount} y se ha guardado. Total acumulado: {total} pesos.")
        else:
            await query.message.reply_text("⚠️ Ya se han guardado todos los números entre 1 y 365.")
    elif query.data == "programar_mensajes":
        await query.message.reply_text("⏰ Escribe la hora en formato 24H (ejemplo: 08:00 para 8 AM o 18:30 para 6:30 PM):")

# Capturar números ingresados manualmente
async def handle_message(update: Update, context: CallbackContext):
    text = update.message.text
    if ":" in text:  # Si el usuario ingresa una hora para programar los mensajes
        try:
            schedule.every().day.at(text).do(lambda: context.application.create_task(daily_savings()))
            await update.message.reply_text(f"✅ Mensajes programados a las {text} diariamente.")
        except Exception as e:
            await update.message.reply_text("⚠️ Formato de hora inválido. Usa HH:MM (ejemplo: 08:00).")
    else:  # Guardar un número manualmente
        try:
            amount = int(text)
            if amount < 1 or amount > 365:
                await update.message.reply_text("⚠️ Ingresa un número entre 1 y 365.")
                return
            save_savings(amount)
            total = get_total_savings()
            await update.message.reply_text(f"✅ Se ha guardado {amount} pesos. Total acumulado: {total} pesos.")
        except ValueError:
            await update.message.reply_text("⚠️ Ingresa un número válido.")

# Enviar número aleatorio diario
async def daily_savings():
    amount = get_unique_random_number()
    if amount is not None:
        save_savings(amount)
        total = get_total_savings()
        bot = app.bot
        await bot.send_message(chat_id=CHAT_ID, text=f"💰 Hoy debes ahorrar: {amount} pesos\n📊 Acumulado total: {total} pesos.")

# Iniciar el bot
if __name__ == "__main__":
    logging.info("🚀 Iniciando el bot de ahorro...")
    init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()
