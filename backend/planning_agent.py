"""
AI Planning Agent
------------------
Turns a free-text request like:
    "Can I organize a wedding in Kandy next month?"
into a structured intent {location, date_phrase, activity, event_size},
resolves that intent into a concrete lat/lon + date range, and hands off
to the existing weather/ML pipeline in main.py.

LLM layer (call_llm_json, below): tries Gemini first when GEMINI_API_KEY is
set — it's faster and more reliable at structured JSON output than the
local model. Falls back to a local Ollama model if Gemini isn't configured
or errors, and finally to a lightweight rule-based extractor, so the agent
still works out of the box with zero cloud setup.
"""

import json
import os
import re
import time
import calendar
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3.5"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_MIN_INTERVAL = 1.05
_last_nominatim_call = 0.0

_TOO_BROAD_RANK = 8

COUNTRY_CITY_HINTS: dict[str, str] = {
    "india": "New Delhi, India",
    "sri lanka": "Colombo, Sri Lanka",
    "united states": "New York, USA",
    "usa": "New York, USA",
    "uk": "London, UK",
    "united kingdom": "London, UK",
    "australia": "Sydney, Australia",
    "canada": "Toronto, Canada",
    "japan": "Tokyo, Japan",
    "china": "Beijing, China",
    "france": "Paris, France",
    "germany": "Berlin, Germany",
    "italy": "Rome, Italy",
    "spain": "Madrid, Spain",
    "brazil": "São Paulo, Brazil",
    "thailand": "Bangkok, Thailand",
    "singapore": "Singapore",
    "malaysia": "Kuala Lumpur, Malaysia",
    "indonesia": "Jakarta, Indonesia",
    "pakistan": "Karachi, Pakistan",
    "bangladesh": "Dhaka, Bangladesh",
    "nepal": "Kathmandu, Nepal",
    "maldives": "Malé, Maldives",
}

WORD_TO_NUM: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}

MONTH_NAMES: dict[str, int] = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_RE = "|".join(sorted(MONTH_NAMES.keys(), key=len, reverse=True))

