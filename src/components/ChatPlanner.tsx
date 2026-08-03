import React, { useEffect, useRef, useState } from "react";
import {
  Send, Sparkles, Loader, MapPin, Calendar, ChevronDown, ChevronUp,
  Wand2, Hotel, TreePine, ExternalLink, Navigation, Sprout,
  AlertTriangle, CheckCircle2, Shield, Heart, Star, Download,
  Mail, Info, Thermometer, Wind, Droplets, Cloud, Mic, Globe,
} from "lucide-react";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import CurrentWeatherCard from "./CurrentWeatherCard";

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type AgentStep = { step: string; tool: string; detail: string };

type VenueResult = {
  name: string;
  type: string;
  distance_km: number;
  website: string | null;
  osm_link: string;
  address: string | null;
};

type OnlineVenueResult = {
  name: string;
  description: string;
  url: string | null;
};

type FarmingResult = {
  crop_name: string;
  farming_score: number;
  suitability_label: string;
  risks: string[];
  opportunities: string[];
  advice: string;
};

type AgentOption = {
  location: string;
  date: string;
  suitability_status: string;
  temp: number;           // feels-like
  temp_actual: number;
  temp_max?: number;
  temp_min?: number;
  rain: number;
  wind: number;
  humidity: number;
  cloud_pct: number;
  // Multi-dimensional scores
  score: number;
  comfort: number;
  safety: number;
  suitability: number;
  grade: string;
  profile_name: string;
  // Explanation
  reasons: string[];
  risks: string[];
  positives: string[];
  tips: string[];
  confidence: string;
  confidence_label: string;
  lat: number;
  lon: number;
  venues: VenueResult[];
  online_venues: OnlineVenueResult[];
  farming: FarmingResult | null;
  image_url: string | null;
};

type AgentResponse = {
  reply: string;
  explanation: string;
  intent: {
    location: string | null;
    date_phrase: string | null;
    activity: string | null;
    event_size: string | null;
  };
  plan?: string;
  steps: AgentStep[];
  options: AgentOption[];
  session_id: string;
};

type ChatMessage =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; data?: AgentResponse }
  | { role: "error"; text: string };

// ─────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────

const SUGGESTIONS = [
  "What's the weather like in Colombo today?",
  "Is tomorrow good for a beach day in Galle?",
  "Plan a weekend trip to Kandy next weekend",
  "Can I organize a wedding in Kandy next month?",
  "Compare Galle vs Kandy for an outdoor party",
  "Is it safe to harvest rice in Polonnaruwa next week?",
];

const confidenceStyle: Record<string, string> = {
  high:   "bg-green-50 text-green-700 border-green-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  low:    "bg-slate-50 text-slate-600 border-slate-200",
};

const gradeColor: Record<string, string> = {
  "A+": "text-green-600", A: "text-green-600", B: "text-blue-600",
  C: "text-amber-600",    D: "text-orange-600", F: "text-red-600",
};

const API_BASE = "";

// Web Speech API only ships as the vendor-prefixed webkitSpeechRecognition
// outside Firefox, and there's no @types package for it — declare just the
// shape this component actually uses instead of reaching for `any`.
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: { transcript: string };
}

interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}

interface SpeechRecognitionInstance {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionCtorType = new () => SpeechRecognitionInstance;

const SpeechRecognitionCtor: SpeechRecognitionCtorType | null =
  (window as unknown as { SpeechRecognition?: SpeechRecognitionCtorType }).SpeechRecognition ??
  (window as unknown as { webkitSpeechRecognition?: SpeechRecognitionCtorType }).webkitSpeechRecognition ??
  null;

// Voices a Sri Lankan farmer is likely to speak — extend as needed.
const VOICE_LANGUAGES = [
  { code: "en-US", label: "EN" },
  { code: "si-LK", label: "SI" },
  { code: "ta-LK", label: "TA" },
];

// ─────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────

export default function ChatPlanner() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      text: "Hi, I'm Weatherly — ask me what to plan around the weather. Try a day out, a weekend trip, an event, or a farming question, and I'll check real forecasts, score comfort/safety, suggest nearby places, and explain my reasoning.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [voiceLang, setVoiceLang] = useState(VOICE_LANGUAGES[0].code);
  const sessionIdRef = useRef<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const transcriptRef = useRef("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  // Stop any in-flight recognition if the component unmounts mid-recording.
  useEffect(() => {
    return () => recognitionRef.current?.abort();
  }, []);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || loading) return;

