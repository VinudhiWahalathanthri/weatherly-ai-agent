import React, { useEffect, useState } from "react";
import {
  Sun, CloudSun, Cloud, CloudFog, CloudDrizzle, CloudRain,
  CloudSnow, CloudLightning, Thermometer, Wind, Droplets, MapPinned,
} from "lucide-react";
import { Card } from "./ui/card";
import { API_BASE } from "@/lib/api";

type WeatherNowResponse = {
  available: boolean;
  temp_c?: number;
  feels_like_c?: number;
  humidity_pct?: number;
  wind_kmh?: number;
  precipitation_mm?: number;
  cloud_pct?: number;
  weather_code?: number;
};

type LoadState = "idle" | "locating" | "loading" | "ready" | "denied" | "error";

function weatherCodeToDisplay(code: number | undefined): { icon: React.ReactNode; label: string } {
  if (code === undefined) return { icon: <Cloud className="w-8 h-8" />, label: "Unknown" };
  if (code === 0) return { icon: <Sun className="w-8 h-8 text-amber-500" />, label: "Clear sky" };
  if (code <= 3) return { icon: <CloudSun className="w-8 h-8 text-amber-400" />, label: "Partly cloudy" };
  if (code === 45 || code === 48) return { icon: <CloudFog className="w-8 h-8 text-slate-400" />, label: "Foggy" };
  if (code >= 51 && code <= 57) return { icon: <CloudDrizzle className="w-8 h-8 text-blue-400" />, label: "Drizzle" };
  if (code >= 61 && code <= 67) return { icon: <CloudRain className="w-8 h-8 text-blue-500" />, label: "Rainy" };
  if (code >= 71 && code <= 77) return { icon: <CloudSnow className="w-8 h-8 text-sky-300" />, label: "Snowy" };
  if (code >= 80 && code <= 82) return { icon: <CloudRain className="w-8 h-8 text-blue-500" />, label: "Showers" };
  if (code >= 95) return { icon: <CloudLightning className="w-8 h-8 text-purple-500" />, label: "Thunderstorm" };
  return { icon: <Cloud className="w-8 h-8 text-slate-400" />, label: "Cloudy" };
}

export default function CurrentWeatherCard({ onAskAI }: { onAskAI?: () => void }) {
  const [state, setState] = useState<LoadState>("idle");
  const [weather, setWeather] = useState<WeatherNowResponse | null>(null);

  const requestLocation = () => {
    if (!navigator.geolocation) {
      setState("error");
      return;
    }
    setState("locating");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        setState("loading");
        try {
          const { latitude, longitude } = pos.coords;
          const res = await fetch(`${API_BASE}/weather/now?lat=${latitude}&lon=${longitude}`);
          const data: WeatherNowResponse = await res.json();
          if (!data.available) {
            setState("error");
            return;
          }
          setWeather(data);
          setState("ready");
        } catch {
          setState("error");
        }
      },
      () => setState("denied"),
      { timeout: 8000 }
    );
  };

  useEffect(() => {
    requestLocation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (state === "idle" || state === "locating" || state === "loading") {
    return (
      <Card className="bg-white/90 border-slate-200/80 p-4 gap-0 rounded-2xl shadow-sm mb-3 animate-pulse">
        <div className="h-14 flex items-center justify-center text-sm text-slate-400">
          Checking today&apos;s weather near you…
        </div>
      </Card>
    );
  }

  if (state === "denied" || state === "error") {
    return (
      <Card className="bg-white/90 border-slate-200/80 p-4 gap-0 rounded-2xl shadow-sm mb-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-slate-500">
            Enable location to see today&apos;s weather here.
          </span>
          <button
            onClick={requestLocation}
            className="flex items-center gap-1.5 text-xs bg-gradient-to-br from-blue-600 to-indigo-600 text-white rounded-full px-3.5 py-2 hover:from-blue-700 hover:to-indigo-700 transition-colors shrink-0 font-medium shadow-sm"
          >
            <MapPinned className="w-3.5 h-3.5" /> Use my location
          </button>
        </div>
      </Card>
    );
  }

  if (!weather) return null;

  const { icon, label } = weatherCodeToDisplay(weather.weather_code);

  return (
    <Card className="bg-white/90 border-slate-200/80 p-4 gap-0 rounded-2xl shadow-sm mb-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-3 min-w-0">
          {icon}
          <div className="min-w-0">
            <div className="text-xl font-black text-slate-900 font-mono-wx">
              {Math.round(weather.temp_c ?? 0)}°C
              <span className="text-xs font-sans font-normal text-slate-400 ml-1.5">{label}</span>
            </div>
            <div className="text-xs text-slate-500">Right now, near you</div>
          </div>
        </div>
        {onAskAI && (
          <button
            onClick={onAskAI}
            className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full px-3.5 py-2 transition-colors shrink-0 font-medium"
          >
            Plan something
          </button>
        )}
      </div>

      <div className="grid grid-cols-3 gap-1.5 mt-3">
        {[
          { label: "Feels", value: `${Math.round(weather.feels_like_c ?? weather.temp_c ?? 0)}°C`, icon: <Thermometer className="w-3.5 h-3.5" /> },
          { label: "Humidity", value: `${Math.round(weather.humidity_pct ?? 0)}%`, icon: <Droplets className="w-3.5 h-3.5" /> },
          { label: "Wind", value: `${Math.round(weather.wind_kmh ?? 0)}km/h`, icon: <Wind className="w-3.5 h-3.5" /> },
        ].map(({ label: l, value, icon: i }) => (
          <div key={l} className="bg-slate-50 border border-slate-100 rounded-xl px-1 py-2 text-center">
            <div className="flex justify-center text-blue-400 mb-1">{i}</div>
            <div className="text-[10px] text-slate-400 uppercase tracking-wide font-medium">{l}</div>
            <div className="font-bold text-slate-800 font-mono-wx text-[13px] mt-0.5">{value}</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