COUNTRY_ACTIVITY_CITIES: dict[str, dict[str, list[str]]] = {
    "india": {
        "beach":   ["Goa, India", "Varkala, India", "Pondicherry, India", "Kovalam, India"],
        "hiking":  ["Manali, India", "Darjeeling, India", "Munnar, India", "Coorg, India"],
        "events":  ["Mumbai, India", "New Delhi, India", "Jaipur, India", "Udaipur, India"],
        "travel":  ["Goa, India", "Jaipur, India", "Agra, India", "Varanasi, India"],
        "sports":  ["Mumbai, India", "Kolkata, India", "Chennai, India", "Bangalore, India"],
        "default": ["Mumbai, India", "New Delhi, India", "Goa, India", "Jaipur, India"],
    },
    "sri lanka": {
        "beach":   ["Galle, Sri Lanka", "Mirissa, Sri Lanka", "Unawatuna, Sri Lanka", "Arugam Bay, Sri Lanka"],
        "hiking":  ["Ella, Sri Lanka", "Nuwara Eliya, Sri Lanka", "Kandy, Sri Lanka"],
        "events":  ["Colombo, Sri Lanka", "Kandy, Sri Lanka", "Galle, Sri Lanka"],
        "travel":  ["Colombo, Sri Lanka", "Kandy, Sri Lanka", "Galle, Sri Lanka", "Ella, Sri Lanka"],
        "default": ["Colombo, Sri Lanka", "Kandy, Sri Lanka", "Galle, Sri Lanka"],
    },
    "thailand": {
        "beach":   ["Phuket, Thailand", "Koh Samui, Thailand", "Krabi, Thailand", "Pattaya, Thailand"],
        "hiking":  ["Chiang Mai, Thailand", "Pai, Thailand", "Kanchanaburi, Thailand"],
        "events":  ["Bangkok, Thailand", "Chiang Mai, Thailand", "Phuket, Thailand"],
        "travel":  ["Bangkok, Thailand", "Chiang Mai, Thailand", "Phuket, Thailand", "Koh Samui, Thailand"],
        "default": ["Bangkok, Thailand", "Chiang Mai, Thailand", "Phuket, Thailand"],
    },
    "indonesia": {
        "beach":   ["Bali, Indonesia", "Lombok, Indonesia", "Gili Islands, Indonesia"],
        "hiking":  ["Bali, Indonesia", "Lombok, Indonesia", "Yogyakarta, Indonesia"],
        "travel":  ["Bali, Indonesia", "Jakarta, Indonesia", "Yogyakarta, Indonesia"],
        "default": ["Bali, Indonesia", "Jakarta, Indonesia", "Yogyakarta, Indonesia"],
    },
    "malaysia": {
        "beach":   ["Langkawi, Malaysia", "Penang, Malaysia", "Kota Kinabalu, Malaysia"],
        "hiking":  ["Cameron Highlands, Malaysia", "Kota Kinabalu, Malaysia"],
        "travel":  ["Kuala Lumpur, Malaysia", "Langkawi, Malaysia", "Penang, Malaysia"],
        "default": ["Kuala Lumpur, Malaysia", "Langkawi, Malaysia", "Penang, Malaysia"],
    },
    "maldives": {
        "beach":   ["Malé, Maldives", "Baa Atoll, Maldives", "Ari Atoll, Maldives"],
        "travel":  ["Malé, Maldives", "Baa Atoll, Maldives"],
        "default": ["Malé, Maldives", "Baa Atoll, Maldives"],
    },
    "australia": {
        "beach":   ["Gold Coast, Australia", "Cairns, Australia", "Byron Bay, Australia", "Bondi Beach, Australia"],
        "hiking":  ["Blue Mountains, Australia", "Hobart, Australia", "Cairns, Australia"],
        "events":  ["Sydney, Australia", "Melbourne, Australia", "Brisbane, Australia"],
        "travel":  ["Sydney, Australia", "Melbourne, Australia", "Cairns, Australia", "Gold Coast, Australia"],
        "default": ["Sydney, Australia", "Melbourne, Australia", "Brisbane, Australia"],
    },
    "usa": {
        "beach":   ["Miami, USA", "Honolulu, USA", "Santa Monica, USA", "Virginia Beach, USA"],
        "hiking":  ["Denver, USA", "Seattle, USA", "Salt Lake City, USA"],
        "events":  ["New York, USA", "Los Angeles, USA", "Chicago, USA", "Las Vegas, USA"],
        "travel":  ["New York, USA", "Los Angeles, USA", "Miami, USA", "Chicago, USA"],
        "default": ["New York, USA", "Los Angeles, USA", "Chicago, USA", "Miami, USA"],
    },
    "united states": {
        "beach":   ["Miami, USA", "Honolulu, USA", "Santa Monica, USA"],
        "default": ["New York, USA", "Los Angeles, USA", "Chicago, USA"],
    },
    "uk": {
        "events":  ["London, UK", "Edinburgh, UK", "Manchester, UK", "Bath, UK"],
        "travel":  ["London, UK", "Edinburgh, UK", "Bath, UK", "Oxford, UK"],
        "default": ["London, UK", "Edinburgh, UK", "Manchester, UK"],
    },
    "united kingdom": {
        "default": ["London, UK", "Edinburgh, UK", "Manchester, UK"],
    },
    "france": {
        "beach":   ["Nice, France", "Cannes, France", "Biarritz, France", "Marseille, France"],
        "events":  ["Paris, France", "Lyon, France", "Nice, France", "Bordeaux, France"],
        "travel":  ["Paris, France", "Nice, France", "Lyon, France", "Bordeaux, France"],
        "default": ["Paris, France", "Nice, France", "Lyon, France"],
    },
    "japan": {
        "travel":  ["Tokyo, Japan", "Kyoto, Japan", "Osaka, Japan", "Hiroshima, Japan"],
        "hiking":  ["Nikko, Japan", "Hakone, Japan", "Sapporo, Japan"],
        "default": ["Tokyo, Japan", "Kyoto, Japan", "Osaka, Japan"],
    },
    "nepal": {
        "hiking":  ["Kathmandu, Nepal", "Pokhara, Nepal", "Lukla, Nepal"],
        "default": ["Kathmandu, Nepal", "Pokhara, Nepal"],
    },
    "pakistan": {
        "hiking":  ["Hunza, Pakistan", "Gilgit, Pakistan", "Lahore, Pakistan"],
        "default": ["Karachi, Pakistan", "Lahore, Pakistan", "Islamabad, Pakistan"],
    },
    "bangladesh": {
        "beach":   ["Cox's Bazar, Bangladesh", "Teknaf, Bangladesh"],
        "default": ["Dhaka, Bangladesh", "Chittagong, Bangladesh"],
    },
}


