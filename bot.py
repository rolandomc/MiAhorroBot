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
    raise ValueError("

⚠️ ERROR: Las variables de entorno TELEGRAM_BOT_TOKEN o DATABASE_URL no están configuradas.")

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

# Guardar hora de programación
def save_schedule(user_id, schedule_time):
    conn = connect_db()
    if conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO scheduled_messages (user_id, schedule_time) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET schedule_time = EXCLUDED.schedule_time",
                       (user_id, schedule_time))
        conn.commit()
        conn.close()
        logging.info(f"✅ Mensajes programados para {user_id} a las {schedule_time}.")

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
        [InlineKeyboardButton("Ingresar número manualmente", callback_data="ingresar_numero")],
        [InlineKeyboardButton("Ver total ahorrado", callback_data="ver_historial")],
        [InlineKeyboardButton("Generar número aleatorio", callback_data="generar_numero")],
        [InlineKeyboardButton("Programar mensajes diarios", callback_data="programar_mensajes")],
        [InlineKeyboardButton("🗑️ Borrar mis ahorros", callback_data="borrar_datos")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"📌 Bienvenido al Bot de Ahorro 💰\n\nUsuario ID: `{user_id}`", reply_markup=reply_markup)

# Manejo de botones
async def button(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    if query.data == "programar_mensajes":
        await query.message.reply_text("⏰ Ingresa la hora en formato 24H (ejemplo: 08:00 o 18:30):")
        context.user_data["esperando_hora"] = True

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

# Capturar horario ingresado por el usuario
async def handle_message(update: Update, context: CallbackContext):
    chat_id = update.message.chat.id
    text = update.message.text.strip()

    if context.user_data.get("esperando_hora", False):
        try:
            horario = datetime.strptime(text.strip(), "%H:%M").time()
            save_schedule(chat_id, horario)
            await update.message.reply_text(f"✅ Has programado los mensajes diarios a las {text}.")
        except ValueError:
            await update.message.reply_text("⚠️ Formato incorrecto. Ingresa la hora en formato HH:MM (ejemplo: 08:00).")
        
        context.user_data["esperando_hora"] = False

# Hilo para ejecución continua
def start_scheduler(application):
    while True:
        asyncio.run(asyncio.create_task(send_daily_savings(application)))
        time.sleep(60)  # Verificar cada minuto

# Iniciar el bot
if __name__ == "__main__":
    logging.info("🚀 Iniciando el bot de ahorro...")
    init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    # Iniciar el hilo de programación de tareas
    scheduler_thread = threading.Thread(target=start_scheduler, args=(app,))
    scheduler_thread.daemon = True
    scheduler_thread.start()

    app.run_polling()