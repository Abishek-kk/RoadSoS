import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  AlertTriangle,
  Hospital,
  MapPin,
  Mic,
  Navigation,
  Phone,
  Shield,
  Siren,
  Search,
  RotateCcw,
  Truck,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { api, type RiskAssessment, type RoadAlert } from "@/lib/api";
import { toast } from "sonner";
import { getLocation, saveLocation, clearSavedLocation, hasSavedLocation } from "@/lib/location";

export const Route = createFileRoute("/")({ component: Dashboard });

type BrowserSpeechRecognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string } }> }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
};

type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

function getSpeechRecognitionConstructor(): BrowserSpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const speechWindow = window as typeof window & {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  };
  return speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition ?? null;
}

function isVoiceSOSPhrase(transcript: string) {
  const normalized = transcript
    .toLowerCase()
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return normalized.includes("help accident happened") || /\bsos\b/.test(normalized);
}

function Dashboard() {
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [alerts, setAlerts] = useState<RoadAlert[]>([]);
  const [risk, setRisk] = useState<RiskAssessment | null>(null);
  const [sosActive, setSosActive] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [locationName, setLocationName] = useState<string | null>(null);
  const sosTimerRef = useRef<number | null>(null);
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [listeningForSOS, setListeningForSOS] = useState(false);

  // Location search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [showSetup, setShowSetup] = useState(false);

  // Dynamic proximity states for dashboard cards
  const [nearestHospitalDist, setNearestHospitalDist] = useState<string>("Calculating…");
  const [nearestPoliceDist, setNearestPoliceDist] = useState<string>("Calculating…");
  const [nearestTowingDist, setNearestTowingDist] = useState<string>("Calculating...");

  // On mount, load location and check if user needs to set one
  useEffect(() => {
    const init = async () => {
      const c = await getLocation();
      setCoords(c);

      // If no saved location, show the setup prompt
      if (!hasSavedLocation()) {
        setShowSetup(true);
      }

      // Reverse geocode to get a readable name
      reverseGeocode(c.lat, c.lng);
    };
    init();
    return () => {
      if (sosTimerRef.current) window.clearTimeout(sosTimerRef.current);
      recognitionRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    setSpeechSupported(Boolean(getSpeechRecognitionConstructor()));
  }, []);

  // Reverse geocode to display a human-readable location name
  const reverseGeocode = async (lat: number, lng: number) => {
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=10`,
      );
      if (res.ok) {
        const data = await res.json();
        const city =
          data.address?.city ||
          data.address?.town ||
          data.address?.village ||
          data.address?.county ||
          data.address?.state ||
          "";
        if (city) setLocationName(city);
      }
    } catch {
      // ignore
    }
  };

  // Search for a city/place by name using Nominatim geocoding
  const handleSearch = useCallback(async () => {
    const query = searchQuery.trim();
    if (!query) return;
    setSearching(true);
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=1`,
      );
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      if (data && data.length > 0) {
        const item = data[0];
        const lat = parseFloat(item.lat);
        const lng = parseFloat(item.lon);
        saveLocation(lat, lng);
        setCoords({ lat, lng });
        const name = item.display_name.split(",")[0];
        setLocationName(name);
        setSearchQuery("");
        setShowSetup(false);
        toast.success(`Location set to ${name}`);
      } else {
        toast.error("Location not found. Try a different name.");
      }
    } catch (e) {
      console.error(e);
      toast.error("Search failed. Check your internet connection.");
    } finally {
      setSearching(false);
    }
  }, [searchQuery]);

  // Reset to auto-detected location
  const handleReset = useCallback(() => {
    clearSavedLocation();
    setLocationName(null);
    getLocation().then((c) => {
      setCoords(c);
      reverseGeocode(c.lat, c.lng);
      toast.success("Location reset to auto-detect");
    });
  }, []);

  // Post location and fetch alerts when coords change
  useEffect(() => {
    if (!coords) return;
    api.postLocation(coords.lat, coords.lng);
    api.alerts(coords.lat, coords.lng).then(setAlerts);
    api.risk(coords.lat, coords.lng).then(setRisk).catch(() => setRisk(null));

    // Fetch nearest hospital dynamically
    api
      .hospitals(coords.lat, coords.lng)
      .then((hList) => {
        if (hList && hList.length > 0) {
          const nearest = hList[0];
          setNearestHospitalDist(formatDistance(nearest.distance_km));
        } else {
          setNearestHospitalDist("None nearby");
        }
      })
      .catch(() => setNearestHospitalDist("Error"));

    // Fetch nearest police station dynamically
    api
      .police(coords.lat, coords.lng)
      .then((pList) => {
        if (pList && pList.length > 0) {
          const nearest = pList[0];
          setNearestPoliceDist(formatDistance(nearest.distance_km));
        } else {
          setNearestPoliceDist("None nearby");
        }
      })
      .catch(() => setNearestPoliceDist("Error"));

    api
      .towing(coords.lat, coords.lng)
      .then((tList) => {
        if (tList && tList.length > 0) {
          const nearest = tList[0];
          setNearestTowingDist(formatDistance(nearest.distance_km));
        } else {
          setNearestTowingDist("None nearby");
        }
      })
      .catch(() => setNearestTowingDist("Error"));
  }, [coords]);

  // SOS countdown timer
  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);

  const triggerSOS = useCallback(
    async (note = "Manual SOS") => {
      if (sosTimerRef.current || countdown > 0) return;
      setCountdown(3);
      sosTimerRef.current = window.setTimeout(async () => {
        sosTimerRef.current = null;
        try {
          const currentCoords = coords ?? (await getLocation());
          setCoords(currentCoords);
          reverseGeocode(currentCoords.lat, currentCoords.lng);

          const res = await api.triggerSOS({ ...currentCoords, user: "Abishek", note });
          const sent = res.notifications?.sent ?? 0;
          const dryRun = res.notifications?.dry_run ?? 0;
          const failed = res.notifications?.failed ?? 0;
          const skipped = res.notifications?.skipped ?? 0;
          const queued = res.notifications?.queued ?? 0;
          const successful = sent + dryRun + queued;

          setSosActive(true);
          if (queued > 0) {
            toast.error("SOS active", {
              description: `Emergency ID ${res.sos_id}. Contact notifications queued: ${queued}. Call 112 or 108 now if you are in danger.`,
            });
          } else if (successful > 0) {
            toast.error("SOS active", {
              description: `Emergency ID ${res.sos_id}. Submitted: ${sent}. Dry runs: ${dryRun}. Failed: ${failed}.`,
            });
          } else {
            toast.warning("SOS recorded, but contacts were not notified", {
              description: `Emergency ID ${res.sos_id}. Failed: ${failed}. Skipped: ${skipped}. Call 112 or 108 now if you are in danger.`,
            });
          }
        } catch {
          setSosActive(false);
          toast.error("SOS failed to send", {
            description:
              "Could not reach the RoadSoS backend. Call 112 or 108 immediately if this is an emergency.",
          });
        } finally {
          setCountdown(0);
        }
      }, 3000);
    },
    [coords, countdown],
  );

  const stopVoiceSOS = useCallback(() => {
    recognitionRef.current?.stop();
    setListeningForSOS(false);
  }, []);

  const startVoiceSOS = useCallback(() => {
    if (!speechSupported || listeningForSOS) return;
    const Recognition = getSpeechRecognitionConstructor();
    if (!Recognition) {
      setSpeechSupported(false);
      return;
    }

    const recognition = new Recognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-IN";
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ");

      if (isVoiceSOSPhrase(transcript)) {
        recognition.stop();
        setListeningForSOS(false);
        toast.error("Voice SOS detected", {
          description: "Starting emergency countdown from your voice command.",
        });
        triggerSOS("Voice SOS: help accident happened");
      }
    };
    recognition.onerror = (event) => {
      setListeningForSOS(false);
      toast.error("Voice SOS unavailable", {
        description:
          event.error === "not-allowed"
            ? "Microphone permission was denied."
            : "Speech recognition stopped unexpectedly.",
      });
    };
    recognition.onend = () => setListeningForSOS(false);

    recognitionRef.current = recognition;
    try {
      recognition.start();
      setListeningForSOS(true);
    } catch {
      setListeningForSOS(false);
    }
  }, [listeningForSOS, speechSupported, triggerSOS]);

  const cancelSOS = () => {
    recognitionRef.current?.abort();
    setListeningForSOS(false);
    if (sosTimerRef.current) {
      window.clearTimeout(sosTimerRef.current);
      sosTimerRef.current = null;
    }
    setCountdown(0);
    setSosActive(false);
    toast.success("SOS cancelled");
  };

  const topAlert = alerts[0];

  return (
    <div className="p-4 md:p-8 space-y-6 max-w-7xl mx-auto">
      {/* ──── Location Setup Prompt (first visit or when manually opened) ──── */}
      {showSetup && (
        <Card className="p-5 border-primary/40 bg-gradient-to-r from-primary/10 to-primary/5 relative">
          <button
            onClick={() => setShowSetup(false)}
            className="absolute top-3 right-3 text-muted-foreground hover:text-foreground transition"
          >
            <X className="h-4 w-4" />
          </button>
          <div className="flex items-start gap-3">
            <div className="h-10 w-10 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center shrink-0">
              <MapPin className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1">
              <div className="font-semibold text-sm">Set Your Location</div>
              <p className="text-xs text-muted-foreground mt-0.5 mb-3">
                Auto-detection may be inaccurate on desktop. Search your city for precise results.
              </p>
              <div className="flex items-center gap-2 max-w-sm">
                <div className="flex-1 flex items-center bg-background border border-border rounded-lg px-3 py-1.5">
                  <Search className="h-3.5 w-3.5 text-muted-foreground mr-2 shrink-0" />
                  <input
                    type="text"
                    placeholder="Enter your city (e.g. Madurai)"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                    className="bg-transparent border-0 outline-none text-sm w-full text-foreground placeholder:text-muted-foreground"
                    disabled={searching}
                    autoFocus
                  />
                </div>
                <Button
                  size="sm"
                  onClick={handleSearch}
                  disabled={searching || !searchQuery.trim()}
                >
                  {searching ? "..." : "Set"}
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* ──── Header ──── */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Road Safety Dashboard</h1>
          <div className="flex flex-wrap items-center gap-2 mt-1 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <MapPin className="h-3.5 w-3.5 text-primary" />
              {locationName ? (
                <span>
                  {locationName}{" "}
                  <span className="text-muted-foreground/60 text-xs">
                    ({coords ? `${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}` : "..."})
                  </span>
                </span>
              ) : coords ? (
                `${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}`
              ) : (
                "Locating…"
              )}
            </span>
            {hasSavedLocation() && (
              <Badge
                variant="secondary"
                className="bg-green-500/15 text-green-400 border-green-500/25 text-[10px] px-1.5 py-0"
              >
                ✓ Your Location
              </Badge>
            )}
            <button
              onClick={() => setShowSetup(true)}
              className="text-xs text-primary hover:underline font-medium transition cursor-pointer"
            >
              Change
            </button>
            {hasSavedLocation() && (
              <button
                onClick={handleReset}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-0.5 hover:underline transition cursor-pointer"
              >
                <RotateCcw className="h-2.5 w-2.5" /> Auto-detect
              </button>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {risk && <RiskBadge risk={risk} />}
          <Badge variant="outline" className="border-green-500 text-green-400">
            <span className="h-2 w-2 rounded-full bg-green-500 mr-2 animate-pulse" />
            Monitoring active
          </Badge>
        </div>
      </header>

      {/* ──── Top Alert Banner ──── */}
      {topAlert && (
        <Card className="p-4 border-primary/50 bg-primary/10 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-primary shrink-0 mt-0.5" />
          <div className="flex-1">
            <div className="font-semibold">
              {topAlert.type} — {formatDistance(topAlert.distance_km)} ahead
            </div>
            <div className="text-sm text-muted-foreground">{topAlert.message}</div>
          </div>
          <Badge className="bg-primary">{topAlert.severity}</Badge>
        </Card>
      )}

      {/* ──── Map + SOS ──── */}
      <div className="grid md:grid-cols-3 gap-4">
        <Card className="md:col-span-2 p-0 overflow-hidden h-72 relative border border-border">
          {coords ? (
            <>
              <iframe
                title="Live GPS Tracking Map"
                className="w-full h-full border-0"
                style={{
                  filter: "invert(90%) hue-rotate(180deg) brightness(90%) contrast(120%)",
                }}
                src={`https://maps.google.com/maps?q=${coords.lat},${coords.lng}&z=14&output=embed`}
                allowFullScreen
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />

              {/* Glassmorphic HUD overlay */}
              <div className="absolute bottom-3 left-3 bg-black/75 backdrop-blur-md border border-white/10 p-3 rounded-lg flex flex-col gap-1 pointer-events-none select-none max-w-[240px]">
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
                  </span>
                  <span className="text-xs font-semibold text-white tracking-wider uppercase">
                    {locationName ? `📍 ${locationName}` : "Live Tracking"}
                  </span>
                </div>
                <div className="text-[10px] text-zinc-400 font-mono">
                  LAT: {coords.lat.toFixed(5)}
                  <br />
                  LNG: {coords.lng.toFixed(5)}
                </div>
                <div className="text-[10px] text-primary font-medium mt-0.5">
                  Proactive Danger Radius: 3-6 km
                </div>
              </div>

              {/* Quick search on map top-right */}
              <div className="absolute top-3 right-3 flex items-center gap-1.5 bg-black/70 backdrop-blur-md border border-white/10 rounded-lg px-2 py-1">
                <Search className="h-3 w-3 text-zinc-400 shrink-0" />
                <input
                  type="text"
                  placeholder="Search location..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  className="bg-transparent border-0 outline-none text-[11px] w-28 text-white placeholder:text-zinc-500"
                  disabled={searching}
                />
                {searchQuery && (
                  <button
                    onClick={handleSearch}
                    disabled={searching}
                    className="text-[10px] text-primary font-semibold hover:text-primary/80 transition"
                  >
                    {searching ? "..." : "Go"}
                  </button>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(220,38,38,0.15),transparent_60%)]" />
              <div
                className="absolute inset-0 opacity-30"
                style={{
                  backgroundImage:
                    "linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px)",
                  backgroundSize: "40px 40px",
                }}
              />
              <div className="relative h-full flex items-center justify-center">
                <div className="text-center">
                  <div className="h-16 w-16 rounded-full bg-primary/20 border-2 border-primary flex items-center justify-center mx-auto mb-3 animate-pulse">
                    <Navigation className="h-6 w-6 text-primary animate-spin" />
                  </div>
                  <div className="text-sm text-muted-foreground">Locating current position…</div>
                </div>
              </div>
            </>
          )}
        </Card>

        <Card className="p-6 flex flex-col items-center justify-center text-center">
          {countdown > 0 ? (
            <>
              <div className="text-6xl font-bold text-primary mb-2">{countdown}</div>
              <div className="text-sm text-muted-foreground mb-4">Sending SOS…</div>
              <Button variant="outline" onClick={cancelSOS}>
                Cancel
              </Button>
            </>
          ) : sosActive ? (
            <>
              <Siren className="h-12 w-12 text-primary animate-pulse mb-3" />
              <div className="font-bold text-primary mb-1">SOS ACTIVE</div>
              <div className="text-xs text-muted-foreground mb-4">
                Emergency contacts and services notified
              </div>
              <Button variant="outline" onClick={cancelSOS}>
                Mark Safe
              </Button>
            </>
          ) : (
            <>
              <div className="flex items-center justify-center gap-3">
                <button
                  onClick={() => triggerSOS()}
                  className="h-32 w-32 rounded-full bg-primary text-primary-foreground font-bold text-2xl shadow-[0_0_60px_-10px_oklch(0.62_0.24_25)] hover:scale-105 active:scale-95 transition"
                >
                  SOS
                </button>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span>
                        <button
                          type="button"
                          onClick={listeningForSOS ? stopVoiceSOS : startVoiceSOS}
                          disabled={!speechSupported}
                          aria-label={
                            listeningForSOS
                              ? "Stop voice SOS listening"
                              : "Start voice SOS listening"
                          }
                          className={[
                            "h-12 w-12 rounded-full border flex items-center justify-center transition",
                            speechSupported
                              ? "border-border bg-background hover:border-primary/60 hover:text-primary"
                              : "border-border bg-muted text-muted-foreground opacity-60 cursor-not-allowed",
                            listeningForSOS
                              ? "border-red-500 bg-red-500/15 text-red-500 animate-pulse"
                              : "",
                          ].join(" ")}
                        >
                          <Mic className="h-5 w-5" />
                        </button>
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      {speechSupported
                        ? listeningForSOS
                          ? "Listening for SOS"
                          : "Say SOS or help accident happened"
                        : "Voice SOS is not supported in this browser"}
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <p className="text-xs text-muted-foreground mt-4">
                Tap to alert emergency services & contacts
              </p>
            </>
          )}
        </Card>
      </div>

      {/* ──── Quick Cards ──── */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <QuickCard
          to="/hospitals"
          icon={Hospital}
          label="Nearest Hospital"
          value={nearestHospitalDist}
        />
        <QuickCard to="/police" icon={Shield} label="Nearest Police" value={nearestPoliceDist} />
        <QuickCard to="/towing" icon={Truck} label="Nearest Towing" value={nearestTowingDist} />
        <QuickCard
          to="/alerts"
          icon={AlertTriangle}
          label="Active Alerts"
          value={`${alerts.length}`}
        />
        <QuickCard to="/contacts" icon={Phone} label="Emergency Contacts" value="Manage" />
      </div>

      {/* ──── Recent Alerts ──── */}
      <Card className="p-5">
        <div className="font-semibold mb-3">Recent danger zone alerts</div>
        <div className="divide-y divide-border">
          {alerts.map((a) => (
            <div key={a.id} className="py-3 flex items-center gap-3">
              <SeverityDot s={a.severity} />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">
                  {a.type} · {formatDistance(a.distance_km)}
                </div>
                <div className="text-xs text-muted-foreground truncate">{a.message}</div>
              </div>
              <Badge variant="outline" className="capitalize">
                {a.severity}
              </Badge>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function QuickCard({
  to,
  icon: Icon,
  label,
  value,
}: {
  to: string;
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <Link to={to}>
      <Card className="p-4 hover:border-primary/50 transition cursor-pointer">
        <Icon className="h-5 w-5 text-primary mb-2" />
        <div className="text-xs text-muted-foreground">{label}</div>
        <div className="font-semibold">{value}</div>
      </Card>
    </Link>
  );
}

function SeverityDot({ s }: { s: string }) {
  const map: Record<string, string> = {
    critical: "bg-red-500",
    high: "bg-orange-500",
    medium: "bg-yellow-500",
    low: "bg-green-500",
  };
  return <span className={`h-2.5 w-2.5 rounded-full ${map[s] ?? "bg-muted"}`} />;
}

function RiskBadge({ risk }: { risk: RiskAssessment }) {
  const level = risk.risk_level === "low" ? "Low" : risk.risk_level === "medium" ? "Medium" : "High";
  const className =
    risk.risk_level === "low"
      ? "border-green-500/60 bg-green-500/15 text-green-400"
      : risk.risk_level === "medium"
        ? "border-yellow-500/60 bg-yellow-500/15 text-yellow-300"
        : "border-red-500/60 bg-red-500/15 text-red-400";

  return (
    <Badge variant="outline" className={`${className} gap-1.5`}>
      <AlertTriangle className="h-3 w-3" />
      {level} Risk
    </Badge>
  );
}

function formatDistance(distance?: number | null) {
  return distance == null ? "nearby" : `${distance} km`;
}
