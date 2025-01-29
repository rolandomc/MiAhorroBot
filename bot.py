import os
import logging
import psycopg2
import schedule
import time
import threading
import random
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
from urllib.parse import urlparse


DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    raise ValueError("⚠️ ERROR: La variable de entorno DATABASE_URL no está configurada correctamente.")

print(f"🌐 URL de conexión a PostgreSQL: {DB_URL}")

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
        if not DB_URL:
            raise ValueError("⚠️ ERROR: La variable de entorno DATABASE_URL no está configurada.")

        result = urlparse(DB_URL)
        conn = psycopg2.connect(
            database=result.path[1:],  # Corregido: Obtener el nombre de la base de datos sin '/'
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

# Obtener número aleatorio único
def get_unique_random_number():
    saved_numbers = get_savings()
    available_numbers = [x for x in range(1, 366) if x not in saved_numbers]
    return random.choice(available_numbers) if available_numbers else None

# Comando /start con menú interactivo
async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("Ingresar número manualmente", callback_data="ingresar_numero")],
        [InlineKeyboardButton("Ver historial de ahorros", callback_data="ver_historial")]
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
        savings = get_savings()
        message = "📜 Historial de ahorro:\n" + "\n".join([f"💰 {amount} pesos" for amount in savings])
        await query.message.reply_text(message if savings else "📌 Aún no has registrado ahorros.")

# Capturar números ingresados manualmente
async def handle_message(update: Update, context: CallbackContext):
    try:
        amount = int(update.message.text)
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
    if amount is None:
        logging.info("❌ No quedan números disponibles.")
        return
    save_savings(amount)
    total = get_total_savings()
    bot = app.bot
    await bot.send_message(chat_id=CHAT_ID, text=f"💰 Hoy debes ahorrar: {amount} pesos\n📊 Acumulado total: {total} pesos.")

# Programar la tarea diaria
def schedule_daily_savings():
    schedule.every().day.at("08:00").do(lambda: app.create_task(daily_savings()))

# Ejecutar el scheduler en un hilo separado
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Iniciar el bot con la nueva API de `python-telegram-bot` v20+
if __name__ == "__main__":
    logging.info("🚀 Iniciando el bot de ahorro...")
    init_db()

    # Crear la aplicación de Telegram usando la nueva API
    app = Application.builder().token(TOKEN).build()

    # Agregar handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Iniciar el scheduler en un hilo separado
    thread = threading.Thread(target=run_scheduler, daemon=True)
    thread.start()

    # Iniciar el bot en modo polling
    app.run_polling()
