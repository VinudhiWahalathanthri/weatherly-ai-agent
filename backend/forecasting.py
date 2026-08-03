"""
Core forecasting pipeline: NASA POWER historical data -> Prophet forecasting ->
ML suitability classification. Used directly by /predict (Manual Mode) and,
importantly, exposed as a *tool* to the AI Planning Agent (agent.py) — the
agent decides when and how many times to call this, it isn't hardcoded to a
single call per request.
"""

from datetime import datetime, timedelta
import os

import numpy as np
import pandas as pd
import requests
import joblib
from prophet import Prophet

import live_weather

MODEL_PATH = os.path.join(os.path.dirname(__file__), "activity_suitability_model.pkl")
ENCODER_PATH = os.path.join(os.path.dirname(__file__), "activity_encoder.pkl")

activity_model = None
activity_encoder = None
MODEL_LOAD_SUCCESS = False

try:
    if os.path.exists(MODEL_PATH) and os.path.exists(ENCODER_PATH):
        activity_model = joblib.load(MODEL_PATH)
        activity_encoder = joblib.load(ENCODER_PATH)
        MODEL_LOAD_SUCCESS = True
        print("[OK] ML Suitability Model and Encoder loaded successfully.")
    else:
        print("[WARN] ML model files not found. Suitability prediction will fall back to a default status.")
except Exception as e:
    print(f"[ERROR] Error loading ML model: {e}")

POWER_API_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
# Core variables for Prophet forecasting
FORECAST_VARS = "T2M,PRECTOTCORR,WS10M"
# Extended variables fetched alongside (not all run through Prophet — too slow)
EXTENDED_VARS = "RH2M,CLOUD_AMT,T2M_MAX,T2M_MIN"
API_PARAMS = FORECAST_VARS  # kept for backwards-compat with fetch helpers
WINDOW_DAYS = 7
FORECAST_OVERRIDE_DAYS = 3


def predict_suitability_ml(pred_data: dict, activity: str) -> str:
    """Uses the loaded ML model to predict suitability."""
    if not MODEL_LOAD_SUCCESS:
        return "Suitable (Fallback)"

    try:
        temp_c = pred_data.get("T2M", 20.0)
        rain_mmh = pred_data.get("PRECTOTCORR", 0.0)
        wind_kmh = pred_data.get("WS10M", 10.0)
        cloud_percent = pred_data.get("CloudPct", 50.0)

        try:
            activity_encoded = activity_encoder.transform([activity.lower()])[0]
        except ValueError:
            return "Caution"

        input_features = pd.DataFrame([[
            temp_c, wind_kmh, rain_mmh, cloud_percent, activity_encoded
        ]], columns=['T2M', 'WS10M', 'PRECTOTCORR', 'CloudPct', 'Activity_Encoded'])

        return activity_model.predict(input_features)[0]
    except Exception as e:
        print(f"ML Prediction Error: {e}")
        return "Caution (ML Error)"


def subtract_years(d: datetime, years: int) -> datetime:
    try:
        return d.replace(year=d.year - years)
    except ValueError:
        return d.replace(year=d.year - years, day=28)


def fetch_nasa_data(lat: float, lon: float, start_date: str, end_date: str, params_override: str | None = None) -> dict:
    start_fmt = start_date.replace("-", "")
    end_fmt = end_date.replace("-", "")
    params = {
        "parameters": params_override or API_PARAMS,
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": start_fmt,
        "end": end_fmt,
        "format": "JSON",
    }
    try:
        response = requests.get(POWER_API_URL, params=params, timeout=20)
        response.raise_for_status()
        data = response.json()
        return data.get("properties", {}).get("parameter", {})
    except Exception as e:
        print("NASA fetch error:", e)
        return {}


def _feels_like(temp_c: float, humidity_pct: float, wind_kmh: float) -> float:
    """Approximate apparent temperature using heat index / wind chill logic."""
    if temp_c >= 27 and humidity_pct >= 40:
        # Steadman heat index (simplified)
        T = temp_c * 9 / 5 + 32  # convert to °F for formula
        R = humidity_pct
        HI = (-42.379 + 2.04901523 * T + 10.14333127 * R
              - 0.22475541 * T * R - 0.00683783 * T ** 2
              - 0.05481717 * R ** 2 + 0.00122874 * T ** 2 * R
              + 0.00085282 * T * R ** 2 - 0.00000199 * T ** 2 * R ** 2)
        return round((HI - 32) * 5 / 9, 1)
    if temp_c <= 10 and wind_kmh >= 4.8:
        # Wind chill
        v = wind_kmh ** 0.16
        wc = 13.12 + 0.6215 * temp_c - 11.37 * v + 0.3965 * temp_c * v
        return round(wc, 1)
    return round(temp_c, 1)


