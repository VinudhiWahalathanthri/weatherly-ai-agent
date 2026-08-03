"""
AI Planning Agent
------------------
Turns a free-text request like:
    "Can I organize a wedding in Kandy next month?"
into a structured intent {location, date_phrase, activity, event_size},
resolves that intent into a concrete lat/lon + date range, and hands off
to the existing weather/ML pipeline in main.py.

LLM layer: tries a local Ollama server (as described in the proposal —
Llama 3 / Mistral 7B) for natural-language understanding. If Ollama isn't
running, falls back to a lightweight rule-based extractor so the agent
still works out of the box without any extra setup.
"""

import json
import re
import time
import calendar
from datetime import datetime, timedelta

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3.5"  
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy caps public-instance traffic at 1 request/second.
# https://operations.osmfoundation.org/policies/nominatim/
_NOMINATIM_MIN_INTERVAL = 1.05
_last_nominatim_call = 0.0

# place_rank <= 8 means the result is a country or large administrative division —
# far too coarse to mean anything for weather-based event planning.
_TOO_BROAD_RANK = 8

# When a user names a country, suggest its primary planning city so the reply
# is helpful rather than a dead end.
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

# When a user says "beach vacation in India", the agent picks the best coastal
# cities to compare rather than just failing with "too broad".
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
    # Farming activities
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


