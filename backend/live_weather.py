from collections import defaultdict
from datetime import datetime, timedelta

import requests

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
MAX_FORECAST_HORIZON_DAYS = 16


def fetch_open_meteo(lat: float, lon: float, start_date: datetime, end_date: datetime) -> dict | None:
    """Returns {date_str: {T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, WS10M, RH2M, CLOUD_AMT}}
    for every date in [start_date, end_date], or None if the call fails, the range
    isn't fully covered by Open-Meteo's forecast horizon, or any requested date is
    missing from the response — callers should fall back to climatology on None."""
    today = datetime.now().date()
    if start_date.date() < today:
        return None
    if (end_date.date() - today).days > MAX_FORECAST_HORIZON_DAYS:
        return None

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,cloud_cover",
        "timezone": "auto",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "temperature_unit": "celsius",
    }

    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()

        daily = data.get("daily", {})
        hourly = data.get("hourly", {})
        daily_dates = daily.get("time", [])
        if not daily_dates:
            return None

        hourly_times = hourly.get("time", [])
        hourly_temp = hourly.get("temperature_2m", [])
        hourly_rh = hourly.get("relative_humidity_2m", [])
        hourly_wind = hourly.get("wind_speed_10m", [])
        hourly_cloud = hourly.get("cloud_cover", [])

        grouped: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: {"temp": [], "rh": [], "wind": [], "cloud": []}
        )
        for i, ts in enumerate(hourly_times):
            date_key = ts.split("T")[0]
            if i < len(hourly_temp) and hourly_temp[i] is not None:
                grouped[date_key]["temp"].append(hourly_temp[i])
            if i < len(hourly_rh) and hourly_rh[i] is not None:
                grouped[date_key]["rh"].append(hourly_rh[i])
            if i < len(hourly_wind) and hourly_wind[i] is not None:
                grouped[date_key]["wind"].append(hourly_wind[i])
            if i < len(hourly_cloud) and hourly_cloud[i] is not None:
                grouped[date_key]["cloud"].append(hourly_cloud[i])

        temp_max_list = daily.get("temperature_2m_max", [])
        temp_min_list = daily.get("temperature_2m_min", [])
        precip_list = daily.get("precipitation_sum", [])

        predictions: dict[str, dict] = {}
        for idx, date_str in enumerate(daily_dates):
            hourly_vals = grouped.get(date_str)
            if not hourly_vals or not hourly_vals["temp"]:
                return None

            t2m = sum(hourly_vals["temp"]) / len(hourly_vals["temp"])
            rh = sum(hourly_vals["rh"]) / len(hourly_vals["rh"]) if hourly_vals["rh"] else 70.0
            wind = sum(hourly_vals["wind"]) / len(hourly_vals["wind"]) if hourly_vals["wind"] else 10.0
            cloud = sum(hourly_vals["cloud"]) / len(hourly_vals["cloud"]) if hourly_vals["cloud"] else 50.0

            t_max = temp_max_list[idx] if idx < len(temp_max_list) and temp_max_list[idx] is not None else t2m + 3
            t_min = temp_min_list[idx] if idx < len(temp_min_list) and temp_min_list[idx] is not None else t2m - 3
            precip = precip_list[idx] if idx < len(precip_list) and precip_list[idx] is not None else 0.0

            predictions[date_str] = {
                "T2M": round(t2m, 2),
                "T2M_MAX": round(t_max, 1),
                "T2M_MIN": round(t_min, 1),
                "PRECTOTCORR": round(precip, 2),
                "WS10M": round(wind, 2),
                "RH2M": round(rh, 1),
                "CLOUD_AMT": round(cloud, 1),
            }

        expected_dates = {
            (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((end_date - start_date).days + 1)
        }
        if not expected_dates.issubset(predictions.keys()):
            return None

        return predictions
    except Exception as e:
        print(f"[WARN] Open-Meteo forecast fetch failed: {e}")
        return None


def fetch_current_conditions(lat: float, lon: float) -> dict | None:
    """Lightweight current-only fetch for the /weather/now endpoint — no activity
    scoring involved, just the raw numbers for a 'right now' display."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,cloud_cover,apparent_temperature,weather_code",
        "timezone": "auto",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "temperature_unit": "celsius",
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=8)
        resp.raise_for_status()
        current = resp.json().get("current", {})
        if not current or current.get("temperature_2m") is None:
            return None
        return {
            "temp_c": current.get("temperature_2m"),
            "feels_like_c": current.get("apparent_temperature"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_kmh": current.get("wind_speed_10m"),
            "precipitation_mm": current.get("precipitation"),
            "cloud_pct": current.get("cloud_cover"),
            "weather_code": current.get("weather_code"),
            "time": current.get("time"),
        }
    except Exception as e:
        print(f"[WARN] Open-Meteo current-conditions fetch failed: {e}")
        return None