def fetch_current_data(lat: float, lon: float) -> dict:
    """Fetches weather data for yesterday for hybrid prediction (extended vars)."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    all_params = f"{FORECAST_VARS},{EXTENDED_VARS}"
    data = fetch_nasa_data(lat, lon, yesterday, yesterday, params_override=all_params)
    if not data:
        return {}

    current_data = {}
    date_key = yesterday.replace("-", "")
    for var in all_params.split(","):
        val = data.get(var, {}).get(date_key)
        if val is not None and val != -999.0:
            if var == "WS10M":
                val *= 3.6
            current_data[var] = val
    return current_data


def run_prediction(lat: float, lon: float, start_date: datetime, end_date: datetime, activity: str) -> dict:
    """Dispatches to a real live forecast (Open-Meteo) when the ENTIRE requested
    range falls within its ~16-day forecast horizon — accurate for "today",
    "tomorrow", "this weekend" style questions, which is what most day/trip
    planning actually asks. Anything further out falls back to the climatology
    pipeline below, which is a 20-year historical average — appropriate for
    long-range questions ("next month", "6 months from now") but wrong for
    near-term ones. Falls back automatically if Open-Meteo is unreachable."""
    live_predictions = live_weather.fetch_open_meteo(lat, lon, start_date, end_date)
    if live_predictions is not None:
        days_ahead = (start_date.date() - datetime.now().date()).days
        final_predictions = {}
        for date_str, pred in sorted(live_predictions.items()):
            pred["feels_like"] = _feels_like(pred["T2M"], pred["RH2M"], pred["WS10M"])
            pred["CloudPct"] = pred["CLOUD_AMT"]
            pred["suitability_status"] = predict_suitability_ml(pred, activity)
            final_predictions[date_str] = pred

        if days_ahead <= 7:
            confidence, confidence_label = "high", "Live short-range forecast (Open-Meteo, high confidence)"
        else:
            confidence, confidence_label = "medium", "Live medium-range forecast (Open-Meteo, moderate confidence)"

        return {
            "location": {"lat": lat, "lon": lon},
            "activity": activity,
            "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            "predictions": final_predictions,
            "confidence": confidence,
            "confidence_label": confidence_label,
        }

    return _run_prediction_climatology(lat, lon, start_date, end_date, activity)


def _run_prediction_climatology(lat: float, lon: float, start_date: datetime, end_date: datetime, activity: str) -> dict:
    """20-year NASA POWER historical average + Prophet trend fit. This is the
    original forecasting pipeline — kept as-is for long-range questions that
    fall outside Open-Meteo's forecast horizon (see run_prediction above)."""
    date_range = pd.date_range(start=start_date, end=end_date)

    current_data = fetch_current_data(lat, lon)

    # Determine how far into the future the request is so we can label confidence.
    days_ahead = (start_date.date() - datetime.now().date()).days
    if days_ahead <= 3:
        confidence = "high"
        confidence_label = "Short-term forecast blend (high confidence)"
    elif days_ahead <= 14:
        confidence = "medium"
        confidence_label = "Medium-term climate estimate (moderate confidence)"
    else:
        confidence = "low"
        confidence_label = "Long-term climate estimate based on 20yr historical avg (low precision)"

    # Fetch both forecast vars and extended vars together for efficiency
    all_params = f"{FORECAST_VARS},{EXTENDED_VARS}"
    historical_data = {}
    for year_offset in range(1, 21):
        hist_start = subtract_years(start_date - timedelta(days=WINDOW_DAYS), year_offset)
        hist_end = subtract_years(end_date + timedelta(days=WINDOW_DAYS), year_offset)
        year_key = start_date.year - year_offset
        historical_data[year_key] = fetch_nasa_data(
            lat, lon, hist_start.strftime("%Y-%m-%d"), hist_end.strftime("%Y-%m-%d"),
            params_override=all_params,
        )

    all_var_list = all_params.split(",")
    full_rows = []
    for var in all_var_list:
        temp_rows = []
        for year, data in historical_data.items():
            for date_str, val in data.get(var, {}).items():
                try:
                    dt = datetime.strptime(date_str, "%Y%m%d")
                    fval = float(val)
                    if fval == -999.0:
                        fval = np.nan
                    elif var == "WS10M":
                        fval *= 3.6
                    temp_rows.append({"ds": dt, "y": fval, "var": var})
                except (ValueError, TypeError):
                    pass

        if not temp_rows:
            continue
        df = pd.DataFrame(temp_rows).set_index("ds").sort_index()
        full_rows.append(df.rename(columns={"y": var}).drop(columns=["var"]))

    full_df = pd.concat(full_rows, axis=1) if full_rows else pd.DataFrame()
    full_df = full_df.apply(lambda col: col.fillna(col.mean()), axis=0)

    # Only run Prophet on the 3 core forecast variables.
    # Extended variables (humidity, cloud, etc.) are derived from historical means
    # — running Prophet on 7+ variables would take too long per request.
    forecast_var_list = [v for v in FORECAST_VARS.split(",") if v in full_df.columns]
    extended_var_list = [v for v in EXTENDED_VARS.split(",") if v in full_df.columns]

    # Pre-compute historical means for extended vars (used as point estimates)
    ext_hist_means: dict[str, float] = {v: float(full_df[v].mean()) for v in extended_var_list}

    prophet_dfs = {}
    for var in forecast_var_list:
        prophet_dfs[var] = full_df[[var]].copy().rename(columns={var: "y"}).reset_index()
        for reg_var in [v for v in forecast_var_list if v != var]:
            if reg_var in full_df.columns:
                prophet_dfs[var][reg_var] = full_df[reg_var].values

    forecast_order = ["PRECTOTCORR", "WS10M", "T2M"]
    forecast_results_df = pd.DataFrame({"ds": date_range})

    WS10M_REGRESSOR_SCALE = 10.0
    DEFAULT_REGRESSOR_SCALE = 5.0
    for var in forecast_order:
        if var not in prophet_dfs:
            continue
        df_to_fit = prophet_dfs[var][["ds", "y"]].copy()
        model = Prophet(yearly_seasonality=True, daily_seasonality=False, weekly_seasonality=False)

        regressors_to_add = [v for v in forecast_var_list if v != var]
        future_df = pd.DataFrame({"ds": date_range})

        for reg_var in regressors_to_add:
            scale = WS10M_REGRESSOR_SCALE if (var == "WS10M" and reg_var in ["T2M", "PRECTOTCORR"]) else DEFAULT_REGRESSOR_SCALE
            model.add_regressor(reg_var, prior_scale=scale)
            if reg_var in full_df.columns:
                df_to_fit[reg_var] = full_df[reg_var].values
            future_df[reg_var] = full_df[reg_var].mean() if reg_var in full_df.columns else 0.0

        if df_to_fit.empty:
            continue

        model.fit(df_to_fit)
        forecast = model.predict(future_df)
        forecast_results_df = pd.merge(
            forecast_results_df,
            forecast[["ds", "yhat"]].rename(columns={"yhat": var}),
            on="ds", how="left",
        )

    predictions = {}
    for _, row in forecast_results_df.iterrows():
        date_str = row["ds"].strftime("%Y-%m-%d")
        temp = round(float(row.get("T2M", 22)), 2)
        humidity = round(ext_hist_means.get("RH2M", 70.0), 1)
        wind = round(float(row.get("WS10M", 10)), 2)
        predictions[date_str] = {
            "T2M": temp,
            "PRECTOTCORR": round(float(row.get("PRECTOTCORR", 0)), 2),
            "WS10M": wind,
            "RH2M": humidity,
            "CLOUD_AMT": round(ext_hist_means.get("CLOUD_AMT", 50.0), 1),
            "T2M_MAX": round(ext_hist_means.get("T2M_MAX", temp + 3), 1),
            "T2M_MIN": round(ext_hist_means.get("T2M_MIN", temp - 3), 1),
            "feels_like": _feels_like(temp, humidity, wind),
            "CloudPct": round(ext_hist_means.get("CLOUD_AMT", 50.0), 1),
        }

    # Blend near-term historical current data for higher accuracy
    if current_data:
        for i in range(min(FORECAST_OVERRIDE_DAYS, len(date_range))):
            date_to_override = date_range[i].strftime("%Y-%m-%d")
            current_weight = (FORECAST_OVERRIDE_DAYS - i) / (FORECAST_OVERRIDE_DAYS + 1)
            prophet_weight = 1 - current_weight
            if date_to_override in predictions:
                for var in [v for v in all_var_list if v in current_data]:
                    prophet_val = predictions[date_to_override].get(var)
                    current_val = current_data.get(var)
                    if current_val is not None and prophet_val is not None:
                        hybrid_val = (current_val * current_weight) + (prophet_val * prophet_weight)
                        predictions[date_to_override][var] = round(hybrid_val, 2)
                # Recalculate feels_like after blending
                p = predictions[date_to_override]
                p["feels_like"] = _feels_like(p["T2M"], p.get("RH2M", 70), p["WS10M"])

    final_predictions = {}
    for date_str, pred in predictions.items():
        suitability_status = predict_suitability_ml(pred, activity)
        final_predictions[date_str] = {
            **pred,
            "suitability_status": suitability_status,
        }

    return {
        "location": {"lat": lat, "lon": lon},
        "activity": activity,
        "date_range": f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
        "predictions": final_predictions,
        "confidence": confidence,
        "confidence_label": confidence_label,
    }
