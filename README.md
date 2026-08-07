# Weatherly

**Will it rain on my parade?** Weatherly is an AI weather-planning assistant.All you have to do is Tell it what you want to do, a wedding, a beach day, a hike, a harvest and it pulls real climate/forecast data, scores the comfort/safety/suitability of your plan, explains its reasoning in plain language, and points you to real nearby venues.

It has two front ends onto the same backend:

- **Plan a Trip** — a conversational AI agent (chat interface).
- **Advanced Search** — a manual mode where you pick a location on a map, an activity, and a date range yourself, and get the raw forecast + suitability charts.

---

## Table of contents

- [Weatherly](#weatherly)
  - [Table of contents](#table-of-contents)
  - [Features](#features)
    - [🤖 AI Planning Agent (`/agent/chat`)](#-ai-planning-agent-agentchat)
    - [🗺️ Advanced Search (manual mode)](#️-advanced-search-manual-mode)
  - [How it works — data \& AI sources](#how-it-works--data--ai-sources)
    - [The LLM layer — Gemini, Ollama, and the offline fallback](#the-llm-layer--gemini-ollama-and-the-offline-fallback)
  - [Prerequisites](#prerequisites)
  - [Setup](#setup)
    - [1. Frontend](#1-frontend)
    - [2. Backend](#2-backend)
    - [3. Ollama (optional, for local/offline AI)](#3-ollama-optional-for-localoffline-ai)
    - [4. Environment variables](#4-environment-variables)
    - [5. Telegram bot (optional)](#5-telegram-bot-optional)
  - [Running the full project](#running-the-full-project)
  - [Project structure](#project-structure)
  - [Licensing](#licensing)

---

## Features

### 🤖 AI Planning Agent (`/agent/chat`)

This is not a single prompt piped to an LLM — it's a real tool-using agent that runs a **decide → act → observe** loop:

- **Understands your request in plain English** — location, date/date phrase, activity, and event size are extracted from free text (e.g. *"Can I organize a wedding in Kandy next month?"*).
- **Plans a strategy** based on what you're actually asking:
  - `direct_lookup` — one specific place + date.
  - `compare_locations` — *"Kandy or Galle?"* → geocodes and forecasts each candidate.
  - `scan_best_date` — *"safest date for..."* → samples several windows across a month to find the best day.
- **Calls real tools** to gather evidence — geocoding, weather/forecast lookups, farming risk checks, venue search — deciding at runtime which ones it needs and how many times, rather than following a fixed script.
- **Scores every option** on three separate, explainable axes — **Comfort**, **Safety**, **Suitability** — each with its own weighting per activity type (a wedding cares about different things than a hike), plus an overall letter grade (A+ → F) and a plain-language explanation of *why*.
- **Remembers the conversation** — session memory means a follow-up like *"what about next week instead?"* reuses the location/activity you already gave it.
- **Shows its work** — every response includes a visible reasoning trace (which tools ran, in what order, and why) so the agent isn't a black box.
- **Farming intelligence** — ask about planting, harvesting, or irrigation and it switches to crop-specific scoring (temperature/rainfall/wind tolerance per crop) with risks, opportunities, and advice.
- **Real nearby venues** — hotels, event venues, parks, and attractions near your recommended location/date, pulled from live map data, plus a web-searched shortlist of named venues when relevant.
- **Destination photos** — a real photo of the recommended place, when one is available.
- **Downloadable & emailable reports** — turn any recommendation into a Markdown/HTML report you can download or have emailed to you.
- **Voice input** — hold the mic button and speak your request (English, Sinhala, or Tamil).
- **Telegram bot** — the same agent, reachable from Telegram (see [`telegram_bot.py`](./telegram_bot.py)).

### 🗺️ Advanced Search (manual mode)

For when you want to drive directly instead of asking:

- Pick a location by clicking a Leaflet/OpenStreetMap map (or search).
- Choose an activity from curated categories (outdoor events, nature & leisure, land sports, water activities, adventure & aviation).
- Pick a date range and see the forecast, suitability status, and comfort/risk charts for each day.
- Export results as CSV, JSON, or a PNG snapshot of the results panel.

---

## How it works — data & AI sources

Weatherly deliberately layers **free, keyless, or self-hostable** data sources so it works out of the box with zero paid setup, while still supporting better cloud options if you have them.

| Layer | Source | Used for |
|---|---|---|
| **Historical climate data** | [NASA POWER API](https://power.larc.nasa.gov/) | ~20 years of daily temperature, rainfall, wind, humidity, and cloud data for any lat/lon on Earth — the backbone for long-range questions ("next month", "6 months from now"). Public domain, no API key. |
| **Long-range forecasting** | [Prophet](https://facebook.github.io/prophet/) (Meta's time-series library) | Projects NASA POWER's historical climatology forward to estimate what a *future* date is likely to look like, since no forecast model predicts actual weather that far out. |
| **Near-term live forecast** | [Open-Meteo API](https://open-meteo.com/) | Real forecast data (not climatology) for "today", "tomorrow", "this weekend" — anything within ~16 days. Free, keyless. |
| **Suitability classification** | Custom `RandomForestClassifier` (scikit-learn), trained via [`backend/train_model.py`](./backend/train_model.py) on [`backend/train_data.csv`](./backend/train_data.csv) | A trained ML model that classifies raw weather conditions + activity type into a suitability label, feeding into the scoring engine. |
| **Comfort/Safety/Suitability scoring** | [`backend/scoring_engine.py`](./backend/scoring_engine.py) | Per-activity scoring profiles (weddings, hikes, farming, etc.) that turn raw numbers into three separate 0–100 scores plus a natural-language explanation — not just a relabeled ML output. |
| **Farming risk analysis** | [`backend/farming.py`](./backend/farming.py) | Crop-specific temperature/rainfall/wind/humidity profiles layered on the same NASA POWER data — no extra API needed. |
| **Geocoding** | [OpenStreetMap Nominatim](https://nominatim.org/) | Turns place names into coordinates. Rate-limited to 1 request/second per Nominatim's usage policy. |
| **Venue discovery** | [OpenStreetMap Overpass API](https://overpass-api.de/) | Finds real hotels, event venues, parks, and attractions near a location — free, no key. |
| **Map tiles** | [Leaflet](https://leafletjs.com/) + OpenStreetMap tiles | Powers the Advanced Search map — no Google Maps key required. |
| **Destination photos** | Wikipedia REST Summary API | Best-effort photo lookup for the recommended place. |
| **Natural-language understanding** (intent extraction + agent decisions) | **Gemini** → **local Ollama model** → **rule-based extractor**, in that order | See below. |

### The LLM layer — Gemini, Ollama, and the offline fallback

The agent's "brain" (turning your sentence into structured intent, and deciding what to do at each step of its reasoning loop) tries three tiers, in order, so the app **always works even with zero cloud setup**:

1. **Google Gemini** (cloud) — used first if `GEMINI_API_KEY` is set. Fastest and most reliable at structured JSON output.
2. **Local Ollama model** (offline, free) — if Gemini isn't configured, quota-exhausted, or errors, the backend automatically calls a locally running [Ollama](https://ollama.com/) model instead (configured as `qwen3.5` in `backend/planning_agent.py`). This needs Ollama installed and running on your machine — see [setup below](#3-ollama-optional-for-localoffline-ai).
3. **Rule-based extractor** (always available) — if neither an LLM is configured nor reachable, a lightweight regex/keyword-based fallback keeps the agent working, just with less nuanced understanding.

You don't need to configure anything to run the project — the fallback chain handles it — but installing Ollama (or setting a Gemini key) noticeably improves how well the agent understands nuanced requests.

---

## Prerequisites

- [Node.js](https://nodejs.org/) (for the frontend)
- [Python](https://www.python.org/) (for the backend)
- [pip](https://pip.pypa.io/en/stable/)
- [virtualenv](https://virtualenv.pypa.io/en/latest/) (or Python's built-in `venv`, used below)
- **[Ollama](https://ollama.com/)** — optional but recommended. Without it (and without a Gemini key), the agent still runs on the rule-based fallback, but understands requests less flexibly.

---

## Setup

### 1. Frontend

```bash
npm install
npm run dev
```

The frontend runs at `http://localhost:5173`.

### 2. Backend

```bash
cd backend
python -m venv venv
```

Activate the virtual environment:

```bash
# Windows
.\venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

Install dependencies and run the server:

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend runs at `http://127.0.0.1:8000`. The Vite dev server proxies `/predict`, `/agent`, `/health`, and `/weather` requests to it, so the frontend never needs CORS or a hardcoded backend URL in dev.

### 3. Ollama (optional, for local/offline AI)

This step is what makes the AI agent understand free-text requests well **without needing a cloud API key**.

1. Download and install Ollama for your OS from **[ollama.com/download](https://ollama.com/download)**.
2. Start Ollama (it runs a local server on `http://localhost:11434`; on Windows/macOS the installer sets it up to run automatically, on Linux run `ollama serve`).
3. Pull a model matching the one configured in [`backend/planning_agent.py`](./backend/planning_agent.py) (`OLLAMA_MODEL`, currently `qwen3.5`):

   ```bash
   ollama pull qwen3.5
   ```

4. That's it — no code changes needed. On each request, the backend checks `http://localhost:11434/api/tags` for an installed model matching that name and uses it automatically if Gemini isn't configured.

> If you'd rather use a different local model (e.g. one you already have pulled, like `llama3` or `mistral`), just change `OLLAMA_MODEL` in `backend/planning_agent.py` to match its exact tag.

If Ollama isn't installed or isn't running, the backend silently skips it and falls back to the rule-based extractor — nothing breaks.

### 4. Environment variables

Weatherly uses three separate `.env` files. None are required to run the app — they unlock optional/better capabilities.

**Root `.env`** (copy from [`.env.example`](./.env.example)) — used by `telegram_bot.py`:

```bash
TELEGRAM_TOKEN=your-telegram-bot-token   # only needed if running the Telegram bot
WEATHERLY_API_URL=http://localhost:8000  # defaults to this if unset
VITE_GOOGLE_MAPS_API_KEY=...             # currently unused — Advanced Search's map runs on free Leaflet/OpenStreetMap tiles instead. Safe to leave blank.
```

**`backend/.env`** (copy from [`backend/.env.example`](./backend/.env.example)):

```bash
# Optional — enables the fastest/most reliable LLM tier (see the LLM layer above).
# Get a free key at https://aistudio.google.com/apikey
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-3.5-flash

# Optional — only needed to actually send "Email Report" from the chat UI.
# Without these, emailing falls back to offering a download instead.
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASS=your-smtp-password
```

### 5. Telegram bot (optional)

To reach the same AI agent from Telegram:

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token into `TELEGRAM_TOKEN` in the root `.env`.
2. Make sure the FastAPI backend is running (`uvicorn main:app` in `/backend`).
3. From the project root:

   ```bash
   python telegram_bot.py
   ```

---

## Running the full project

With the backend (`uvicorn main:app --reload`) and frontend (`npm run dev`) both running, open `http://localhost:5173` in your browser. Everything else — NASA/Open-Meteo data, geocoding, venue search, and the LLM fallback chain — is wired up automatically.

---

## Project structure

```
project-root/
│
├── src/
│   ├── components/
│   │   ├── ChatPlanner.tsx        # AI Planning Agent chat UI
│   │   ├── CurrentWeatherCard.tsx # "Weather right now" card (geolocation-based)
│   │   ├── HomeContent.tsx        # Advanced Search (manual mode) UI
│   │   └── NavigationBar.tsx
│   └── ...
├── public/
├── package.json
│
├── backend/
│   ├── main.py               # FastAPI routes (/predict, /agent/chat, /weather/now, reports)
│   ├── agent.py               # The agent: planner, tools, decision engine, memory
│   ├── planning_agent.py      # Intent extraction (Gemini → Ollama → rule-based), geocoding, date resolution
│   ├── forecasting.py         # NASA POWER + Prophet + ML pipeline (tool)
│   ├── live_weather.py        # Open-Meteo near-term forecast (tool)
│   ├── scoring_engine.py      # Comfort/Safety/Suitability scoring per activity
│   ├── farming.py             # Crop-specific weather suitability & risk
│   ├── venue_discovery.py     # OpenStreetMap Overpass venue search
│   ├── images.py              # Wikipedia destination photo lookup
│   ├── report_generator.py    # Markdown/HTML planning report builder
│   ├── train_model.py         # Trains the ML suitability classifier
│   ├── activity_suitability_model.pkl / activity_encoder.pkl
│   └── requirements.txt
│
├── telegram_bot.py            # Telegram front end for the same agent
├── LICENSES.md
├── .env.example
└── README.md
```

---

## Licensing

Third-party tool/model/API licensing (NASA, Open-Meteo, OpenStreetMap, Ollama-served models, and all libraries) is documented in [`LICENSES.md`](./LICENSES.md) — review it before deployment or submission.
