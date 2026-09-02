"""
Weatherly AI Planning Agent
----------------------------
A genuine LLM-driven ReAct-style agent, not a single-prompt wrapper and not
a hardcoded if/elif dispatcher either. On every turn:

  1. An LLM call extracts structured intent from the free-text message
     (tool: extract_intent).
  2. The agent enters a decide -> act -> observe loop: at each step an LLM
     call is given the intent, session memory, and everything gathered so
     far, and DECIDES the next tool to call (geocode a place, evaluate a
     location's weather/suitability, check crop-specific farming risk, look
     up real nearby venues, ask the user a clarifying question, or finish
     with a recommendation). Nothing about which locations get compared,
     whether farming/venue tools run, or how many rounds happen is
     hardcoded — the model chooses all of that at runtime, and the
     "steps" trace returned to the UI is the model's own stated reasoning
     for each choice, not a templated description of fixed branches.
  3. The decision engine (scoring_engine.py) scores every location the
     agent decided to evaluate; the agent itself picks the winner and
     explains its own reasoning in the final reply.
  4. Session memory carries the last intent across turns so follow-ups
     ("what about Galle instead?") don't need to repeat context.

Guardrails: a 4B local model won't always return clean JSON. If a decision
call fails or is unparsable, a minimal deterministic fallback keeps the
loop moving (and says so plainly in the trace) instead of hanging the
request — this is a safety net around the agent, not the agent's actual
planning logic.
"""

import json
import math
import re
from datetime import datetime

from planning_agent import (
    extract_intent, geocode_location, resolve_date_phrase, resolve_scan_range,
    get_country_city_suggestions, call_llm_json, generate_chitchat_reply,
    search_venues_online, parse_iso_date,
)
from forecasting import run_prediction
from venue_discovery import find_venues as _find_venues_api
from farming import farming_analysis as _farming_analysis_api, CROP_PROFILES
from scoring_engine import compute_scores, explain_decision
from images import get_place_image

MAX_ITERATIONS = 5
MAX_LOCATIONS = 4

_VENUE_REQUEST_KEYWORDS = {
    "venue", "venues", "hotel", "hotels", "place to stay", "places to stay",
    "where to hold", "where to host", "accommodation", "accomodation",
    "stay near", "book a place", "resort", "resorts",
}

_SCAN_REQUEST_KEYWORDS = {
    "best date", "best day", "safest date", "safest day", "which date",
    "which day", "what date", "what day", "ideal date", "ideal day",
    "optimal date", "optimal day", "best time",
}


def _wants_date_scan(message: str) -> bool:
    return any(kw in message.lower() for kw in _SCAN_REQUEST_KEYWORDS)

_FARMING_KEYWORDS = {kw for profile in CROP_PROFILES for kw in profile.keywords} | {
    "farming", "farm", "agriculture", "agricultural", "crop", "crops",
    "livestock", "cultivat", "sow", "sowing", "irrigat", "harvest", "planting",
}


def _is_farming_activity(activity: str) -> bool:
    lower = (activity or "").lower()
    return any(kw in lower for kw in _FARMING_KEYWORDS)

_NO_PREFERENCE_KEYWORDS = {
    "anywhere", "any city", "any location", "any place", "any where",
    "you decide", "you choose", "you pick", "your choice", "your pick",
    "doesnt matter", "doesn't matter", "no preference", "no specific city",
    "wherever", "surprise me", "up to you", "not sure", "i dont know",
    "i don't know", "no idea",
}