    setMessages((prev) => [...prev, { role: "user", text: message }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionIdRef.current }),
      });

      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data: AgentResponse = await res.json();
      sessionIdRef.current = data.session_id;
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply, data }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "error",
          text: "Couldn't reach the planning agent. Is the backend running on http://localhost:8000?",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const startListening = () => {
    if (!SpeechRecognitionCtor || loading || listening) return;

    const recognition = new SpeechRecognitionCtor();
    recognition.lang = voiceLang;
    recognition.continuous = true;
    recognition.interimResults = true;
    transcriptRef.current = "";

    recognition.onresult = (event: SpeechRecognitionEventLike) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const chunk = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += chunk + " ";
        else interimText += chunk;
      }
      transcriptRef.current = (transcriptRef.current + finalText).trim();
      setInput((transcriptRef.current + " " + interimText).trim());
    };

    recognition.onerror = () => setListening(false);

    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;
      const finalMessage = transcriptRef.current.trim();
      if (finalMessage) send(finalMessage);
    };

    recognitionRef.current = recognition;
    setInput("");
    setListening(true);
    recognition.start();
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
  };

  return (
    <div className="flex flex-col h-full max-w-3xl mx-auto w-full pt-16">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-2">
        <div className="w-8 h-8 rounded-full bg-green-600 flex items-center justify-center shrink-0">
          <Sparkles className="w-4 h-4 text-white" />
        </div>
        <div>
          <div className="font-semibold text-sm text-gray-900">Weatherly AI Planning Agent</div>
          <div className="text-xs text-gray-500">Comfort · Safety · Suitability for trips, events &amp; farming</div>
        </div>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} onSend={send} />
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-sm text-gray-400 pl-1">
            <Loader className="w-4 h-4 animate-spin text-blue-500" />
            <span>Fetching NASA climate data, running analysis…</span>
          </div>
        )}
      </div>

      {/* Current weather + suggestion chips */}
      {messages.length <= 1 && (
        <div className="px-4 pb-1">
          <CurrentWeatherCard onAskAI={() => inputRef.current?.focus()} />
        </div>
      )}
      {messages.length <= 1 && (
        <div className="px-4 pb-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              className="text-xs px-3 py-1.5 rounded-full border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 hover:border-gray-300 transition-colors shadow-sm"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Listening indicator */}
      {listening && (
        <div className="px-4 pb-1 flex items-center gap-1.5 text-xs text-red-500">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500" />
          </span>
          Listening… release the mic to send
        </div>
      )}

      {/* Input */}
      <form
        onSubmit={(e) => { e.preventDefault(); send(input); }}
        className="flex items-center gap-2 p-4 border-t border-gray-200 bg-white"
      >
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={listening ? "Speak now…" : "e.g. 'Best beach vacation in Thailand next month?'"}
          className="flex-1 bg-gray-50 border border-gray-300 rounded-full px-4 py-2.5 text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 transition-all"
        />

        {SpeechRecognitionCtor && (
          <>
            <select
              value={voiceLang}
              onChange={(e) => setVoiceLang(e.target.value)}
              disabled={listening}
              title="Voice input language"
              className="text-xs bg-gray-50 border border-gray-300 rounded-full px-2 py-2.5 text-gray-500 outline-none shrink-0"
            >
              {VOICE_LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>

            <Button
              type="button"
              size="icon"
              disabled={loading}
              onMouseDown={startListening}
              onMouseUp={stopListening}
              onMouseLeave={() => listening && stopListening()}
              onTouchStart={(e) => { e.preventDefault(); startListening(); }}
              onTouchEnd={(e) => { e.preventDefault(); stopListening(); }}
              title="Hold to talk"
              className={`rounded-full shrink-0 transition-colors ${
                listening
                  ? "bg-red-500 hover:bg-red-600 text-white animate-pulse"
                  : "bg-gray-100 hover:bg-gray-200 text-gray-600"
              }`}
            >
              <Mic className="w-4 h-4" />
            </Button>
          </>
        )}

        <Button
          type="submit"
          size="icon"
          disabled={loading}
          className="rounded-full bg-green-600 hover:bg-green-700 text-white shrink-0"
        >
          <Send className="w-4 h-4" />
        </Button>
      </form>
    </div>
  );
}

// ─────────────────────────────────────────────
// Message bubble
// ─────────────────────────────────────────────

function MessageBubble({ msg, onSend }: { msg: ChatMessage; onSend: (t: string) => void }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[80%] text-sm leading-relaxed shadow-sm whitespace-pre-wrap">
          {msg.text}
        </div>
      </div>
    );
  }

  const isError = msg.role === "error";

  return (
    <div className="flex justify-start">
      <div className="max-w-[92%] space-y-2">
        <div
          className={`flex items-start gap-2.5 rounded-2xl rounded-bl-sm px-4 py-3 text-sm leading-relaxed shadow-sm ${
            isError
              ? "bg-red-50 text-red-700 border border-red-200"
              : "bg-white text-gray-800 border border-gray-200"
          }`}
        >
          {!isError && <Sparkles className="w-4 h-4 mt-0.5 shrink-0 text-blue-500" />}
          <span className="whitespace-pre-wrap">{msg.text}</span>
        </div>

        {"data" in msg && msg.data && <AgentTrace data={msg.data} />}
        {"data" in msg && msg.data && msg.data.options.length > 0 && (
          <OptionsGrid options={msg.data.options} agentData={msg.data} onSend={onSend} />
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Agent trace (collapsible)
// ─────────────────────────────────────────────

function AgentTrace({ data }: { data: AgentResponse }) {
  const [open, setOpen] = useState(false);
  if (!data.steps?.length) return null;

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 overflow-hidden shadow-sm">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-gray-500 hover:text-gray-700 transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Wand2 className="w-3.5 h-3.5 text-blue-500" />
          Agent reasoning ({data.plan ?? "plan"} · {data.steps.length} steps)
        </span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && (
        <ol className="px-3 pb-3 space-y-1.5 border-t border-gray-100 pt-2">
          {data.steps.map((s, i) => (
            <li key={i} className="text-xs text-gray-600 flex gap-2">
              <span className="text-gray-300 shrink-0 font-mono">{i + 1}.</span>
              <span>
                <span className="text-gray-800 font-medium">{s.step}</span>
                <span className="text-gray-400"> ({s.tool})</span>
                {" — "}{s.detail}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Options grid
// ─────────────────────────────────────────────

function OptionsGrid({ options, agentData, onSend }: { options: AgentOption[]; agentData: AgentResponse; onSend: (t: string) => void }) {
  return (
    <div className="space-y-3">
      {options.slice(0, 4).map((o, i) => (
        <OptionCard key={i} option={o} isTop={i === 0} agentData={i === 0 ? agentData : undefined} />
      ))}
      {options.length > 0 && (
        <ReportActions options={options} agentData={agentData} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Score gauge — small horizontal bar
// ─────────────────────────────────────────────

function ScoreBar({ label, value, icon, color }: { label: string; value: number; icon: React.ReactNode; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={`shrink-0 ${color}`}>{icon}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-[10px] text-gray-500">{label}</span>
          <span className="text-[11px] font-bold text-gray-800">{value}</span>
        </div>
        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              value >= 75 ? "bg-green-500" : value >= 55 ? "bg-amber-400" : "bg-red-400"
            }`}
            style={{ width: `${value}%` }}
          />
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────
// Individual option card
// ─────────────────────────────────────────────

function OptionCard({ option: o, isTop, agentData }: { option: AgentOption; isTop: boolean; agentData?: AgentResponse }) {
  const [showAnalysis, setShowAnalysis] = useState(isTop);

  return (
    <Card className={`bg-white border-gray-200 p-3 gap-0 shadow-sm ${isTop ? "ring-2 ring-blue-500/20 border-blue-200" : ""}`}>
      {o.image_url && (
        <div className="-mx-3 -mt-3 mb-2 h-28 overflow-hidden rounded-t-xl">
          <img
            src={o.image_url}
            alt={o.location.split(",")[0]}
            className="w-full h-full object-cover"
            loading="lazy"
            onError={(e) => { e.currentTarget.style.display = "none"; }}
          />
        </div>
      )}
      {/* Location + grade */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-xs text-gray-500 truncate">
          <MapPin className="w-3.5 h-3.5 shrink-0 text-blue-500" />
          <span className="truncate font-semibold text-gray-800">{o.location.split(",")[0]}</span>
          {isTop && (
            <span className="text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full border border-blue-100 shrink-0">
              Top pick
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0 ml-2">
          <span className={`text-[10px] border px-1.5 py-0.5 rounded-full ${confidenceStyle[o.confidence] ?? confidenceStyle.low}`}>
            {o.confidence === "high" ? "Forecast" : o.confidence === "medium" ? "Med. term" : "Climate est."}
          </span>
          <span className={`text-lg font-black ${gradeColor[o.grade] ?? "text-gray-600"}`}>{o.grade}</span>
        </div>
      </div>

      {/* Date + overall score */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5 text-sm text-gray-700 font-medium">
          <Calendar className="w-4 h-4 text-gray-400" />
          {o.date}
        </div>
        <div className="text-right">
          <span className="text-sm font-black text-blue-600">{o.score}</span>
          <span className="text-[10px] text-gray-400">/100</span>
        </div>
      </div>

      {/* Three-score bars */}
      <div className="space-y-1.5 mb-3">
        <ScoreBar label="Comfort" value={o.comfort} icon={<Heart className="w-3 h-3" />} color="text-pink-500" />
        <ScoreBar label="Safety" value={o.safety} icon={<Shield className="w-3 h-3" />} color="text-blue-500" />
        <ScoreBar label="Suitability" value={o.suitability} icon={<Star className="w-3 h-3" />} color="text-amber-500" />
      </div>

      {/* Weather stats grid */}
      <div className="grid grid-cols-4 gap-1 text-[10px] mb-2">
        {[
          { label: "Feels", value: `${o.temp}°C`, icon: <Thermometer className="w-2.5 h-2.5" /> },
          { label: "Rain", value: `${o.rain}mm`, icon: <Droplets className="w-2.5 h-2.5" /> },
          { label: "Wind", value: `${o.wind}km/h`, icon: <Wind className="w-2.5 h-2.5" /> },
          { label: "Humidity", value: `${o.humidity}%`, icon: <Cloud className="w-2.5 h-2.5" /> },
        ].map(({ label, value, icon }) => (
          <div key={label} className="bg-gray-50 border border-gray-100 rounded-lg px-1 py-1.5 text-center">
            <div className="flex justify-center text-gray-400 mb-0.5">{icon}</div>
            <div className="text-gray-400">{label}</div>
            <div className="font-semibold text-gray-800 mt-0.5">{value}</div>
          </div>
        ))}
      </div>

      {/* Confidence note */}
      {o.confidence_label && (
        <div className="flex items-start gap-1 text-[10px] text-gray-400 mb-2">
          <Info className="w-3 h-3 shrink-0 mt-0.5" />
          <span>{o.confidence_label}</span>
        </div>
      )}

      {/* Analysis section — toggle */}
      {isTop && (
        <button
          onClick={() => setShowAnalysis((v) => !v)}
          className="w-full flex items-center justify-between text-[11px] text-blue-600 hover:text-blue-800 font-medium mb-1 transition-colors"
        >
          <span className="flex items-center gap-1"><Wand2 className="w-3 h-3" />Full analysis</span>
          {showAnalysis ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>
      )}

      {showAnalysis && isTop && (
        <div className="space-y-2 border-t border-gray-100 pt-2">
          {agentData?.explanation && (
            <p className="text-[11px] text-gray-700 leading-relaxed bg-blue-50 rounded-lg px-2.5 py-2 border border-blue-100">
              {agentData.explanation}
            </p>
          )}

          {o.positives.length > 0 && (
            <div>
              <div className="flex items-center gap-1 text-[10px] text-green-700 font-semibold mb-1">
                <CheckCircle2 className="w-3 h-3" /> Strengths
              </div>
              {o.positives.map((p, i) => (
                <div key={i} className="text-[11px] text-green-800 flex gap-1.5 mb-0.5">
                  <span className="text-green-400 shrink-0">✓</span>{p}
                </div>
              ))}
            </div>
          )}

          {o.risks.length > 0 && (
            <div>
              <div className="flex items-center gap-1 text-[10px] text-red-600 font-semibold mb-1">
                <AlertTriangle className="w-3 h-3" /> Risks
              </div>
              {o.risks.map((r, i) => (
                <div key={i} className="text-[11px] text-red-700 flex gap-1.5 mb-0.5">
                  <span className="text-red-400 shrink-0">⚠</span>{r}
                </div>
              ))}
            </div>
          )}

          {o.tips.length > 0 && (
            <div>
              <div className="flex items-center gap-1 text-[10px] text-blue-700 font-semibold mb-1">
                <Info className="w-3 h-3" /> Preparation Tips
              </div>
              {o.tips.map((t, i) => (
                <div key={i} className="text-[11px] text-blue-800 flex gap-1.5 mb-0.5">
                  <span className="text-blue-400 shrink-0">→</span>{t}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {o.farming && <FarmingPanel farming={o.farming} />}
      {o.online_venues && o.online_venues.length > 0 && <OnlineVenueList venues={o.online_venues} />}
      {o.venues && o.venues.length > 0 && <VenueList venues={o.venues} />}
    </Card>
  );
}

// ─────────────────────────────────────────────
// Report download + email actions
// ─────────────────────────────────────────────

function ReportActions({ options, agentData }: { options: AgentOption[]; agentData: AgentResponse }) {
  const [emailInput, setEmailInput] = useState("");
  const [showEmail, setShowEmail] = useState(false);
  const [emailStatus, setEmailStatus] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const downloadReport = async () => {
    try {
      const res = await fetch(`/agent/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          options,
          activity: agentData.intent.activity || "outdoor activity",
          explanation: agentData.explanation || "",
          intent: agentData.intent,
        }),
      });
      const report = await res.json();
      const blob = new Blob([report.markdown], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `weatherly-report-${options[0]?.location?.split(",")[0] ?? "plan"}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert("Report generation failed. Is the backend running?");
    }
  };

  const sendEmail = async () => {
    if (!emailInput.includes("@")) { setEmailStatus("Please enter a valid email address."); return; }
    setSending(true);
    setEmailStatus(null);
    try {
      const res = await fetch(`/agent/email-report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_email: emailInput,
          options,
          activity: agentData.intent.activity || "outdoor activity",
          explanation: agentData.explanation || "",
          intent: agentData.intent,
        }),
      });
      const data = await res.json();
      if (data.sent) {
        setEmailStatus(`Report sent to ${emailInput}`);
      } else {
        // Backend returned the report for client download instead
        setEmailStatus("Email server not configured — downloading report instead.");
        if (data.report?.markdown) {
          const blob = new Blob([data.report.markdown], { type: "text/markdown;charset=utf-8" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "weatherly-report.md";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }
      }
    } catch {
      setEmailStatus("Request failed — check backend is running.");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-gray-50 p-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[11px] font-medium text-gray-600">Planning Report</span>
      </div>
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={downloadReport}
          className="flex items-center gap-1.5 text-[11px] bg-white border border-gray-200 rounded-full px-3 py-1.5 text-gray-700 hover:bg-gray-100 transition-colors shadow-sm font-medium"
        >
          <Download className="w-3 h-3" /> Download Report
        </button>
        <button
          onClick={() => setShowEmail((v) => !v)}
          className="flex items-center gap-1.5 text-[11px] bg-blue-600 rounded-full px-3 py-1.5 text-white hover:bg-blue-700 transition-colors shadow-sm font-medium"
        >
          <Mail className="w-3 h-3" /> Email Report
        </button>
      </div>

      {showEmail && (
        <div className="mt-2 flex gap-2">
          <input
            value={emailInput}
            onChange={(e) => setEmailInput(e.target.value)}
            placeholder="your@email.com"
            className="flex-1 text-xs border border-gray-300 rounded-full px-3 py-1.5 outline-none focus:border-blue-400"
          />
          <button
            onClick={sendEmail}
            disabled={sending}
            className="text-xs bg-blue-600 text-white rounded-full px-3 py-1.5 disabled:opacity-50"
          >
            {sending ? "Sending…" : "Send"}
          </button>
        </div>
      )}

      {emailStatus && (
        <div className="mt-1.5 text-[10px] text-gray-600">{emailStatus}</div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Farming panel
// ─────────────────────────────────────────────

const farmingLabelStyles: Record<string, string> = {
  "Excellent":            "bg-green-50 text-green-700 border-green-200",
  "Good":                 "bg-emerald-50 text-emerald-700 border-emerald-200",
  "Fair — some concerns": "bg-amber-50 text-amber-700 border-amber-200",
  "Poor — significant risks": "bg-red-50 text-red-700 border-red-200",
};

function FarmingPanel({ farming }: { farming: FarmingResult }) {
  const [open, setOpen] = useState(false);
  const labelStyle = farmingLabelStyles[farming.suitability_label] ?? "bg-gray-50 text-gray-700 border-gray-200";

  return (
    <div className="mt-2 border border-green-100 rounded-xl bg-green-50/50 overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-3 py-2 text-[11px] text-green-800 hover:bg-green-50 transition-colors"
      >
        <span className="flex items-center gap-1.5 font-medium">
          <Sprout className="w-3.5 h-3.5 text-green-600" />
          {farming.crop_name} — {farming.suitability_label}
          <span className={`ml-1.5 px-1.5 py-0.5 rounded-full border text-[10px] font-semibold ${labelStyle}`}>
            {farming.farming_score}/100
          </span>
        </span>
        {open ? <ChevronUp className="w-3 h-3 text-green-600" /> : <ChevronDown className="w-3 h-3 text-green-600" />}
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2 border-t border-green-100 pt-2">
          {farming.advice && (
            <p className="text-[11px] text-green-900 italic">{farming.advice}</p>
          )}
          {farming.risks.length > 0 && (
            <div>
              <div className="flex items-center gap-1 text-[10px] text-red-600 font-semibold mb-1">
                <AlertTriangle className="w-3 h-3" /> Risks
              </div>
              {farming.risks.map((r, i) => (
                <div key={i} className="text-[11px] text-red-700 bg-red-50 border border-red-100 rounded px-2 py-1 mb-0.5">{r}</div>
              ))}
            </div>
          )}
          {farming.opportunities.length > 0 && (
            <div>
              <div className="flex items-center gap-1 text-[10px] text-green-700 font-semibold mb-1">
                <CheckCircle2 className="w-3 h-3" /> Opportunities
              </div>
              {farming.opportunities.map((o, i) => (
                <div key={i} className="text-[11px] text-green-800 bg-green-50 border border-green-100 rounded px-2 py-1 mb-0.5">{o}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Online venue list (Google-Search-grounded recommendations)
// ─────────────────────────────────────────────

function OnlineVenueList({ venues }: { venues: OnlineVenueResult[] }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="mt-2 border-t border-gray-100 pt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between text-[11px] text-gray-500 hover:text-gray-700 transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Globe className="w-3 h-3 text-blue-400" />
          <span className="font-medium">{venues.length} venue recommendation{venues.length !== 1 ? "s" : ""} (web search)</span>
        </span>
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {open && (
        <ul className="mt-2 space-y-2">
          {venues.map((v, i) => (
            <li key={i} className="flex items-start gap-2 p-2 bg-gray-50 rounded-lg border border-gray-100">
              <Globe className="w-3.5 h-3.5 shrink-0 text-blue-500 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="text-[12px] font-medium text-gray-800">{v.name}</div>
                {v.description && (
                  <div className="text-[11px] text-gray-500 mt-0.5">{v.description}</div>
                )}
                {v.url && (
                  <a href={v.url} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1 text-[11px] text-blue-500 hover:text-blue-700 font-medium transition-colors mt-1">
                    <ExternalLink className="w-2.5 h-2.5" /> Visit website
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────
// Venue list
// ─────────────────────────────────────────────

const VENUE_TYPE_ICON: Record<string, React.ReactNode> = {
  Hotel:            <Hotel className="w-3.5 h-3.5 shrink-0 text-indigo-500" />,
  Resort:           <Hotel className="w-3.5 h-3.5 shrink-0 text-indigo-500" />,
  Hostel:           <Hotel className="w-3.5 h-3.5 shrink-0 text-indigo-500" />,
  Park:             <TreePine className="w-3.5 h-3.5 shrink-0 text-green-500" />,
  "Nature Reserve": <TreePine className="w-3.5 h-3.5 shrink-0 text-green-500" />,
  Garden:           <TreePine className="w-3.5 h-3.5 shrink-0 text-green-500" />,
};

function VenueList({ venues }: { venues: VenueResult[] }) {
  const [open, setOpen] = useState(true);

  return (
    <div className="mt-2 border-t border-gray-100 pt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between text-[11px] text-gray-500 hover:text-gray-700 transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Navigation className="w-3 h-3 text-blue-400" />
          <span className="font-medium">{venues.length} nearby venue{venues.length !== 1 ? "s" : ""} &amp; hotel{venues.length !== 1 ? "s" : ""}</span>
        </span>
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>

      {open && (
        <ul className="mt-2 space-y-2">
          {venues.map((v, i) => (
            <li key={i} className="flex items-start gap-2 p-2 bg-gray-50 rounded-lg border border-gray-100">
              <span className="mt-0.5">
                {VENUE_TYPE_ICON[v.type] ?? <MapPin className="w-3.5 h-3.5 shrink-0 text-gray-400" />}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-[12px] font-medium text-gray-800">{v.name}</span>
                  <span className="text-[10px] text-gray-400 bg-white border border-gray-200 px-1.5 py-0.5 rounded-full shrink-0">
                    {v.type} · {v.distance_km} km
                  </span>
                </div>
                {v.address && (
                  <div className="text-[10px] text-gray-400 mt-0.5 truncate">{v.address}</div>
                )}
                <div className="flex items-center gap-3 mt-1">
                  <a href={v.osm_link} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1 text-[11px] text-blue-500 hover:text-blue-700 font-medium transition-colors">
                    <ExternalLink className="w-2.5 h-2.5" /> View on map
                  </a>
                  {v.website && (
                    <a href={v.website} target="_blank" rel="noopener noreferrer"
                      className="flex items-center gap-1 text-[11px] text-blue-500 hover:text-blue-700 font-medium transition-colors">
                      <ExternalLink className="w-2.5 h-2.5" /> Website
                    </a>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