def get_country_city_suggestions(country_name: str, activity: str) -> list[str]:
    """Given a broad country name and activity, return specific city candidates."""
    key = country_name.strip().lower()
    country_data = COUNTRY_ACTIVITY_CITIES.get(key, {})
    if not country_data:
        return []

    activity_lower = activity.lower()
    if any(kw in activity_lower for kw in ["beach", "surf", "coastal", "sea", "ocean", "swim"]):
        category = "beach"
    elif any(kw in activity_lower for kw in ["hike", "hiking", "trek", "camp", "mountain", "nature"]):
        category = "hiking"
    elif any(kw in activity_lower for kw in ["wedding", "party", "festival", "event", "ceremony", "reception"]):
        category = "events"
    elif any(kw in activity_lower for kw in ["travel", "vacation", "trip", "holiday", "tourism", "visit"]):
        category = "travel"
    elif any(kw in activity_lower for kw in ["cricket", "football", "sports", "tournament", "game", "match"]):
        category = "sports"
    else:
        category = "default"

    return country_data.get(category, country_data.get("default", []))


ACTIVITY_KEYWORDS = {
    "wedding": ["wedding", "marriage", "ceremony", "reception"],
    "hiking": ["hike", "hiking", "trek", "trekking"],
    "camping": ["camp", "camping"],
    "picnic": ["picnic"],
    "festival": ["festival", "concert", "market", "fair"],
    "sports event": ["cricket", "football", "match", "tournament", "sports event", "game"],
    "outdoor party": ["party", "birthday"],
    "travel": ["travel", "trip", "vacation", "holiday", "visit"],
    "photography session": ["photoshoot", "photography"],
    "rice farming": ["rice", "paddy"],
    "wheat farming": ["wheat"],
    "vegetable farming": ["vegetable", "vegetables"],
    "crop harvest": ["harvest", "harvesting"],
    "crop planting": ["planting", "sowing", "sow", "cultivat"],
    "irrigation": ["irrigation", "irrigate"],
    "tea farming": ["tea plantation", "tea farming"],
    "farming": ["farming", "farm", "agriculture", "agricultural", "crop", "crops", "livestock"],
}

WEEKDAYS = {name.lower(): i for i, name in enumerate(calendar.day_name)}


def _resolve_ollama_model() -> str | None:
    """Returns the exact installed model tag (e.g. "qwen3.5:4b") matching OLLAMA_MODEL's
    base name, or None if Ollama isn't running or that model isn't installed.

    /api/generate needs an exact tag match — asking for "qwen3.5" 404s with
    "model not found" if only "qwen3.5:4b" is actually pulled, so we resolve
    the real installed tag instead of guessing at it.
    """
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=2.0)
        if resp.status_code != 200:
            return None
        base = OLLAMA_MODEL.split(":")[0]
        for m in resp.json().get("models", []):
            name = m.get("name", "")
            if name.split(":")[0] == base:
                return name
        return None
    except Exception:
        return None


_gemini_client = None


def _get_gemini_client():
    """Lazily constructs the Gemini client once GEMINI_API_KEY is confirmed set.
    Import is deferred so the app still runs if google-genai isn't installed
    and the user only wants the Ollama/rule-based path."""
    global _gemini_client
    if _gemini_client is None and GEMINI_API_KEY:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


_gemini_quota_exhausted_until = 0.0


def _gemini_quota_available() -> bool:
    return time.monotonic() >= _gemini_quota_exhausted_until


def _mark_gemini_exhausted(error_text: str) -> None:
    """Free-tier quota errors (429 RESOURCE_EXHAUSTED) include a retryDelay —
    honor it and skip calling Gemini again until then, instead of eating a
    slow round-trip-to-429 on every single decision this loop makes. This is
    what was turning a 1-request quota hit into every subsequent call in the
    same request (and follow-up turns) paying the same latency again."""
    global _gemini_quota_exhausted_until
    if "RESOURCE_EXHAUSTED" not in error_text and "429" not in error_text:
        return
    delay = 60.0
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", error_text)
    if m:
        delay = float(m.group(1))
    _gemini_quota_exhausted_until = time.monotonic() + delay


