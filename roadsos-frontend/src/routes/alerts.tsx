import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type RoadAlert } from "@/lib/api";

export const Route = createFileRoute("/alerts")({ component: Alerts });

function Alerts() {
  const [alerts, setAlerts] = useState<RoadAlert[]>([]);
  useEffect(() => { api.alerts().then(setAlerts); }, []);

  const sev: Record<string, string> = {
    critical: "bg-red-500/15 text-red-400 border-red-500/30",
    high: "bg-orange-500/15 text-orange-400 border-orange-500/30",
    medium: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
    low: "bg-green-500/15 text-green-400 border-green-500/30",
  };

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-4">
      <h1 className="text-3xl font-bold tracking-tight">Active Road Alerts</h1>
      <p className="text-sm text-muted-foreground">Real-time danger zones detected within your 3–6 km radius.</p>
      <div className="grid gap-3">
        {alerts.map((a) => (
          <Card key={a.id} className={`p-4 border ${sev[a.severity]}`}>
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 mt-0.5 shrink-0" />
              <div className="flex-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-semibold">{a.type}</div>
                  <Badge variant="outline" className="capitalize">{a.severity}</Badge>
                </div>
                <p className="text-sm mt-1">{a.message}</p>
                <div className="text-xs text-muted-foreground mt-2">
                  {a.distance_km} km ahead · {new Date(a.created_at).toLocaleTimeString()}
                </div>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}