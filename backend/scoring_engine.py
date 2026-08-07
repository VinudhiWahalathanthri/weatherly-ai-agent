"""
Activity-Specific Scoring Engine
----------------------------------
Replaces the generic score_option() in agent.py with proper separated scores:
  - Comfort Score:     How pleasant the conditions feel for humans
  - Safety Score:      Risk of harm, cancellation or damage
  - Suitability Score: How well conditions match THIS specific activity

Each activity has its own profile with different thresholds and weights.
The engine also generates a natural-language explanation of WHY it scored
as it did — never just a number dump.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math


@dataclass
class ActivityProfile:
    name: str
    temp_ideal: tuple[float, float]
    temp_acceptable: tuple[float, float]
    rain_ok: float
    rain_caution: float
    rain_unsafe: float
    wind_ok: float
    wind_caution: float
    wind_unsafe: float
    humidity_ideal: tuple[float, float]
    cloud_preference: float
    comfort_weight: float = 0.35
    safety_weight: float = 0.30
    suitability_weight: float = 0.35
    tips: list[str] = field(default_factory=list)
    min_backup_for_size: int = 50


PROFILES: dict[str, ActivityProfile] = {
    "wedding": ActivityProfile(
        name="Outdoor Wedding / Ceremony",
        temp_ideal=(20, 28),
        temp_acceptable=(16, 34),
        rain_ok=0.5, rain_caution=2.0, rain_unsafe=5.0,
        wind_ok=15, wind_caution=25, wind_unsafe=40,
        humidity_ideal=(40, 70),
        cloud_preference=0.5,
        tips=["Book a marquee or indoor backup", "Monitor forecast 48h before", "Provide shade and fans if >30°C", "Consider evening ceremony if very hot"],
    ),
    "outdoor ceremony": ActivityProfile(
        name="Outdoor Ceremony / Reception",
        temp_ideal=(20, 28), temp_acceptable=(16, 34),
        rain_ok=0.5, rain_caution=2.0, rain_unsafe=5.0,
        wind_ok=15, wind_caution=25, wind_unsafe=40,
        humidity_ideal=(40, 70), cloud_preference=0.5,
        tips=["Book a marquee or indoor backup", "Monitor forecast 48h before"],
    ),
    "outdoor party": ActivityProfile(
        name="Outdoor Party / Celebration",
        temp_ideal=(21, 30),
        temp_acceptable=(17, 35),
        rain_ok=1.0, rain_caution=3.0, rain_unsafe=8.0,
        wind_ok=20, wind_caution=30, wind_unsafe=50,
        humidity_ideal=(40, 75),
        cloud_preference=0.5,
        tips=["Set up a gazebo or canopy", "Have towels and rain covers ready", "Book a backup indoor venue"],
    ),
    "birthday": ActivityProfile(
        name="Birthday / Social Gathering",
        temp_ideal=(21, 30), temp_acceptable=(17, 35),
        rain_ok=1.0, rain_caution=3.0, rain_unsafe=8.0,
        wind_ok=20, wind_caution=30, wind_unsafe=50,
        humidity_ideal=(40, 75), cloud_preference=0.5,
        tips=["Set up a gazebo or canopy", "Have a wet-weather plan ready"],
    ),
    "cricket": ActivityProfile(
        name="Cricket Tournament",
        temp_ideal=(18, 30),
        temp_acceptable=(14, 36),
        rain_ok=0.2, rain_caution=1.0, rain_unsafe=3.0,
        wind_ok=25, wind_caution=40, wind_unsafe=60,
        humidity_ideal=(40, 80),
        cloud_preference=0.8,
        tips=["Check Duckworth-Lewis rules for rain interruptions", "Cover pitch overnight if rain expected", "Provide hydration stations if >32°C"],
    ),
    "sports event": ActivityProfile(
        name="Sports Event / Tournament",
        temp_ideal=(15, 28), temp_acceptable=(10, 35),
        rain_ok=1.0, rain_caution=3.0, rain_unsafe=8.0,
        wind_ok=25, wind_caution=40, wind_unsafe=60,
        humidity_ideal=(40, 80), cloud_preference=0.8,
        tips=["Hydrate players heavily above 30°C", "Have lightning protocol ready"],
    ),
    "outdoor sports": ActivityProfile(
        name="Outdoor Sports",
        temp_ideal=(15, 28), temp_acceptable=(10, 35),
        rain_ok=1.0, rain_caution=3.0, rain_unsafe=8.0,
        wind_ok=25, wind_caution=40, wind_unsafe=60,
        humidity_ideal=(40, 80), cloud_preference=0.8,
        tips=["Hydrate heavily above 30°C", "Lightning protocol if storms forecast"],
    ),
    "football": ActivityProfile(
        name="Football / Soccer Match",
        temp_ideal=(12, 25), temp_acceptable=(5, 32),
        rain_ok=2.0, rain_caution=5.0, rain_unsafe=12.0,
        wind_ok=30, wind_caution=50, wind_unsafe=70,
        humidity_ideal=(40, 80), cloud_preference=1.0,
        tips=["Wet pitch can improve play but watch for waterlogging"],
    ),
    "hiking": ActivityProfile(
        name="Hiking / Trekking",
        temp_ideal=(12, 24),
        temp_acceptable=(5, 32),
        rain_ok=1.0, rain_caution=5.0, rain_unsafe=15.0,
        wind_ok=30, wind_caution=50, wind_unsafe=70,
        humidity_ideal=(30, 75),
        cloud_preference=1.0,
        tips=["Pack waterproofs and layers", "Avoid ridges in lightning storms", "Start early to avoid afternoon heat"],
    ),
    "camping": ActivityProfile(
        name="Camping",
        temp_ideal=(12, 26), temp_acceptable=(5, 32),
        rain_ok=2.0, rain_caution=8.0, rain_unsafe=20.0,
        wind_ok=25, wind_caution=40, wind_unsafe=60,
        humidity_ideal=(30, 80), cloud_preference=1.0,
        tips=["Waterproof all gear", "Avoid camping near rivers if heavy rain expected"],
    ),
    "beach vacation": ActivityProfile(
        name="Beach Holiday",
        temp_ideal=(26, 34),
        temp_acceptable=(22, 38),
        rain_ok=1.0, rain_caution=4.0, rain_unsafe=10.0,
        wind_ok=20, wind_caution=35, wind_unsafe=55,
        humidity_ideal=(55, 80),
        cloud_preference=0.2,
        tips=["Apply SPF 50+", "UV index often highest 11am–3pm at beach", "Strong wind = rough surf — check red flag conditions"],
    ),
    "travel": ActivityProfile(
        name="Travel / Tourism",
        temp_ideal=(18, 30), temp_acceptable=(10, 36),
        rain_ok=3.0, rain_caution=8.0, rain_unsafe=20.0,
        wind_ok=30, wind_caution=50, wind_unsafe=70,
        humidity_ideal=(30, 80), cloud_preference=1.0,
        tips=["Keep flexible itinerary for rain days", "Light rain rarely ruins sightseeing"],
    ),
    "photography session": ActivityProfile(
        name="Photography Session",
        temp_ideal=(16, 28), temp_acceptable=(10, 34),
        rain_ok=0.5, rain_caution=2.0, rain_unsafe=6.0,
        wind_ok=20, wind_caution=35, wind_unsafe=50,
        humidity_ideal=(40, 75),
        cloud_preference=1.2,
        tips=["Golden hour (sunrise/sunset) best for portraits", "Overcast = perfect diffused light for photography", "Rain can create beautiful reflections"],
    ),
    "picnic": ActivityProfile(
        name="Picnic / Garden Party",
        temp_ideal=(20, 28), temp_acceptable=(16, 33),
        rain_ok=0.5, rain_caution=2.0, rain_unsafe=5.0,
        wind_ok=15, wind_caution=25, wind_unsafe=40,
        humidity_ideal=(40, 70), cloud_preference=0.5,
        tips=["Pick shaded area for hot days", "Watch for ants and insects in humid conditions"],
    ),
    "surfing": ActivityProfile(
        name="Surfing / Bodyboarding",
        temp_ideal=(22, 32), temp_acceptable=(18, 36),
        rain_ok=5.0, rain_caution=15.0, rain_unsafe=30.0,
        wind_ok=20, wind_caution=35, wind_unsafe=55,
        humidity_ideal=(60, 85), cloud_preference=1.0,
        tips=["Offshore wind = cleaner waves", "Check wave height — above 3m avoid for beginners"],
    ),
    "festival": ActivityProfile(
        name="Festival / Market / Concert",
        temp_ideal=(18, 28), temp_acceptable=(12, 34),
        rain_ok=1.0, rain_caution=4.0, rain_unsafe=10.0,
        wind_ok=20, wind_caution=35, wind_unsafe=55,
        humidity_ideal=(40, 75), cloud_preference=0.7,
        tips=["Wellies and ponchos for guests if rain possible", "Ensure infrastructure is anchored for wind"],
    ),
    "farming": ActivityProfile(
        name="Agricultural / Farm Work",
        temp_ideal=(18, 30), temp_acceptable=(10, 38),
        rain_ok=5.0, rain_caution=20.0, rain_unsafe=50.0,
        wind_ok=25, wind_caution=40, wind_unsafe=60,
        humidity_ideal=(40, 85), cloud_preference=1.0,
        tips=["Heavy rain delays harvesting and spraying", "Extreme heat requires worker breaks every 45 mins"],
    ),
    "uav operation": ActivityProfile(
        name="UAV / Drone Operation",
        temp_ideal=(10, 28), temp_acceptable=(5, 35),
        rain_ok=0.0, rain_caution=0.5, rain_unsafe=2.0,
        wind_ok=20, wind_caution=35, wind_unsafe=50,
        humidity_ideal=(20, 75), cloud_preference=0.5,
        tips=["Wind above 35km/h = grounded for most drones", "Check local air regulations"],
    ),
    "_default": ActivityProfile(
        name="Outdoor Activity",
        temp_ideal=(18, 28), temp_acceptable=(12, 35),
        rain_ok=2.0, rain_caution=6.0, rain_unsafe=15.0,
        wind_ok=25, wind_caution=40, wind_unsafe=65,
        humidity_ideal=(40, 80), cloud_preference=1.0,
        tips=["Check conditions 24h before", "Have a backup plan for rain"],
    ),
}


def _get_profile(activity: str) -> ActivityProfile:
    lower = activity.lower().strip()
    if lower in PROFILES:
        return PROFILES[lower]
    for key, profile in PROFILES.items():
        if key != "_default" and key in lower:
            return profile
    return PROFILES["_default"]


def _linear_score(value: float, ideal_lo: float, ideal_hi: float,
                   ok_lo: float, ok_hi: float) -> float:
    """Returns 100 inside ideal, slopes to 0 outside ok range."""
    if ideal_lo <= value <= ideal_hi:
        return 100.0
    if value < ok_lo or value > ok_hi:
        return 0.0
    if value < ideal_lo:
        return 100.0 * (value - ok_lo) / (ideal_lo - ok_lo + 1e-6)
    return 100.0 * (ok_hi - value) / (ok_hi - ideal_hi + 1e-6)


def _rain_score(rain: float, ok: float, caution: float, unsafe: float) -> float:
    if rain <= ok:
        return 100.0
    if rain >= unsafe:
        return 0.0
    if rain <= caution:
        return 100.0 * (1 - (rain - ok) / (caution - ok + 1e-6)) * 0.5 + 50.0
    return 50.0 * (1 - (rain - caution) / (unsafe - caution + 1e-6))


def _wind_score(wind: float, ok: float, caution: float, unsafe: float) -> float:
    return _rain_score(wind, ok, caution, unsafe)


def _humidity_score(rh: float, ideal_lo: float, ideal_hi: float) -> float:
    return _linear_score(rh, ideal_lo, ideal_hi, 0, 100)


def _cloud_score(cloud_pct: float, preference: float) -> float:
    """preference: 0=loves clear, 1=neutral, 2=prefers overcast."""
    if preference <= 0.5:
        return max(0.0, 100.0 - cloud_pct * (0.5 + (0.5 - preference)))
    if preference >= 1.5:
        return min(100.0, cloud_pct * 1.2)
    return 85.0


def detect_weather_risks(pred: dict, profile: ActivityProfile) -> list[str]:
    risks = []
    temp = pred.get("feels_like") or pred.get("T2M", 22)
    rain = pred.get("PRECTOTCORR", 0)
    wind = pred.get("WS10M", 0)
    rh = pred.get("RH2M", 70)
    cloud = pred.get("CLOUD_AMT", pred.get("CloudPct", 50))

    if temp >= 38:
        risks.append("Extreme heat (≥38°C feels-like) — heat exhaustion risk")
    elif temp >= 34 and rh >= 70:
        risks.append(f"Hot and humid ({temp:.0f}°C feels-like, {rh:.0f}% humidity) — uncomfortable for prolonged outdoor stays")
    elif temp <= 8:
        risks.append(f"Cold conditions ({temp:.0f}°C) — dress in layers, hypothermia risk in wet weather")

    if rain >= profile.rain_unsafe:
        risks.append(f"Heavy rain ({rain:.1f}mm/day) — event disruption highly likely")
    elif rain >= profile.rain_caution:
        risks.append(f"Moderate rain ({rain:.1f}mm/day) — plan for wet conditions")

    if wind >= profile.wind_unsafe:
        risks.append(f"Dangerous winds ({wind:.0f}km/h) — structural and safety hazard")
    elif wind >= profile.wind_caution:
        risks.append(f"Strong winds ({wind:.0f}km/h) — may disrupt outdoor setups")

    if rh >= 90:
        risks.append(f"Very high humidity ({rh:.0f}%) — oppressive, consider air-conditioned spaces")

    if cloud >= 80 and rain < profile.rain_ok:
        risks.append("Heavy cloud cover — overcast conditions likely")

    return risks


def detect_positives(pred: dict, profile: ActivityProfile) -> list[str]:
    positives = []
    temp = pred.get("feels_like") or pred.get("T2M", 22)
    rain = pred.get("PRECTOTCORR", 0)
    wind = pred.get("WS10M", 0)
    rh = pred.get("RH2M", 70)

    if profile.temp_ideal[0] <= temp <= profile.temp_ideal[1]:
        positives.append(f"Temperature is ideal ({temp:.0f}°C feels-like)")
    if rain <= profile.rain_ok:
        positives.append("Rainfall is minimal — dry conditions expected")
    if wind <= profile.wind_ok:
        positives.append(f"Calm winds ({wind:.0f}km/h) — comfortable outdoor conditions")
    if profile.humidity_ideal[0] <= rh <= profile.humidity_ideal[1]:
        positives.append(f"Humidity is comfortable ({rh:.0f}%)")
    return positives


def compute_scores(pred: dict, activity: str) -> dict:
    """
    Returns:
      comfort       int 0-100
      safety        int 0-100
      suitability   int 0-100
      overall       int 0-100 (weighted blend)
      grade         str  A+ / A / B / C / D / F
      risks         list[str]
      positives     list[str]
      profile_name  str
    """
    profile = _get_profile(activity)

    temp = pred.get("feels_like") or pred.get("T2M", 22)
    rain = pred.get("PRECTOTCORR", 0)
    wind = pred.get("WS10M", 0)
    rh   = pred.get("RH2M", 70)
    cloud = pred.get("CLOUD_AMT", pred.get("CloudPct", 50))

    temp_s  = _linear_score(temp, *profile.temp_ideal, *profile.temp_acceptable)
    rain_s  = _rain_score(rain, profile.rain_ok, profile.rain_caution, profile.rain_unsafe)
    wind_s  = _wind_score(wind, profile.wind_ok, profile.wind_caution, profile.wind_unsafe)
    humid_s = _humidity_score(rh, *profile.humidity_ideal)
    cloud_s = _cloud_score(cloud, profile.cloud_preference)
    comfort = int(0.35 * temp_s + 0.25 * rain_s + 0.20 * wind_s + 0.12 * humid_s + 0.08 * cloud_s)

    s_temp = 100.0 if temp <= 36 else max(0.0, 100.0 - (temp - 36) * 15)
    s_rain = 100.0 if rain < profile.rain_caution else max(0.0, 100.0 - (rain - profile.rain_caution) * 8)
    s_wind = 100.0 if wind < profile.wind_caution else max(0.0, 100.0 - (wind - profile.wind_caution) * 4)
    if temp <= 0:
        s_temp = max(0.0, s_temp - 40)
    safety = int(0.35 * s_temp + 0.35 * s_rain + 0.30 * s_wind)

    ml_status = pred.get("suitability_status", "Caution")
    ml_base = {"Suitable": 80, "Suitable (Fallback)": 75, "Caution": 50,
                "Caution (ML Error)": 50, "Unsuitable": 20, "Unsuitable (High Risk)": 10}.get(ml_status, 50)

    activity_adj = 0.0
    activity_adj += (temp_s - 50) * 0.15
    activity_adj += (rain_s - 50) * 0.20
    activity_adj += (wind_s - 50) * 0.10
    suitability = int(max(0, min(100, ml_base + activity_adj * 0.5)))

    if rain >= profile.rain_unsafe or wind >= profile.wind_unsafe:
        comfort = min(comfort, 30)
        safety = min(safety, 30)
        suitability = min(suitability, 30)
    elif rain >= profile.rain_caution or wind >= profile.wind_caution:
        comfort = min(comfort, 60)
        safety = min(safety, 65)
        suitability = min(suitability, 60)

    overall = int(
        profile.comfort_weight * comfort
        + profile.safety_weight * safety
        + profile.suitability_weight * suitability
    )
    overall = max(0, min(100, overall))

    if overall >= 90: grade = "A+"
    elif overall >= 80: grade = "A"
    elif overall >= 70: grade = "B"
    elif overall >= 55: grade = "C"
    elif overall >= 35: grade = "D"
    else: grade = "F"

    risks     = detect_weather_risks(pred, profile)
    positives = detect_positives(pred, profile)

    return {
        "comfort":       comfort,
        "safety":        safety,
        "suitability":   suitability,
        "overall":       overall,
        "grade":         grade,
        "risks":         risks,
        "positives":     positives,
        "profile_name":  profile.name,
        "tips":          profile.tips,
    }


def explain_decision(
    scores: dict,
    pred: dict,
    activity: str,
    location: str,
    date: str,
    confidence_label: str = "",
) -> str:
    """Generates a 3-4 sentence human-readable explanation of the recommendation."""
    temp = pred.get("feels_like") or pred.get("T2M", 22)
    rain = pred.get("PRECTOTCORR", 0)
    wind = pred.get("WS10M", 0)
    rh   = pred.get("RH2M", 70)

    overall = scores.get("overall", scores.get("score", 50))
    grade = scores.get("grade", "C")

    profile = _get_profile(activity)
    severe_hazard = rain >= profile.rain_unsafe or wind >= profile.wind_unsafe

    if severe_hazard:
        verdict = f"{location} on {date} is not recommended for {activity} due to hazardous conditions"
    elif overall >= 80:
        verdict = f"{location} on {date} is an excellent choice for {activity}"
    elif overall >= 65:
        verdict = f"{location} on {date} is a good option for {activity}"
    elif overall >= 50:
        verdict = f"{location} on {date} is workable for {activity}, with some caveats"
    else:
        verdict = f"{location} on {date} presents significant challenges for {activity}"

    why_parts = []
    if scores["positives"]:
        why_parts.append(scores["positives"][0].lower())
    if scores["comfort"] >= 75:
        why_parts.append(f"conditions feel comfortable ({temp:.0f}°C, {rh:.0f}% humidity)")

    why = f"The main strengths are {', and '.join(why_parts[:2])}." if why_parts else ""

    risk_str = ""
    if scores["risks"]:
        top_risk = scores["risks"][0]
        risk_str = f" The key concern is {top_risk.lower()}."

    conf_note = f" Note: {confidence_label}." if confidence_label else ""

    tips = scores.get("tips", [])
    tip_str = f" Tip: {tips[0]}." if tips else ""

    explanation = f"{verdict} (Overall: {overall}/100, Grade {grade}). {why}{risk_str}{conf_note}{tip_str}"
    return explanation.strip()
