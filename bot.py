from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import sqlite3, json
from datetime import datetime, timezone, timedelta

# ───────── CONFIG ─────────
import os
BOT_TOKEN = os.getenv("BOT_TOKEN")
IST = timezone(timedelta(hours=5, minutes=30))

# ───────── DB ─────────
def db():
    return sqlite3.connect("vault.db")

# ───────── STATE ─────────
STATE = {}

# ───────── HELPERS ─────────
def fmt(x):
    return x if x else "—"

def valid_time(s):
    try:
        datetime.strptime(s, "%d-%m-%Y %H:%M")
        return True
    except:
        return False

def item_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁 Open", callback_data="act:open")],
        [InlineKeyboardButton("🕓 Edit time", callback_data="act:time")],
        [InlineKeyboardButton("🏷 Edit tags", callback_data="act:tags")],
        [InlineKeyboardButton("🗑 Delete", callback_data="act:delete")],
        [InlineKeyboardButton("⬅ Back", callback_data="act:back")]
    ])

# ───────── START / HELP ─────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Vault bot launched successfully\n\n"
        "Commands:\n"
        "/vault – Open vault\n"
        "/categories – Browse categories\n"
        "/recent – View recent items\n"
        "/search <date|category>\n"
        "/delete – Delete items or categories\n"
        "/export – Backup metadata\n"
        "/help – How it works\n\n"
        "Examples:\n"
        "/search 13-02-2026\n"
        "/search ss-02-26"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "How it works:\n"
        "• Category → Items\n"
        "• Item → Open / Edit / Delete\n"
        "• Search by category or custom/sent date\n"
        "• Time format: DD-MM-YYYY HH:MM\n\n"
        "Files stay on Telegram.\n"
        "Metadata stays local."
    )

# ───────── VAULT ─────────
async def vault(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Categories", callback_data="vault:cats")],
        [InlineKeyboardButton("🕒 Recent", callback_data="vault:recent")]
    ])
    await update.message.reply_text("Vault:", reply_markup=kb)

# ───────── CATEGORIES ─────────
async def show_categories(message):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT category, COUNT(*) FROM items GROUP BY category")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await message.reply_text("No categories yet.")
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{c} ({n})", callback_data=f"cat:{c}")]
        for c, n in rows
    ])
    await message.reply_text("Categories:", reply_markup=kb)

async def cat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cat = q.data.split(":", 1)[1]

    STATE[q.message.chat.id] = {"view": "category", "category": cat}

    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, type, sent_ist FROM items WHERE category=? ORDER BY id DESC",
        (cat,)
    )
    rows = cur.fetchall()
    conn.close()

    kb = [
        [InlineKeyboardButton(f"{t} • {s}", callback_data=f"item:{i}")]
        for i, t, s in rows
    ]
    kb.append([InlineKeyboardButton("🗑 Delete category", callback_data="delcat")])

    await q.message.reply_text(
        f"📁 Category: {cat}",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ───────── DELETE CATEGORY ─────────
async def delcat_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, delete category", callback_data="delcat_yes")],
        [InlineKeyboardButton("❌ Cancel", callback_data="delcat_no")]
    ])
    await q.message.reply_text("Delete entire category?", reply_markup=kb)

async def delcat_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat = q.message.chat.id
    state = STATE.get(chat)

    if q.data.endswith("no") or not state:
        await q.message.reply_text("Cancelled.")
        return

    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE category=?", (state["category"],))
    conn.commit()
    conn.close()
    STATE.pop(chat, None)

    await q.message.reply_text("🗑 Category deleted.")

# ───────── RECENT ─────────
async def recent_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    STATE[update.message.chat.id] = {"view": "recent"}

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id, type, sent_ist FROM items ORDER BY id DESC LIMIT 20")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No recent items.")
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{t} • {s}", callback_data=f"item:{i}")]
        for i, t, s in rows
    ])
    await update.message.reply_text("Recent items:", reply_markup=kb)

# ───────── SEARCH (CATEGORY + SENT + CUSTOM TIME) ─────────
async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /search <date or category>")
        return

    query = " ".join(context.args).strip()
    STATE[update.message.chat.id] = {"view": "search", "query": query}

    conn = db()
    cur = conn.cursor()

    is_date = "-" in query

    if is_date:
        cur.execute("""
            SELECT id, type, sent_ist FROM items
            WHERE sent_ist LIKE ?
               OR custom_ist LIKE ?
            ORDER BY id DESC
        """, (f"%{query}%", f"%{query}%"))
    else:
        cur.execute("""
            SELECT id, type, sent_ist FROM items
            WHERE LOWER(category) LIKE LOWER(?)
            ORDER BY id DESC
        """, (f"%{query}%",))

    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("No results found.")
        return

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{t} • {s}", callback_data=f"item:{i}")]
        for i, t, s in rows
    ])
    await update.message.reply_text(f"Results for '{query}':", reply_markup=kb)

# ───────── ITEM SELECT ─────────
async def item_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    STATE[q.message.chat.id]["item"] = int(q.data.split(":")[1])
    await q.message.reply_text("Choose action:", reply_markup=item_kb())