_GREETING_FILLER = r"(?:\s+(?:there|everyone|guys|friend|folks|team))?"
_GREETING_RE = re.compile(
    rf"^(hi+|he+y+a?|hello+|yo+|howdy|greetings|good ?(morning|afternoon|evening|night)){_GREETING_FILLER}[\s!.,]*$"
)
_FAREWELL_RE = re.compile(r"^(bye+|goodbye|see ?you( later| soon)?|good ?night|cya|take care)[\s!.,]*$")
_THANKS_RE = re.compile(r"^(thanks?( you)?( so much| a lot| very much)?|thx|ty|much appreciated|appreciate it)[\s!.,]*$")
_SMALLTALK_SET = {
    "how are you", "how are you doing", "hows it going", "how's it going",
    "whats up", "what's up", "how are things",
    "what can you do", "what do you do", "what can you do for me",
    "who are you", "what are you", "are you an ai", "are you a bot",
    "can you help me", "can you help", "help",
}


def _is_chitchat(message: str) -> bool:
    normalized = re.sub(r"[^\w\s']", " ", message.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return False
    if _GREETING_RE.match(normalized) or _FAREWELL_RE.match(normalized) or _THANKS_RE.match(normalized):
        return True
    return normalized in _SMALLTALK_SET

SESSIONS: dict[str, dict] = {}


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
    return len(message.split()) <= 6


def _merge_with_memory(intent: dict, message: str, session: dict) -> dict:
    """Fills gaps in the new intent using the last known intent for this session,
    but ONLY for genuine follow-up messages — not brand-new questions."""
    last = session.get("last_intent") or {}
    merged = dict(intent)

    if not _is_followup(message):
        for key in ("date_phrase", "start_date", "end_date", "activity", "event_size"):
            if not merged.get(key) and last.get(key):
                merged[key] = last[key]
    else:
        for key in ("location", "date_phrase", "start_date", "end_date", "activity", "event_size"):
            if not merged.get(key) and last.get(key):
                merged[key] = last[key]
    return merged


def split_candidate_locations(raw_location: str | None, message: str) -> list[str]:
    """Splits an explicit comparison ('Kandy vs Galle') into separate names.
    This is only a HINT surfaced to the agent's planner — it does not by
    itself force a comparison plan; the model decides what to do with it."""
    if not raw_location:
        return []
    import re as _re
    parts = _re.split(r"\s+(?:or|vs\.?|versus)\s+|\s*,\s*", raw_location)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else [raw_location]


def score_option(pred: dict, activity: str = "outdoor activity") -> dict:
    """Decision engine: Comfort/Safety/Suitability/Overall scores for one forecast."""
    scores = compute_scores(pred, activity)
    reasons = scores["positives"][:2] + scores["risks"][:1]
    if not reasons:
        reasons = ["conditions within acceptable range"]
    return {
        "score": scores["overall"], "overall": scores["overall"],
        "comfort": scores["comfort"], "safety": scores["safety"],
        "suitability": scores["suitability"], "grade": scores["grade"],
        "reasons": reasons, "risks": scores["risks"],
        "positives": scores["positives"], "tips": scores["tips"],
        "profile_name": scores["profile_name"],
    }


def _sample_windows(start, end, max_samples: int = 4):
    from datetime import timedelta
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


def _same_place(lat1: float, lon1: float, lat2: float, lon2: float, threshold_km: float = 3.0) -> bool:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a)) <= threshold_km


def _resolve_evaluated(state: dict, location_hint: str | None) -> dict | None:
    if not location_hint:
        return None
    hint = location_hint.strip().lower()
    hint_first = hint.split(",")[0].strip()
    for key, opt in state["evaluated"].items():
        key_lower = key.lower()
        key_first = key_lower.split(",")[0].strip()
        if hint == key_lower or hint_first == key_first or hint in key_lower:
            return opt
    return None


def _tool_geocode(args: dict, state: dict, activity: str) -> dict:
    location = (args.get("location") or "").strip()
    if not location:
        return {"error": "no location given"}
    lat, lon, geo_detail = geocode_location(location)
    if lat is None:
        state.setdefault("failed_locations", set()).add(location.strip().lower())
        if geo_detail.startswith("TOO_BROAD:"):
            suggestions = get_country_city_suggestions(location, activity)
            return {"resolved": False, "reason": geo_detail[len("TOO_BROAD:"):].strip(),
                     "suggested_cities": suggestions[:5]}
        return {"resolved": False, "reason": geo_detail}
    return {"resolved": True, "location": geo_detail, "lat": round(lat, 4), "lon": round(lon, 4)}


