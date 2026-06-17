import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from openai import OpenAI

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_KEY_HERE")
ADMIN_ID = 8180209483
GPT_MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = "You are a helpful AI assistant."

CHANNELS = [
    {"id": -1002090323246, "name": "Main Channel", "invite": "https://t.me/+gvybwxOt3Z8xZGI9"},
    {"id": -1001167075214, "name": "Updates Channel", "invite": "https://t.me/+ylu_V8Dh9uowM2Y1"}
]

WELCOME_PHOTO = "welcome.jpg"
WELCOME_CAPTION = (
    "🎉 <b>Welcome, {name}!</b>\n\n"
    "I'm your personal AI assistant powered by GPT.\n\n"
    "🤖 Answer any question\n"
    "💡 Help you brainstorm ideas\n"
    "📝 Write & summarize content\n"
    "🔧 Help with code\n\n"
    "Just send me a message to get started!\n"
    "Use /reset anytime to clear our chat history.\n\n"
    "<i>⚡ Powered by GPT-4o Mini</i>"
)
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)
user_histories: dict[int, list] = {}


async def get_unjoined(bot, user_id):
    unjoined = []
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(ch["id"], user_id)
            if member.status not in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
                unjoined.append(ch)
        except:
            unjoined.append(ch)
    return unjoined


async def send_force_join(message, name, unjoined):
    text = (
        f"👋 Hey <b>{name}</b>!\n\n"
        f"🔒 Join all channels below to use this bot:\n\n"
        + "\n".join(f"🔴 {ch['name']}" for ch in unjoined)
        + "\n\nThen press ✅ Verify below."
    )
    buttons = [[InlineKeyboardButton(f"➕ Join {ch['name']}", url=ch["invite"])] for ch in unjoined]
    buttons.append([InlineKeyboardButton("✅ I've Joined — Verify", callback_data="verify")])
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")


async def send_welcome(bot, chat_id, name):
    caption = WELCOME_CAPTION.format(name=name)
    try:
        await bot.send_photo(chat_id=chat_id, photo=WELCOME_PHOTO, caption=caption, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    unjoined = await get_unjoined(context.bot, user.id)
    if unjoined:
        await send_force_join(update.message, user.first_name, unjoined)
    else:
        await send_welcome(context.bot, update.effective_chat.id, user.first_name)


async def verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    unjoined = await get_unjoined(context.bot, user.id)
    if unjoined:
        await query.answer(f"❌ Still need to join: {', '.join(c['name'] for c in unjoined)}", show_alert=True)
    else:
        await query.delete_message()
        await send_welcome(context.bot, query.message.chat_id, user.first_name)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    unjoined = await get_unjoined(context.bot, user.id)
    if unjoined:
        await send_force_join(update.message, user.first_name, unjoined)
        return
    user_histories.pop(user.id, None)
    await update.message.reply_text("🔄 Cleared! Start fresh.")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Not authorized.")
        return
    await update.message.reply_text(f"📊 Active users: <b>{len(user_histories)}</b>", parse_mode="HTML")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    unjoined = await get_unjoined(context.bot, user.id)
    if unjoined:
        await send_force_join(update.message, user.first_name, unjoined)
        return

    if user.id not in user_histories:
        user_histories[user.id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_histories[user.id].append({"role": "user", "content": update.message.text})
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=user_histories[user.id],
            max_tokens=1000,
        )
        reply = response.choices[0].message.content
        user_histories[user.id].append({"role": "assistant", "content": reply})
        if len(user_histories[user.id]) > 21:
            user_histories[user.id] = [user_histories[user.id][0]] + user_histories[user.id][-20:]
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error(f"GPT error: {e}")
        await update.message.reply_text("⚠️ Something went wrong. Try again.")


if __name__ == "__main__":
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(verify, pattern="^verify$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)
