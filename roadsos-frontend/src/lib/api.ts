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
};

export type PostLocationResponse = {
  ok: boolean;
  alerts?: DangerZoneAlert[];
  risk?: unknown;
  location?: unknown;
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
  suggestions?: string[];
};

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

  alerts: (lat?: number, lng?: number) =>
    request<RoadAlert[]>(`/api/alerts${locationQuery(lat, lng)}`, undefined, MOCK_ALERTS),

  risk: (lat: number, lng: number) =>
    request<RiskAssessment>(`/api/risk${locationQuery(lat, lng)}`),

  contacts: () =>
    request<Contact[]>("/api/contacts", undefined, [
      { id: "1", name: "Mom", phone: "+919843947069", relation: "Family" },
      { id: "2", name: "Dad", phone: "+917305647064", relation: "Family" },
      { id: "3", name: "Friend 1", phone: "+919915625185", relation: "Friend" },
      { id: "4", name: "Friend 2", phone: "+916284170998", relation: "Friend" },
    ]),

  chat: (messages: ChatMessage[], coords?: { lat: number; lng: number } | null) =>
    request<ChatResponse>(
      "/api/chat",
      { method: "POST", body: JSON.stringify({ messages, ...coords }) },
      undefined,
      120000
    ),

  addContact: (c: Omit<Contact, "id">) =>
    request<Contact>("/api/contacts", { method: "POST", body: JSON.stringify(c) }, { id: "c-" + Date.now(), ...c }),
};
