"""
Weatherly AI Planning Agent
----------------------------
This is a genuine tool-using agent, not a single-prompt wrapper. For every
request it:

  1. Extracts intent from the message               (tool: extract_intent)
  2. PLANS a strategy based on what's being asked     (branches: compare / scan / direct)
  3. Calls forecasting + geocoding tools, sometimes several times, to gather
     observations                                     (tools: geocode, forecast)
  4. Scores every observation with a consistent, explainable decision function
     (the "Decision Engine")                          (tool: score_option)
  5. Ranks the observations and produces a recommendation + a visible
     step-by-step reasoning trace
  6. Remembers prior turns per session so follow-ups ("what about Galle
     instead?") don't need to repeat context           (memory)

None of this is hardcoded to "one LLM call -> one answer" — the branch taken,
the number of tool calls, and the final answer all depend on what the agent
discovers as it goes.
"""

import re
from datetime import datetime, timedelta

from planning_agent import extract_intent, geocode_location, resolve_date_phrase, resolve_scan_range, get_country_city_suggestions
from forecasting import run_prediction
from venue_discovery import find_venues
from farming import farming_analysis
from scoring_engine import compute_scores, explain_decision

_FARMING_KEYWORDS = {
    "farming", "farm", "harvest", "planting", "plant", "crop", "crops", "rice",
    "wheat", "maize", "corn", "tea", "coconut", "rubber", "sugarcane", "vegetable",
    "vegetables", "irrigation", "livestock", "agricultural", "agriculture", "paddy",
    "sowing", "sow", "cultivat",
}


def _geo_reply(loc_name: str, geo_detail: str) -> str:
    """Build a helpful user-facing reply when geocoding fails."""
    if geo_detail.startswith("TOO_BROAD:"):
        return geo_detail[len("TOO_BROAD:"):].strip()
    return f"I couldn't locate \"{loc_name}\" ({geo_detail}). Try naming a specific city."


def _expand_country_locations(candidate_locations: list[str], activity: str, steps: list[dict]) -> list[str]:
    """Replace country-level names with specific city candidates based on activity.
    E.g. 'India' + 'beach vacation' → ['Goa, India', 'Varkala, India', 'Pondicherry, India'].
    City-level names pass through unchanged after one geocode check."""
    expanded: list[str] = []
    for loc_name in candidate_locations:
        lat, lon, geo_detail = geocode_location(loc_name)
        if lat is not None:
            # Already a valid city-level location — keep it as-is.
            expanded.append(loc_name)
            continue
        if geo_detail.startswith("TOO_BROAD:"):
            city_suggestions = get_country_city_suggestions(loc_name, activity)
            if city_suggestions:
                city_labels = ", ".join(c.split(",")[0] for c in city_suggestions[:4])
                steps.append({
                    "step": "Expand to cities",
                    "tool": "country_city_suggestions",
                    "detail": (
                        f"'{loc_name}' is a country — auto-selected {len(city_suggestions)} "
                        f"candidate cities for {activity}: {city_labels}"
                    ),
                })
                expanded.extend(city_suggestions[:4])
            else:
                steps.append({
                    "step": "Geocode",
                    "tool": "geocode_location",
                    "detail": _geo_reply(loc_name, geo_detail),
                })
        else:
            steps.append({
                "step": "Geocode",
                "tool": "geocode_location",
                "detail": _geo_reply(loc_name, geo_detail),
            })
    return expanded

# ---------------------------------------------------------------------------
# Session memory (in-memory for this demo — swap for Redis/DB in production)
# ---------------------------------------------------------------------------
SESSIONS: dict[str, dict] = {}

SUITABILITY_RANK = {"Suitable": 0, "Suitable (Fallback)": 0, "Caution": 1, "Caution (ML Error)": 1,
                     "Unsuitable": 2, "Unsuitable (High Risk)": 2}


def _get_session(session_id: str) -> dict:
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"last_intent": {}, "history": []}
    return SESSIONS[session_id]


_FOLLOWUP_SIGNALS = {
    "instead", "what about", "how about", "and what", "what if",
    "try", "change to", "switch to", "same but", "same for",
}

def _is_followup(message: str) -> bool:
    """Heuristic: short messages or explicit follow-up phrases reuse session context."""
    lower = message.lower()
    if any(sig in lower for sig in _FOLLOWUP_SIGNALS):
        return True
    # Very short messages (≤6 words) are almost always follow-ups.
    return len(message.split()) <= 6