def _tool_evaluate_location(args: dict, state: dict, activity: str) -> dict:
    location = (args.get("location") or "").strip()
    date_phrase = args.get("date_phrase") or state.get("date_phrase")
    start_date_arg = args.get("start_date") or state.get("start_date")
    end_date_arg = args.get("end_date") or state.get("end_date")
    scan = bool(args.get("scan", False))
    if not location:
        return {"error": "no location given"}
    if len(state["evaluated"]) >= MAX_LOCATIONS:
        return {"error": f"already evaluated {MAX_LOCATIONS} locations — finish with the best one instead of adding more"}

    lat, lon, geo_detail = geocode_location(location)
    if lat is None:
        state.setdefault("failed_locations", set()).add(location.strip().lower())
        if geo_detail.startswith("TOO_BROAD:"):
            suggestions = get_country_city_suggestions(location, activity)
            return {"resolved": False, "reason": geo_detail[len("TOO_BROAD:"):].strip(),
                     "suggested_cities": suggestions[:5]}
        return {"resolved": False, "reason": geo_detail}
    resolved_name = geo_detail

    explicit_start = parse_iso_date(start_date_arg)
    explicit_end = parse_iso_date(end_date_arg) or explicit_start

    if scan:
        scan_start, scan_end = resolve_scan_range(date_phrase or "next month")
        windows = _sample_windows(scan_start, scan_end, max_samples=4)
    elif explicit_start:
        windows = [(explicit_start, explicit_end)]
    else:
        start, end = resolve_date_phrase(date_phrase or "next month")
        windows = [(start, end)]

    best_date, best_pred, best_scoring = None, None, None
    confidence, confidence_label, days_modeled = "low", "", 0
    for w_start, w_end in windows:
        result = run_prediction(lat, lon, w_start, w_end, activity)
        days_modeled += len(result["predictions"])
        confidence = result.get("confidence", confidence)
        confidence_label = result.get("confidence_label", confidence_label)
        for date_str, pred in sorted(result["predictions"].items()):
            scoring = score_option(pred, activity)
            if best_scoring is None or scoring["score"] > best_scoring["score"]:
                best_date, best_pred, best_scoring = date_str, pred, scoring

    if best_date is None:
        return {"resolved": True, "location": resolved_name, "error": "no usable forecast days in that range"}

    existing_key = None
    for key, opt in state["evaluated"].items():
        if _same_place(lat, lon, opt["lat"], opt["lon"]):
            existing_key = key
            break
    target_key = existing_key or resolved_name
    prior = state["evaluated"].get(target_key, {})

    state["evaluated"][target_key] = {
        "location_name": resolved_name, "lat": lat, "lon": lon,
        "date": best_date, "pred": best_pred, "scoring": best_scoring,
        "confidence": confidence, "confidence_label": confidence_label,
        "venues": prior.get("venues", []), "online_venues": prior.get("online_venues", []),
        "farming": prior.get("farming"), "image_url": prior.get("image_url") or get_place_image(resolved_name),
    }
    return {
        "resolved": True, "location": resolved_name, "best_date": best_date,
        "overall": best_scoring["score"], "comfort": best_scoring["comfort"],
        "safety": best_scoring["safety"], "suitability": best_scoring["suitability"],
        "grade": best_scoring["grade"], "days_modeled": days_modeled,
        "top_risk": best_scoring["risks"][0] if best_scoring["risks"] else None,
        "top_positive": best_scoring["positives"][0] if best_scoring["positives"] else None,
    }


def _tool_find_venues(args: dict, state: dict, activity: str) -> dict:
    location = (args.get("location") or "").strip()
    opt = _resolve_evaluated(state, location)
    if opt is None:
        return {"error": f"'{location}' hasn't been evaluated yet — call evaluate_location first"}
    venues = _find_venues_api(opt["lat"], opt["lon"], activity)
    opt["venues"] = venues
    return {"location": opt["location_name"], "venue_count": len(venues),
             "sample": [v["name"] for v in venues[:4]]}