def _call_gemini_json(prompt: str) -> dict | None:
    if not _gemini_quota_available():
        return None
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        from google.genai import types
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
        )
        text = (resp.text or "").strip()
        return json.loads(text) if text else None
    except Exception as e:
        print(f"Gemini JSON call failed: {e}")
        _mark_gemini_exhausted(str(e))
        return None


_CHITCHAT_FALLBACK = "Hey! I'm Weatherly — ask me about the weather for a day out, a trip, an event, or a farming activity and I'll help you plan around it."


def _call_gemini_text(prompt: str) -> str | None:
    """Plain-text Gemini call (no JSON mime type) for short conversational
    replies — used for greetings/small-talk, not structured extraction."""
    if not _gemini_quota_available():
        return None
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        from google.genai import types
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.6, max_output_tokens=60),
        )
        text = (resp.text or "").strip()
        return text or None
    except Exception as e:
        print(f"Gemini text call failed: {e}")
        _mark_gemini_exhausted(str(e))
        return None


def generate_chitchat_reply(message: str) -> str:
    """Short, casual reply for greetings/thanks/small-talk — skips the JSON
    tool-calling path entirely since there's nothing to plan here."""
    if not GEMINI_API_KEY:
        return _CHITCHAT_FALLBACK
    prompt = (
        "You are Weatherly, a friendly weather-planning assistant for day trips, "
        "events, and farming. The user just sent a casual message (greeting, thanks, "
        "or small talk), not a planning question. Reply in 1 short, warm sentence "
        "(max ~20 words), optionally inviting them to ask about weather for a trip, "
        "event, or farming activity. No markdown, no quotes around your reply.\n\n"
        f'User said: "{message}"\nYour reply:'
    )
    return _call_gemini_text(prompt) or _CHITCHAT_FALLBACK


def search_venues_online(location: str, activity: str) -> list[dict] | None:
    """Uses Gemini's Google Search grounding to find real, currently-operating
    venues for an activity near a location — actual named businesses with
    working website/Maps links, not just OpenStreetMap tag data. Returns
    None if Gemini isn't configured or the call/parse fails (caller falls
    back to the OSM-based find_venues tool); returns [] if Gemini genuinely
    found nothing.
    """
    if not _gemini_quota_available():
        return None
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        from google.genai import types
        prompt = (
            f'Find up to 4 real, currently-operating venues suitable for hosting "{activity}" '
            f"near {location}. Use Google Search to confirm each one actually exists right now — "
            "never invent a place. Prefer venues that have a real website or Google Maps listing.\n\n"
            "Respond with ONLY a JSON array (no markdown fences, no other text) where each item has "
            'exactly these keys: "name" (string), "description" (one short sentence on why it fits), '
            '"url" (its real website or Google Maps link, or null if none was found).'
        )
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3,
            ),
        )
        text = (resp.text or "").strip()
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return None
        results = json.loads(match.group(0))
        cleaned = []
        for r in results[:5]:
            if isinstance(r, dict) and r.get("name"):
                cleaned.append({
                    "name": str(r["name"]),
                    "description": str(r.get("description") or ""),
                    "url": r.get("url") or None,
                })
        return cleaned
    except Exception as e:
        print(f"Gemini web venue search failed: {e}")
        _mark_gemini_exhausted(str(e))
        return None


def _call_ollama_json(prompt: str, timeout: int) -> dict | None:
    model = _resolve_ollama_model()
    if not model:
        return None
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False, "think": False},
            timeout=timeout,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        return json.loads(match.group(0))
    except Exception as e:
        print(f"Ollama JSON call failed: {e}")
        return None


def call_llm_json(prompt: str, timeout: int = 20) -> dict | None:
    """Unified LLM entry point shared by intent extraction and the ReAct
    agent loop (agent.py). Tries Gemini first when GEMINI_API_KEY is set —
    it's faster and more reliable at structured JSON output than the local
    4B Ollama model — and falls back to Ollama if Gemini isn't configured
    or the call fails, so the agent still works with zero cloud setup.
    Returns None if nothing is available/parsable — callers decide how to
    fall back further (rules-based extraction, deterministic planner action).
    """
    if GEMINI_API_KEY:
        result = _call_gemini_json(prompt)
        if result is not None:
            return result
    return _call_ollama_json(prompt, timeout=timeout)


