import { getSavedLocation, getSavedLocationName } from "@/lib/location";

const BASE = (import.meta as any).env?.VITE_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit, fallback?: T, timeoutMs = 30000): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...init,
    });
    if (!res.ok) throw new Error(`${res.status}`);
    return (await res.json()) as T;
  } catch (e) {
    if (fallback !== undefined) return fallback;
    throw e;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export function apiErrorMessage(error: unknown) {
  if (error instanceof DOMException && error.name === "AbortError") {
    return "The RoadSoS backend is taking too long to answer. Please try again.";
  }
  if (error instanceof TypeError) {
    return "I could not reach the RoadSoS backend. Please make sure the backend is running on port 8000.";
  }
  return "The RoadSoS backend had trouble answering that request. Please try again.";
}

export type Hospital = {
  id: string;
  name: string;
  lat: number | null;
  lng: number | null;
  phone: string;
  address: string;
  distance_km?: number | null;
  eta?: string | null;
  eta_minutes?: number | null;
  route_waypoints?: RoutePoint[];
};

export type PoliceStation = {
  id: string;
  name: string;
  lat: number | null;
  lng: number | null;
  phone: string;
  address: string;
  distance_km?: number | null;
  eta?: string | null;
  eta_minutes?: number | null;
  officer?: string | null;
  route_waypoints?: RoutePoint[];
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
  lat: number | null;
  lng: number | null;
  rating?: number | null;
  distance_km?: number | null;
  eta?: string | null;
  eta_minutes?: number | null;
  availability?: string | null;
  route_waypoints?: RoutePoint[];
};

export type Ambulance = {
  id: string;
  ambulance_id: string;
  name: string;
  lat: number | null;
  lng: number | null;
  phone: string;
  status: "available" | "busy";
  distance_km?: number | null;
  eta?: string | null;
  eta_minutes?: number | null;
  updated_at?: string | null;
  route_waypoints?: RoutePoint[];
};

export type RoutePoint = { lat: number; lng: number };

export type ServiceRoute = {
  provider: string;
  reachable: boolean;
  polyline?: RoutePoint[];
  route_points?: RoutePoint[];
  distance_km?: number;
  total_distance_km?: number;
  eta?: string;
  eta_minutes?: number;
  travel_time_minutes?: number;
};

export type NearestResponse<T> = {
  ok: boolean;
  results: T[];
};

export type EmergencyContext = {
  user_location?: RoutePoint;
  nearest_ambulance?: Ambulance | null;
  nearest_hospital?: Hospital | null;
  nearest_police?: PoliceStation | null;
  nearest_tow?: TowingService | null;
  route?: ServiceRoute | null;
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

export type RiskAssessment = {
  score: number;
  risk_level: "low" | "medium" | "high" | "critical";
  summary: string;
  safety_tips: string[];
  nearest_danger_zones: unknown[];
  active_alerts: unknown[];
  factors: unknown[];
};

export type DangerZoneAlert = {
  zone_id: string;
  zone_name: string;
  status: string;
  risk_level: string;
  risk_score: number;
  distance_km: number;
  inside_zone: boolean;
  message: string;
  advisory?: string;
  road_name?: string;
  city?: string | null;
  district?: string | null;
  danger_type?: string[];
  lat?: number;
  lng?: number;
};

export type NearbyDangerRoadsResponse = {
  ok: boolean;
  radius_km: number;
  results: DangerZoneAlert[];
};

export type RecentDangerZoneAlert = {
  id: number;
  zone_id: string;
  zone_name: string;
  risk_level: string;
  risk_score: number | null;
  distance_km: number | null;
  inside_zone: boolean;
  message: string | null;
  advisory: string | null;
  lat: number;
  lng: number;
  notified_push: boolean;
  notified_sms: boolean;
  created_at: string;
};

export type PostLocationResponse = {
  ok: boolean;
  alerts?: DangerZoneAlert[];
  risk?: unknown;
  location?: { user_id?: number | null } | unknown;
};

export type Contact = {
  id: string;
  name: string;
  phone: string;
  relation: string;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };
export type ChatResponse = {
  reply: string;
  intent?: string;
  used_llm?: boolean;
  llm_provider?: string;
  response_source?: string | null;
  suggestions?: string[];
};
export type ChatStreamHandlers = {
  onToken?: (token: string) => void;
};

type ChatStreamEvent =
  | { type: "token"; content?: string }
  | { type: "done"; result?: ChatResponse }
  | { type: "error"; message?: string };

function locationQuery(lat?: number, lng?: number) {
  const params = new URLSearchParams();
  if (lat !== undefined) params.set("lat", String(lat));
  if (lng !== undefined) params.set("lng", String(lng));
  const query = params.toString();
  return query ? `?${query}` : "";
}

const MOCK_ALERTS: RoadAlert[] = [
  { id: "a1", type: "Blackspot", severity: "critical", message: "Accident-prone curve 2.4 km ahead. Reduce speed.", lat: 13.09, lng: 80.27, distance_km: 2.4, created_at: new Date().toISOString() },
  { id: "a2", type: "Construction", severity: "high", message: "Road work in progress on NH-48. Lane shift active.", lat: 13.07, lng: 80.25, distance_km: 5.6, created_at: new Date().toISOString() },
  { id: "a3", type: "Weather", severity: "medium", message: "Heavy rain detected in your travel corridor.", lat: 13.05, lng: 80.22, distance_km: 8.1, created_at: new Date().toISOString() },
  { id: "a4", type: "Traffic", severity: "low", message: "Slow-moving traffic 12 km ahead.", lat: 13.02, lng: 80.21, distance_km: 12, created_at: new Date().toISOString() },
];

export const api = {
  postLocation: (lat: number, lng: number) =>
    request<PostLocationResponse>("/api/location", { method: "POST", body: JSON.stringify({ lat, lng }) }, { ok: true, alerts: [] }),

  triggerSOS: (payload: { lat: number; lng: number; user?: string; note?: string }) =>
    request<{
      ok: boolean;
      sos_id: string;
      status: string;
      maps_url?: string;
      message?: string;
      emergency_numbers?: string[];
      notifications?: { contacts: number; queued?: number; sent: number; dry_run: number; failed: number; skipped?: number };
      emergency_context?: EmergencyContext;
    }>(
      "/api/sos",
      { method: "POST", body: JSON.stringify(payload) }
    ),

  hospitals: (lat?: number, lng?: number) =>
    request<Hospital[]>(`/api/hospitals${locationQuery(lat, lng)}`),

  police: (lat?: number, lng?: number) =>
    request<PoliceStation[]>(`/api/police${locationQuery(lat, lng)}`),

  towing: (lat?: number, lng?: number) =>
    request<TowingService[]>(`/api/towing${locationQuery(lat, lng)}`),

  ambulances: (lat: number, lng: number, limit = 3) =>
    request<Ambulance[]>(`/api/ambulances${ambulanceQuery(lat, lng, limit)}`),

  nearestHospital: async (lat: number, lng: number, limit = 3) => ({
    ok: true,
    results: (await request<Hospital[]>(`/api/hospitals${locationQuery(lat, lng)}`)).slice(0, limit),
  }),

  nearestPolice: async (lat: number, lng: number, limit = 3) => ({
    ok: true,
    results: (await request<PoliceStation[]>(`/api/police${locationQuery(lat, lng)}`)).slice(0, limit),
  }),

  nearestTow: async (lat: number, lng: number, limit = 3) => ({
    ok: true,
    results: (await request<TowingService[]>(`/api/towing${locationQuery(lat, lng)}`)).slice(0, limit),
  }),

  nearestAmbulances: async (lat: number, lng: number, limit = 3) => ({
    ok: true,
    results: await request<Ambulance[]>(`/api/ambulances${ambulanceQuery(lat, lng, limit)}`),
  }),

  locationRoute: (lat: number, lng: number, service = "hospital") =>
    request<{ ok: boolean; service: string; destination?: Hospital | PoliceStation | TowingService | null; route?: ServiceRoute | null }>(
      `/api/location/route${routeQuery(lat, lng, service)}`
    ),

  alerts: (lat?: number, lng?: number) =>
    request<RoadAlert[]>(`/api/alerts${locationQuery(lat, lng)}`, undefined, MOCK_ALERTS),

  nearbyDangerRoads: (lat: number, lng: number, radiusKm = 8, limit = 50) =>
    request<NearbyDangerRoadsResponse>(
      `/api/location/danger-zones${dangerRoadQuery(lat, lng, radiusKm, limit)}`,
      undefined,
      { ok: true, radius_km: radiusKm, results: [] },
    ),

  recentDangerZoneAlerts: (userId: number, limit = 20) =>
    request<{ ok: boolean; alerts: RecentDangerZoneAlert[] }>(
      `/api/alerts/recent?user_id=${userId}&limit=${limit}`,
      undefined,
      { ok: true, alerts: [] },
    ),

  risk: (lat: number, lng: number) =>
    request<RiskAssessment>(`/api/risk${locationQuery(lat, lng)}`),

  contacts: () =>
    request<Contact[]>("/api/contacts", undefined, [
      { id: "1", name: "Mom", phone: "+919843947069", relation: "Family" },
      { id: "2", name: "Dad", phone: "+917305647064", relation: "Family" },
      { id: "3", name: "Friend 1", phone: "+919915625185", relation: "Friend" },
      { id: "4", name: "Friend 2", phone: "+916284170998", relation: "Friend" },
    ]),

  chat: (messages: ChatMessage[], coords?: { lat: number; lng: number } | null, locationName?: string | null) =>
    request<ChatResponse>(
      "/api/chat",
      {
        method: "POST",
        body: JSON.stringify(chatPayload(messages, coords, locationName)),
      },
      undefined,
      120000
    ),

  chatStream: (
    messages: ChatMessage[],
    coords?: { lat: number; lng: number } | null,
    locationName?: string | null,
    handlers: ChatStreamHandlers = {},
  ) => streamChat(messages, coords, locationName, handlers),

  addContact: (c: Omit<Contact, "id">) =>
    request<Contact>("/api/contacts", { method: "POST", body: JSON.stringify(c) }, { id: "c-" + Date.now(), ...c }),
};

function routeQuery(lat: number, lng: number, service: string) {
  const params = new URLSearchParams({ lat: String(lat), lng: String(lng), service });
  return `?${params.toString()}`;
}

function ambulanceQuery(lat: number, lng: number, limit: number) {
  const params = new URLSearchParams({ lat: String(lat), lng: String(lng), limit: String(limit) });
  return `?${params.toString()}`;
}

function dangerRoadQuery(lat: number, lng: number, radiusKm: number, limit: number) {
  const params = new URLSearchParams({
    lat: String(lat),
    lng: String(lng),
    radius_km: String(radiusKm),
    limit: String(limit),
  });
  return `?${params.toString()}`;
}

function chatPayload(messages: ChatMessage[], coords?: { lat: number; lng: number } | null, locationName?: string | null) {
  const resolvedCoords = coords ?? getSavedLocation();
  const resolvedLocationName = locationName ?? getSavedLocationName();
  return {
    messages,
    ...(resolvedCoords ?? {}),
    ...locationPartsFromLabel(resolvedLocationName),
    location_name: resolvedLocationName ?? undefined,
    current_datetime: new Date().toString(),
  };
}

function locationPartsFromLabel(locationName?: string | null) {
  const parts = (locationName ?? "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

  if (!parts.length) return {};
  return {
    city: parts[0],
    state: parts[1],
    country: parts[2],
  };
}

async function streamChat(
  messages: ChatMessage[],
  coords?: { lat: number; lng: number } | null,
  locationName?: string | null,
  handlers: ChatStreamHandlers = {},
): Promise<ChatResponse> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 120000);

  try {
    const res = await fetch(`${BASE}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(chatPayload(messages, coords, locationName)),
      signal: controller.signal,
    });

    if (!res.ok || !res.body) throw new Error(`${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalResponse: ChatResponse | null = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        finalResponse = handleChatStreamLine(line, handlers, finalResponse);
      }
    }

    buffer += decoder.decode();
    if (buffer.trim()) {
      finalResponse = handleChatStreamLine(buffer, handlers, finalResponse);
    }

    if (!finalResponse) throw new Error("Stream ended without a final response.");
    return finalResponse;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function handleChatStreamLine(
  line: string,
  handlers: ChatStreamHandlers,
  current: ChatResponse | null,
): ChatResponse | null {
  const trimmed = line.trim();
  if (!trimmed) return current;

  const event = JSON.parse(trimmed) as ChatStreamEvent;
  if (event.type === "token") {
    if (event.content) handlers.onToken?.(event.content);
    return current;
  }
  if (event.type === "done") {
    if (!event.result) throw new Error("Stream ended without a result.");
    return event.result;
  }
  if (event.type === "error") {
    throw new Error(event.message || "The RoadSoS backend had trouble streaming that response.");
  }
  return current;
}