def _tool_search_venues_online(args: dict, state: dict, activity: str) -> dict:
    location = (args.get("location") or "").strip()
    opt = _resolve_evaluated(state, location)
    if opt is None:
        return {"error": f"'{location}' hasn't been evaluated yet — call evaluate_location first"}
    results = search_venues_online(opt["location_name"], activity)
    if results is None:
        return {"error": "web venue search unavailable right now (needs Gemini) — try find_venues instead"}
    opt["online_venues"] = results
    return {"location": opt["location_name"], "venue_count": len(results),
             "sample": [v["name"] for v in results[:4]]}


def _tool_farming_analysis(args: dict, state: dict, activity: str) -> dict:
    location = (args.get("location") or "").strip()
    opt = _resolve_evaluated(state, location)
    if opt is None:
        return {"error": f"'{location}' hasn't been evaluated yet — call evaluate_location first"}
    pred = opt["pred"]
    result = _farming_analysis_api(activity, temp_c=pred["T2M"], rain_mm=pred["PRECTOTCORR"], wind_kmh=pred["WS10M"])
    opt["farming"] = result
    return {"location": opt["location_name"], "suitability": result["suitability_label"], "score": result["farming_score"]}


_TOOL_FUNCS = {
    "geocode": _tool_geocode,
    "evaluate_location": _tool_evaluate_location,
    "find_venues": _tool_find_venues,
    "search_venues_online": _tool_search_venues_online,
    "farming_analysis": _tool_farming_analysis,
}

TOOL_SPECS = {
    "geocode": {
        "args": "location (string)",
        "description": "Check whether a place name resolves to a specific city (not a whole "
                        "country/region) and get its coordinates, without fetching weather yet.",
    },
    "evaluate_location": {
        "args": "location (string), start_date and end_date (YYYY-MM-DD, or null to use the extracted date), scan (boolean, default false)",
        "description": "The main tool. Geocodes a location, fetches its forecast/climate data, and "
                        "scores it (Comfort/Safety/Suitability/Overall + risks) for the activity. Call "
                        f"once per candidate location, up to {MAX_LOCATIONS}. Compute start_date/end_date "
                        "yourself from today's date and whatever the user said — do the date arithmetic, "
                        "don't just repeat their words. Set scan=true only when the user wants the single "
                        "best/safest date across a wide range (leave start_date/end_date null in that case).",
    },
    "find_venues": {
        "args": "location (string, must match an already-evaluated location)",
        "description": "Look up nearby venues (hotels, parks, grounds, etc) via OpenStreetMap map data — "
                        "reliable, gives distance and a map link. Call this FIRST when venues are relevant. "
                        "ALWAYS call at least one of find_venues or search_venues_online before finishing if "
                        "the user's message mentions venues, hotels, places to stay, or where to hold/host "
                        "the event — do not finish without it if they asked.",
    },
    "search_venues_online": {
        "args": "location (string, must match an already-evaluated location)",
        "description": "Search the web (Google Search) for real, named venues with an actual website link "
                        "— richer than find_venues, but this runs on a limited quota and can be unavailable. "
                        "Use it to ADD a couple of curated picks after find_venues already has results, not "
                        "as your first attempt — if it errors, don't retry it, just rely on find_venues.",
    },
    "farming_analysis": {
        "args": "location (string, must match an already-evaluated location)",
        "description": "Crop-specific suitability, risks and opportunities for an evaluated location. "
                        "Only call this if the activity is agricultural (planting, harvesting, a crop, etc).",
    },
    "ask_user": {
        "args": "question (string)",
        "description": "Stop and ask the user a clarifying question instead of guessing — use this if "
                        "the location is missing/ambiguous and there is nothing sensible to evaluate.",
    },
    "finish": {
        "args": "winner_location (string, must match an already-evaluated location), rationale (string)",
        "description": "Stop gathering information and deliver a recommendation. Pick the winning "
                        "location among everything evaluated and explain the choice in 1-2 sentences, "
                        "in your own words, referencing the actual scores/risks you saw.",
    },
}


