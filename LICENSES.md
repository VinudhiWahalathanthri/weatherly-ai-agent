# Third-Party Licenses & API Terms — Weatherly AI

This document lists every third-party tool, model, API, and dataset used by
Weatherly AI, its license/terms, and any obligations we need to meet before
submitting or deploying. Review this before the final submission.

## AI / LLM layer

| Component | License / Terms | Notes & obligations |
|---|---|---|
| **Ollama** (runtime) | MIT | Fully open source, no restrictions. |
| **Llama 3** (via Ollama) | [Meta Llama 3 Community License](https://www.llama.com/llama3/license/) — *source-available, not OSI-approved open source* | Must include the license + an **"Built with Meta Llama 3"** attribution notice if the app is distributed. Cannot use Llama 3's outputs to train a competing foundation model. If Weatherly ever exceeds 700M monthly active users, a separate commercial license from Meta is required (not a practical concern at hackathon/early stage, but worth knowing). |
| **Mistral 7B** (via Ollama, alternative) | **Apache 2.0** — fully permissive open source | **Recommended over Llama 3** for this submission: no attribution/MAU clauses to track, and it satisfies the brief's "open-source" guidance more cleanly. Swap by setting `OLLAMA_MODEL = "mistral"` in `backend/planning_agent.py` and running `ollama pull mistral`. |

**Recommendation:** default to Mistral 7B unless there's a specific reason to prefer Llama 3 — it removes all the license bookkeeping above.

## Weather & geographic data

| Component | License / Terms | Notes & obligations |
|---|---|---|
| **NASA POWER API** | Public domain (U.S. Government work); NASA requests but does not require attribution | No sign-up cost. Rate limits apply per NASA's fair-use policy — don't hammer it with parallel requests. |
| **Open-Meteo API** | [CC BY 4.0](https://open-meteo.com/en/license) (data), source code MIT | Free for non-commercial use; commercial use should follow their API terms (currently free tier under fair use, paid tiers for high volume). Attribution: "Weather data by Open-Meteo.com". |
| **OpenStreetMap / Nominatim** (geocoding) | Data: **ODbL** (share-alike); Nominatim service: [Usage Policy](https://operations.osmfoundation.org/policies/nominatim/) | **Must**: (1) cap requests to 1/second — already enforced in `planning_agent.py`; (2) send a real identifying User-Agent (update the placeholder email in `geocode_location()` before submitting); (3) display "© OpenStreetMap contributors" attribution somewhere in the UI; (4) no bulk/systematic scraping — we only geocode on-demand per user request, which is compliant. For production scale, self-host Nominatim or use a paid geocoder instead of the shared public instance. |
| **Leaflet + OpenStreetMap tiles** (map picker in `HomeContent.tsx`) | Leaflet: BSD-2-Clause. Map tiles: [OpenStreetMap Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/) (free, attribution required — already added as an in-map credit) | **No API key, no billing, no cost.** This replaced the earlier Google Maps JavaScript API integration. For anything beyond light/demo traffic, consider a paid tile provider (MapTiler, Mapbox, Stadia Maps) or self-hosting tiles — the public `tile.openstreetmap.org` servers are volunteer-run and rate-limited. |
| ~~Google Maps JavaScript API~~ | *(Removed)* | Previously used for the map picker; removed in favor of the free Leaflet/OpenStreetMap stack above so the project has zero paid dependencies. If you ever revert to it, treat the key that used to be hardcoded in this repo as compromised and use a fresh, restricted one via an env var. |

## ML / data science stack (backend)

| Component | License |
|---|---|
| FastAPI | MIT |
| Pydantic | MIT |
| Uvicorn | BSD-3 |
| Prophet (Meta) | MIT |
| scikit-learn | BSD-3 |
| pandas | BSD-3 |
| NumPy | BSD-3 |
| joblib | BSD-3 |
| requests | Apache 2.0 |

All fully permissive — no action needed.

## Frontend stack

| Component | License |
|---|---|
| React / React DOM | MIT |
| Vite | MIT |
| Tailwind CSS | MIT |
| Radix UI primitives | MIT |
| lucide-react | ISC |
| framer-motion | MIT |
| Leaflet | BSD-2-Clause |
| **react-leaflet** | **Hippocratic License 2.1** — an "ethical source" license, *not* OSI-approved open source. Permissive for essentially all normal use; it only restricts organizations engaged in specific defined harms (e.g. human rights violations). Worth noting explicitly since the brief asks for "well-documented" licensing — this one is a bit unusual and evaluators may ask about it. Now actively used for the free map picker (see above). |
| html2canvas / html-to-image | MIT |

## Summary of action items before submission

1. **~~Regenerate the Google Maps API key~~** — no longer needed; Google Maps has been removed and replaced with free OpenStreetMap/Leaflet tiles.
2. **Set a real contact email** in the Nominatim `User-Agent` header in `backend/planning_agent.py`.
3. OSM attribution is already shown as an in-map credit (Leaflet's `TileLayer attribution` prop) — no extra work needed, just don't remove it.
4. Consider switching the LLM from Llama 3 to **Mistral 7B** for cleaner, fully-permissive licensing.
5. Keep `.env` out of version control (already handled via `.gitignore`) — currently there's nothing sensitive to put in it, since the project has zero paid/keyed dependencies.