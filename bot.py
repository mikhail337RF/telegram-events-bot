import json
import os
from datetime import datetime
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext
import threading

app = Flask(__name__)
DATA_FILE = "events.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# --- Команды бота ---
def start(update: Update, context: CallbackContext):
    keyboard = [[InlineKeyboardButton("📅 Список", callback_data="list")],
                [InlineKeyboardButton("➕ Добавить", callback_data="add")]]
    update.message.reply_text("Привет! Выбери действие:", reply_markup=InlineKeyboardMarkup(keyboard))

def button(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    if query.data == "list":
        user_id = str(update.effective_user.id)
        data = load_data()
        events = data.get(user_id, [])
        if not events:
            query.edit_message_text("Пока нет мероприятий.")
            return
        text = "\n".join([f"{i+1}. {e['name']} ({e['date']})" for i, e in enumerate(events)])
        query.edit_message_text(f"📅 Твои мероприятия:\n{text}")
    elif query.data == "add":
        context.user_data["awaiting"] = "name"
        query.edit_message_text("Введи название мероприятия:")

def handle_text(update: Update, context: CallbackContext):
    if context.user_data.get("awaiting") == "name":
        context.user_data["temp_name"] = update.message.text
        context.user_data["awaiting"] = "date"
        update.message.reply_text("Теперь введи дату (например, 15.06 19:00):")
    elif context.user_data.get("awaiting") == "date":
        name = context.user_data.pop("temp_name")
        date = update.message.text
        user_id = str(update.effective_user.id)
        data = load_data()
        if user_id not in data:
            data[user_id] = []
        data[user_id].append({"name": name, "date": date, "created": str(datetime.now())})
        save_data(data)
        context.user_data.pop("awaiting", None)
        update.message.reply_text(f"✅ Добавлено: {name} на {date}")

# --- Flask healthcheck ---
@app.route('/')
@app.route('/health')
def health():
    return jsonify({"status": "alive"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# --- Запуск бота (способ для 13.7) ---
def run_bot():
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ Токен не найден!")
        return
    
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    
    updater.start_polling()
    print("✅ Бот запущен и работает!")
    updater.idle()

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Запускаем бота (главный поток)
    run_bot()
