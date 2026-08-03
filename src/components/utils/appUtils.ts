import html2canvas from "html2canvas-oklch";

// ---------- Types ----------
export type Risk = {
  type: string;
  iconClass?: string;
  value: number;
};

export type ClimateData = {
  month: string;
  temp: number;
  rain: number;
};

export type WeatherVariable = {
  key: string;
  label: string;
  unit: string;
};

export type LocationMarkerProps = {
  onLocationSelect: (lat: number, lng: number) => void;
};

// ---------- Constants ----------
export const ACTIVITY_CATEGORIES: Record<string, string[]> = {
  "Outdoor Events": [
    "Outdoor Ceremony/Reception",
    "Large Festival/Market",
    "Outdoor Photography Session",
  ],
  "Nature & Leisure": ["Walks", "Picnics", "Camping", "Gardening"],
  "Land Sports & Fitness": [
    "Hiking",
    "Jogging / Running",
    "Cycling ",
    "Outdoor Sports",
  ],
  "Water Activities": [
    "Swimming",
    "Surfing / Bodyboarding",
    "Sailing / Kayaking / Canoeing",
    "Fishing",
  ],
  "Adventure & Aviation": [
    "Paragliding / Hang Gliding",
    "Ziplining / Ropes Course",
    "UAV Operation",
  ],
};

export const WEATHER_VARIABLES: WeatherVariable[] = [
  { key: "T2M", label: "Temperature", unit: "°C" },
  { key: "PRECTOTCORR", label: "Rainfall", unit: "mm/day" },
  { key: "WS10M", label: "Wind Speed", unit: "km/h" },
];

export const risks: Risk[] = [
  { type: "Extreme Heat", iconClass: "text-red-500", value: 80 },
  { type: "Avg Heat", iconClass: "text-red-500", value: 52 },
  { type: "Low Heat", iconClass: "text-red-500", value: 20 },
  { type: "Extreme Rain", iconClass: "text-blue-500", value: 80 },
  { type: "Avg Rain", iconClass: "text-blue-500", value: 52 },
  { type: "Low Rain", iconClass: "text-blue-500", value: 20 },
  { type: "Extreme Wind", iconClass: "text-yellow-500", value: 80 },
  { type: "Avg Wind", iconClass: "text-yellow-500", value: 52 },
  { type: "Low Wind", iconClass: "text-yellow-500", value: 20 },
];

export const climateData: ClimateData[] = [
  { month: "Jan", temp: 15, rain: 30 },
  { month: "Feb", temp: 18, rain: 25 },
  { month: "Mar", temp: 22, rain: 40 },
  { month: "Apr", temp: 28, rain: 60 },
  { month: "May", temp: 32, rain: 80 },
  { month: "Jun", temp: 35, rain: 90 },
];

// ---------- Utility Functions ----------
export const getWeatherGradient = (condition?: string): string => {
  const baseBlue = "#1e3a5f";
  const topColor = (() => {
    switch (condition?.toLowerCase()) {
      case "rain":
      case "rainy":
        return "#4b0082";
      case "cloudy":
        return "#64748b";
      case "clear":
      case "sunny":
        return "#f59e0b";
      case "snow":
        return "#93c5fd";
      case "storm":
        return "#4338ca";
      default:
        return "#334155";
    }
  })();

  return `linear-gradient(to bottom, ${topColor} 0%, ${baseBlue} 80%)`;
};

export const handleDownloadCSV = (results, location, activity) => {
  if (!results || !results.predictions) {
    console.error("No prediction data available to export.");
    return;
  }

  const predictions = results.predictions;

  const headers = [
    "Date",
    "Location",
    "Activity",
    "Suitability Status",
    "Avg Temp (T2M)",
    "Total Rainfall (PRECTOTCORR)",
    "Avg Wind Speed (WS10M)",
  ];

  let csvContent = headers.join(",") + "\n";

  Object.entries(predictions).forEach(([date, data]) => {
    const row = [
      `"${date}"`,
      `"${location.replace(/"/g, '""')}"`,
      `"${activity}"`,
      `"${data.suitability_status}"`,
      data.T2M.toFixed(2),
      data.PRECTOTCORR.toFixed(2),
      data.WS10M.toFixed(2),
    ];

    csvContent += row.join(",") + "\n";
  });
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.setAttribute(
    "download",
    `weather_forecast_${location.replace(/[^a-z0-9]/gi, "_")}.csv`
  );
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  console.log("CSV download initiated.");
};
export const getTodayDate = () => {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export const getMaxDate = () => {
  const nextYear = new Date();
  nextYear.setFullYear(nextYear.getFullYear() + 1);

  const year = nextYear.getFullYear();
  const month = String(nextYear.getMonth() + 1).padStart(2, "0");
  const day = String(nextYear.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export const minDate = getTodayDate();
export const maxDate = getMaxDate();

export const handleExportPng = (location) => {
  // 1. Get the DOM element by ID
  const input = document.getElementById("weather");

  if (!input) {
    console.error(
      "Capture section (#capture-section) not found. Cannot export PNG."
    );
    alert("The content to capture is not visible or lacks the correct ID.");
    return;
  }

  // 2. Convert HTML element to canvas using html2canvas
  html2canvas(input, {
    // Use CORS for external images (like your weather icons)
    useCORS: true,
    // Use a scale > 1 for better resolution/quality (e.g., 2x or 3x)
    scale: 2,
    // Optional: Crop any scrolling overflow if your results section is scrollable
    windowWidth: input.scrollWidth,
    windowHeight: input.scrollHeight,
  })
    .then((canvas) => {
      // 3. Convert the canvas to a data URL (PNG format)
      const imgData = canvas.toDataURL("image/png");

      // 4. Create and trigger the download
      const link = document.createElement("a");
      link.href = imgData;

      const filename = `weather_report_${location.replace(
        /[^a-z0-9]/gi,
        "_"
      )}.png`;
      link.download = filename;

      document.body.appendChild(link);
      link.click();

      // 5. Cleanup
      document.body.removeChild(link);
      console.log("PNG download initiated.");
    })
    .catch((err) => {
      console.error("Error generating PNG:", err);
      alert(
        "Failed to generate image. Please check console for details or try a different browser."
      );
    });
};

/**
 * Converts the results object into a downloadable JSON file.
 * @param {object} data - The complete data object (including results, lat, lon, etc.).
 * @param {string} location - The name of the searched location.
 */
export const handleDownloadJSON = (data, location) => {
  if (!data) {
    console.error("No data available to export.");
    return;
  }

  // Convert the JavaScript object into a formatted JSON string
  // null, 2 formats the JSON nicely with a 2-space indentation
  const jsonString = JSON.stringify(data, null, 2);

  // Create a Blob containing the JSON data
  const blob = new Blob([jsonString], { type: "application/json" });
  const url = URL.createObjectURL(blob);

  // Create a temporary link element for the download
  const link = document.createElement("a");
  link.href = url;

  // Set the filename using the location and current date
  const filename = `weather_data_${location.replace(/[^a-z0-9]/gi, "_")}.json`;
  link.setAttribute("download", filename);

  // Simulate a click on the link to trigger the download
  document.body.appendChild(link);
  link.click();

  // Clean up
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  console.log("JSON download initiated.");
};