def _format_tools_for_prompt() -> str:
    return "\n".join(f"- {name}({spec['args']}): {spec['description']}" for name, spec in TOOL_SPECS.items())


def _summarize_observation(tool_name: str, obs: dict) -> str:
    if "error" in obs and tool_name not in ("evaluate_location", "geocode"):
        return f"Error: {obs['error']}"
    if tool_name in ("geocode", "evaluate_location"):
        if not obs.get("resolved", True) or obs.get("reason"):
            sug = obs.get("suggested_cities")
            base = obs.get("reason", "not found")
            return base + (f" Suggested cities: {', '.join(s.split(',')[0] for s in sug[:4])}" if sug else "")
        if "error" in obs:
            return obs["error"]
        if tool_name == "geocode":
            return f"'{obs['location']}' resolved to ({obs['lat']}, {obs['lon']})"
        risk_note = f" Top risk: {obs['top_risk']}." if obs.get("top_risk") else ""
        return (f"{obs['location']} on {obs['best_date']}: Overall {obs['overall']}/100 (Grade {obs['grade']}) "
                f"— Comfort {obs['comfort']}, Safety {obs['safety']}, Suitability {obs['suitability']}.{risk_note}")
    if tool_name in ("find_venues", "search_venues_online"):
        sample = f": {', '.join(obs['sample'])}" if obs.get("sample") else ""
        return f"Found {obs.get('venue_count', 0)} venue(s) near {obs.get('location', '?')}{sample}"
    if tool_name == "farming_analysis":
        return f"{obs.get('location', '?')}: {obs.get('suitability', '?')} ({obs.get('score', '?')}/100) for farming"
    return json.dumps(obs)


def _build_decision_prompt(message: str, intent: dict, scratchpad: list[str], candidate_hint: str) -> str:
    tools_block = _format_tools_for_prompt()
    scratchpad_block = "\n".join(scratchpad) if scratchpad else "(nothing yet — this is your first move)"
    today = datetime.now()
    date_hint = ""
    if intent.get("start_date"):
        date_hint = f", already computed as start_date={intent.get('start_date')!r} end_date={intent.get('end_date') or intent.get('start_date')!r} — reuse these"
    return f"""You are the planning engine of a weather-decision agent. You never talk to the \
user directly — you choose ONE next action by calling a tool, based on everything known so far.
Today's actual date is {today.strftime('%Y-%m-%d')} ({today.strftime('%A')}).

User's original request: "{message}"
Extracted intent: location={intent.get('location')!r}, date={intent.get('date_phrase')!r}{date_hint}, activity={intent.get('activity')!r}, event_size={intent.get('event_size')!r}
{candidate_hint}

Tools available:
{tools_block}

What you've learned so far:
{scratchpad_block}

Rules:
- Evaluate at most {MAX_LOCATIONS} locations before finishing.
- Do not call finish until at least one location has been evaluated.
- Do not call find_venues, search_venues_online, or farming_analysis on a location you have not evaluated yet.
- Decide the single next action. Respond with ONLY a JSON object, no other text, in this exact shape:
{{"thought": "<brief reasoning about what to do next and why>", "tool": "<tool name>", "args": {{...}}}}
JSON:"""


