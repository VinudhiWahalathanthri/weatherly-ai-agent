import { useState } from "react";
import HomeContent from "./components/HomeContent";
import ChatPlanner from "./components/ChatPlanner";
import { Sparkles, MapPin } from "lucide-react";

function App() {
  // AI chat is the default landing experience — it's the low-friction path for
  // everyday day/trip planning. Manual mode is repositioned as "Advanced Search"
  // for people who want to pick exact dates/locations on a map themselves.
  const [mode, setMode] = useState<"manual" | "ai">("ai");

  return (
    <div className="h-screen relative">
      {/* Floating mode switcher — jumps between the AI Planner and Advanced Search */}
      <div className="fixed top-5 right-6 z-[60] flex items-center gap-1 bg-white/95 backdrop-blur-md rounded-full p-1 border border-gray-200 shadow-lg">
        <button
          onClick={() => setMode("ai")}
          className={`flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-full transition-colors ${
            mode === "ai" ? "bg-gray-900 text-white" : "text-gray-500 hover:text-gray-900"
          }`}
        >
          <Sparkles className="w-3.5 h-3.5" />
          Plan a Trip
        </button>
        <button
          onClick={() => setMode("manual")}
          className={`flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-full transition-colors ${
            mode === "manual" ? "bg-gray-900 text-white" : "text-gray-500 hover:text-gray-900"
          }`}
        >
          <MapPin className="w-3.5 h-3.5" />
          Advanced Search
        </button>
      </div>

      {mode === "ai" ? (
        <div className="h-screen bg-slate-50">
          <ChatPlanner />
        </div>
      ) : (
        <HomeContent />
      )}
    </div>
  );
}

export default App;
