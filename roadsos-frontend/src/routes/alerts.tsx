import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AlertTriangle, Bell, MapPin, Smartphone } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type DangerZoneAlert, type RecentDangerZoneAlert } from "@/lib/api";
import { getLocationDetails } from "@/lib/location";

export const Route = createFileRoute("/alerts")({ component: Alerts });

type Coords = { lat: number; lng: number };
const DANGER_ALERT_RADIUS_KM = 8;

const sev: Record<string, string> = {
  critical: "bg-red-500/15 text-red-400 border-red-500/30",
  "very high": "bg-red-500/15 text-red-400 border-red-500/30",
  high: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  medium: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  low: "bg-green-500/15 text-green-400 border-green-500/30",
};

function Alerts() {
  const [coords, setCoords] = useState<Coords | null>(null);
  const [liveAlerts, setLiveAlerts] = useState<DangerZoneAlert[]>([]);
  const [recentAlerts, setRecentAlerts] = useState<RecentDangerZoneAlert[]>([]);
  const [userId, setUserId] = useState<number | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const refreshLocation = async () => {
      const location = await getLocationDetails();
      if (cancelled) return;
      setCoords({ lat: location.lat, lng: location.lng });
    };

    void refreshLocation();
    const pollingId = window.setInterval(refreshLocation, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(pollingId);
    };
  }, []);

  useEffect(() => {
    if (!coords) return;
    let cancelled = false;

    const refreshRecent = (resolvedUserId: number) => {
      api.recentDangerZoneAlerts(resolvedUserId).then((response) => {
        if (!cancelled) setRecentAlerts(response.alerts);
      });
    };

    const refreshDangerAlerts = async () => {
      try {
        const [locationResponse, dangerRoadsResponse] = await Promise.all([
          api.postLocation(coords.lat, coords.lng),
          api.nearbyDangerRoads(coords.lat, coords.lng, DANGER_ALERT_RADIUS_KM),
        ]);
        if (cancelled) return;

        setLiveAlerts(dangerRoadsResponse.results ?? []);
        setLastCheckedAt(new Date().toISOString());

        const resolvedUserId = getResponseUserId(locationResponse.location);
        if (resolvedUserId) {
          setUserId(resolvedUserId);
          refreshRecent(resolvedUserId);
        }
      } catch {
        if (!cancelled) setLiveAlerts([]);
      }
    };

    void refreshDangerAlerts();

    return () => {
      cancelled = true;
    };
  }, [coords]);

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">Road Alerts</h1>
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <MapPin className="h-4 w-4 text-primary" />
          {coords ? `${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}` : "Locating..."}
          {lastCheckedAt && <span>Last checked {formatRelativeTime(lastCheckedAt)}</span>}
        </div>
      </header>

      <section className="space-y-3">
        <SectionHeader
          title="Live Dangerous Road Alerts"
          description={`Known dangerous roads within ${DANGER_ALERT_RADIUS_KM} km of your selected location.`}
        />
        <div className="grid gap-3">
          {liveAlerts.length ? (
            liveAlerts.map((alert) => (
              <LiveDangerZoneCard key={`${alert.zone_id}-${alert.distance_km}`} alert={alert} />
            ))
          ) : (
            <EmptyState
              message={
                coords
                  ? `No dangerous roads found within ${DANGER_ALERT_RADIUS_KM} km of your selected location.`
                  : "Waiting for live location..."
              }
            />
          )}
        </div>
      </section>

      <section className="space-y-3">
        <SectionHeader
          title="Recent Danger Zone Alerts"
          description="Persisted proximity history from live danger-zone checks."
        />
        <Card className="p-0 overflow-hidden">
          {recentAlerts.length ? (
            <div className="divide-y divide-border">
              {recentAlerts.map((alert) => (
                <RecentDangerZoneRow key={alert.id} alert={alert} />
              ))}
            </div>
          ) : (
            <EmptyState
              message={
                userId
                  ? "No persisted danger-zone alerts yet."
                  : "Waiting for the first live check..."
              }
            />
          )}
        </Card>
      </section>
    </div>
  );
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div>
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  );
}

function LiveDangerZoneCard({ alert }: { alert: DangerZoneAlert }) {
  const className = riskClass(alert.risk_level);
  return (
    <Card className={`p-4 border ${className}`}>
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-semibold">{alert.road_name || alert.zone_name}</div>
              <div className="text-xs text-muted-foreground mt-0.5">
                {alert.inside_zone ? "Inside zone" : "Nearby"} / {formatDistance(alert.distance_km)}
                {alert.district ? ` / ${alert.district}` : ""}
              </div>
            </div>
            <Badge variant="outline" className="capitalize shrink-0">
              {alert.risk_level}
            </Badge>
          </div>
          <p className="text-sm mt-2">{alert.message}</p>
          {alert.danger_type?.length ? (
            <p className="text-xs text-muted-foreground mt-2">
              Risk factors: {alert.danger_type.slice(0, 3).join(", ")}
            </p>
          ) : null}
          {alert.advisory && <p className="text-xs text-muted-foreground mt-2">{alert.advisory}</p>}
        </div>
      </div>
    </Card>
  );
}

function RecentDangerZoneRow({ alert }: { alert: RecentDangerZoneAlert }) {
  return (
    <div className="p-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium truncate">{alert.zone_name}</span>
          <Badge variant="outline" className={`capitalize ${riskClass(alert.risk_level)}`}>
            {alert.risk_level}
          </Badge>
        </div>
        <div className="text-xs text-muted-foreground mt-1">
          {formatDistance(alert.distance_km)} / {formatRelativeTime(alert.created_at)}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {alert.notified_push && (
          <span className="inline-flex items-center gap-1">
            <Bell className="h-3.5 w-3.5" />
            push sent
          </span>
        )}
        {alert.notified_sms && (
          <span className="inline-flex items-center gap-1">
            <Smartphone className="h-3.5 w-3.5" />
            sms sent
          </span>
        )}
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <Card className="p-4 border-dashed">
      <p className="text-sm text-muted-foreground">{message}</p>
    </Card>
  );
}

function riskClass(level?: string) {
  return (
    sev[String(level ?? "").toLowerCase()] ?? "bg-muted/30 text-muted-foreground border-border"
  );
}

function formatDistance(distance?: number | null) {
  if (distance == null) return "nearby";
  return `${Number(distance).toFixed(distance < 10 ? 1 : 0)} km`;
}

function formatRelativeTime(value: string) {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "just now";
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function getResponseUserId(location: unknown) {
  if (!location || typeof location !== "object") return null;
  const userId = (location as { user_id?: unknown }).user_id;
  return typeof userId === "number" ? userId : null;
}