def _merge_with_memory(intent: dict, message: str, session: dict) -> dict:
    """Fills gaps in the new intent using the last known intent for this session,
    but ONLY for genuine follow-up messages — not brand-new questions.
    This prevents 'what about Tokyo?' from inheriting 'wedding in Kandy' as its activity."""
    last = session.get("last_intent") or {}
    merged = dict(intent)

    if not _is_followup(message):
        # New question — only inherit if this specific field is completely absent
        # AND the message gives no hint of a different value.
        # Location specifically: never inherit unless it's clearly a follow-up.
        for key in ("date_phrase", "activity", "event_size"):
            if not merged.get(key) and last.get(key):
                merged[key] = last[key]
        # Do NOT inherit location for new questions — let the agent ask the user.
    else:
        for key in ("location", "date_phrase", "activity", "event_size"):
            if not merged.get(key) and last.get(key):
                merged[key] = last[key]
    return merged


# ---------------------------------------------------------------------------
# TOOL: decision engine — wraps scoring_engine for per-option scoring
# ---------------------------------------------------------------------------
def score_option(pred: dict, activity: str = "outdoor activity") -> dict:
    """Returns Comfort/Safety/Suitability/Overall scores using activity-specific engine."""
    scores = compute_scores(pred, activity)
    reasons = scores["positives"][:2] + scores["risks"][:1]
    if not reasons:
        reasons = ["conditions within acceptable range"]
    return {
        "score": scores["overall"],
        "overall": scores["overall"],
        "comfort": scores["comfort"],
        "safety": scores["safety"],
        "suitability": scores["suitability"],
        "grade": scores["grade"],
        "reasons": reasons,
        "risks": scores["risks"],
        "positives": scores["positives"],
        "tips": scores["tips"],
        "profile_name": scores["profile_name"],
    }


# ---------------------------------------------------------------------------
# TOOL: expand a single window into several sample points across a wider
# range, used when the user wants the *best* date rather than a fixed one
# ---------------------------------------------------------------------------
def sample_windows_in_range(start: datetime, end: datetime, max_samples: int = 4) -> list[tuple[datetime, datetime]]:
    span_days = max((end - start).days, 1)
    if span_days <= 7:
        return [(start, end)]

    step = span_days / max_samples
    windows = []
    for i in range(max_samples):
        w_start = start + timedelta(days=round(i * step))
        w_end = w_start + timedelta(days=min(6, span_days - round(i * step)))
        windows.append((w_start, w_end))
    return windows


# ---------------------------------------------------------------------------
# TOOL: split a message into multiple candidate locations for comparison
# ---------------------------------------------------------------------------
def split_candidate_locations(raw_location: str | None, message: str) -> list[str]:
    if not raw_location:
        return []
    # "Kandy or Galle", "Kandy vs Galle", "Kandy, Galle" (in the raw location span)
    parts = re.split(r"\s+(?:or|vs\.?|versus)\s+|\s*,\s*", raw_location)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else [raw_location]


def _best_date_for_predictions(predictions: dict, activity: str = "outdoor activity") -> tuple[str | None, dict | None, dict | None]:
    """Reduces a predictions dict down to its single best (date, pred, scoring) tuple."""
    best_date, best_pred, best_scoring = None, None, None
    for date_str, pred in sorted(predictions.items()):
        scoring = score_option(pred, activity)
        if best_scoring is None or scoring["score"] > best_scoring["score"]:
            best_date, best_pred, best_scoring = date_str, pred, scoring
    return best_date, best_pred, best_scoring


