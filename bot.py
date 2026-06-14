import logging
import os
import threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from openai import OpenAI

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_KEY_HERE")
ADMIN_ID = 8180209483
GPT_MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = "You are a helpful AI assistant."

CHANNELS = [
    {
        "id": -1002090323246,
        "name": "Main Channel",
        "invite": "https://t.me/+gvybwxOt3Z8xZGI9"
    },
    {
        "id": -1001167075214,
        "name": "Updates Channel",
        "invite": "https://t.me/+ylu_V8Dh9uowM2Y1"
    }
]

# ─── WELCOME MESSAGE ──────────────────────────────────────────────────────────
# Set your photo: local file path OR a public image URL
# Examples:
#   WELCOME_PHOTO = "welcome.jpg"                   <- put file next to bot.py
#   WELCOME_PHOTO = "https://i.imgur.com/xyz.jpg"  <- public URL also works
WELCOME_PHOTO = "welcome.jpg"

# {name} is auto-replaced with the user's first name
WELCOME_CAPTION = (
    "🎉 <b>Welcome, {name}!</b>\n\n"
    "I'm your personal AI assistant powered by GPT.\n\n"
    "Here's what I can do:\n"
    "🤖 Answer any question\n"
    "💡 Help you brainstorm ideas\n"
    "📝 Write & summarize content\n"
    "🔧 Help with code\n\n"
    "Just send me a message to get started!\n"
    "Use /reset anytime to clear our chat history.\n\n"
    "<i>⚡ Powered by GPT-4o Mini</i>"
)
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)
user_histories: dict[int, list] = {}


# ─── PING SERVER (keeps Render awake) ────────────────────────────────────────
# After deploying on Render, copy your app URL and paste it on:
#   https://uptimerobot.com  (free) — ping every 5 mins
# That's it! Bot stays online 24/7.

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot is running!", 200

@flask_app.route("/ping")
def ping():
    return "pong", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=8080)
# ──────────────────────────────────────────────────────────────────────────────


# ─── HELPERS ─────────────────────────────────────────────────────────────────

async def get_unjoined_channels(bot, user_id: int) -> list:
    unjoined = []
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(ch["id"], user_id)
            if member.status not in [
                ChatMember.MEMBER,
                ChatMember.ADMINISTRATOR,
                ChatMember.OWNER,
            ]:
                unjoined.append(ch)
        except Exception:
            unjoined.append(ch)
    return unjoined


def force_join_markup(unjoined: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"➕ Join {ch['name']}", url=ch["invite"])]
        for ch in unjoined
    ]
    buttons.append([InlineKeyboardButton("✅ I've Joined — Verify", callback_data="verify_join")])
    return InlineKeyboardMarkup(buttons)


async def send_force_join(target, user_first_name: str, unjoined: list):
    channel_list = "\n".join(f"  🔴 {ch['name']}" for ch in unjoined)
    text = (
        f"👋 Hey <b>{user_first_name}</b>!\n\n"
        f"🔒 <b>Access Denied</b>\n"
        f"You must join all channels below to use this bot:\n\n"
        f"{channel_list}\n\n"
        f"After joining, press <b>✅ Verify</b> below."
    )
    markup = force_join_markup(unjoined)
    if hasattr(target, "edit_message_text"):
        await target.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await target.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def send_welcome(target, user_first_name: str, chat_id: int = None, bot=None):
    caption = WELCOME_CAPTION.format(name=user_first_name)
    try:
        if hasattr(target, "reply_photo"):
            await target.reply_photo(photo=WELCOME_PHOTO, caption=caption, parse_mode="HTML")
        else:
            try:
                await target.delete_message()
            except Exception:
                pass
            await bot.send_photo(chat_id=chat_id, photo=WELCOME_PHOTO, caption=caption, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send welcome photo: {e}")
        fallback = f"⚠️ (Set WELCOME_PHOTO correctly to show image)\n\n{caption}"
        if hasattr(target, "reply_text"):
            await target.reply_text(fallback, parse_mode="HTML")
        else:
            await bot.send_message(chat_id=chat_id, text=fallback, parse_mode="HTML")


# ─── COMMANDS ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    unjoined = await get_unjoined_channels(context.bot, user.id)
    if unjoined:
        await send_force_join(update.message, user.first_name, unjoined)
        return
    await send_welcome(update.message, user.first_name)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    unjoined = await get_unjoined_channels(context.bot, user.id)
    if unjoined:
        await send_force_join(update.message, user.first_name, unjoined)
        return
    user_histories.pop(user.id, None)
    await update.message.reply_text("🔄 Conversation cleared! Start fresh.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized.")
        return
    count = len(user_histories)
    await update.message.reply_text(f"📊 Active users with chat history: <b>{count}</b>", parse_mode="HTML")


# ─── VERIFY CALLBACK ─────────────────────────────────────────────────────────

async def verify_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    unjoined = await get_unjoined_channels(context.bot, user.id)

    if not unjoined:
        await send_welcome(query, user.first_name, chat_id=query.message.chat_id, bot=context.bot)
    else:
        await query.answer(
            f"❌ Still not joined: {', '.join(ch['name'] for ch in unjoined)}",
            show_alert=True
        )
        await send_force_join(query, user.first_name, unjoined)


# ─── MESSAGE HANDLER ─────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    text = update.message.text

    unjoined = await get_unjoined_channels(context.bot, user_id)
    if unjoined:
        await send_force_join(update.message, user.first_name, unjoined)
        return

    if user_id not in user_histories:
        user_histories[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_histories[user_id].append({"role": "user", "content": text})
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=user_histories[user_id],
            max_tokens=1000,
        )
        reply = response.choices[0].message.content
        user_histories[user_id].append({"role": "assistant", "content": reply})

        if len(user_histories[user_id]) > 21:
            user_histories[user_id] = (
                [user_histories[user_id][0]] +
                user_histories[user_id][-20:]
            )

        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    # Start Flask ping server in background thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info("Ping server running on port 8080")

    # Start Telegram bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(verify_join_callback, pattern="^verify_join$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
