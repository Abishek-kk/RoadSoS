import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { MapPin, Phone, Shield } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api, type PoliceStation } from "@/lib/api";
import { getLocation, saveLocation } from "@/lib/location";

export const Route = createFileRoute("/police")({ component: Police });

function Police() {
  const [list, setList] = useState<PoliceStation[]>([]);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function load() {
      const c = await getLocation();
      setCoords(c);
      loadPolice(c.lat, c.lng);
    }
    load();
  }, []);

  async function loadPolice(lat: number, lng: number) {
    setError(null);
    setLoading(true);
    try {
      setList(await api.police(lat, lng));
    } catch {
      setList([]);
      setError("Could not load nearby police stations. Please check that the backend is running.");
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
    loadPolice(lat, lng);
  }
  return (
    <div className="p-4 md:p-8 max-w-5xl mx-auto space-y-4">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Nearby Police Stations</h1>
        <p className="text-sm text-muted-foreground">Dial 100 for immediate response. Highway patrol included.</p>
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
        {!error && loading && <ServiceMessage message="Loading nearby police stations..." />}
        {!error && !loading && list.length === 0 && coords && <ServiceMessage message="No police stations found near this location." />}
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

function ServiceMessage({ message }: { message: string }) {
  return (
    <Card className="p-4 md:col-span-2 text-sm text-muted-foreground">
      {message}
    </Card>
  );
}
