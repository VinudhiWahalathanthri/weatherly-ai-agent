import React, { useState } from "react";
import { MapPin, Cloud, Navigation, Search, Loader } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { MapContainer, TileLayer, Marker, useMapEvents, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

type SelectedLocation = { lat: string; lng: string };

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
  React.useEffect(() => {
    map.flyTo(center, zoom);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [center[0], center[1], zoom]);
  return null;
}

export default function WeatherLocationSelector() {
  const [selectedLocation, setSelectedLocation] = useState<SelectedLocation | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [mapCenter, setMapCenter] = useState<[number, number]>([40.7128, -74.006]);
  const [mapZoom, setMapZoom] = useState(10);
  const [markerPos, setMarkerPos] = useState<[number, number] | null>(null);
  const [searching, setSearching] = useState(false);

  const handleMapClick = (lat: number, lng: number) => {
    const pos: [number, number] = [lat, lng];
    setMarkerPos(pos);
    setSelectedLocation({ lat: lat.toFixed(6), lng: lng.toFixed(6) });
  };

  const handleUseMyLocation = () => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        const pos: [number, number] = [lat, lng];
        setMarkerPos(pos);
        setMapCenter(pos);
        setMapZoom(13);
        setSelectedLocation({ lat: lat.toFixed(6), lng: lng.toFixed(6) });
      },
      () => {
        alert("Unable to get your location. Please check your browser permissions.");
      }
    );
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery) return;
    setSearching(true);
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(searchQuery)}&format=json&limit=1`,
        { headers: { "Accept-Language": "en" } }
      );
      const results = await res.json();
      if (results?.[0]) {
        const lat = parseFloat(results[0].lat);
        const lng = parseFloat(results[0].lon);
        const pos: [number, number] = [lat, lng];
        setMarkerPos(pos);
        setMapCenter(pos);
        setMapZoom(13);
        setSelectedLocation({ lat: lat.toFixed(6), lng: lng.toFixed(6) });
      } else {
        alert("Location not found. Please try a different search term.");
      }
    } catch {
      alert("Search failed. Please try again.");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-indigo-50">
      <div className="bg-white/80 backdrop-blur-sm border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="bg-gradient-to-br from-blue-500 to-indigo-600 p-2 rounded-xl">
                <Cloud className="w-6 h-6 text-white" />
              </div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                SkyView Weather
              </h1>
            </div>
            <button
              onClick={handleUseMyLocation}
              className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
            >
              <Navigation className="w-4 h-4" />
              Use My Location
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MapPin className="w-5 h-5 text-blue-500" />
                  Select Your Location
                </CardTitle>
                <CardDescription>
                  Click anywhere on the map to get weather information for that location
                </CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleSearch} className="mb-4 relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search for a city or address..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-4 py-3 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </form>

                <div className="relative w-full h-96 bg-gray-100 rounded-lg overflow-hidden border-2 border-gray-200">
                  {searching && (
                    <div className="absolute inset-0 flex items-center justify-center bg-white/60 z-[500]">
                      <Loader className="w-8 h-8 animate-spin text-blue-500" />
                    </div>
                  )}
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
                    {markerPos && <Marker position={markerPos} />}
                  </MapContainer>
                </div>

                <p className="text-sm text-gray-500 mt-2 text-center">
                  💡 Uses OpenStreetMap — free, no API key required
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4">
            <Card className="border-0 shadow-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white">
              <CardHeader>
                <CardTitle>Location Coordinates</CardTitle>
                <CardDescription className="text-blue-100">
                  Selected location details
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {selectedLocation ? (
                  <>
                    <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
                      <div className="text-sm text-blue-100 mb-1">Latitude</div>
                      <div className="text-2xl font-bold font-mono">{selectedLocation.lat}°</div>
                    </div>
                    <div className="bg-white/10 backdrop-blur-sm rounded-lg p-4">
                      <div className="text-sm text-blue-100 mb-1">Longitude</div>
                      <div className="text-2xl font-bold font-mono">{selectedLocation.lng}°</div>
                    </div>
                    <button className="w-full bg-white text-blue-600 font-semibold py-3 rounded-lg hover:bg-blue-50 transition-colors">
                      Get Weather Data
                    </button>
                  </>
                ) : (
                  <div className="text-center py-8">
                    <MapPin className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p className="text-blue-100">Click on the map to select a location</p>
                  </div>
                )}
              </CardContent>
            </Card>

            {selectedLocation && (
              <Alert className="border-0 shadow-lg bg-gradient-to-br from-amber-50 to-orange-50">
                <AlertDescription className="text-sm">
                  <span className="font-semibold text-amber-900">Next Step:</span>
                  <p className="text-amber-800 mt-1">
                    These coordinates will be used to fetch weather data from your weather API service.
                  </p>
                </AlertDescription>
              </Alert>
            )}

            <Card className="border-0 shadow-xl">
              <CardHeader>
                <CardTitle className="text-lg">How It Works</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-gray-600">
                {[
                  { n: 1, title: "Select Location", desc: "Click anywhere on the map or search for a city" },
                  { n: 2, title: "Get Coordinates", desc: "Latitude and longitude are automatically captured" },
                  { n: 3, title: "Fetch Weather", desc: "Use coordinates to get real-time weather data" },
                ].map(({ n, title, desc }) => (
                  <div key={n} className="flex items-start gap-3">
                    <div className="bg-blue-100 rounded-full p-1 mt-0.5">
                      <div className="w-5 h-5 flex items-center justify-center text-blue-600 font-bold text-xs">{n}</div>
                    </div>
                    <div>
                      <div className="font-semibold text-gray-900">{title}</div>
                      <div>{desc}</div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
