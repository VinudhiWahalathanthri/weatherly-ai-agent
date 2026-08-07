"""
Farming Intelligence Module
-----------------------------
Gives crop-specific weather suitability scores and agricultural risk alerts
on top of the standard weather forecasts.

Uses the same NASA POWER data the rest of the system fetches — no extra APIs.
All logic is free and works offline.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CropProfile:
    name: str
    temp_range: tuple[float, float, float, float]
    rain_min_monthly: float
    rain_max_monthly: float
    wind_max: float
    humidity_ideal: tuple[float, float]
    keywords: list[str]

    def temp_score(self, temp_c: float) -> int:
        """0–100 score based on how close temp is to ideal range."""
        t_min, t_lo, t_hi, t_max = self.temp_range
        if temp_c < t_min or temp_c > t_max:
            return 0
        if t_lo <= temp_c <= t_hi:
            return 100
        if temp_c < t_lo:
            return int(100 * (temp_c - t_min) / (t_lo - t_min + 0.001))
        return int(100 * (t_max - temp_c) / (t_max - t_hi + 0.001))

    def rain_score(self, rain_mm_monthly: float) -> int:
        if rain_mm_monthly < self.rain_min_monthly * 0.4:
            return 0
        if rain_mm_monthly > self.rain_max_monthly * 2.5:
            return 0
        if self.rain_min_monthly <= rain_mm_monthly <= self.rain_max_monthly:
            return 100
        if rain_mm_monthly < self.rain_min_monthly:
            return int(100 * rain_mm_monthly / self.rain_min_monthly)
        return int(100 * (self.rain_max_monthly * 2 - rain_mm_monthly) / self.rain_max_monthly)


CROP_PROFILES: list[CropProfile] = [
    CropProfile(
        name="Rice (Paddy)",
        temp_range=(15, 22, 32, 40),
        rain_min_monthly=150,
        rain_max_monthly=300,
        wind_max=40,
        humidity_ideal=(70, 90),
        keywords=["rice", "paddy", "paddy field"],
    ),
    CropProfile(
        name="Wheat",
        temp_range=(5, 10, 22, 30),
        rain_min_monthly=50,
        rain_max_monthly=120,
        wind_max=35,
        humidity_ideal=(40, 70),
        keywords=["wheat"],
    ),
    CropProfile(
        name="Maize / Corn",
        temp_range=(10, 18, 28, 38),
        rain_min_monthly=80,
        rain_max_monthly=200,
        wind_max=40,
        humidity_ideal=(50, 80),
        keywords=["maize", "corn"],
    ),
    CropProfile(
        name="Tea",
        temp_range=(12, 18, 28, 35),
        rain_min_monthly=100,
        rain_max_monthly=200,
        wind_max=30,
        humidity_ideal=(70, 90),
        keywords=["tea", "tea plantation"],
    ),
    CropProfile(
        name="Vegetables (general)",
        temp_range=(10, 15, 25, 35),
        rain_min_monthly=60,
        rain_max_monthly=150,
        wind_max=30,
        humidity_ideal=(50, 80),
        keywords=["vegetable", "vegetables", "garden", "farming", "crop", "harvest", "planting", "agriculture"],
    ),
    CropProfile(
        name="Coconut",
        temp_range=(20, 24, 32, 38),
        rain_min_monthly=130,
        rain_max_monthly=250,
        wind_max=45,
        humidity_ideal=(70, 90),
        keywords=["coconut"],
    ),
    CropProfile(
        name="Rubber",
        temp_range=(20, 25, 32, 38),
        rain_min_monthly=150,
        rain_max_monthly=300,
        wind_max=30,
        humidity_ideal=(80, 95),
        keywords=["rubber"],
    ),
    CropProfile(
        name="Sugarcane",
        temp_range=(16, 24, 34, 40),
        rain_min_monthly=100,
        rain_max_monthly=250,
        wind_max=40,
        humidity_ideal=(60, 85),
        keywords=["sugarcane", "sugar cane"],
    ),
]


def _match_crop(activity: str) -> CropProfile | None:
    lower = activity.lower()
    for profile in CROP_PROFILES:
        for kw in profile.keywords:
            if kw in lower:
                return profile
    return None


def detect_risks(temp_c: float, rain_mm: float, wind_kmh: float, humidity_pct: float) -> list[str]:
    """Return plain-English risk alerts for the given conditions."""
    risks: list[str] = []
    if temp_c <= 0:
        risks.append("Frost risk — potential crop damage or livestock stress")
    elif temp_c <= 4:
        risks.append("Near-freezing temperatures — protect sensitive crops overnight")
    if temp_c >= 40:
        risks.append("Extreme heat — irrigation critical, livestock need shade and water")
    if rain_mm <= 20:
        risks.append("Drought conditions — irrigation required, monitor soil moisture")
    if rain_mm >= 250:
        risks.append("Heavy rainfall / flood risk — delay planting, check drainage")
    if wind_kmh >= 60:
        risks.append("Strong winds — risk of crop lodging and structural damage")
    if humidity_pct >= 90:
        risks.append("Very high humidity — fungal disease risk (apply preventive measures)")
    if humidity_pct <= 30:
        risks.append("Very low humidity — moisture stress for crops, increase irrigation")
    return risks


def detect_opportunities(temp_c: float, rain_mm: float, wind_kmh: float) -> list[str]:
    """Return plain-English positive conditions worth acting on."""
    opps: list[str] = []
    if 20 <= rain_mm <= 120 and 18 <= temp_c <= 30:
        opps.append("Good planting conditions — soil moisture and temperature are ideal")
    if rain_mm < 40 and wind_kmh < 20:
        opps.append("Dry and calm — good window for harvesting or spray application")
    if 15 <= temp_c <= 28 and rain_mm < 80:
        opps.append("Suitable for field operations (tilling, weeding, transplanting)")
    return opps


def farming_analysis(
    activity: str,
    temp_c: float,
    rain_mm: float,
    wind_kmh: float,
    humidity_pct: float = 70.0,
) -> dict:
    """
    rain_mm is the forecasted day's rainfall (mm/day) — the same unit used
    everywhere else in the app. Crop profiles and the risk/opportunity
    thresholds below are calibrated on MONTHLY totals (a farmer cares about a
    month's moisture, not one day), so it's scaled up here before any of
    those comparisons. Feeding the raw daily figure into monthly thresholds
    was the bug that let a single heavy-rain day read as a farming
    "opportunity" — 37mm in one day is a downpour, not the mild top-up a
    37mm/month figure would represent.

    Returns a dict with:
      crop_name, farming_score (0-100), suitability_label,
      risks (list[str]), opportunities (list[str]), advice (str)
    """
    crop = _match_crop(activity)
    if crop is None:
        crop = CROP_PROFILES[4]

    rain_mm_monthly = rain_mm * 30

    t_score = crop.temp_score(temp_c)
    r_score = crop.rain_score(rain_mm_monthly)
    w_score = max(0, int(100 * (1 - max(0, wind_kmh - crop.wind_max) / 40)))
    farming_score = int(0.45 * t_score + 0.40 * r_score + 0.15 * w_score)

    if r_score <= 10:
        farming_score = min(farming_score, 30)
    elif r_score <= 40:
        farming_score = min(farming_score, 55)

    risks = detect_risks(temp_c, rain_mm_monthly, wind_kmh, humidity_pct)
    opportunities = detect_opportunities(temp_c, rain_mm_monthly, wind_kmh)

    if rain_mm >= 30:
        risks.insert(0, f"Heavy rain today ({rain_mm:.0f}mm/day) — delay any field work, spraying, or harvesting planned for today")

    if farming_score >= 75 and not risks:
        label = "Excellent"
    elif farming_score >= 55:
        label = "Good"
    elif farming_score >= 35:
        label = "Fair — some concerns"
    else:
        label = "Poor — significant risks"

    advice_parts = []
    if temp_c > crop.temp_range[2]:
        advice_parts.append(f"temperature above ideal for {crop.name} (ideal: {crop.temp_range[1]}–{crop.temp_range[2]}°C)")
    if rain_mm_monthly < crop.rain_min_monthly:
        advice_parts.append(f"supplemental irrigation likely needed (est. {rain_mm_monthly:.0f}mm/month at this rate, {crop.name} needs {crop.rain_min_monthly}mm)")
    if rain_mm_monthly > crop.rain_max_monthly:
        advice_parts.append(f"excess rainfall may waterlog fields (est. {rain_mm_monthly:.0f}mm/month at this rate, max {crop.rain_max_monthly}mm)")
    advice = f"{crop.name}: {'; '.join(advice_parts)}." if advice_parts else f"{crop.name} conditions look suitable."

    return {
        "crop_name": crop.name,
        "farming_score": farming_score,
        "suitability_label": label,
        "risks": risks,
        "opportunities": opportunities,
        "advice": advice,
        "temp_score": t_score,
        "rain_score": r_score,
    }
