import { useState } from "react";
import HomeContent from "./components/HomeContent";
import ChatPlanner from "./components/ChatPlanner";
import { Sparkles, MapPin } from "lucide-react";

function App() {
  const [mode, setMode] = useState<"manual" | "ai">("ai");

  return (
    <div className="h-screen relative">
      <div className="fixed top-5 right-6 z-[60] flex items-center gap-1 bg-white/90 backdrop-blur-md rounded-full p-1 border border-slate-200/80 shadow-lg shadow-blue-900/5">
        <button
          onClick={() => setMode("ai")}
          className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-full transition-all ${
            mode === "ai" ? "bg-gradient-to-r from-slate-900 to-blue-900 text-white shadow-sm" : "text-slate-500 hover:text-slate-900"
          }`}
        >
          <Sparkles className="w-3.5 h-3.5" />
          Plan a Trip
        </button>
        <button
          onClick={() => setMode("manual")}
          className={`flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-full transition-all ${
            mode === "manual" ? "bg-gradient-to-r from-slate-900 to-blue-900 text-white shadow-sm" : "text-slate-500 hover:text-slate-900"
          }`}
        >
          <MapPin className="w-3.5 h-3.5" />
          Advanced Search
        </button>
      </div>

      {mode === "ai" ? (
        <div className="h-screen weatherly-atmosphere">
          <ChatPlanner />
        </div>
      ) : (
        <HomeContent />
      )}
    </div>
  );
}

export default App;
