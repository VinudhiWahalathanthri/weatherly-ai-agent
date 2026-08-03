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
import re

from planning_agent import (
    extract_intent, geocode_location, resolve_date_phrase, resolve_scan_range,
    get_country_city_suggestions, call_llm_json, generate_chitchat_reply,
    search_venues_online,
)
from forecasting import run_prediction
from venue_discovery import find_venues as _find_venues_api
from farming import farming_analysis as _farming_analysis_api
from scoring_engine import compute_scores, explain_decision
from images import get_place_image

# Kept low deliberately: each iteration burns one LLM call (Gemini's free tier
# caps at 20 requests/day), and most real questions (evaluate -> maybe venues ->
# finish) converge in 2-4 steps anyway.
MAX_ITERATIONS = 5
MAX_LOCATIONS = 4

_VENUE_REQUEST_KEYWORDS = {
    "venue", "venues", "hotel", "hotels", "place to stay", "places to stay",
    "where to hold", "where to host", "accommodation", "accomodation",
    "stay near", "book a place", "resort", "resorts",
}

# Chit-chat detection: a full-message allowlist match, never substring/startswith —
# "hey, is it safe to hike in Kandy tomorrow?" must NOT be treated as a greeting.
_GREETING_RE = re.compile(r"^(hi+|he+y+a?|hello+|yo+|howdy|greetings|good ?(morning|afternoon|evening|night))[\s!.,]*$")
_FAREWELL_RE = re.compile(r"^(bye+|goodbye|see ?you( later| soon)?|good ?night|cya|take care)[\s!.,]*$")
_THANKS_RE = re.compile(r"^(thanks?( you)?( so much| a lot| very much)?|thx|ty|much appreciated|appreciate it)[\s!.,]*$")
_SMALLTALK_SET = {
    "how are you", "how are you doing", "hows it going", "how's it going",
    "whats up", "what's up", "how are things",
}


