import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { MapPin, Phone, Shield } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, type PoliceStation } from "@/lib/api";
import { getLocation } from "@/lib/location";

export const Route = createFileRoute("/police")({ component: Police });

function Police() {
  const [list, setList] = useState<PoliceStation[]>([]);
  useEffect(() => {
    getLocation().then((coords) => {
      api.police(coords.lat, coords.lng).then(setList);
    });
  }, []);
  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-4">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Nearby Police Stations</h1>
        <p className="text-sm text-muted-foreground">Dial 100 for immediate response. Highway patrol included.</p>
      </div>
      <div className="grid md:grid-cols-2 gap-3">
        {list.map((p) => (
          <Card key={p.id} className="p-4 flex flex-col gap-3">
            <div className="flex items-start gap-3">
              <div className="h-10 w-10 rounded-lg bg-accent/20 text-accent flex items-center justify-center shrink-0">
                <Shield className="h-5 w-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold">{p.name}</div>
                <div className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                  <MapPin className="h-3 w-3" /> {p.address} · {formatDistance(p.distance_km)}
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              {p.phone ? (
                <Button asChild size="sm" className="flex-1">
                  <a href={`tel:${p.phone.replace(/\s/g, "")}`}><Phone className="h-3.5 w-3.5 mr-1" />Call {p.phone}</a>
                </Button>
              ) : (
                <Button size="sm" variant="secondary" className="flex-1 cursor-not-allowed opacity-50" disabled>
                  <Phone className="h-3.5 w-3.5 mr-1" />No Phone
                </Button>
              )}
              <Button asChild size="sm" variant="outline" className="flex-1">
                <a
                  target="_blank"
                  rel="noreferrer"
                  href={p.lat && p.lng ? `https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}` : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(p.name + " " + p.address)}`}
                >
                  Directions
                </a>
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

function formatDistance(distance?: number) {
  return distance == null ? "nearby" : `${distance} km`;
}
