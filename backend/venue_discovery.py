"""
Venue Discovery Tool
---------------------
Finds nearby hotels, parks, and event venues using the Overpass API
(OpenStreetMap data — completely free, no API key required).

Called by the planning agent after it identifies the best location/date
so the user gets actionable links alongside the weather recommendation.
"""

import math
import requests

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# OSM tags relevant to each activity type. The agent matches the activity
# string against these keys (substring match, lowercase).
ACTIVITY_VENUE_TAGS: dict[str, list[tuple[str, str]]] = {
    "wedding":        [("amenity", "events_venue"), ("tourism", "hotel"), ("leisure", "park")],
    "ceremony":       [("amenity", "events_venue"), ("tourism", "hotel"), ("leisure", "park")],
    "party":          [("leisure", "park"), ("amenity", "events_venue"), ("leisure", "recreation_ground")],
    "festival":       [("leisure", "park"), ("amenity", "events_venue"), ("leisure", "recreation_ground")],
    "hiking":         [("leisure", "nature_reserve"), ("tourism", "camp_site"), ("leisure", "park")],
    "camping":        [("tourism", "camp_site"), ("leisure", "nature_reserve")],
    "picnic":         [("leisure", "park"), ("leisure", "garden")],
    "cricket":        [("leisure", "sports_centre"), ("leisure", "pitch"), ("leisure", "park")],
    "football":       [("leisure", "sports_centre"), ("leisure", "pitch"), ("leisure", "stadium")],
    "sports":         [("leisure", "sports_centre"), ("leisure", "pitch"), ("leisure", "stadium")],
    "tournament":     [("leisure", "sports_centre"), ("leisure", "stadium"), ("leisure", "pitch")],
    "photography":    [("leisure", "park"), ("leisure", "garden"), ("tourism", "attraction")],
    "travel":         [("tourism", "hotel"), ("tourism", "hostel"), ("tourism", "attraction")],
    "vacation":       [("tourism", "hotel"), ("tourism", "resort"), ("tourism", "attraction")],
    "surfing":        [("leisure", "beach_resort"), ("leisure", "park")],
    "swimming":       [("leisure", "swimming_pool"), ("leisure", "beach_resort")],
    # Farming / agricultural activities
    "farming":        [("shop", "agrarian"), ("shop", "farm"), ("amenity", "marketplace")],
    "harvest":        [("shop", "agrarian"), ("amenity", "marketplace"), ("landuse", "farmyard")],
    "planting":       [("shop", "agrarian"), ("shop", "farm"), ("landuse", "farmyard")],
    "irrigation":     [("shop", "agrarian"), ("man_made", "water_well"), ("waterway", "irrigation_canal")],
    "crop":           [("shop", "agrarian"), ("shop", "farm"), ("amenity", "marketplace")],
    "agriculture":    [("shop", "agrarian"), ("shop", "farm"), ("amenity", "marketplace")],
    "livestock":      [("shop", "agrarian"), ("landuse", "farmyard"), ("shop", "farm")],
    "rice":           [("shop", "agrarian"), ("amenity", "marketplace"), ("landuse", "farmyard")],
    "wheat":          [("shop", "agrarian"), ("amenity", "marketplace"), ("shop", "farm")],
    # Outdoor events (enhanced)
    "outdoor":        [("amenity", "events_venue"), ("leisure", "park"), ("tourism", "hotel")],
    "conference":     [("amenity", "events_venue"), ("tourism", "hotel"), ("amenity", "community_centre")],
    "concert":        [("amenity", "events_venue"), ("leisure", "stadium"), ("tourism", "hotel")],
    "_default":       [("amenity", "events_venue"), ("leisure", "park"), ("tourism", "hotel")],
}

# Always append these to every result set so the user always gets
# somewhere to stay, regardless of activity.
HOTEL_TAGS: list[tuple[str, str]] = [
    ("tourism", "hotel"),
    ("tourism", "resort"),
    ("tourism", "hostel"),
]


def _match_tags(activity: str) -> list[tuple[str, str]]:
    lower = activity.lower()
    for key, tags in ACTIVITY_VENUE_TAGS.items():
        if key in lower:
            # Merge activity-specific tags with hotel tags, preserving order.
            combined = list(tags)
            for ht in HOTEL_TAGS:
                if ht not in combined:
                    combined.append(ht)
            return combined
    return list(ACTIVITY_VENUE_TAGS["_default"]) + HOTEL_TAGS


def _overpass_query(lat: float, lon: float, tags: list[tuple[str, str]], radius_m: int) -> str:
    node_lines = "\n".join(
        f'  node["{k}"="{v}"](around:{radius_m},{lat},{lon});'
        for k, v in tags
    )
    return f"""[out:json][timeout:12];
(
{node_lines}
);
out body 30;
"""


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def find_venues(lat: float, lon: float, activity: str, radius_m: int = 15000, max_results: int = 6) -> list[dict]:
    """
    Returns up to `max_results` nearby venues relevant to `activity`.
    Each result dict has: name, type, distance_km, website, osm_link, address.
    Returns [] on any error so the agent degrades gracefully.
    """
    tags = _match_tags(activity)
    query = _overpass_query(lat, lon, tags, radius_m)

    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=14,
            headers={"User-Agent": "WeatherlyAI/1.0 (sinurawahalathanthri11@gmail.com)"},
        )
        resp.raise_for_status()
        elements = resp.json().get("elements", [])
    except Exception as e:
        print(f"[WARN] Overpass venue search failed: {e}")
        return []

    venues: list[dict] = []
    seen_names: set[str] = set()

    for el in elements:
        osm_tags = el.get("tags", {})
        name = osm_tags.get("name", "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)

        el_lat = float(el.get("lat", lat))
        el_lon = float(el.get("lon", lon))
        distance_km = round(_haversine(lat, lon, el_lat, el_lon), 1)

        el_type = el.get("type", "node")
        el_id = el.get("id", "")
        osm_link = f"https://www.openstreetmap.org/{el_type}/{el_id}"

        website = (
            osm_tags.get("website")
            or osm_tags.get("contact:website")
            or osm_tags.get("url")
        )

        addr_parts = [
            osm_tags.get("addr:housenumber", ""),
            osm_tags.get("addr:street", ""),
            osm_tags.get("addr:city", ""),
        ]
        address = ", ".join(p for p in addr_parts if p)

        venue_category = (
            osm_tags.get("amenity")
            or osm_tags.get("leisure")
            or osm_tags.get("tourism")
            or "venue"
        )

        venues.append({
            "name": name,
            "type": venue_category.replace("_", " ").title(),
            "distance_km": distance_km,
            "website": website,
            "osm_link": osm_link,
            "address": address or None,
        })

    venues.sort(key=lambda v: v["distance_km"])
    return venues[:max_results]