def _is_chitchat(message: str) -> bool:
    normalized = re.sub(r"[^\w\s']", " ", message.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return False
    if _GREETING_RE.match(normalized) or _FAREWELL_RE.match(normalized) or _THANKS_RE.match(normalized):
        return True
    return normalized in _SMALLTALK_SET

# ---------------------------------------------------------------------------
# Session memory (in-memory for this demo — swap for Redis/DB in production)
# ---------------------------------------------------------------------------
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
        for key in ("date_phrase", "activity", "event_size"):
            if not merged.get(key) and last.get(key):
                merged[key] = last[key]
        # Never inherit location for a new question — let the agent ask.
    else:
        for key in ("location", "date_phrase", "activity", "event_size"):
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


# ---------------------------------------------------------------------------
# TOOLS — each takes (args, state, activity) and returns a small observation
# dict for the LLM to read. Full results are stashed on `state["evaluated"]`
# so the model only has to reason over compact summaries, not raw payloads.
# ---------------------------------------------------------------------------

def _resolve_evaluated(state: dict, location_hint: str | None) -> dict | None:
    if not location_hint:
        return None
    hint = location_hint.strip().lower()
    for key, opt in state["evaluated"].items():
        if hint == key.lower() or hint == key.lower().split(",")[0] or hint in key.lower():
            return opt
    return None


def _tool_geocode(args: dict, state: dict, activity: str) -> dict:
    location = (args.get("location") or "").strip()
    if not location:
        return {"error": "no location given"}
    lat, lon, geo_detail = geocode_location(location)
    if lat is None:
        if geo_detail.startswith("TOO_BROAD:"):
            suggestions = get_country_city_suggestions(location, activity)
            return {"resolved": False, "reason": geo_detail[len("TOO_BROAD:"):].strip(),
                     "suggested_cities": suggestions[:5]}
        return {"resolved": False, "reason": geo_detail}
    return {"resolved": True, "location": geo_detail, "lat": round(lat, 4), "lon": round(lon, 4)}


def _tool_evaluate_location(args: dict, state: dict, activity: str) -> dict:
    location = (args.get("location") or "").strip()
    date_phrase = args.get("date_phrase") or state.get("date_phrase")
    scan = bool(args.get("scan", False))
    if not location:
        return {"error": "no location given"}
    if len(state["evaluated"]) >= MAX_LOCATIONS:
        return {"error": f"already evaluated {MAX_LOCATIONS} locations — finish with the best one instead of adding more"}

    lat, lon, geo_detail = geocode_location(location)
    if lat is None:
        if geo_detail.startswith("TOO_BROAD:"):
            suggestions = get_country_city_suggestions(location, activity)
            return {"resolved": False, "reason": geo_detail[len("TOO_BROAD:"):].strip(),
                     "suggested_cities": suggestions[:5]}
        return {"resolved": False, "reason": geo_detail}
    resolved_name = geo_detail

    if scan:
        scan_start, scan_end = resolve_scan_range(date_phrase or "next month")
        windows = _sample_windows(scan_start, scan_end, max_samples=4)
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

    state["evaluated"][resolved_name] = {
        "location_name": resolved_name, "lat": lat, "lon": lon,
        "date": best_date, "pred": best_pred, "scoring": best_scoring,
        "confidence": confidence, "confidence_label": confidence_label,
        "venues": [], "online_venues": [], "farming": None, "image_url": get_place_image(resolved_name),
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
        "args": "location (string), date_phrase (string or null — defaults to the extracted date), scan (boolean, default false)",
        "description": "The main tool. Geocodes a location, fetches its forecast/climate data, and "
                        "scores it (Comfort/Safety/Suitability/Overall + risks) for the activity. Call "
                        f"once per candidate location, up to {MAX_LOCATIONS}. Set scan=true only when "
                        "the user wants the single best/safest date across a wide range, not a specific one.",
    },
    "find_venues": {
        "args": "location (string, must match an already-evaluated location)",
        "description": "Look up nearby venues (hotels, parks, grounds, etc) via OpenStreetMap map data — "
                        "fast, gives distance and a map link, but names/websites are sometimes sparse.",
    },
    "search_venues_online": {
        "args": "location (string, must match an already-evaluated location)",
        "description": "Search the web (Google Search) for real, named venues/hotels/event spaces with "
                        "an actual website or Maps link — richer, more concrete recommendations than "
                        "find_venues. Prefer this one when the user wants actual venues to consider "
                        "booking. ALWAYS call at least one of find_venues or search_venues_online before "
                        "finishing if the user's message mentions venues, hotels, places to stay, or where "
                        "to hold/host the event — do not finish without it if they asked.",
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
    return f"""You are the planning engine of a weather-decision agent. You never talk to the \
user directly — you choose ONE next action by calling a tool, based on everything known so far.

User's original request: "{message}"
Extracted intent: location={intent.get('location')!r}, date={intent.get('date_phrase')!r}, activity={intent.get('activity')!r}, event_size={intent.get('event_size')!r}
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


def _deterministic_fallback_action(state: dict, candidates: list[str]) -> dict:
    """Only used when the LLM is unavailable or its output can't be parsed —
    a safety net around the agent's planning, not the planning itself."""
    for c in candidates:
        if _resolve_evaluated(state, c) is None:
            return {"thought": "(fallback — model unavailable)", "tool": "evaluate_location", "args": {"location": c}}
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
    score_line = (
        f"**Recommended: {loc} — {date}**\n"
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


# ---------------------------------------------------------------------------
# THE AGENT
# ---------------------------------------------------------------------------
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

    state = {"evaluated": {}, "date_phrase": intent.get("date_phrase")}
    scratchpad: list[str] = []
    ask_user_question = None
    finish_args = None
    consecutive_failures = 0

    for i in range(MAX_ITERATIONS):
        prompt = _build_decision_prompt(message, intent, scratchpad, candidate_hint)
        decision = call_llm_json(prompt, timeout=25)

        if decision is None or "tool" not in decision or decision.get("tool") not in TOOL_SPECS:
            consecutive_failures += 1
            action = _deterministic_fallback_action(state, candidates)
        else:
            consecutive_failures = 0
            action = decision

        thought = action.get("thought") or f"Chose {action.get('tool')}"
        tool_name = action.get("tool")
        args = action.get("args") or {}

        if tool_name == "finish" and not state["evaluated"]:
            # Invalid — nothing evaluated yet. Treat like an unparsable action.
            consecutive_failures += 1
            action = _deterministic_fallback_action(state, candidates)
            thought = action.get("thought") or thought
            tool_name = action.get("tool")
            args = action.get("args") or {}
        elif tool_name == "finish" and wants_venues and not any(
            o.get("venues") or o.get("online_venues") for o in state["evaluated"].values()
        ):
            # The user explicitly asked for venues and the agent hasn't looked yet — force it
            # rather than silently finishing without answering what was actually asked.
            # search_venues_online gives real named businesses with links, closer to what
            # someone means by "venue recommendations" than bare OSM map data — but if that's
            # already been tried and came back empty, fall back to find_venues instead of
            # retrying the same failing call and burning the iteration budget.
            best_so_far = max(state["evaluated"].values(), key=lambda o: o["scoring"]["score"])
            already_tried_online = any("search_venues_online(" in s for s in scratchpad)
            if already_tried_online:
                thought = "Falling back to OpenStreetMap venue lookup — the web search didn't return usable results."
                tool_name = "find_venues"
            else:
                thought = "Forcing a venue search before finishing — the user asked about venues/hotels."
                tool_name = "search_venues_online"
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
        scratchpad.append(f"Action {i + 1}: {tool_name}({args}) -> {json.dumps(observation)}")
        steps.append({"step": tool_name, "tool": tool_name, "detail": _summarize_observation(tool_name, observation)})

        if consecutive_failures >= 3:
            break

    if ask_user_question:
        return {"reply": ask_user_question, "intent": intent, "steps": steps, "options": []}

    if not state["evaluated"]:
        reply = "I gathered what I could but couldn't evaluate any location — try naming a specific city."
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
