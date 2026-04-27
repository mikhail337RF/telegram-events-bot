import json
import os
from datetime import datetime
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import asyncio
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

# ----- БЛОК С ЛОГИКОЙ БОТА -----
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, text=None):
    keyboard = [
        [InlineKeyboardButton("📅 Мои мероприятия", callback_data="list")],
        [InlineKeyboardButton("➕ Добавить мероприятие", callback_data="add")],
        [InlineKeyboardButton("🔔 Настройки", callback_data="settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = text or "🎉 *Личный календарь мероприятий*\nВыбери действие:"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["adding"] = {"step": "name"}
    await update.callback_query.edit_message_text("✏️ Введи *название* мероприятия:", parse_mode="Markdown")

async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, idx = query.data.split("_")
    context.user_data["edit_idx"] = int(idx)
    
    keyboard = [
        [InlineKeyboardButton("📝 Название", callback_data=f"edit_field_name_{idx}")],
        [InlineKeyboardButton("📅 Дату и время", callback_data=f"edit_field_date_{idx}")],
        [InlineKeyboardButton("🔗 Ссылку", callback_data=f"edit_field_link_{idx}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="list")]
    ]
    await query.edit_message_text("✏️ *Что хочешь изменить?*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, field, idx = query.data.split("_")
    context.user_data["editing"] = {"field": field, "idx": int(idx), "step": "value"}
    
    prompts = {
        "name": "Введи *новое название*:",
        "date": "Введи *новую дату и время* (например: 15.06 19:00):",
        "link": "Введи *новую ссылку* (или напиши 'нет' чтобы удалить):"
    }
    await query.edit_message_text(prompts[field], parse_mode="Markdown")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text = update.message.text
    
    if "adding" in context.user_data:
        step = context.user_data["adding"]["step"]
        
        if step == "name":
            context.user_data["adding"]["name"] = text
            context.user_data["adding"]["step"] = "date"
            await update.message.reply_text("📅 Введи *дату и время* (например: 15.06 19:00):", parse_mode="Markdown")
        
        elif step == "date":
            context.user_data["adding"]["date"] = text
            context.user_data["adding"]["step"] = "link"
            await update.message.reply_text("🔗 Введи *ссылку* (или напиши 'нет'):", parse_mode="Markdown")
        
        elif step == "link":
            link = "" if text.lower() == "нет" else text
            data = load_data()
            if user_id not in data:
                data[user_id] = []
            data[user_id].append({
                "name": context.user_data["adding"]["name"],
                "date": context.user_data["adding"]["date"],
                "link": link,
                "created": str(datetime.now())
            })
            save_data(data)
            await update.message.reply_text(f"✅ *Добавлено!*\n\n{context.user_data['adding']['name']}\n📅 {context.user_data['adding']['date']}\n🔗 {link if link else '—'}", parse_mode="Markdown")
            del context.user_data["adding"]
            await main_menu(update, context)
    
    elif "editing" in context.user_data:
        data = load_data()
        events = data.get(user_id, [])
        idx = context.user_data["editing"]["idx"]
        field = context.user_data["editing"]["field"]
        
        if field == "link" and text.lower() == "нет":
            text = ""
        
        events[idx][field] = text
        data[user_id] = events
        save_data(data)
        
        await update.message.reply_text(f"✅ *{field.capitalize()} обновлено!*", parse_mode="Markdown")
        del context.user_data["editing"]
        await show_list(update, context)
    
    else:
        await update.message.reply_text("Используй кнопки меню 👆")

async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    events = data.get(user_id, [])
    
    if not events:
        await update.callback_query.edit_message_text("📭 *У тебя пока нет мероприятий*\nНажми «➕ Добавить»", parse_mode="Markdown")
        return
    
    events_sorted = sorted(events, key=lambda x: x["date"])
    
    text = "*📅 Твои мероприятия:*\n\n"
    for i, e in enumerate(events_sorted, 1):
        text += f"{i}. *{e['name']}*\n   📆 {e['date']}\n"
        if e.get('link', ''):
            text += f"   🔗 [ссылка]({e['link']})\n"
        text += "\n"
    
    keyboard = []
    for i, e in enumerate(events_sorted):
        keyboard.append([
            InlineKeyboardButton(f"✏️ {e['name'][:15]}", callback_data=f"edit_{i}"),
            InlineKeyboardButton(f"❌ Удалить", callback_data=f"del_{i}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="menu")])
    
    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown", disable_web_page_preview=True)

async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data = load_data()
    events = data.get(user_id, [])
    
    idx = int(update.callback_query.data.split("_")[1])
    deleted = events.pop(idx)
    data[user_id] = events
    save_data(data)
    
    await update.callback_query.answer(f"❌ Удалено: {deleted['name']}")
    await show_list(update, context)

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("⏰ Включить уведомления", callback_data="notif_on")],
        [InlineKeyboardButton("🔕 Выключить уведомления", callback_data="notif_off")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu")]
    ]
    await update.callback_query.edit_message_text("🔔 *Настройки*\nУведомления появятся в следующей версии!", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "menu":
        await main_menu(update, context)
    elif query.data == "list":
        await show_list(update, context)
    elif query.data == "add":
        await start_add(update, context)
    elif query.data == "settings":
        await settings(update, context)
    elif query.data.startswith("del_"):
        await delete_event(update, context)
    elif query.data.startswith("edit_"):
        if query.data == "edit_":
            return
        await start_edit(update, context)
    elif query.data.startswith("edit_field_"):
        await edit_field(update, context)
    elif query.data in ["notif_on", "notif_off"]:
        await query.edit_message_text("🔔 Функция уведомлений будет добавлена позже!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await main_menu(update, context)

# ----- ЗАПУСК БОТА (современный способ для версии 20.x) -----
async def run_bot():
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        print("❌ Ошибка: переменная TELEGRAM_BOT_TOKEN не установлена")
        return
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    print("✅ Бот запущен и работает!")
    
    # Запускаем polling (без Updater)
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Держим бота активным
    while True:
        await asyncio.sleep(1)

# ----- Flask healthcheck -----
@app.route('/')
@app.route('/health')
def health():
    return jsonify({"status": "alive"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Запускаем бота
    asyncio.run(run_bot())
