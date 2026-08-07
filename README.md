# Weatherly
Weatherly is an AI weather-planning assistant.All you have to do is Tell it what you want to do, a wedding, a beach day, a hike, a harvest and it pulls real climate/forecast data, scores the comfort/safety/suitability of your plan, explains its reasoning in plain language, and points you to real nearby venues.

Made with ❤️ By Vinudhi, Sinura, Venuki and Pulesh for IDEALIZE'26

It has two front ends onto the same backend:

- **Plan a Trip** : a conversational AI agent (chat interface).
- **Advanced Search** : a manual mode where you pick a location on a map, an activity, and a date range yourself, and get the raw forecast + suitability charts.

<img width="2560" height="3576" alt="localhost_5173_(Nest Hub Max)" src="https://github.com/user-attachments/assets/2ab6a037-cc93-43be-9656-0a984c7b67fe" />

<img width="1483" height="928" alt="image" src="https://github.com/user-attachments/assets/14aa3850-4c85-48b0-967b-d9502644abba" />


## Features

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
- **Voice input** — hold the mic button and speak your request in English
- **Telegram bot** — the same agent, reachable from Telegram (see [`telegram_bot.py`](./telegram_bot.py)).

### Advanced Search (manual mode)

For when you want to drive directly instead of asking:

- Pick a location by clicking a Leaflet/OpenStreetMap map (or search).
- Choose an activity from curated categories (outdoor events, nature & leisure, land sports, water activities, adventure & aviation).
- Pick a date range and see the forecast, suitability status, and comfort/risk charts for each day.
- Export results as CSV, JSON, or a PNG snapshot of the results panel.

---

## How it works — data & AI sources

| Layer | Source | Used for |
|---|---|---|
| **Historical climate data** | [NASA POWER API](https://power.larc.nasa.gov/) 
| **Long-range forecasting** | [Prophet](https://facebook.github.io/prophet/) (Meta's time-series library) | Projects NASA POWER's historical climatology forward to estimate what a *future* date is likely to look like, since no forecast model predicts actual weather that far out. |
| **Near-term live forecast** | [Open-Meteo API](https://open-meteo.com/) | Real forecast data (not climatology) for "today", "tomorrow", "this weekend" — anything within ~16 days. Free, keyless. |
| **Suitability classification** | Custom `RandomForestClassifier` (scikit-learn), trained via [`backend/train_model.py`](./backend/train_model.py) on [`backend/train_data.csv`](./backend/train_data.csv) | A trained ML model that classifies raw weather conditions + activity type into a suitability label, feeding into the scoring engine. |
| **Comfort/Safety/Suitability scoring** | [`backend/scoring_engine.py`](./backend/scoring_engine.py) | Per-activity scoring profiles (weddings, hikes, farming, etc.) that turn raw numbers into three separate 0–100 scores plus a natural-language explanation — not just a relabeled ML output. |
| **Farming risk analysis** | [`backend/farming.py`](./backend/farming.py) | Crop-specific temperature/rainfall/wind/humidity profiles layered on the same NASA POWER data — no extra API needed. |
| **Geocoding** | [OpenStreetMap Nominatim](https://nominatim.org/) | Turns place names into coordinates. Rate-limited to 1 request/second per Nominatim's usage policy. |
| **Venue discovery** | [OpenStreetMap Overpass API](https://overpass-api.de/) | Finds real hotels, event venues, parks, and attractions near a location — free, no key. |
| **Map tiles** | [Leaflet](https://leafletjs.com/) + OpenStreetMap tiles | Powers the Advanced Search map — no Google Maps key required. |
| **Destination photos** | Wikipedia REST Summary API | Best-effort photo lookup for the recommended place. |
| **Natural-language understanding** (intent extraction + agent decisions) | **Gemini** → **local Ollama model** → **rule-based extractor**, in that order 

<img width="1880" height="972" alt="Screenshot 2026-08-07 184538" src="https://github.com/user-attachments/assets/a5fb69d1-6a33-4a4d-ba78-2fc03711ede6" />

<img width="551" height="923" alt="Screenshot 2026-08-07 192301" src="https://github.com/user-attachments/assets/346526a8-d359-4185-9bd9-dfb00e07da41" />

<img width="387" height="921" alt="Screenshot 2026-08-07 192248" src="https://github.com/user-attachments/assets/5dfa0a09-97d8-42ce-bb3e-3a8c94cc54dd" />

## Prerequisites

- [Node.js](https://nodejs.org/) (for the frontend)
- [Python](https://www.python.org/) (for the backend)
- [pip](https://pip.pypa.io/en/stable/)
- [virtualenv](https://virtualenv.pypa.io/en/latest/)
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

The backend runs at `http://127.0.0.1:8000`. 

### 3. Ollama

This step is what makes the AI agent understand free-text requests well **without needing a cloud API key**.

1. Download and install Ollama for your OS from **[ollama.com/download](https://ollama.com/download)**.
2. Start Ollama (it runs a local server on `http://localhost:11434`; on Windows/macOS the installer sets it up to run automatically, on Linux run `ollama serve`).
3. Pull a model matching the one configured in [`backend/planning_agent.py`](./backend/planning_agent.py) (`OLLAMA_MODEL`, currently `qwen3.5`):

   ```bash
   ollama pull qwen3.5
   ```

### 5. Telegram bot

To reach the same AI agent from Telegram:

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy its token into `TELEGRAM_TOKEN` in the root `.env`.
2. Make sure the FastAPI backend is running (`uvicorn main:app` in `/backend`).
3. From the project root:

   ```bash
   python telegram_bot.py
   ```