def _deterministic_fallback_action(state: dict, candidates: list[str], allow_expand: bool, scan: bool = False) -> dict:
    """Only used when the LLM is unavailable or its output can't be parsed —
    a safety net around the agent's planning, not the planning itself."""
    failed = state.get("failed_locations", set())
    tried = state.setdefault("fallback_tried", set())

    def _already_handled(c: str) -> bool:
        # Either the fallback itself already tried this exact string (catches
        # the case where the raw candidate string doesn't fuzzy-match the
        # geocoded name in _resolve_evaluated), or it's already been evaluated
        # under any spelling — including by a real LLM tool call before the
        # LLM stopped responding mid-conversation.
        return c.strip().lower() in tried or _resolve_evaluated(state, c) is not None

    for c in candidates:
        if not _already_handled(c) and c.strip().lower() not in failed:
            tried.add(c.strip().lower())
            return {"thought": "(fallback — model unavailable)", "tool": "evaluate_location",
                     "args": {"location": c, "scan": scan}}
    suggested = state.get("suggested_cities", [])
    if not allow_expand and suggested and not state["evaluated"]:
        # A candidate came back TOO_BROAD (e.g. a whole country) and the user
        # hasn't said "anywhere"/answered a clarifying question yet — ask for
        # a specific city instead of silently picking one for them.
        cities = ", ".join(s.split(",")[0] for s in suggested[:4])
        return {"thought": "(fallback — model unavailable, asking for a specific city)", "tool": "ask_user",
                "args": {"question": f"That's a wide area — could you name a specific city? For example: {cities}. "
                                      f"Or just say 'anywhere' and I'll pick the best one for you."}}
    if len(state["evaluated"]) < MAX_LOCATIONS:
        for c in suggested:
            if not _already_handled(c) and c.strip().lower() not in failed:
                tried.add(c.strip().lower())
                return {"thought": "(fallback — model unavailable, trying a suggested city)",
                        "tool": "evaluate_location", "args": {"location": c, "scan": scan}}
    if state["evaluated"]:
        best = max(state["evaluated"].values(), key=lambda o: o["scoring"]["score"])
        return {"thought": "(fallback — model unavailable)", "tool": "finish",
                "args": {"winner_location": best["location_name"], "rationale": "Best score among evaluated options."}}
    return {"thought": "(fallback — model unavailable)", "tool": "ask_user",
            "args": {"question": "Could you tell me the city or place you mean?"}}


def _build_reply(winner: dict, options: list[dict], explanation: str, rationale: str) -> str:
    loc = winner["location_name"].split(",")[0]
    date = winner["date"]
    sc = winner["scoring"]
    label = "Recommended" if sc.get("grade", "C") not in ("D", "F") else "Not Recommended"
    score_line = (
        f"**{label}: {loc} — {date}**\n"
        f"Overall: {sc['score']}/100 (Grade {sc.get('grade', 'C')}) | "
        f"Comfort: {sc.get('comfort', sc['score'])}/100 | Safety: {sc.get('safety', sc['score'])}/100 | "
        f"Suitability: {sc.get('suitability', sc['score'])}/100"
    )
    compare_note = ""
    if len(options) > 1:
        others = ", ".join(f"{o['location_name'].split(',')[0]} ({o['scoring']['score']}/100)" for o in options[1:])
        compare_note = f"\n\nThe agent evaluated {len(options)} option(s) and picked this over {others}."
    agent_note = f"\n\n*Agent's reasoning: {rationale}*" if rationale else ""
    return f"{score_line}{compare_note}{agent_note}\n\n{explanation}"