def _extract_intent_llm(message: str) -> dict | None:
    model = _resolve_ollama_model()
    if not model:
        return None

    prompt = f"""You extract structured planning intent from a user's weather-planning request.
Respond with ONLY a JSON object, no other text, in this exact shape:
{{"location": "<city/place name or null>", "date_phrase": "<the phrase describing when, or null>", "activity": "<short activity description or null>", "event_size": "<number of people if mentioned, else null>"}}

User request: "{message}"
JSON:"""

    try:
        resp = requests.post(
            OLLAMA_URL,
            # think=False skips qwen3.5's chain-of-thought pass — with it enabled a
            # single extraction took ~170s (831 tokens of reasoning) and blew the
            # timeout on every request, silently forcing the rule-based fallback.
            json={"model": model, "prompt": prompt, "stream": False, "think": False},
            timeout=20,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        parsed = json.loads(match.group(0))
        return {
            "location": parsed.get("location") or None,
            "date_phrase": parsed.get("date_phrase") or None,
            "activity": parsed.get("activity") or None,
            "event_size": parsed.get("event_size") or None,
        }
    except Exception as e:
        print(f"Ollama intent extraction failed, falling back to rules: {e}")
        return None


def _extract_intent_rules(message: str) -> dict:
    """Regex/keyword fallback intent extractor — no external service required."""
    lower = message.lower()

    # Activity
    activity = None
    for label, keywords in ACTIVITY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            activity = label
            break

    # Date phrase: capture common relative-date expressions
    word_nums = "|".join(WORD_TO_NUM.keys())
    date_patterns = [
        r"next weekend", r"this weekend", r"next month", r"this month",
        r"next week", r"this week", r"tomorrow", r"today",
        r"in \d+ (?:day|days|week|weeks|month|months)",
        rf"(?:{word_nums}|\d+) (?:day|days|week|weeks|month|months) from now",
        rf"in (?:{word_nums}) (?:day|days|week|weeks|month|months)",
        r"next (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        r"on \d{4}-\d{2}-\d{2}", r"\d{4}-\d{2}-\d{2}",
    ]
    date_phrase = None
    for pat in date_patterns:
        m = re.search(pat, lower)
        if m:
            date_phrase = m.group(0)
            break

    # Location extraction — ordered from most to least reliable.
    # Key principle: "in <city>" is the most reliable signal; "for" is NEVER used
    # because it almost always precedes an activity ("for a cricket tournament"),
    # not a location. Each pattern caps at ~25 chars to avoid grabbing full phrases.
    location = None

    _COMMON_WORDS = {
        "next", "this", "the", "a", "an", "for", "good", "safe", "best", "outdoor",
        "indoor", "what", "which", "where", "when", "how", "can", "will", "would",
        "should", "is", "are", "was", "my", "your", "our", "their", "some", "any",
        "compare", "find", "get", "show", "tell", "give", "help", "please",
    }

    # Used only by the last-resort location fallback (step 6 below): a much wider
    # net of filler/question/domain words to strip out so whatever remains is
    # (hopefully) just the place name, however plainly it was typed.
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
        # Contractions with the apostrophe already stripped by lower() — "what's"
        # arrives here as "whats", etc.
        "whats", "hows", "wheres", "whens", "whos", "thats", "theres", "im",
        "ive", "youre", "youve", "dont", "doesnt", "didnt", "isnt", "arent",
        "wasnt", "werent", "wont", "cant", "couldnt", "wouldnt", "shouldnt",
        "hasnt", "havent",
    }

    # 1. Explicit comparison: "Compare X vs Y", "X vs Y", "X or Y for ..."
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
        # 2. "in <City>" — most reliable: "cricket tournament in Colombo next month"
        #    Uses word boundary + lookahead so it stops at the city name, not the whole rest of sentence.
        in_match = re.search(
            r"(?i)\bin\s+([A-Za-z][A-Za-z\s]{1,24}?)(?=\s*(?:next|this|tomorrow|today|on\s+\d|in\s+\d|instead|,|\.|\?|!|$))",
            message,
        )
        if in_match:
            candidate = in_match.group(1).strip().title()
            if candidate.lower() not in _COMMON_WORDS and len(candidate) >= 3:
                location = candidate

    if not location:
        # 3. Other prepositions (but NOT "for"): "to Kandy", "at Kandy", "near Kandy"
        prep_match = re.search(
            r"(?i)\b(?:to|at|near|around|about)\s+([A-Za-z][A-Za-z\s]{1,24}?)(?=\s*(?:next|this|tomorrow|today|on\s+\d|in\s+\d|instead|,|\.|\?|!|$))",
            message,
        )
        if prep_match:
            candidate = prep_match.group(1).strip().title()
            if candidate.lower() not in _COMMON_WORDS and len(candidate) >= 3:
                location = candidate

    if not location:
        # 4. "City, Country" bare form: "Goa, India"
        city_country = re.search(r"([A-Z][A-Za-z]{2,}),\s*([A-Z][A-Za-z\s]{2,20}?)(?=\s+(?:next|this|for)|[.?!,]|$)", message)
        if city_country:
            location = f"{city_country.group(1)}, {city_country.group(2).strip()}"

    if not location:
        # 5. Title-case proper noun that immediately precedes a date word
        #    e.g. "...cricket tournament Colombo next month"
        tail_match = re.search(
            r"\b([A-Z][A-Za-z]{2,}(?:\s+[A-Z][A-Za-z]{2,})?)\s+(?:next|this|in|on)\b",
            message,
        )
        if tail_match:
            candidate = tail_match.group(1).strip()
            if candidate.lower() not in _COMMON_WORDS:
                location = candidate

    if not location:
        # 6. Last resort — strip out everything already recognized (the activity
        # keyword, the date phrase, filler/question words) and treat whatever's
        # left as the place name. Covers phrasing with no preposition, comma, or
        # capitalization to anchor on, e.g. a bare "homagama sri lanka".
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
        if remainder and len(remainder) >= 3:
            location = remainder.title()

    # Event size
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
    else:
        # Backfill anything the LLM missed using the rule-based extractor
        fallback = _extract_intent_rules(message)
        for key, val in fallback.items():
            if not intent.get(key):
                intent[key] = val
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

        # Reject country/large-region results — their centroid coordinates are
        # useless for weather planning (e.g. "India" → middle of Madhya Pradesh).
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


def resolve_date_phrase(phrase: str | None) -> tuple[datetime, datetime]:
    """Resolves a relative-date phrase into a concrete (start, end) datetime range.
    Defaults to 'next month' (a representative week) if nothing is understood."""
    now = datetime.now()
    phrase = (phrase or "").lower().strip()

    explicit = re.search(r"(\d{4}-\d{2}-\d{2})", phrase)
    if explicit:
        d = datetime.strptime(explicit.group(1), "%Y-%m-%d")
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

    # "X months/weeks/days from now" or "in X months/weeks/days" (digit or word)
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

    # Unrecognized phrase — default to a representative week next month
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

    # For narrower phrases (weekend, specific weekday, "in N days") a scan
    # isn't meaningful — just use the normal resolver's range.
    return resolve_date_phrase(phrase)


def _add_months(base: datetime, months: int) -> datetime:
    month = base.month - 1 + months
    year = base.year + month // 12
    month = month % 12 + 1
    day = min(base.day, calendar.monthrange(year, month)[1])
    return base.replace(year=year, month=month, day=day)