# ---------------------------------------------------------------------------
# THE AGENT
# ---------------------------------------------------------------------------
def run_agent(message: str, session_id: str) -> dict:
    session = _get_session(session_id)
    steps = []

    # Step 1 — understand the request
    raw_intent = extract_intent(message)
    intent = _merge_with_memory(raw_intent, message, session)
    steps.append({
        "step": "Understand request",
        "tool": "extract_intent",
        "detail": f"location={intent.get('location')!r}, date={intent.get('date_phrase')!r}, activity={intent.get('activity')!r}"
                  + (" (filled in from earlier in this conversation)" if raw_intent.get("location") != intent.get("location") else ""),
    })

    activity = intent.get("activity") or "outdoor activity"
    lower_msg = message.lower()

    # Step 2 — PLAN: decide a strategy based on what's actually being asked
    candidate_locations = split_candidate_locations(intent.get("location"), message)
    wants_comparison = len(candidate_locations) > 1
    wants_best_date = any(kw in lower_msg for kw in ["safest date", "best date", "best day", "which date", "safest day"]) and not wants_comparison

    # Expand any country-level names to specific city candidates before planning.
    # This allows "beach vacation in India" to auto-select coastal Indian cities.
    # Note: geocoding is cached implicitly by the rate-limiter sleep, so cities
    # that were already validated here won't be penalised again in the plan loop.
    if candidate_locations:
        candidate_locations = _expand_country_locations(candidate_locations, activity, steps)
        # Re-evaluate comparison intent after expansion (1 country → N cities = compare).
        wants_comparison = len(candidate_locations) > 1

    if wants_comparison:
        plan_name = "compare_locations"
    elif wants_best_date:
        plan_name = "scan_best_date"
    else:
        plan_name = "direct_lookup"

    steps.append({
        "step": "Choose a plan",
        "tool": "planner",
        "detail": f"Selected '{plan_name}' strategy based on the request phrasing.",
    })

    if not candidate_locations:
        wants_location_rec = any(kw in lower_msg for kw in ["best location", "where should", "where can", "which location", "suggest a place", "recommend a place"])
        if wants_location_rec:
            reply = (
                "I'd love to help pick the best location! I need a region to search within — "
                "could you name a city or area? For example: \"What's the best spot for an "
                "outdoor party near Colombo next week?\" or compare two places like "
                "\"Kandy or Galle next weekend?\""
            )
        else:
            reply = "I couldn't tell which location you mean — could you name a city or place?"
        return {"reply": reply, "intent": intent, "steps": steps, "options": []}


    start_date, end_date = resolve_date_phrase(intent.get("date_phrase") or "next month")
    steps.append({
        "step": "Resolve dates",
        "tool": "resolve_date_phrase",
        "detail": f"'{intent.get('date_phrase') or 'next month'}' -> {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
    })

    options = []  # each: {location_name, lat, lon, date, pred, scoring}

    if plan_name == "compare_locations":
        for loc_name in candidate_locations:
            lat, lon, geo_detail = geocode_location(loc_name)
            if lat is None:
                msg = _geo_reply(loc_name, geo_detail)
                steps.append({"step": "Geocode", "tool": "geocode_location", "detail": msg})
                continue
            resolved_name = geo_detail
            steps.append({"step": "Geocode", "tool": "geocode_location", "detail": f"'{loc_name}' -> {resolved_name} ({lat:.3f}, {lon:.3f})"})

            result = run_prediction(lat, lon, start_date, end_date, activity)
            steps.append({"step": "Forecast", "tool": "run_prediction", "detail": f"{resolved_name}: {len(result['predictions'])} day(s) modeled via NASA POWER + Prophet"})

            best_date, best_pred, scoring = _best_date_for_predictions(result["predictions"], activity)
            if best_date:
                options.append({
                    "location_name": resolved_name, "lat": lat, "lon": lon,
                    "date": best_date, "pred": best_pred, "scoring": scoring,
                    "confidence": result.get("confidence", "low"),
                    "confidence_label": result.get("confidence_label", ""),
                })

    elif plan_name == "scan_best_date":
        loc_name = candidate_locations[0]
        lat, lon, geo_detail = geocode_location(loc_name)
        if lat is None:
            msg = _geo_reply(loc_name, geo_detail)
            steps.append({"step": "Geocode", "tool": "geocode_location", "detail": msg})
            return {"reply": msg, "intent": intent, "steps": steps, "options": []}
        resolved_name = geo_detail
        steps.append({"step": "Geocode", "tool": "geocode_location", "detail": f"'{loc_name}' -> {resolved_name}"})

        scan_start, scan_end = resolve_scan_range(intent.get("date_phrase") or "next month")
        windows = sample_windows_in_range(scan_start, scan_end, max_samples=4)
        steps.append({"step": "Plan date scan", "tool": "sample_windows_in_range", "detail": f"Scanning {scan_start.strftime('%Y-%m-%d')}–{scan_end.strftime('%Y-%m-%d')} in {len(windows)} window(s) to find the single best day"})

        for w_start, w_end in windows:
            result = run_prediction(lat, lon, w_start, w_end, activity)
            steps.append({"step": "Forecast", "tool": "run_prediction", "detail": f"{w_start.strftime('%Y-%m-%d')}–{w_end.strftime('%Y-%m-%d')}: {len(result['predictions'])} day(s) modeled"})
            best_date, best_pred, scoring = _best_date_for_predictions(result["predictions"], activity)
            if best_date:
                options.append({
                    "location_name": resolved_name, "lat": lat, "lon": lon,
                    "date": best_date, "pred": best_pred, "scoring": scoring,
                    "confidence": result.get("confidence", "low"),
                    "confidence_label": result.get("confidence_label", ""),
                })

    else:  # direct_lookup
        loc_name = candidate_locations[0]
        lat, lon, geo_detail = geocode_location(loc_name)
        if lat is None:
            msg = _geo_reply(loc_name, geo_detail)
            steps.append({"step": "Geocode", "tool": "geocode_location", "detail": msg})
            return {"reply": msg, "intent": intent, "steps": steps, "options": []}
        resolved_name = geo_detail
        steps.append({"step": "Geocode", "tool": "geocode_location", "detail": f"'{loc_name}' -> {resolved_name} ({lat:.3f}, {lon:.3f})"})

        result = run_prediction(lat, lon, start_date, end_date, activity)
        steps.append({"step": "Forecast", "tool": "run_prediction", "detail": f"{len(result['predictions'])} day(s) modeled via NASA POWER + Prophet"})

        best_date, best_pred, scoring = _best_date_for_predictions(result["predictions"], activity)
        if best_date:
            options.append({
                "location_name": resolved_name, "lat": lat, "lon": lon,
                "date": best_date, "pred": best_pred, "scoring": scoring,
                "confidence": result.get("confidence", "low"),
                "confidence_label": result.get("confidence_label", ""),
            })

    if not options:
        # Check if all geocoding steps failed with TOO_BROAD — give the specific hint.
        broad_steps = [s for s in steps if s.get("step") == "Geocode" and "TOO_BROAD" not in s["detail"] and "not found" in s["detail"].lower()]
        too_broad_steps = [s for s in steps if s.get("step") == "Geocode" and "Try a specific city" in s["detail"]]
        if too_broad_steps and not broad_steps:
            reply = too_broad_steps[0]["detail"]
        else:
            reply = "I gathered forecasts but couldn't score any usable day — try a narrower date range or a more specific city."
        return {"reply": reply, "intent": intent, "steps": steps, "options": []}

    # Step: decision engine ranks everything gathered so far
    options.sort(key=lambda o: o["scoring"]["score"], reverse=True)
    steps.append({
        "step": "Rank options",
        "tool": "scoring_engine",
        "detail": "Scored " + ", ".join(
            f"{o['location_name'].split(',')[0]} {o['date']} "
            f"(Overall {o['scoring']['score']}/100, "
            f"Comfort {o['scoring'].get('comfort','?')} Safety {o['scoring'].get('safety','?')} "
            f"Suitability {o['scoring'].get('suitability','?')})"
            for o in options
        ),
    })

    winner = options[0]
    # Generate the full explanation for the winner
    winner_explanation = explain_decision(
        scores=winner["scoring"],
        pred=winner["pred"],
        activity=activity,
        location=winner["location_name"].split(",")[0],
        date=winner["date"],
        confidence_label=winner.get("confidence_label", ""),
    )
    reply = _build_reply(plan_name, activity, winner, options, winner_explanation)

    # Farming intelligence — if the query is about an agricultural activity,
    # enrich each option with crop-specific suitability and risk alerts.
    is_farming = any(kw in lower_msg for kw in _FARMING_KEYWORDS)
    for o in options:
        if is_farming:
            o["farming"] = farming_analysis(
                activity,
                temp_c=o["pred"]["T2M"],
                rain_mm=o["pred"]["PRECTOTCORR"],
                wind_kmh=o["pred"]["WS10M"],
            )
        else:
            o["farming"] = None

    if is_farming:
        steps.append({
            "step": "Farming analysis",
            "tool": "farming_analysis",
            "detail": f"Crop suitability scored for {activity} at {options[0]['location_name'].split(',')[0]}: "
                      f"{options[0]['farming']['suitability_label']} ({options[0]['farming']['farming_score']}/100)",
        })

    # Discover nearby venues for each option (best location first).
    # We run this after scoring so we only hit the Overpass API for results
    # the user will actually see (max 2 locations to keep latency down).
    steps.append({
        "step": "Find venues",
        "tool": "find_venues",
        "detail": f"Searching OpenStreetMap for {activity} venues near top result(s)…",
    })
    for o in options[:2]:
        o["venues"] = find_venues(o["lat"], o["lon"], activity)

    # Fill remaining options with empty venue list.
    for o in options[2:]:
        o["venues"] = []

    steps[-1]["detail"] = (
        f"Found {sum(len(o['venues']) for o in options)} venue(s) across {min(2, len(options))} location(s) via Overpass/OpenStreetMap"
    )

    # Save memory for follow-ups
    session["last_intent"] = {**intent, "location": winner["location_name"].split(",")[0]}
    session["history"].append({"message": message, "reply": reply})
    session["history"] = session["history"][-6:]

    return {
        "reply": reply,
        "explanation": winner_explanation,
        "intent": intent,
        "plan": plan_name,
        "steps": steps,
        "options": [
            {
                "location": o["location_name"],
                "date": o["date"],
                "suitability_status": o["pred"]["suitability_status"],
                "temp": round(o["pred"].get("feels_like") or o["pred"]["T2M"], 1),
                "temp_actual": round(o["pred"]["T2M"], 1),
                "rain": o["pred"]["PRECTOTCORR"],
                "wind": o["pred"]["WS10M"],
                "humidity": o["pred"].get("RH2M", 70),
                "cloud_pct": o["pred"].get("CLOUD_AMT", o["pred"].get("CloudPct", 50)),
                "temp_max": o["pred"].get("T2M_MAX"),
                "temp_min": o["pred"].get("T2M_MIN"),
                # Multi-dimensional scores
                "score": o["scoring"]["score"],
                "comfort": o["scoring"].get("comfort", o["scoring"]["score"]),
                "safety": o["scoring"].get("safety", o["scoring"]["score"]),
                "suitability": o["scoring"].get("suitability", o["scoring"]["score"]),
                "grade": o["scoring"].get("grade", "C"),
                "profile_name": o["scoring"].get("profile_name", activity),
                # Explanation
                "reasons": o["scoring"]["reasons"],
                "risks": o["scoring"].get("risks", []),
                "positives": o["scoring"].get("positives", []),
                "tips": o["scoring"].get("tips", []),
                # Confidence
                "confidence": o.get("confidence", "low"),
                "confidence_label": o.get("confidence_label", "Historical climate estimate"),
                # Location + extras
                "lat": o["lat"],
                "lon": o["lon"],
                "venues": o.get("venues", []),
                "farming": o.get("farming"),
            }
            for o in options
        ],
    }