def _extract_intent_llm(message: str) -> dict | None:
    today = datetime.now()
    prompt = f"""You are the front door of a weather-planning assistant. Today's actual date is \
{today.strftime('%Y-%m-%d')} ({today.strftime('%A')}) — use this as your reference point for any \
relative or absolute date the user mentions ("next month", "tomorrow", "the 9th of August", "in three \
weeks", "the first weekend of September", whatever phrasing they use). Do the date arithmetic yourself \
and give back real calendar dates — don't make the caller guess what your words meant.

First judge whether this message is actually a planning request (asking about weather for a trip, \
event, day out, or farming activity) versus casual conversation (greetings, thanks, small talk, "what \
can you do", asking who you are, etc). Getting this right matters — misreading a greeting as a planning \
request wastes time running a full weather lookup on nothing.

If it IS a planning request, extract the fields (missing ones are null, not guessed). For the date: if \
the user named or implied a specific time, compute start_date and end_date (YYYY-MM-DD, inclusive — for \
a single day just repeat the same date in both). If they gave no time indication at all, leave both null.
If it is NOT a planning request, leave the fields null and instead write a short, warm, in-character \
reply (max ~20 words) as "casual_reply" — you're Weatherly, a weather-planning assistant for trips, \
events, and farming.

Respond with ONLY a JSON object, no other text, in this exact shape:
{{"is_planning_request": <true or false>, "location": "<city/place name or null>", "date_phrase": "<the phrase describing when, verbatim or paraphrased, or null>", "start_date": "<YYYY-MM-DD or null>", "end_date": "<YYYY-MM-DD or null>", "activity": "<short activity description or null>", "event_size": "<number of people if mentioned, else null>", "casual_reply": "<reply if not a planning request, else null>"}}

User message: "{message}"
JSON:"""

    parsed = call_llm_json(prompt, timeout=20)
    if parsed is None:
        return None
    location = parsed.get("location") or None
    activity = parsed.get("activity") or None
    is_planning_request = parsed.get("is_planning_request", True)
    if is_planning_request is False and (location or activity):
        # A smaller/local model can contradict itself — flagging "not a planning
        # request" while still extracting a location or activity. Trust the
        # concrete extraction over the classification in that case.
        is_planning_request = True
    return {
        "is_planning_request": is_planning_request,
        "location": location,
        "date_phrase": parsed.get("date_phrase") or None,
        "start_date": parsed.get("start_date") or None,
        "end_date": parsed.get("end_date") or None,
        "activity": activity,
        "event_size": parsed.get("event_size") or None,
        "casual_reply": parsed.get("casual_reply") or None,
    }


