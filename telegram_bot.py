"""
Weatherly Telegram Bot
-----------------------
Connects Telegram users to the Weatherly AI planning agent.
Run this alongside the FastAPI backend (uvicorn main:app in /backend).

Usage:
  Set TELEGRAM_TOKEN in your .env file, then run:
  python telegram_bot.py
"""

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
    """Turn the agent JSON into a nicely formatted Telegram message."""
    lines = [f"🌤 *Weatherly AI*\n\n{data['reply']}"]

    options = data.get("options", [])
    if options:
        lines.append("\n*📊 Top Results:*")
        for i, opt in enumerate(options[:3]):
            icon = format_suitability(opt["suitability_status"])
            lines.append(
                f"\n{icon} *{opt['location'].split(',')[0]}* — {opt['date']}\n"
                f"  Score: {opt['score']}/100  |  "
                f"🌡 {opt['temp']}°C  💧 {opt['rain']}mm  💨 {opt['wind']}km/h\n"
                f"  _{', '.join(opt['reasons'][:2])}_"
            )

    # Build venue buttons for the top result
    buttons = []
    if options and options[0].get("venues"):
        lines.append(f"\n*📍 Nearby venues ({options[0]['location'].split(',')[0]}):*")
        for venue in options[0]["venues"][:4]:
            name_short = venue["name"][:28]
            lines.append(f"  • {name_short} ({venue['type']}, {venue['distance_km']} km)")
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
        "👋 *Welcome to Weatherly AI!*\n\n"
        "I help you plan events, trips, and farming activities using weather intelligence.\n\n"
        "*Try asking:*\n"
        "• _Can I organize a wedding in Kandy next month?_\n"
        "• _Best beach spots in India six months from now?_\n"
        "• _Is it safe to harvest rice in Colombo next week?_\n"
        "• _Compare Galle vs Kandy for an outdoor party_\n\n"
        "Just type your question! 🌤",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "*Weatherly AI — What I can do:*\n\n"
        "🎉 *Event Planning*\n"
        "  Wedding venues, outdoor parties, festivals, sports tournaments\n\n"
        "🌾 *Farming Advice*\n"
        "  Planting windows, harvest timing, irrigation scheduling, frost alerts\n\n"
        "✈️ *Travel Planning*\n"
        "  Best destinations by season, beach holidays, hiking trips\n\n"
        "📍 *Venue & Hotel Links*\n"
        "  I find real nearby venues with map links automatically\n\n"
        "💬 *I remember context* — ask follow-ups like 'what about next week instead?'\n\n"
        "Type anything to get started!",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    text = update.message.text

    # Show typing indicator while the agent thinks (takes 10-60s)
    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        data = call_agent(user_id, text)
        user_sessions[user_id] = data["session_id"]
        reply, keyboard = build_reply(data)
        await update.message.reply_text(
            reply,
            parse_mode="Markdown",
            reply_markup=keyboard,
            disable_web_page_preview=True,
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