# ───────── ACTIONS ─────────
async def action_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat = q.message.chat.id
    state = STATE.get(chat, {})
    item_id = state.get("item")

    if not item_id:
        return

    if q.data == "act:open":
        conn = db()
        cur = conn.cursor()
        cur.execute("""
            SELECT type, telegram_file_id, text_content,
                   category, sent_ist, custom_ist, edited_ist, tags
            FROM items WHERE id=?
        """, (item_id,))
        t, fid, text, cat, sent, custom, edited, tags = cur.fetchone()
        conn.close()

        caption = (
            f"📁 Category: {cat}\n"
            f"📤 Sent: {fmt(sent)}\n"
            f"🕓 Custom: {fmt(custom)}\n"
            f"✏️ Edited: {fmt(edited)}\n"
            f"🏷 Tags: {fmt(tags)}"
        )

        if t == "photo":
            await context.bot.send_photo(chat, fid, caption=caption)
        elif t == "video":
            await context.bot.send_video(chat, fid, caption=caption)
        elif t == "audio":
            await context.bot.send_audio(chat, fid, caption=caption)
        elif t == "document":
            await context.bot.send_document(chat, fid, caption=caption)
        else:
            await q.message.reply_text(text + "\n\n" + caption)

        await q.message.reply_text("Choose action:", reply_markup=item_kb())

    elif q.data == "act:time":
        STATE[chat]["mode"] = "time"
        await q.message.reply_text("Send new time:\nDD-MM-YYYY HH:MM")

    elif q.data == "act:tags":
        STATE[chat]["mode"] = "tags"
        await q.message.reply_text("Send tags (comma separated)")

    elif q.data == "act:delete":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Yes, delete", callback_data="confirm:yes")],
            [InlineKeyboardButton("❌ Cancel", callback_data="confirm:no")]
        ])
        await q.message.reply_text("Are you sure?", reply_markup=kb)

    elif q.data == "act:back":
        view = state.get("view")
        if view == "category":
            await show_categories(q.message)
        elif view == "recent":
            await recent_cmd(q.message, context)
        elif view == "search":
            await search_cmd(q.message, context)
        else:
            await vault(q.message, context)

# ───────── TEXT INPUT (EDITORS) ─────────
async def text_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat.id
    state = STATE.get(chat)

    if not state or "mode" not in state:
        return

    item_id = state["item"]
    txt = update.message.text.strip()

    conn = db()
    cur = conn.cursor()

    if state["mode"] == "time":
        if not valid_time(txt):
            await update.message.reply_text("Invalid format.")
            return
        cur.execute("""
            UPDATE items SET custom_ist=?, edited_ist=?
            WHERE id=?
        """, (txt, datetime.now(IST).strftime("%d-%m-%Y %H:%M"), item_id))

    elif state["mode"] == "tags":
        tags = ", ".join([t.strip() for t in txt.split(",") if t.strip()])
        cur.execute("""
            UPDATE items SET tags=?, edited_ist=?
            WHERE id=?
        """, (tags, datetime.now(IST).strftime("%d-%m-%Y %H:%M"), item_id))

    conn.commit()
    conn.close()
    STATE.pop(chat, None)

    await update.message.reply_text("Updated.", reply_markup=item_kb())

# ───────── CONFIRM DELETE ITEM ─────────
async def confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat = q.message.chat.id

    if q.data.endswith("no"):
        await q.message.reply_text("Cancelled.")
        return

    item_id = STATE.get(chat, {}).get("item")
    if not item_id:
        return

    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    STATE.pop(chat, None)

    await q.message.reply_text("🗑 Deleted.")

# ───────── DELETE COMMAND ─────────
async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    STATE[update.message.chat.id] = {"view": "delete"}
    await show_categories(update.message)

# ───────── EXPORT ─────────
async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM items")
    cols = [d[0] for d in cur.description]
    data = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()

    with open("vault_export.json", "w") as f:
        json.dump(data, f, indent=2)

    await update.message.reply_document(open("vault_export.json", "rb"))

# ───────── COMMAND MENU ─────────
async def setup_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Show commands"),
        BotCommand("vault", "Open vault"),
        BotCommand("categories", "Browse categories"),
        BotCommand("recent", "View recent items"),
        BotCommand("search", "Search vault"),
        BotCommand("delete", "Delete items or categories"),
        BotCommand("export", "Backup metadata"),
        BotCommand("help", "How it works")
    ])

# ───────── MAIN ─────────
def main():
    print("🚀 Vault bot launched successfully")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.post_init = setup_commands

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("vault", vault))
    app.add_handler(CommandHandler("categories", lambda u, c: show_categories(u.message)))
    app.add_handler(CommandHandler("recent", recent_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("export", export_cmd))

    app.add_handler(CallbackQueryHandler(cat_cb, "^cat:"))
    app.add_handler(CallbackQueryHandler(delcat_cb, "^delcat$"))
    app.add_handler(CallbackQueryHandler(delcat_confirm_cb, "^delcat_"))
    app.add_handler(CallbackQueryHandler(item_cb, "^item:"))
    app.add_handler(CallbackQueryHandler(action_cb, "^act:"))
    app.add_handler(CallbackQueryHandler(confirm_cb, "^confirm"))
    app.add_handler(CallbackQueryHandler(
        lambda u, c: show_categories(u.callback_query.message),
        "^vault:cats"
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_cb))

    app.run_polling()

if __name__ == "__main__":

    main()
