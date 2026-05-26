const BASE = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit, fallback?: T): Promise<T> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return (await res.json()) as T;
  } catch (e) {
    if (fallback !== undefined) return fallback;
    throw e;
  }
}

export type Hospital = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  phone: string;
  address: string;
  distance_km?: number | null;
};

export type PoliceStation = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  phone: string;
  address: string;
  distance_km?: number;
};

export type TowingService = {
  id: string;
  name: string;
  district?: string;
  state?: string;
  address: string;
  phone: string;
  type?: string;
  open_24x7?: boolean;
  lat: number;
  lng: number;
  rating?: number | null;
  distance_km?: number | null;
};

export type RoadAlert = {
  id: string;
  type: string;
  severity: "low" | "medium" | "high" | "critical";
  message: string;
  lat: number;
  lng: number;
  distance_km?: number;
  created_at: string;
};

export type Contact = {
  id: string;
  name: string;
  phone: string;
  relation: string;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };

function locationQuery(lat?: number, lng?: number) {
  const params = new URLSearchParams();
  if (lat !== undefined) params.set("lat", String(lat));
  if (lng !== undefined) params.set("lng", String(lng));
  const query = params.toString();
  return query ? `?${query}` : "";
}

const MOCK_HOSPITALS: Hospital[] = [
  { id: "h1", name: "Apollo Emergency Hospital", lat: 13.0827, lng: 80.2707, phone: "+91 044 2829 0200", address: "Greams Lane, Chennai", distance_km: 2.4 },
  { id: "h2", name: "Fortis Trauma Center", lat: 13.0067, lng: 80.2206, phone: "+91 044 4289 2222", address: "Vadapalani, Chennai", distance_km: 5.1 },
  { id: "h3", name: "MIOT International", lat: 13.0136, lng: 80.1908, phone: "+91 044 4200 2288", address: "Manapakkam, Chennai", distance_km: 7.8 },
  { id: "h4", name: "Government General Hospital", lat: 13.0805, lng: 80.2785, phone: "+91 044 2530 5000", address: "Park Town, Chennai", distance_km: 3.2 },
];

const MOCK_POLICE: PoliceStation[] = [
  { id: "p1", name: "Anna Nagar Police Station", lat: 13.0850, lng: 80.2101, phone: "100", address: "Anna Nagar, Chennai", distance_km: 1.8 },
  { id: "p2", name: "T. Nagar Police Station", lat: 13.0418, lng: 80.2341, phone: "100", address: "T. Nagar, Chennai", distance_km: 3.9 },
  { id: "p3", name: "Highway Patrol Unit 14", lat: 13.0598, lng: 80.2497, phone: "103", address: "NH-48 Junction", distance_km: 6.2 },
];

const MOCK_TOWING: TowingService[] = [
  { id: "tw1", name: "Roadside Towing Support", lat: 13.0827, lng: 80.2707, phone: "112", address: "Chennai", type: "Car/Bike Towing", open_24x7: true, distance_km: 2.7 },
  { id: "tw2", name: "Highway Recovery Service", lat: 13.0598, lng: 80.2497, phone: "112", address: "NH Junction", type: "Car/Truck Towing", open_24x7: true, distance_km: 5.4 },
];

const MOCK_ALERTS: RoadAlert[] = [
  { id: "a1", type: "Blackspot", severity: "critical", message: "Accident-prone curve 2.4 km ahead. Reduce speed.", lat: 13.09, lng: 80.27, distance_km: 2.4, created_at: new Date().toISOString() },
  { id: "a2", type: "Construction", severity: "high", message: "Road work in progress on NH-48. Lane shift active.", lat: 13.07, lng: 80.25, distance_km: 5.6, created_at: new Date().toISOString() },
  { id: "a3", type: "Weather", severity: "medium", message: "Heavy rain detected in your travel corridor.", lat: 13.05, lng: 80.22, distance_km: 8.1, created_at: new Date().toISOString() },
  { id: "a4", type: "Traffic", severity: "low", message: "Slow-moving traffic 12 km ahead.", lat: 13.02, lng: 80.21, distance_km: 12, created_at: new Date().toISOString() },
];

export const api = {
  postLocation: (lat: number, lng: number) =>
    request<{ ok: boolean }>("/api/location", { method: "POST", body: JSON.stringify({ lat, lng }) }, { ok: true }),

  triggerSOS: (payload: { lat: number; lng: number; user?: string; note?: string }) =>
    request<{
      ok: boolean;
      sos_id: string;
      status: string;
      maps_url?: string;
      message?: string;
      emergency_numbers?: string[];
      notifications?: { contacts: number; queued?: number; sent: number; dry_run: number; failed: number; skipped?: number };
    }>(
      "/api/sos",
      { method: "POST", body: JSON.stringify(payload) }
    ),

  hospitals: (lat?: number, lng?: number) =>
    request<Hospital[]>(`/api/hospitals${locationQuery(lat, lng)}`, undefined, MOCK_HOSPITALS),

  police: (lat?: number, lng?: number) =>
    request<PoliceStation[]>(`/api/police${locationQuery(lat, lng)}`, undefined, MOCK_POLICE),

  towing: (lat?: number, lng?: number) =>
    request<TowingService[]>(`/api/towing${locationQuery(lat, lng)}`, undefined, MOCK_TOWING),

  alerts: (lat?: number, lng?: number) =>
    request<RoadAlert[]>(`/api/alerts${locationQuery(lat, lng)}`, undefined, MOCK_ALERTS),

  contacts: () =>
    request<Contact[]>("/api/contacts", undefined, [
      { id: "1", name: "Mom", phone: "+919843947069", relation: "Family" },
      { id: "2", name: "Dad", phone: "+917305647064", relation: "Family" },
      { id: "3", name: "Friend 1", phone: "+919915625185", relation: "Friend" },
      { id: "4", name: "Friend 2", phone: "+916284170998", relation: "Friend" },
    ]),

  chat: (messages: ChatMessage[], coords?: { lat: number; lng: number } | null) =>
    request<{ reply: string }>(
      "/api/chat",
      { method: "POST", body: JSON.stringify({ messages, ...coords }) }
    ),

  addContact: (c: Omit<Contact, "id">) =>
    request<Contact>("/api/contacts", { method: "POST", body: JSON.stringify(c) }, { id: "c-" + Date.now(), ...c }),
};
