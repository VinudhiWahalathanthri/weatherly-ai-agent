"""
Weatherly Telegram Bot
-----------------------
Connects Telegram users to the Weatherly AI planning agent.
Run this alongside the FastAPI backend (uvicorn main:app in /backend).

Usage:
  Set TELEGRAM_TOKEN in your .env file, then run:
  python telegram_bot.py
"""

import asyncio
import html
import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

WEATHERLY_API = os.getenv("WEATHERLY_API_URL", "http://localhost:8000")

# Per-user session IDs so the agent remembers context across messages.
user_sessions: dict[str, str] = {}


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def call_agent(user_id: str, message: str) -> dict:
    """POST to the Weatherly planning agent and return the full response."""
    payload = {
        "message": message,
        "session_id": user_sessions.get(user_id),
    }
    resp = requests.post(f"{WEATHERLY_API}/agent/chat", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()


def format_suitability(status: str) -> str:
    icons = {
        "Suitable": "✅", "Suitable (Fallback)": "✅",
        "Caution": "⚠️", "Caution (ML Error)": "⚠️",
        "Unsuitable": "❌", "Unsuitable (High Risk)": "❌",
    }
    return icons.get(status, "🔵")


def build_reply(data: dict) -> tuple[str, InlineKeyboardMarkup | None]:
    """Turn the agent JSON into a nicely formatted Telegram message.

    Uses HTML parse mode (not Telegram's legacy Markdown) — place names,
    addresses, and explanation text routinely contain '_', '*', '(', ')', '.'
    which break Markdown's parser (400 "can't parse entities"). HTML's escaping
    surface is just &, <, > (one html.escape() call), far less error-prone than
    hand-escaping every Markdown special character in dynamic content.
    """
    esc = html.escape
    lines = [f"🌤 <b>Weatherly AI</b>\n\n{esc(data['reply'])}"]

    options = data.get("options", [])
    if options:
        lines.append("\n<b>📊 Top Results:</b>")
        for i, opt in enumerate(options[:3]):
            icon = format_suitability(opt["suitability_status"])
            conf_label = opt.get("confidence_label")
            conf_line = f"\n  <i>{esc(conf_label)}</i>" if conf_label else ""
            lines.append(
                f"\n{icon} <b>{esc(opt['location'].split(',')[0])}</b> — {esc(opt['date'])}\n"
                f"  Score: {opt['score']}/100  |  "
                f"🌡 {opt['temp']}°C  💧 {opt['rain']}mm  💨 {opt['wind']}km/h\n"
                f"  <i>{esc(', '.join(opt['reasons'][:2]))}</i>{conf_line}"
            )

    # Build venue buttons for the top result
    buttons = []
    if options and options[0].get("venues"):
        lines.append(f"\n<b>📍 Nearby venues ({esc(options[0]['location'].split(',')[0])}):</b>")
        for venue in options[0]["venues"][:4]:
            name_short = venue["name"][:28]
            lines.append(f"  • {esc(name_short)} ({esc(venue['type'])}, {venue['distance_km']} km)")
            buttons.append([
                InlineKeyboardButton(
                    f"🗺 {name_short}",
                    url=venue["osm_link"],
                )
            ])
            if venue.get("website"):
                buttons[-1].append(
                    InlineKeyboardButton("🌐 Website", url=venue["website"])
                )

    keyboard = InlineKeyboardMarkup(buttons) if buttons else None
    return "\n".join(lines), keyboard


# ──────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 <b>Welcome to Weatherly AI!</b>\n\n"
        "I help you plan days out, trips, events, and farming activities using weather intelligence.\n\n"
        "<b>Try asking:</b>\n"
        "• <i>What's the weather like in Colombo today?</i>\n"
        "• <i>Is tomorrow good for a beach day in Galle?</i>\n"
        "• <i>Can I organize a wedding in Kandy next month?</i>\n"
        "• <i>Is it safe to harvest rice in Colombo next week?</i>\n\n"
        "Just type your question! 🌤",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Weatherly AI — What I can do:</b>\n\n"
        "🌤 <b>Day &amp; Trip Planning</b>\n"
        "  Real live weather for today/this week, plus longer-range trip planning\n\n"
        "🎉 <b>Event Planning</b>\n"
        "  Wedding venues, outdoor parties, festivals, sports tournaments\n\n"
        "🌾 <b>Farming Advice</b>\n"
        "  Planting windows, harvest timing, irrigation scheduling, frost alerts\n\n"
        "📍 <b>Venue &amp; Hotel Links</b>\n"
        "  I find real nearby venues with map links automatically\n\n"
        "💬 <b>I remember context</b> — ask follow-ups like 'what about next week instead?'\n\n"
        "Type anything to get started!",
        parse_mode="HTML",
    )


async def _typing_keepalive(bot, chat_id: int, stop_event: asyncio.Event) -> None:
    """Telegram's typing indicator auto-expires after ~5s, but the agent call
    can take 10-90s — resend it every 4s until the agent call resolves so the
    chat doesn't go quiet mid-response (which reads as broken)."""
    while not stop_event.is_set():
        try:
            await bot.send_chat_action(chat_id, "typing")
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    text = update.message.text
    chat_id = update.effective_chat.id

    stop_event = asyncio.Event()
    keepalive_task = asyncio.create_task(_typing_keepalive(context.bot, chat_id, stop_event))
    try:
        # call_agent is a blocking `requests.post` — run it off the event loop so
        # the keepalive task above can actually keep firing while it waits.
        data = await asyncio.to_thread(call_agent, user_id, text)
        user_sessions[user_id] = data["session_id"]
        reply, keyboard = build_reply(data)

        options = data.get("options", [])
        top_image = options[0].get("image_url") if options else None
        if top_image:
            try:
                await update.message.reply_photo(
                    photo=top_image,
                    caption=f"📍 {options[0]['location'].split(',')[0]}",
                )
            except Exception as img_err:
                logging.warning("Failed to send destination photo: %s", img_err)

        await update.message.reply_text(
            reply,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except requests.exceptions.Timeout:
        await update.message.reply_text(
            "⏱️ That's taking longer than expected — please try again in a moment."
        )
    except requests.exceptions.ConnectionError:
        await update.message.reply_text(
            "⚠️ The Weatherly backend isn't reachable right now.\n"
            "Please make sure it's running on port 8000."
        )
    except Exception as e:
        logging.error("Agent error: %s", e)
        await update.message.reply_text(
            "Something went wrong — please try again or rephrase your question."
        )
    finally:
        stop_event.set()
        await keepalive_task


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.error("Update caused error: %s", context.error)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> None:
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError(
            "TELEGRAM_TOKEN not set. Add it to your .env file:\n"
            "  TELEGRAM_TOKEN=your-token-here"
        )

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("✅ Weatherly Telegram bot is running. Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