def _extract_intent_rules(message: str) -> dict:
    """Regex/keyword fallback intent extractor — no external service required."""
    lower = message.lower()

    activity = None
    for label, keywords in ACTIVITY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            activity = label
            break

    word_nums = "|".join(WORD_TO_NUM.keys())
    date_patterns = [
        r"next weekend", r"this weekend", r"next month", r"this month",
        r"next week", r"this week", r"tomorrow", r"today",
        r"in \d+ (?:day|days|week|weeks|month|months)",
        rf"(?:{word_nums}|\d+) (?:day|days|week|weeks|month|months) from now",
        rf"in (?:{word_nums}) (?:day|days|week|weeks|month|months)",
        r"next (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        r"on \d{4}-\d{2}-\d{2}", r"\d{4}-\d{2}-\d{2}",
        rf"\b(?:{_MONTH_RE})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b",
        rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{_MONTH_RE})\.?(?:,?\s+\d{{4}})?\b",
    ]
    date_phrase = None
    for pat in date_patterns:
        m = re.search(pat, lower)
        if m:
            date_phrase = m.group(0)
            break

    location = None

    _COMMON_WORDS = {
        "next", "this", "the", "a", "an", "for", "good", "safe", "best", "outdoor",
        "indoor", "what", "which", "where", "when", "how", "can", "will", "would",
        "should", "is", "are", "was", "my", "your", "our", "their", "some", "any",
        "compare", "find", "get", "show", "tell", "give", "help", "please",
    }

    _FILLER_WORDS = _COMMON_WORDS | {
        "i", "we", "you", "it", "in", "at", "on", "to", "of", "or", "and", "with",
        "no", "not", "do", "does", "doing", "did", "have", "having", "had", "be",
        "if", "so", "there", "here", "me", "us", "them", "he", "she", "they",
        "want", "wanna", "like", "plan", "planning", "organize", "organise",
        "hold", "holding", "host", "hosting", "go", "going", "visit", "visiting",
        "weather", "forecast", "climate", "conditions", "condition", "temperature",
        "idea", "safety", "risk", "risky", "possible", "advisable", "recommend",
        "recommended", "suitable", "ok", "okay",
        "rain", "raining", "rainy", "sunny", "cloudy", "hot", "cold", "cool",
        "warm", "windy", "humid", "look", "looking", "looks", "seem", "seems",
        "outside", "out", "day", "days", "week", "weeks",
        "month", "months", "weekend", "tomorrow", "today", "now", "from", "then",
        "please", "thanks", "thank",
        "whats", "hows", "wheres", "whens", "whos", "thats", "theres", "im",
        "ive", "youre", "youve", "dont", "doesnt", "didnt", "isnt", "arent",
        "wasnt", "werent", "wont", "cant", "couldnt", "wouldnt", "shouldnt",
        "hasnt", "havent",
    }

    cmp_match = re.search(
        r"(?i)(?:compare\s+)?([A-Za-z][A-Za-z\s]{1,20}?)\s+(?:vs\.?|versus|or)\s+([A-Za-z][A-Za-z\s]{1,20}?)(?=\s+(?:for|next|this|in|on)\b|[.?!,]|$)",
        message,
    )
    if cmp_match:
        a = cmp_match.group(1).strip().title()
        b = cmp_match.group(2).strip().title()
        if a.lower() not in _COMMON_WORDS and b.lower() not in _COMMON_WORDS:
            location = f"{a} vs {b}"

    if not location:
        in_match = re.search(
            r"(?i)\bin\s+([A-Za-z][A-Za-z\s]{1,24}?)(?=\s*(?:next|this|tomorrow|today|on\s+\d|in\s+\d|instead|,|\.|\?|!|$))",
            message,
        )
        if in_match:
            candidate = in_match.group(1).strip().title()
            if candidate.lower() not in _COMMON_WORDS and len(candidate) >= 3:
                location = candidate

    if not location:
        prep_match = re.search(
            r"(?i)\b(?:to|at|near|around|about)\s+([A-Za-z][A-Za-z\s]{1,24}?)(?=\s*(?:next|this|tomorrow|today|on\s+\d|in\s+\d|instead|,|\.|\?|!|$))",
            message,
        )
        if prep_match:
            candidate = prep_match.group(1).strip().title()
            if candidate.lower() not in _COMMON_WORDS and len(candidate) >= 3:
                location = candidate

    if not location:
        city_country = re.search(r"([A-Z][A-Za-z]{2,}),\s*([A-Z][A-Za-z\s]{2,20}?)(?=\s+(?:next|this|for)|[.?!,]|$)", message)
        if city_country:
            location = f"{city_country.group(1)}, {city_country.group(2).strip()}"

    if not location:
        tail_match = re.search(
            r"\b([A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]{2,})?)\s+(?:next|this|in|on)\b",
            message,
        )
        if tail_match:
            candidate = tail_match.group(1).strip()
            if candidate.lower() not in _COMMON_WORDS:
                location = candidate

    if not location:
        remainder = lower
        if date_phrase:
            remainder = remainder.replace(date_phrase, " ")
        if activity:
            for kw in ACTIVITY_KEYWORDS[activity]:
                remainder = re.sub(rf"\b{re.escape(kw)}\w*", " ", remainder)
        remainder = re.sub(r"\d+\s*(?:people|guests|attendees)", " ", remainder)
        remainder = re.sub(rf"\b(?:{'|'.join(_FILLER_WORDS)})\b", " ", remainder)
        remainder = re.sub(r"[^\w\s]", " ", remainder)
        remainder = re.sub(r"\s+", " ", remainder).strip()
        if remainder and 3 <= len(remainder) and len(remainder.split()) <= 4:
            location = remainder.title()

    size_match = re.search(r"(\d{1,5})\s*(?:people|guests|attendees)", lower)
    event_size = size_match.group(1) if size_match else None

    return {
        "location": location,
        "date_phrase": date_phrase,
        "activity": activity,
        "event_size": event_size,
    }


