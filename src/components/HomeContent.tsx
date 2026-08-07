"use client";

import { useState, useEffect } from "react";
import { motion, useMotionValue } from "framer-motion";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { MapContainer, TileLayer, Marker, useMapEvents, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function MapClickHandler({ onClick }: { onClick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) {
      onClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

function MapPanner({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap();
  useEffect(() => {
    map.flyTo(center, zoom);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [center[0], center[1], zoom]);
  return null;
}
import {
  ACTIVITY_CATEGORIES,
  getWeatherGradient,
  handleDownloadCSV,
  handleDownloadJSON,
  handleExportPng,
  maxDate,
  minDate,
  risks,
} from "./utils/AppUtils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Thermometer,
  Snowflake,
  CloudRain,
  Search,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { SelectGroup, SelectLabel } from "@radix-ui/react-select";
import { Progress } from "./ui/progress";
import RainyIcon from "@/assets/icons/rainy-4.svg";
import ClearIcon from "@/assets/icons/day.svg";
import WindIcon from "@/assets/icons/rainy-1.svg";
import Hero from "./ui/Hero";
import Footer from "./ui/footer";

export default function App() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedActivity, setSelectedActivity] = useState("");

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [results, setResults] = useState<any>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [data, setData] = useState<any>(null);
  const [mapCenter, setMapCenter] = useState<[number, number]>([7.8731, 80.7718]);
  const [mapZoom, setMapZoom] = useState(7);

  const [lat, setLat] = useState<number | null>(null);
  const [lon, setLon] = useState<number | null>(null);

  const [progress, setProgress] = useState(0);

  const selectedVariables = {
    T2M: true,
    PRECTOTCORR: true,
    WS10M: true,
  };

  const cursorX = useMotionValue(0);
  const cursorY = useMotionValue(0);
  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      cursorX.set(e.clientX);
      cursorY.set(e.clientY);
    };
    window.addEventListener("mousemove", onMouseMove);
    return () => window.removeEventListener("mousemove", onMouseMove);
  }, [cursorX, cursorY]);

  const reverseGeocode = async (latitude: number, longitude: number) => {
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?lat=${latitude}&lon=${longitude}&format=json`,
        { headers: { "Accept-Language": "en" } }
      );
      const data = await res.json();
      if (data?.display_name) setSearchQuery(data.display_name);
    } catch (err) {
      console.error("Reverse geocoding failed:", err);
    }
  };

  const handleMapClick = (latitude: number, longitude: number) => {
    const roundedLat = Math.round(latitude * 1000) / 1000;
    const roundedLon = Math.round(longitude * 1000) / 1000;
    setLat(roundedLat);
    setLon(roundedLon);
    reverseGeocode(roundedLat, roundedLon);
  };

  const handleSearchPlace = async () => {
    if (!searchQuery) return;
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(searchQuery)}&format=json&limit=1`,
        { headers: { "Accept-Language": "en" } }
      );
      const results = await res.json();
      if (results?.[0]) {
        const foundLat = parseFloat(results[0].lat);
        const foundLon = parseFloat(results[0].lon);
        setLat(Math.round(foundLat * 1000) / 1000);
        setLon(Math.round(foundLon * 1000) / 1000);
        setMapCenter([foundLat, foundLon]);
        setMapZoom(13);
        setSearchQuery(results[0].display_name);
      }
    } catch (err) {
      console.error("Place search failed:", err);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery || !lat || !lon || !selectedActivity) {
      setError("Please fill all required fields.");
      alert("Please fill all the fields");
      return;
    }

    const payload = {
      lat,
      lon,
      startDate: startDate,
      endDate: endDate,
      activity: selectedActivity,
      variables: selectedVariables,
    };

    try {
      setLoading(true);
      const response = await fetch("/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) throw new Error(`Server error: ${response.status}`);
      const responseData = await response.json();

      console.log("✅ API Success. Received Data:", responseData);

      setResults(responseData);
      setData({
        lat,
        lon,
        location: searchQuery,
        date: selectedDate,
        event: selectedActivity,
        results: responseData,
      });
    } catch (err) {
      setError(`Prediction failed: ${(err as Error).message}`);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const chartData = results
    ? Object.entries(results.predictions).map(([date, values]) => ({
        date,
        Temperature: values.T2M,
        Rainfall: values.PRECTOTCORR,
        Wind: values.WS10M,
      }))
    : [];

  useEffect(() => {
    let interval: NodeJS.Timeout;

    if (loading) {
      setProgress(0);
      interval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 90) return prev;
          return prev + Math.random() * 5;
        });
      }, 200);
    } else {
      setProgress(100);
      const timeout = setTimeout(() => setProgress(0), 500);
      return () => clearTimeout(timeout);
    }

    return () => clearInterval(interval);
  }, [loading]);

  const cardList = {
    hidden: {},
    show: { transition: { staggerChildren: 0.12 } },
  };

  const cardVariant = {
    hidden: { opacity: 0, y: 12, scale: 0.98 },
    show: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: { type: "spring", stiffness: 120 },
    },
  };

  const getSuitabilityColor = (status: string) => {
    switch (status) {
      case "Suitable":
        return {
          bg: "bg-gradient-to-r from-green-500 to-emerald-500",
          text: "Excellent for your activity",
          icon: "☀️",
        };
      case "Caution":
        return {
          bg: "bg-gradient-to-r from-yellow-500 to-amber-500",
          text: "Proceed with Caution",
          icon: "⚠️",
        };
      case "Unsuitable":
        return {
          bg: "bg-gradient-to-r from-red-500 to-rose-500",
          text: "Unsuitable, reschedule or move indoors",
          icon: "❌",
        };
      default:
        return {
          bg: "bg-gradient-to-r from-gray-500 to-slate-500",
          text: "Status Unknown",
          icon: "❓",
        };
    }
  };

  const getWeatherDescription = (prediction: { T2M: number; PRECTOTCORR: number; WS10M: number }) => {
    const { T2M, PRECTOTCORR, WS10M } = prediction;

    if (WS10M > 35) {
      return {
        description: `High Wind (${WS10M.toFixed(0)} km/h)`,
        icon: WindIcon,
      };
    }

    if (PRECTOTCORR > 5) {
      return {
        description: `Heavy Rain (${PRECTOTCORR.toFixed(1)} mm/day)`,
        icon: RainyIcon,
      };
    }
    if (PRECTOTCORR > 1.5) {
      return {
        description: `Moderate Rain (${PRECTOTCORR.toFixed(1)} mm/day)`,
        icon: RainyIcon,
      };
    }

    if (T2M > 35) {
      return {
        description: `Extreme Heat (${T2M.toFixed(0)}°C)`,
        icon: ClearIcon,
      };
    }
    return {
      description: `Clear & Mild (${T2M.toFixed(0)}°C)`,
      icon: ClearIcon,
    };
  };
  const firstDayPrediction = results?.predictions?.[startDate] || null;

  const suitabilityInfo = firstDayPrediction
    ? getSuitabilityColor(firstDayPrediction.suitability_status)
    : { bg: "bg-gray-400", text: "Awaiting Search", icon: "..." };

  const weatherStatus = firstDayPrediction
    ? getWeatherDescription(firstDayPrediction)
    : { description: "N/A", icon: RainyIcon };

  /**
   * Finds the best alternative date AFTER the current startDate within the prediction range.
   * Priority: 'Suitable' > 'Caution'.
   *
   * @param predictions The results.predictions object.
   * @param startDate The current start date chosen by the user.
   * @returns An object containing the best date and its data, or null.
   */
  const findNextBestDate = (predictions: Record<string, { suitability_status: string; T2M: number; PRECTOTCORR: number; WS10M: number }> | null, startDate: string) => {
    if (!predictions) return null;
    const dates = Object.keys(predictions).sort();

    let nextSuitable = null;
    let nextCaution = null;
    for (const date of dates) {
      if (date <= startDate) continue;

      const predictionData = predictions[date];
      const status = predictionData.suitability_status;

      if (status === "Suitable" && !nextSuitable) {
        nextSuitable = {
          date,
          status,
          T2M: predictionData.T2M,
          PRECTOTCORR: predictionData.PRECTOTCORR,
          WS10M: predictionData.WS10M,
        };
        break;
      }

      if (status === "Caution" && !nextCaution) {
        nextCaution = {
          date,
          status,
          T2M: predictionData.T2M,
          PRECTOTCORR: predictionData.PRECTOTCORR,
          WS10M: predictionData.WS10M,
        };
      }
    }

    if (nextSuitable) return nextSuitable;
    if (nextCaution) return nextCaution;

    return null;
  };

  const nextBestDateInfo = findNextBestDate(results?.predictions, startDate);

  const formatDateForDisplay = (dateString: string) => {
    if (!dateString) return "";
    try {
      return new Date(dateString).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch (e) {
      return dateString;
    }
  };

  /**
   * Calculates dynamic risk percentages based on weather predictions for a single day.
   * @param {object} prediction - The data for the start date (firstDayPrediction).
   * @returns {Array<object>} - An array of dynamic risk objects.
   */
  const getDynamicRisks = (prediction: { T2M: number; PRECTOTCORR: number; WS10M: number } | null) => {
    if (!prediction) return [];

    const { T2M, PRECTOTCORR, WS10M } = prediction;

    let heatRiskValue = 0;
    if (T2M >= 35) heatRiskValue = 90;
    else if (T2M >= 30) heatRiskValue = 65;
    else if (T2M >= 25) heatRiskValue = 30;
    else heatRiskValue = 10;

    let rainRiskValue = 0;
    if (PRECTOTCORR >= 10) rainRiskValue = 95;
    else if (PRECTOTCORR >= 4) rainRiskValue = 70;
    else if (PRECTOTCORR >= 1) rainRiskValue = 40;
    else rainRiskValue = 5;

    let windRiskValue = 0;
    if (WS10M >= 30) windRiskValue = 85;
    else if (WS10M >= 20) windRiskValue = 55;
    else if (WS10M >= 10) windRiskValue = 25;
    else windRiskValue = 5;

    return [
      {
        type: "Heat Stress Risk",
        value: heatRiskValue,
        Icon: Thermometer,
        details: `Avg Temp: ${T2M.toFixed(1)} °C`,
        colorClass: heatRiskValue > 60 ? "text-red-500" : "text-red-500",
      },
      {
        type: "Rain/Flooding Risk",
        value: rainRiskValue,
        Icon: CloudRain,
        details: `Total Rain: ${PRECTOTCORR.toFixed(1)} mm/day`,
        colorClass: rainRiskValue > 60 ? "text-blue-600" : "text-blue-500",
      },
      {
        type: "Wind Hazard Risk",
        value: windRiskValue,
        Icon: Snowflake,
        details: `Avg Wind: ${WS10M.toFixed(1)} km/h`,
        colorClass: windRiskValue > 60 ? "text-yellow-600" : "text-yellow-500",
      },
    ];
  };

  const dynamicRisks = getDynamicRisks(firstDayPrediction);
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 50);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);
  const navLinkVariant = {
    hidden: { opacity: 0, y: -8 },
    show: { opacity: 1, y: 0 },
  };

  const calculateOffsetDate = (dateString: string, offset: number) => {
    const date = new Date(dateString);

    if (isNaN(date.getTime())) {
      return "";
    }

    date.setDate(date.getDate() + offset);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");

    return `${year}-${month}-${day}`;
  };

  useEffect(() => {
    if (startDate) {
      const newEndDate = calculateOffsetDate(startDate, 7);
      setEndDate(newEndDate);
    }
  }, [startDate]);

  return (
    <div
      className="w-full min-h-screen text-white scroll-smooth"
      style={{ backgroundColor: "#f7fbff" }}
    >
      <motion.nav
        initial={{ y: -80, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6 }}
        className={`fixed top-0 left-0 w-full z-50 transition-all duration-500 ${
          isScrolled
            ? "bg-white/20 backdrop-blur-md border-b border-white/10"
            : "bg-transparent"
        }`}
      >
        <div className="max-w-7xl mx-auto flex items-center py-4 px-6">
          <motion.div
            className="mr-auto flex items-center gap-4 cursor-pointer"
            style={{
              WebkitMaskImage: "none",
            }}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <motion.img
              src={
                isScrolled
                  ? "src/assets/Weatherly (1).svg"
                  : "src/assets/Weatherly.svg"
              }
              alt="Logo"
              className="h-12 rounded transition-all duration-500"
              whileHover={{ scale: 1.05 }}
              style={{
                transformOrigin: "center",
              }}
            />
            <motion.div
              className="text-sm hidden md:block"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <div style={{ fontWeight: 700, color: "#0f172a" }}>Weatherly</div>
              <div style={{ fontSize: 11, color: "#475569" }}>
                Smart forecasts
              </div>
            </motion.div>
          </motion.div>
        </div>
      </motion.nav>

      <Hero />

      <section id="weather">
        <div className="w-full justify-center py-6 px-6 md:px-10 lg:px-40 text-black mt-8">
          <motion.span
            className="text-2xl font-bold text-[#142636]"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
          >
            Plan your Perfect Day
          </motion.span>
          <br />
          <motion.span
            className="text-[#1a3243]"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.12 }}
          >
            Click on map & choose date and event to get weather forecast
          </motion.span>
        </div>

        <div className="w-full text-white">
          <div className="w-full justify-center text-black">
            <div className="py-0 px-6 md:px-10 lg:px-40">
              <motion.div
                className="flex flex-col md:flex-row items-center space-y-3 md:space-y-0 md:space-x-4"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
              >
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search for a location"
                  onKeyDown={(e) => e.key === "Enter" && handleSearchPlace()}
                  className="rounded-2xl border border-gray-300 focus:border-blue-400 focus:ring-0 focus:outline-none shadow-sm focus:shadow-lg focus:shadow-blue-200 px-4 py-2 transition-all duration-300 w-full md:w-1/2"
                />

                <h1 className="text-sm">From</h1>
                <Input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  min={minDate}
                  max={maxDate}
                  className="w-full md:w-1/6 rounded-2xl border border-gray-300 focus:border-blue-400 focus:ring-0 focus:outline-none shadow-sm focus:shadow-lg focus:shadow-blue-200 transition-all duration-300"
                />

                <h1 className="text-sm">To</h1>
                <Input
                  type="date"
                  disabled
                  value={endDate}
                  className="w-full md:w-1/6 rounded-2xl border border-gray-300 focus:border-blue-400 focus:ring-0 focus:outline-none shadow-sm focus:shadow-lg focus:shadow-blue-200 transition-all duration-300"
                />

                <Select
                  value={selectedActivity}
                  onValueChange={setSelectedActivity}
                >
                  <SelectTrigger className="w-full md:w-1/6 border border-gray-300 rounded-2xl focus:border-blue-400 focus:ring-0 focus:outline-none shadow-sm focus:shadow-lg focus:shadow-blue-200 transition-all duration-300">
                    <SelectValue placeholder="Select an activity" />
                  </SelectTrigger>

                  <SelectContent className="backdrop-blur-3xl border border-gray-200">
                    {Object.entries(ACTIVITY_CATEGORIES).map(
                      ([category, activities]) => (
                        <SelectGroup key={category}>
                          <SelectLabel className="text-gray-500 font-semibold">
                            {category}
                          </SelectLabel>
                          {activities.map((activity) => (
                            <SelectItem key={activity} value={activity}>
                              {activity}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      )
                    )}
                  </SelectContent>
                </Select>

                <motion.div whileHover={{ scale: 1.02 }}>
                  <Button
                    onClick={handleSearch}
                    className="text-white hover:bg-gray-800 rounded-2xl w-full md:w-auto px-5 py-2"
                    style={{ backgroundColor: "#4ABD62" }}
                  >
                    <Search className="w-4 h-4 mr-2 inline-block" /> Search
                  </Button>
                </motion.div>
              </motion.div>

              <motion.div
                className="w-full h-96 bg-gray-100 rounded-lg overflow-hidden border-2 border-gray-200 mt-5 mb-6"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.12 }}
              >
                <MapContainer
                  center={mapCenter}
                  zoom={mapZoom}
                  style={{ width: "100%", height: "100%" }}
                  scrollWheelZoom
                >
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                  <MapClickHandler onClick={handleMapClick} />
                  <MapPanner center={mapCenter} zoom={mapZoom} />
                  {lat !== null && lon !== null && <Marker position={[lat, lon]} />}
                </MapContainer>
              </motion.div>

              <div className="mt-2 mb-10">
                {loading && (
                  <>
                    <p className="text-gray-700 mb-1">Loading...</p>
                    <Progress value={progress} className="h-3 rounded-full" />
                  </>
                )}
              </div>

              <div>
                {results && firstDayPrediction && (
                  <motion.div
                    initial="hidden"
                    animate="show"
                    variants={cardList}
                  >
                    <motion.div
                      className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-6"
                      variants={cardVariant}
                    >
                      <div className="col-span-2 shadow-lg border border-gray-200 rounded-2xl p-8 bg-gradient-to-br from-white to-blue-50">
                        <div className="flex items-start justify-between mb-6">
                          <div>
                            <h2 className="font-bold text-lg text-[#0f172a]">
                              Weather Prediction for {startDate}
                            </h2>
                            <p className="text-gray-600 mt-1">
                              {searchQuery || "Selected Location"}
                            </p>
                          </div>

                          <motion.div
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            className={`${suitabilityInfo.bg} px-4 py-2 rounded-full text-white text-sm font-semibold shadow-lg`}
                          >
                            <span className="mr-2">{suitabilityInfo.icon}</span>
                            {suitabilityInfo.text}
                          </motion.div>
                        </div>

                        <div className="grid grid-cols-2 gap-2">
                          <div className="flex flex-col justify-center">
                            <h3 className="font-semibold text-lg text-gray-800 mb-0 flex items-center gap-2">
                              Tips & Reminders
                            </h3>
                            <div className="space-y-3">
                              {[
                                "Have a backup plan in case of emergencies",
                                "Stay hydrated and carry extra water",
                                "Wear comfortable clothing and sunscreen",
                                "Check the weather forecast before heading out",
                              ].map((tip, idx) => (
                                <motion.div
                                  key={idx}
                                  initial={{ opacity: 0, x: -20 }}
                                  animate={{ opacity: 1, x: 0 }}
                                  transition={{ delay: idx * 0.1 }}
                                  className="flex items-start gap-3 group"
                                >
                                  <div className="mt-1 w-2 h-2 rounded-full bg-blue-500 group-hover:scale-150 transition-transform" />
                                  <span className="text-gray-600 text-sm leading-relaxed">
                                    {tip}
                                  </span>
                                </motion.div>
                              ))}
                            </div>
                          </div>

                          <div className=" items-center justify-center relative bottom-4">
                            <motion.div
                              initial={{ scale: 0.8, opacity: 0 }}
                              animate={{ scale: 1, opacity: 1 }}
                              transition={{ duration: 0.5 }}
                              className="relative"
                            >
                              <div className="absolute inset-0 bg-blue-200 rounded-full blur-3xl opacity-30" />
                              <img
                                src={weatherStatus.icon}
                                className="w-48 mx-auto relative z-10"
                                alt="weather-icon"
                              />
                            </motion.div>
                            <motion.div
                              initial={{ opacity: 0, y: 10 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: 0.3 }}
                              className="mt-2 text-center"
                            >
                              <span className="text-xl font-bold text-gray-800">
                                {weatherStatus.description}
                              </span>
                              <p className="text-sm text-gray-500 mt-1">
                                Predicted conditions
                              </p>
                            </motion.div>
                          </div>
                        </div>
                      </div>
                      <div className="shadow-lg border border-gray-200 rounded-2xl p-8 bg-gradient-to-br from-white to-blue-50 justify-between">
                        <h2 className="font-bold text-lg text-[#0f172a]">
                          Next Best Date
                        </h2>
                        <p className="text-gray-600 text-sm mb-4 mt-2">
                          {nextBestDateInfo
                            ? `The most suitable alternative day for your activity is:`
                            : `No better day was found in the current range or your selected date is already Suitable.`}
                        </p>

                        <div className="min-h-10">
                          {" "}
                          {nextBestDateInfo ? (
                            <>
                              <div className="w-full justify-center items-center text-center">
                                <img
                                  src={weatherStatus.icon}
                                  className="w-32 p-0 text-center self-center mx-auto"
                                  alt="weather-icon"
                                />
                              </div>
                              <div>
                                <span
                                  className=" text-blue-700 flex"
                                  style={{ fontSize: 20, fontWeight: "bold" }}
                                >
                                  {formatDateForDisplay(nextBestDateInfo.date)}
                                  <span
                                    className={`text-sm ml-2 px-2 py-1 rounded-full text-white ${
                                      getSuitabilityColor(
                                        nextBestDateInfo.status
                                      )
                                        .bg.replace(
                                          "bg-gradient-to-r from-",
                                          "bg-"
                                        )
                                        .split(" ")[0]
                                    }`}
                                  >
                                    {nextBestDateInfo.status}
                                  </span>
                                </span>
                                <span className="text-sm text-gray-500">
                                  Great for {results.activity || "outdoor fun"}{" "}
                                  with an average temperature of{" "}
                                  {nextBestDateInfo.T2M.toFixed(1)}°C.
                                </span>

                                <motion.button
                                  className="px-4 py-2 mt-8 text-white"
                                  style={{
                                    backgroundColor: "#4ABD62",
                                    borderRadius: 10,
                                    boxShadow: "0px 4px 4px rgba(0, 0, 0, 0.1)",
                                    cursor: "pointer",
                                    fontSize: 14,
                                  }}
                                  whileHover={{ scale: 1.05 }}
                                  onClick={() => {
                                    const element =
                                      document.getElementById("weather");
                                    const navbarHeight =
                                      document.querySelector("nav")
                                        ?.offsetHeight || 0;
                                    const topPosition =
                                      element.getBoundingClientRect().top +
                                      window.pageYOffset -
                                      navbarHeight;

                                    window.scrollTo({
                                      top: topPosition,
                                      behavior: "smooth",
                                    });
                                  }}
                                >
                                  Get details forcast for this date.
                                </motion.button>
                              </div>
                            </>
                          ) : (
                            <div className=" items-center justify-center text-center relative bottom-4">
                              <motion.div
                                initial={{ scale: 0.8, opacity: 0 }}
                                animate={{ scale: 1, opacity: 1 }}
                                transition={{ duration: 0.5 }}
                                className="relative"
                              >
                                <div className="absolute inset-0 bg-blue-200 rounded-full blur-3xl opacity-30" />
                                <img
                                  src={"src/assets/no-data.png"}
                                  className="w-32 py-6 mx-auto relative z-10"
                                  alt="weather-icon"
                                />
                              </motion.div>
                              <motion.button
                                className="px-5 py-2"
                                style={{
                                  backgroundColor: "#212E61",
                                  borderRadius: 15,
                                  boxShadow:
                                    "0px 4px 4px rgba(255, 255, 255, 0.4)",
                                  cursor: "pointer",
                                }}
                                whileHover={{ scale: 1.05 }}
                                onClick={() => {
                                  const element =
                                    document.getElementById("weather");
                                  const navbarHeight =
                                    document.querySelector("nav")
                                      ?.offsetHeight || 0;
                                  const topPosition =
                                    element.getBoundingClientRect().top +
                                    window.pageYOffset -
                                    navbarHeight;

                                  window.scrollTo({
                                    top: topPosition,
                                    behavior: "smooth",
                                  });
                                }}
                              >
                                <span
                                  style={{
                                    fontFamily: "Lato",
                                    fontWeight: "bold",
                                    fontSize: 14,
                                    color: "white",
                                  }}
                                >
                                  Select another date please.
                                </span>
                              </motion.button>
                            </div>
                          )}
                        </div>
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </div>

              {results && dynamicRisks.length > 0 && (
                <motion.div
                  className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6 mb-6"
                  initial="hidden"
                  animate="show"
                  variants={cardList}
                >
                  {dynamicRisks.map((risk, i) => (
                    <motion.div
                      key={i}
                      className="p-6 border rounded-2xl border-gray-200 shadow-lg bg-white"
                      variants={cardVariant}
                      whileHover={{ y: -6, scale: 1.02 }}
                      transition={{ type: "spring", stiffness: 200 }}
                    >
                      <div className="flex items-center gap-4">
                        <div
                          className={`border rounded-2xl border-gray-200 h-12 w-12 flex items-center justify-center ${risk.colorClass}`}
                        >
                          <risk.Icon className="w-6 h-6" />
                        </div>

                        <div>
                          <span className="text-xl font-bold text-[#0f172a]">
                            {risk.value}%
                          </span>
                          <br />
                          <span className="text-sm text-gray-600">
                            Likelihood
                          </span>
                        </div>
                      </div>
                      <div className="mt-4 font-semibold text-lg text-[#0f172a]">
                        {risk.type}
                      </div>
                      <div className="text-sm text-gray-500">
                        {risk.details}
                      </div>{" "}
                      <div className="mt-2">
                        <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                          <motion.div
                            className={`h-2 rounded-full`}
                            initial={{ width: 0 }}
                            animate={{ width: `${risk.value}%` }}
                            transition={{ duration: 1.2 }}
                            style={{
                              background:
                                risk.value < 30
                                  ? "linear-gradient(90deg,#34d399,#059669)"
                                  : risk.value < 60
                                  ? "linear-gradient(90deg,#fbbf24,#f59e0b)"
                                  : "linear-gradient(90deg,#ef4444,#dc2626)",
                            }}
                          />
                        </div>
                        <div className="flex justify-between text-xs mt-1 text-gray-600">
                          <span>Low</span>
                          <span>High</span>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </motion.div>
              )}

              {chartData.length > 0 && (
                <div className="border rounded-2xl border-gray-200 shadow-lg p-6 overflow-x-scroll bg-white mb-16">
                  <h2 className="font-bold text-lg mb-10 text-[#0f172a]">
                    Climate Trends for {results.activity} at{" "}
                    {results.location.lat}, {results.location.lon}
                  </h2>
                  <div className="w-full overflow-x-auto md:overflow-x-visible">
                    <div
                      className="min-w-[600px] md:min-w-full"
                      style={{ height: 300 }}
                    >
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="date" />
                          <YAxis />
                          <Tooltip />
                          <Legend />
                          <Line
                            type="monotone"
                            dataKey="Temperature"
                            stroke="#ef4444"
                            name="Temp (°C)"
                          />
                          <Line
                            type="monotone"
                            dataKey="Rainfall"
                            stroke="#3b82f6"
                            name="Rain (mm)"
                          />
                          <Line
                            type="monotone"
                            dataKey="Wind"
                            stroke="#f59e0b"
                            name="Wind (km/h)"
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>

                  <motion.div
                    className="mt-6 mb-5 flex gap-4 justify-end"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.12 }}
                  >
                    <motion.button
                      onClick={() => handleDownloadJSON(data, searchQuery)}
                      className=" text-white hover:bg-gray-800 rounded-2xl w-30 px-4 py-2"
                      style={{ backgroundColor: "#4A70BD" }}
                      whileHover={{ scale: 1.03 }}
                    >
                      Download JSON
                    </motion.button>
                    <motion.button
                      onClick={() =>
                        handleDownloadCSV(
                          results,
                          searchQuery,
                          selectedActivity
                        )
                      }
                      className=" text-white hover:bg-gray-800 rounded-2xl w-30 px-4 py-2"
                      style={{ backgroundColor: "#4E4ABD" }}
                      whileHover={{ scale: 1.03 }}
                    >
                      Download CSV
                    </motion.button>
                  </motion.div>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}