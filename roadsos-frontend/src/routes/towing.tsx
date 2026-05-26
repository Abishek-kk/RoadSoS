import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Clock, MapPin, Phone, Star, Truck } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, type TowingService } from "@/lib/api";
import { getLocation, saveLocation } from "@/lib/location";

export const Route = createFileRoute("/towing")({ component: Towing });

function Towing() {
  const [list, setList] = useState<TowingService[]>([]);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function load() {
      const c = await getLocation();
      setCoords(c);
      loadTowing(c.lat, c.lng);
    }
    load();
  }, []);

  async function loadTowing(lat: number, lng: number) {
    setError(null);
    setLoading(true);
    try {
      setList(await api.towing(lat, lng));
    } catch {
      setList([]);
      setError("Could not load nearby towing services. Please check that the backend is running.");
    } finally {
      setLoading(false);
    }
  }

  function changeLocation() {
    const input = window.prompt("Enter lat,lng (comma separated)");
    if (!input) return;
    const parts = input.split(",").map((s) => s.trim());
    if (parts.length !== 2) return alert("Please enter latitude and longitude separated by a comma.");
    const lat = Number(parts[0]);
    const lng = Number(parts[1]);
    if (Number.isNaN(lat) || Number.isNaN(lng)) return alert("Invalid numbers");
    saveLocation(lat, lng);
    setCoords({ lat, lng });
    loadTowing(lat, lng);
  }

  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-4">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Nearby Towing Services</h1>
        <p className="text-sm text-muted-foreground">Sorted by GPS proximity with direct call and directions.</p>
      </div>
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          Using location: {coords ? `${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}` : "detecting..."}
        </div>
        <div>
          <button className="text-sm text-primary underline" onClick={changeLocation}>Change location</button>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        {error && <ServiceMessage message={error} />}
        {!error && loading && <ServiceMessage message="Loading nearby towing services..." />}
        {!error && !loading && list.length === 0 && coords && <ServiceMessage message="No towing services found near this location." />}
        {list.map((t) => (
          <Card key={t.id} className="p-4 flex flex-col gap-3">
            <div className="flex items-start gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/15 text-primary flex items-center justify-center shrink-0">
                <Truck className="h-5 w-5" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold">{t.name}</div>
                <div className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                  <MapPin className="h-3 w-3 shrink-0" /> {t.address} - {formatDistance(t.distance_km)}
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {t.type && <Badge variant="secondary">{t.type}</Badge>}
                  {t.open_24x7 && (
                    <Badge variant="outline" className="gap-1">
                      <Clock className="h-3 w-3" /> 24x7
                    </Badge>
                  )}
                  {t.rating != null && (
                    <Badge variant="outline" className="gap-1">
                      <Star className="h-3 w-3" /> {t.rating}
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              {t.phone ? (
                <Button asChild size="sm" className="flex-1">
                  <a href={`tel:${t.phone.replace(/\s/g, "")}`}>
                    <Phone className="h-3.5 w-3.5 mr-1" />Call
                  </a>
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
                  href={t.lat && t.lng ? `https://www.google.com/maps/dir/?api=1&destination=${t.lat},${t.lng}` : `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(t.name + " " + t.address)}`}
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

function formatDistance(distance?: number | null) {
  return distance == null ? "nearby" : `${distance} km`;
}

function ServiceMessage({ message }: { message: string }) {
  return (
    <Card className="p-4 md:col-span-2 text-sm text-muted-foreground">
      {message}
    </Card>
  );
}