def extract_intent(message: str) -> dict:
    intent = _extract_intent_llm(message)
    if intent is None:
        intent = _extract_intent_rules(message)
        intent["is_planning_request"] = True
        intent["casual_reply"] = None
        intent["start_date"] = None
        intent["end_date"] = None
    elif intent.get("is_planning_request") is False:
        # The LLM (especially the small local model) can misread a genuine
        # planning request as small talk when it fails to spot the location/
        # activity. Cross-check with the rule-based extractor before trusting
        # that verdict — if it finds a concrete activity or location, this
        # wasn't chitchat.
        fallback = _extract_intent_rules(message)
        if fallback.get("activity") or fallback.get("location"):
            intent["is_planning_request"] = True
            intent["casual_reply"] = None
            for key in ("location", "date_phrase", "activity", "event_size"):
                if not intent.get(key):
                    intent[key] = fallback.get(key)
    else:
        fallback = _extract_intent_rules(message)
        for key in ("location", "date_phrase", "activity", "event_size"):
            if not intent.get(key):
                intent[key] = fallback.get(key)
    return intent


def geocode_location(name: str | None) -> tuple[float, float, str] | tuple[None, None, str]:
    """Returns (lat, lon, display_name) on success, or (None, None, error_detail) on failure.

    When the query resolves to a whole country or large region (place_rank <= 8)
    the coordinates are a meaningless centroid — we refuse them and return a
    suggestion for a specific city instead so the agent can give a helpful reply.
    """
    if not name:
        return None, None, "no location name provided"

    global _last_nominatim_call
    elapsed = time.monotonic() - _last_nominatim_call
    if elapsed < _NOMINATIM_MIN_INTERVAL:
        time.sleep(_NOMINATIM_MIN_INTERVAL - elapsed)

    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": name, "format": "json", "limit": 1, "addressdetails": 0},
            headers={"User-Agent": "WeatherlyAI/1.0 (sinurawahalathanthri11@gmail.com)"},
            timeout=10,
        )
        _last_nominatim_call = time.monotonic()
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None, None, f"no results found for '{name}'"
        top = results[0]

        place_rank = int(top.get("place_rank", 0))
        if place_rank <= _TOO_BROAD_RANK:
            hint_city = COUNTRY_CITY_HINTS.get(name.strip().lower(), "")
            hint = f" Try a specific city, e.g. \"{hint_city}\"." if hint_city else " Please name a specific city."
            return None, None, f"TOO_BROAD: '{name}' is a country or large region.{hint}"

        return float(top["lat"]), float(top["lon"]), top.get("display_name", name)
    except Exception as e:
        print(f"Geocoding error for '{name}': {e}")
        return None, None, f"geocoding error: {e}"


def _next_weekday(base: datetime, weekday: int) -> datetime:
    days_ahead = (weekday - base.weekday() + 7) % 7
    days_ahead = days_ahead or 7
    return base + timedelta(days=days_ahead)


def _parse_count(text: str) -> int | None:
    """Extract a number from text — handles both digits and English words."""
    m = re.search(r"\d+", text)
    if m:
        return int(m.group(0))
    for word, num in WORD_TO_NUM.items():
        if word in text:
            return num
    return None


def _parse_month_day_year(phrase: str) -> tuple[int, int, int | None] | None:
    """Finds a month name and a 1-31 day number anywhere in the phrase (in either
    order — "august 9" or "9th of august"), plus an optional 4-digit year."""
    month_match = re.search(rf"\b({_MONTH_RE})\.?\b", phrase)
    if not month_match:
        return None
    month = MONTH_NAMES[month_match.group(1)]

    day = None
    for day_match in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", phrase):
        candidate = int(day_match.group(1))
        if 1 <= candidate <= 31 and len(day_match.group(1)) <= 2:
            day = candidate
            break
    if day is None:
        return None

    year_match = re.search(r"\b(\d{4})\b", phrase)
    year = int(year_match.group(1)) if year_match else None
    return month, day, year


def parse_iso_date(value: str | None) -> datetime | None:
    """Validates and parses a YYYY-MM-DD string (as computed by the LLM's own
    date arithmetic in extract_intent). Returns None on anything malformed so
    callers can fall back to the phrase-based resolver below."""
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None


