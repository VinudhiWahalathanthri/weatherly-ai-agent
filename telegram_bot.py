"""
Weatherly Telegram Bot
-----------------------
A thin Telegram front-end onto the same AI planning agent used by the web app.
Every message is forwarded to the FastAPI backend's /agent/chat endpoint
(see backend/agent.py) and the reply is sent back as-is — no logic lives here.

Requires the FastAPI backend to already be running (uvicorn main:app, in /backend).

Setup:
  1. Create a bot with @BotFather on Telegram and copy its token.
  2. Put TELEGRAM_TOKEN=<token> in a .env file at the project root
     (optionally also BACKEND_URL if the backend isn't at the default).
  3. Run: python telegram_bot.py
"""

import os

import requests
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

# Maps a Telegram chat to the agent's session_id, so follow-ups
# ("what about next week instead?") keep working like they do in the web chat.
CHAT_SESSIONS: dict[int, str] = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hey! I'm Weatherly. Tell me what you're planning — a wedding, a hike, a "
        "beach day, a harvest — and where/when, and I'll check the weather and "
        "score whether it's a good idea."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    CHAT_SESSIONS.pop(update.effective_chat.id, None)
    await update.message.reply_text("Started a fresh conversation.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    message_text = update.message.text or ""
    session_id = CHAT_SESSIONS.get(chat_id)

    await update.message.chat.send_action("typing")

    try:
        resp = requests.post(
            f"{BACKEND_URL}/agent/chat",
            json={"message": message_text, "session_id": session_id},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        await update.message.reply_text(
            f"Sorry, I couldn't reach the weather backend ({e}). "
            f"Make sure it's running at {BACKEND_URL}."
        )
        return

    CHAT_SESSIONS[chat_id] = data.get("session_id", session_id)
    reply = data.get("reply") or "Sorry, I didn't get a usable reply — try rephrasing."

    options = data.get("options") or []
    if options:
        reply += _format_venues(options[0])

    await update.message.reply_text(reply, parse_mode="Markdown", disable_web_page_preview=True)


def _format_venues(winner: dict) -> str:
    """The web chat renders venues as separate cards (see ChatPlanner.tsx);
    Telegram only gets the plain-text reply, so fold the same data in as text
    instead of silently dropping it."""
    sections = []

    online_venues = winner.get("online_venues") or []
    if online_venues:
        lines = [f"🌐 *Venue recommendations:*"]
        for v in online_venues[:4]:
            line = f"• *{v.get('name', 'Unknown')}*"
            if v.get("description"):
                line += f" — {v['description']}"
            if v.get("url"):
                line += f" ([link]({v['url']}))"
            lines.append(line)
        sections.append("\n".join(lines))

    venues = winner.get("venues") or []
    if venues:
        lines = [f"📍 *Nearby venues & hotels:*"]
        for v in venues[:4]:
            line = f"• *{v.get('name', 'Unknown')}* ({v.get('type', 'Place')}, {v.get('distance_km', '?')} km)"
            if v.get("osm_link"):
                line += f" — [map]({v['osm_link']})"
            lines.append(line)
        sections.append("\n".join(lines))

    return ("\n\n" + "\n\n".join(sections)) if sections else ""


def main() -> None:
    if not TELEGRAM_TOKEN:
        raise SystemExit(
            "TELEGRAM_TOKEN is not set. Add it to a .env file at the project root "
            "(see README's Telegram bot setup section)."
        )

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"Weatherly Telegram bot running, forwarding to {BACKEND_URL}...")
    app.run_polling()


if __name__ == "__main__":
    main()
