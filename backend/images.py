"""
Destination Images
--------------------
Best-effort photo lookup for a recommended place, via Wikipedia's free/keyless
REST summary API. Used to show a real photo of the destination alongside its
weather recommendation. Degrades to None on any failure (no page, disambiguation
page with no thumbnail, network error) so callers never need special-case
error handling.
"""

from functools import lru_cache
from urllib.parse import quote

import requests

WIKI_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


@lru_cache(maxsize=256)
def get_place_image(place_name: str) -> str | None:
    """Returns a thumbnail image URL for a place name, or None if unavailable.
    Cached in-process so popular destinations are only looked up once."""
    if not place_name:
        return None
    title = place_name.split(",")[0].strip()
    if not title:
        return None
    try:
        resp = requests.get(
            WIKI_SUMMARY_URL.format(title=quote(title)),
            headers={"User-Agent": "WeatherlyAI/1.0 (sinurawahalathanthri11@gmail.com)"},
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("thumbnail", {}).get("source") or None
    except Exception as e:
        print(f"[WARN] Wikipedia image lookup failed for '{title}': {e}")
        return None