def _build_reply(plan_name: str, activity: str, winner: dict, options: list[dict], explanation: str = "") -> str:
    loc = winner["location_name"].split(",")[0]
    date = winner["date"]
    sc = winner["scoring"]
    overall = sc["score"]
    comfort = sc.get("comfort", overall)
    safety = sc.get("safety", overall)
    suitability = sc.get("suitability", overall)
    grade = sc.get("grade", "C")

    # Header line with the three scores
    score_line = (
        f"**Recommended: {loc} — {date}**\n"
        f"Overall: {overall}/100 (Grade {grade}) | "
        f"Comfort: {comfort}/100 | Safety: {safety}/100 | Suitability: {suitability}/100"
    )

    if plan_name == "compare_locations" and len(options) > 1:
        runner_up = options[1]
        ru_loc = runner_up["location_name"].split(",")[0]
        ru_score = runner_up["scoring"]["score"]
        compare_note = f"\n\nOf {len(options)} locations compared, {loc} came out ahead of {ru_loc} ({ru_score}/100)."
        return f"{score_line}{compare_note}\n\n{explanation}"

    if plan_name == "scan_best_date":
        scan_note = f"\n\nI scanned {len(options)} date windows — {date} had the best conditions."
        return f"{score_line}{scan_note}\n\n{explanation}"

    return f"{score_line}\n\n{explanation}"