def resolve_date_phrase(phrase: str | None) -> tuple[datetime, datetime]:
    """Resolves a relative-date phrase into a concrete (start, end) datetime range.
    Defaults to 'next month' (a representative week) if nothing is understood."""
    now = datetime.now()
    phrase = (phrase or "").lower().strip()

    explicit = re.search(r"(\d{4}-\d{2}-\d{2})", phrase)
    if explicit:
        d = datetime.strptime(explicit.group(1), "%Y-%m-%d")
        return d, d + timedelta(days=2)

    month_day = _parse_month_day_year(phrase)
    if month_day:
        month, day, year = month_day
        resolved_year = year or now.year
        try:
            d = datetime(resolved_year, month, day)
        except ValueError:
            d = None
        if d:
            if year is None and d.date() < now.date():
                d = d.replace(year=resolved_year + 1)
            return d, d + timedelta(days=2)

    if "tomorrow" in phrase:
        d = now + timedelta(days=1)
        return d, d

    if "today" in phrase:
        return now, now

    if "next weekend" in phrase:
        sat = _next_weekday(now, 5)
        if sat <= now + timedelta(days=1):
            sat += timedelta(days=7)
        return sat, sat + timedelta(days=1)

    if "this weekend" in phrase:
        sat = now + timedelta(days=(5 - now.weekday()) % 7)
        return sat, sat + timedelta(days=1)

    for day_name, idx in WEEKDAYS.items():
        if day_name in phrase:
            d = _next_weekday(now, idx)
            return d, d

    m = re.search(r"(\w+)\s+months?\s+from\s+now", phrase)
    if m:
        count = _parse_count(m.group(1))
        if count:
            target = _add_months(now, count)
            return target, target + timedelta(days=6)

    m = re.search(r"(\w+)\s+weeks?\s+from\s+now", phrase)
    if m:
        count = _parse_count(m.group(1))
        if count:
            d = now + timedelta(weeks=count)
            return d, d + timedelta(days=6)

    m = re.search(r"(\w+)\s+days?\s+from\s+now", phrase)
    if m:
        count = _parse_count(m.group(1))
        if count:
            d = now + timedelta(days=count)
            return d, d

    m = re.search(r"in\s+(\w+)\s+month", phrase)
    if m:
        count = _parse_count(m.group(1))
        if count:
            target = _add_months(now, count)
            return target, target + timedelta(days=6)

    m = re.search(r"in\s+(\w+)\s+week", phrase)
    if m:
        count = _parse_count(m.group(1))
        if count:
            d = now + timedelta(weeks=count)
            return d, d + timedelta(days=2)

    m = re.search(r"in\s+(\w+)\s+day", phrase)
    if m:
        count = _parse_count(m.group(1))
        if count:
            d = now + timedelta(days=count)
            return d, d

    if "next week" in phrase:
        d = now + timedelta(weeks=1)
        return d, d + timedelta(days=6)

    if "this week" in phrase:
        return now, now + timedelta(days=(6 - now.weekday()))

    if "next month" in phrase or not phrase:
        target = _add_months(now, 1)
        return target, target + timedelta(days=6)

    if "this month" in phrase:
        last_day = calendar.monthrange(now.year, now.month)[1]
        return now, now.replace(day=min(now.day + 6, last_day))

    target = _add_months(now, 1)
    return target, target + timedelta(days=6)


def resolve_scan_range(phrase: str | None) -> tuple[datetime, datetime]:
    """Like resolve_date_phrase, but widens coarse phrases ('next month') into a
    full scannable window instead of one representative week — used by the
    agent's scan_best_date plan, which needs a real range to sample across."""
    now = datetime.now()
    phrase = (phrase or "").lower().strip()

    if "next month" in phrase or not phrase:
        target = _add_months(now, 1)
        last_day = calendar.monthrange(target.year, target.month)[1]
        return target.replace(day=1), target.replace(day=last_day)

    if "this month" in phrase:
        last_day = calendar.monthrange(now.year, now.month)[1]
        return now, now.replace(day=last_day)

    m = re.search(r"in\s+(\w+)\s+month", phrase)
    if not m:
        m = re.search(r"(\w+)\s+months?\s+from\s+now", phrase)
    if m:
        months = _parse_count(m.group(1)) or 1
        target = _add_months(now, months)
        last_day = calendar.monthrange(target.year, target.month)[1]
        return now, target.replace(day=last_day)

    return resolve_date_phrase(phrase)


def _add_months(base: datetime, months: int) -> datetime:
    month = base.month - 1 + months
    year = base.year + month // 12
    month = month % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return base.replace(year=year, month=month, day=day)