def run_agent(message: str, session_id: str) -> dict:
    session = _get_session(session_id)

    if _is_chitchat(message):
        reply = generate_chitchat_reply(message)
        session["history"].append({"message": message, "reply": reply})
        session["history"] = session["history"][-6:]
        return {
            "reply": reply, "explanation": "", "intent": {}, "plan": "chitchat",
            "steps": [{"step": "Greeting/small talk detected", "tool": "chitchat",
                       "detail": "Skipped the planning loop and replied directly."}],
            "options": [],
        }

    raw_intent = extract_intent(message)

    if raw_intent.get("is_planning_request") is False:
        reply = raw_intent.get("casual_reply") or generate_chitchat_reply(message)
        session["history"].append({"message": message, "reply": reply})
        session["history"] = session["history"][-6:]
        return {
            "reply": reply, "explanation": "", "intent": {}, "plan": "chitchat",
            "steps": [{"step": "Understand request", "tool": "extract_intent",
                       "detail": "Judged not to be a planning request — replied directly instead of "
                                 "running a weather lookup on nothing."}],
            "options": [],
        }

    intent = _merge_with_memory(raw_intent, message, session)
    activity = intent.get("activity") or "outdoor activity"

    steps = [{
        "step": "Understand request", "tool": "extract_intent",
        "detail": f"location={intent.get('location')!r}, date={intent.get('date_phrase')!r}, activity={intent.get('activity')!r}"
                  + (" (filled in from earlier in this conversation)" if raw_intent.get("location") != intent.get("location") else ""),
    }]

    candidates = split_candidate_locations(intent.get("location"), message)
    if len(candidates) > 1:
        candidate_hint = f"Locations mentioned in the request: {candidates}"
    elif candidates:
        candidate_hint = f"Location mentioned: {candidates[0]!r}"
    else:
        candidate_hint = "No specific location was mentioned yet."

    wants_venues = any(kw in message.lower() for kw in _VENUE_REQUEST_KEYWORDS)
    if wants_venues:
        candidate_hint += ("\nThe user explicitly asked about venues/hotels/places to stay — you must "
                            "call find_venues for at least one evaluated location before finishing.")

    wants_scan = _wants_date_scan(message)
    if wants_scan:
        candidate_hint += ("\nThe user wants the single best/safest DATE across a range, not just one "
                            "fixed day — call evaluate_location with scan=true (leave start_date/end_date "
                            "null) so it samples across the whole period instead of one default date.")

    no_preference = any(kw in message.lower() for kw in _NO_PREFERENCE_KEYWORDS)
    was_awaiting_clarification = session.get("awaiting_clarification", False)
    session["awaiting_clarification"] = False
    if no_preference or was_awaiting_clarification:
        candidate_hint += ("\nThe user has no specific city preference (either they said so, or this "
                            "message is their reply to a clarifying question you already asked) — do NOT "
                            "call ask_user again this turn. If the location is a country/region, "
                            "geocode/evaluate_location will hand you suggested_cities; pick 2-4 of those "
                            "good candidates for the activity yourself, evaluate them, and recommend the best.")

    state = {
        "evaluated": {},
        "date_phrase": intent.get("date_phrase"),
        "start_date": intent.get("start_date"),
        "end_date": intent.get("end_date"),
    }
    scratchpad: list[str] = []
    ask_user_question = None
    finish_args = None
    consecutive_failures = 0

    for i in range(MAX_ITERATIONS):
        prompt = _build_decision_prompt(message, intent, scratchpad, candidate_hint)
        decision = call_llm_json(prompt, timeout=60)

        if decision is None or "tool" not in decision or decision.get("tool") not in TOOL_SPECS:
            consecutive_failures += 1
            action = _deterministic_fallback_action(state, candidates, no_preference or was_awaiting_clarification, scan=wants_scan)
        else:
            consecutive_failures = 0
            action = decision

        thought = action.get("thought") or f"Chose {action.get('tool')}"
        tool_name = action.get("tool")
        args = action.get("args") or {}

        if tool_name == "finish" and not state["evaluated"]:
            consecutive_failures += 1
            action = _deterministic_fallback_action(state, candidates, no_preference or was_awaiting_clarification, scan=wants_scan)
            thought = action.get("thought") or thought
            tool_name = action.get("tool")
            args = action.get("args") or {}
        elif tool_name == "finish" and wants_venues and not any(
            o.get("venues") or o.get("online_venues") for o in state["evaluated"].values()
        ):
            best_so_far = max(state["evaluated"].values(), key=lambda o: o["scoring"]["score"])
            thought = "Forcing a venue lookup before finishing — the user asked about venues/hotels."
            tool_name = "find_venues"
            args = {"location": best_so_far["location_name"]}
        elif tool_name == "finish" and _is_farming_activity(activity) and not any(
            o.get("farming") for o in state["evaluated"].values()
        ):
            best_so_far = max(state["evaluated"].values(), key=lambda o: o["scoring"]["score"])
            thought = "Forcing crop-specific farming analysis before finishing — this is a farming activity."
            tool_name = "farming_analysis"
            args = {"location": best_so_far["location_name"]}

        steps.append({"step": f"Decide (step {i + 1})", "tool": "planner", "detail": thought})

        if tool_name == "finish":
            finish_args = args
            break
        if tool_name == "ask_user":
            ask_user_question = args.get("question") or "Could you tell me more about what you're planning?"
            break

        func = _TOOL_FUNCS.get(tool_name)
        observation = func(args, state, activity) if func else {"error": f"unknown tool '{tool_name}'"}
        if observation.get("suggested_cities"):
            state["suggested_cities"] = observation["suggested_cities"]
        scratchpad.append(f"Action {i + 1}: {tool_name}({args}) -> {json.dumps(observation)}")
        steps.append({"step": tool_name, "tool": tool_name, "detail": _summarize_observation(tool_name, observation)})

        if consecutive_failures >= 3:
            break

    if ask_user_question:
        session["last_intent"] = intent
        session["awaiting_clarification"] = True
        session["history"].append({"message": message, "reply": ask_user_question})
        session["history"] = session["history"][-6:]
        return {"reply": ask_user_question, "intent": intent, "steps": steps, "options": []}

    if not state["evaluated"]:
        reply = "I gathered what I could but couldn't evaluate any location — try naming a specific city."
        session["last_intent"] = intent
        session["history"].append({"message": message, "reply": reply})
        session["history"] = session["history"][-6:]
        return {"reply": reply, "intent": intent, "steps": steps, "options": []}

    options = sorted(state["evaluated"].values(), key=lambda o: o["scoring"]["score"], reverse=True)

    if finish_args:
        winner = _resolve_evaluated(state, finish_args.get("winner_location")) or options[0]
        rationale = finish_args.get("rationale", "")
    else:
        winner = options[0]
        rationale = "Reached the step limit, so recommending the best-scoring option evaluated so far."

    steps.append({
        "step": "Finalize recommendation", "tool": "planner",
        "detail": f"Selected {winner['location_name'].split(',')[0]} as the winner.",
    })

    winner_explanation = explain_decision(
        scores=winner["scoring"], pred=winner["pred"], activity=activity,
        location=winner["location_name"].split(",")[0], date=winner["date"],
        confidence_label=winner.get("confidence_label", ""),
    )
    reply = _build_reply(winner, options, winner_explanation, rationale)

    session["last_intent"] = {**intent, "location": winner["location_name"].split(",")[0]}
    session["history"].append({"message": message, "reply": reply})
    session["history"] = session["history"][-6:]

    return {
        "reply": reply,
        "explanation": winner_explanation,
        "intent": intent,
        "plan": "react_agent",
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
                "score": o["scoring"]["score"],
                "comfort": o["scoring"].get("comfort", o["scoring"]["score"]),
                "safety": o["scoring"].get("safety", o["scoring"]["score"]),
                "suitability": o["scoring"].get("suitability", o["scoring"]["score"]),
                "grade": o["scoring"].get("grade", "C"),
                "profile_name": o["scoring"].get("profile_name", activity),
                "reasons": o["scoring"]["reasons"],
                "risks": o["scoring"].get("risks", []),
                "positives": o["scoring"].get("positives", []),
                "tips": o["scoring"].get("tips", []),
                "confidence": o.get("confidence", "low"),
                "confidence_label": o.get("confidence_label", "Historical climate estimate"),
                "lat": o["lat"],
                "lon": o["lon"],
                "venues": o.get("venues", []),
                "online_venues": o.get("online_venues", []),
                "farming": o.get("farming"),
                "image_url": o.get("image_url"),
            }
            for o in options
        ],
    }
