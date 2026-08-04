


# Weatherly

Will it rain on my parade.
---

## Prerequisites

Make sure you have the following installed:

- [Node.js](https://nodejs.org/)
- [Python](https://www.python.org/)
- [pip](https://pip.pypa.io/en/stable/)
- [virtualenv](https://virtualenv.pypa.io/en/latest/)

---

## Getting Started

### Frontend

1. Navigate to the project root.
2. Install dependencies:

```bash
npm install
````

3. Run the development server:

```bash
npm run dev
```

The frontend will now be running on `http://localhost:5173`.

---

### Backend

1. Navigate to the backend folder:

```bash
cd backend
```

2. Create a virtual environment (if not already created):

```bash
python -m venv venv
```

3. Activate the virtual environment:

* **Windows:**

```bash
.\venv\Scripts\activate
```

* **macOS/Linux:**

```bash
source venv/bin/activate
```


5. Install Dependencies
```bash
pip install -r requirements.txt
```

6. Run the backend server:

```bash
uvicorn main:app --reload
```

The backend will now be running on `http://127.0.0.1:8000`.

---

## AI Planning Agent 

`POST /agent/chat` is a real tool-using agent, not a single prompt-to-answer wrapper:

1. **Understands** the request (`planning_agent.extract_intent` — tries a local Ollama LLM, falls back to a rule-based parser).
2. **Plans** a strategy based on what's actually being asked:
   - `direct_lookup` — one specific place + date
   - `compare_locations` — "Kandy or Galle?" → geocodes + forecasts each candidate
   - `scan_best_date` — "safest date for..." → samples several windows across the month to find the best day
3. **Calls tools** to gather observations: `geocode_location` (OpenStreetMap), `run_prediction` (NASA POWER + Prophet + the ML suitability model) — potentially several times per request depending on the plan.
4. **Scores and ranks** every observation with an explainable decision function (`agent.score_option`) — not just relabeling the ML output, but a real comfort/safety score with stated reasons.
5. **Remembers** context per session, so follow-ups like *"what about next week instead?"* reuse the location/activity from earlier in the conversation without needing to repeat it.
6. Returns a **visible reasoning trace** (`steps`) alongside the answer, so you can see exactly which tools ran and why.

See `backend/agent.py` for the implementation. `backend/forecasting.py` holds the NASA/Prophet/ML pipeline as a standalone module the agent calls as a tool. `backend/planning_agent.py` holds intent extraction, geocoding, and date resolution.

Third-party tool/model/API licensing is documented in [`LICENSES.md`](./LICENSES.md) — review it before submission (there's a couple of action items, like regenerating the Google Maps key).

---

## Running the Full Project

Once both frontend and backend servers are running, you can access the full application via your browser at the frontend URL (`http://localhost:5173`).

---

## Project Structure

```
project-root/
│
├── src/
│   ├── components/
│   │   ├── ChatPlanner.tsx      # AI Planning Agent chat UI
│   │   └── HomeContent.tsx      # Manual Mode UI
│   └── ...
├── public/
└── package.json
│
├── backend/
│   ├── main.py            # FastAPI routes (/predict, /agent/chat)
│   ├── agent.py            # The agent: planner, tools, decision engine, memory
│   ├── forecasting.py       # NASA POWER + Prophet + ML pipeline (tool)
│   ├── planning_agent.py    # Intent extraction, geocoding, date resolution
│   └── requirements.txt
│
├── LICENSES.md
├── .env.example
└── README.md
```
