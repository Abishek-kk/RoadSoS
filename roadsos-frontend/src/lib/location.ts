// Location service priority:
//   1. Manual saved location override, until explicitly reset
//   2. Fresh auto-detected location cache (30 minutes)
//   3. Browser Geolocation API (high accuracy, then low accuracy retry)
//   4. IP-based geolocation (ipapi.co)
//   5. Hardcoded fallback (Madurai - 9.9252, 78.1198)

const STORAGE_KEY = "roadsos_user_location";
const SAVED_LOCATION_MAX_AGE_MS = 30 * 60 * 1000;
const BROWSER_GEOLOCATION_TIMEOUT_MS = 15000;

export type Coordinates = { lat: number; lng: number };
export type BrowserGeolocationStatus = "success" | "denied" | "timeout" | "unavailable" | "error";
export type LocationSource = "saved" | "browser" | "ip" | "fallback";
export type LocationStatus = LocationSource | "denied" | "timeout" | "unavailable" | "error";

export type LocationResult = Coordinates & {
  source: LocationSource;
  status: LocationStatus;
  browserStatus?: BrowserGeolocationStatus;
  label?: string;
};

type SavedLocationSource = "manual" | "browser" | "ip" | "fallback";
type SavedLocation = Coordinates & {
  timestamp: number;
  source?: SavedLocationSource;
  label?: string;
};
type GetLocationOptions = { forceRefresh?: boolean; browserOnly?: boolean };

type BrowserAttemptResult =
  | { coords: Coordinates; status: "success" }
  | { coords: null; status: Exclude<BrowserGeolocationStatus, "success"> };

const ADDRESS_PRIORITY = [
  "suburb",
  "village",
  "hamlet",
  "neighbourhood",
  "town",
  "city_district",
  "city",
  "county",
  "state",
] as const;

export async function getLocation(options: GetLocationOptions = {}): Promise<Coordinates> {
  const result = await getLocationDetails(options);
  return { lat: result.lat, lng: result.lng };
}

export async function getLocationDetails(
  options: GetLocationOptions = {},
): Promise<LocationResult> {
  const saved = readSavedLocation();
  if (saved?.source === "manual") {
    return { lat: saved.lat, lng: saved.lng, source: "saved", status: "saved", label: saved.label };
  }

  if (!options.forceRefresh && !options.browserOnly) {
    if (saved) {
      return { lat: saved.lat, lng: saved.lng, source: "saved", status: "saved", label: saved.label };
    }
  }

  const browserResult = await tryBrowserGeolocation();
  if (browserResult.coords) {
    saveLocation(browserResult.coords.lat, browserResult.coords.lng, "browser");
    return {
      ...browserResult.coords,
      source: "browser",
      status: "browser",
      browserStatus: browserResult.status,
    };
  }

  if (options.browserOnly) {
    throw new Error(`Browser geolocation ${browserResult.status}`);
  }

  const ipCoords = await tryIPGeolocation();
  if (ipCoords) {
    return {
      ...ipCoords,
      source: "ip",
      status: browserResult.status,
      browserStatus: browserResult.status,
    };
  }

  return {
    lat: 9.9252,
    lng: 78.1198,
    source: "fallback",
    status: browserResult.status,
    browserStatus: browserResult.status,
  };
}

export async function reverseGeocode(lat: number, lng: number): Promise<string | null> {
  try {
    const params = new URLSearchParams({
      format: "json",
      lat: String(lat),
      lon: String(lng),
      zoom: "18",
    });
    const res = await fetch(`https://nominatim.openstreetmap.org/reverse?${params.toString()}`);
    if (!res.ok) return null;
    const data = await res.json();
    return placeLabelFromAddress(data.address);
  } catch {
    return null;
  }
}

function placeLabelFromAddress(address: unknown): string | null {
  if (!address || typeof address !== "object") return null;

  const values = address as Record<string, unknown>;
  const primary = firstAddressValue(values, ADDRESS_PRIORITY);
  if (!primary) return null;

  const state = cleanAddressValue(values.state);
  if (state && state.toLowerCase() !== primary.toLowerCase()) {
    return `${primary}, ${state}`;
  }
  return primary;
}

function firstAddressValue(
  values: Record<string, unknown>,
  keys: readonly string[],
): string | null {
  for (const key of keys) {
    const value = cleanAddressValue(values[key]);
    if (value) return value;
  }
  return null;
}

function cleanAddressValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

async function tryBrowserGeolocation(): Promise<BrowserAttemptResult> {
  if (typeof window === "undefined" || typeof navigator === "undefined" || !navigator.geolocation) {
    return { coords: null, status: "unavailable" };
  }

  const firstAttempt = await requestBrowserPosition({
    enableHighAccuracy: true,
    timeout: BROWSER_GEOLOCATION_TIMEOUT_MS,
    maximumAge: 0,
  });
  if (firstAttempt.coords || firstAttempt.status === "denied") return firstAttempt;

  return requestBrowserPosition({
    enableHighAccuracy: false,
    timeout: BROWSER_GEOLOCATION_TIMEOUT_MS,
    maximumAge: 0,
  });
}

function requestBrowserPosition(options: PositionOptions): Promise<BrowserAttemptResult> {
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) =>
        resolve({
          coords: { lat: position.coords.latitude, lng: position.coords.longitude },
          status: "success",
        }),
      (error) => resolve({ coords: null, status: geolocationErrorStatus(error) }),
      options,
    );
  });
}

function geolocationErrorStatus(
  error: GeolocationPositionError,
): Exclude<BrowserGeolocationStatus, "success"> {
  switch (error.code) {
    case 1:
      return "denied";
    case 2:
      return "unavailable";
    case 3:
      return "timeout";
    default:
      return "error";
  }
}

async function tryIPGeolocation(): Promise<Coordinates | null> {
  try {
    const res = await fetch("https://ipapi.co/json/");
    if (!res.ok) return null;
    const data = await res.json();
    const lat = Number(data.latitude);
    const lng = Number(data.longitude);
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      return { lat, lng };
    }
  } catch {
    // Keep falling through to the local fallback.
  }
  return null;
}

export function saveLocation(lat: number, lng: number, source: SavedLocationSource = "manual", label?: string | null) {
  if (typeof window !== "undefined") {
    if (source !== "manual" && readSavedLocation()?.source === "manual") {
      return;
    }
    const payload: SavedLocation = { lat, lng, source, timestamp: Date.now() };
    const cleanLabel = label?.trim();
    if (cleanLabel) payload.label = cleanLabel;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  }
}

export function getSavedLocation(): Coordinates | null {
  const saved = readSavedLocation();
  return saved ? { lat: saved.lat, lng: saved.lng } : null;
}

export function getSavedLocationName(): string | null {
  return readSavedLocation()?.label ?? null;
}

function readSavedLocation(): SavedLocation | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed.lat !== "number" || typeof parsed.lng !== "number") {
      return null;
    }
    if (typeof parsed.timestamp !== "number") {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    if (parsed.source !== "manual" && Date.now() - parsed.timestamp > SAVED_LOCATION_MAX_AGE_MS) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return {
      lat: parsed.lat,
      lng: parsed.lng,
      timestamp: parsed.timestamp,
      source: parsed.source,
      label: typeof parsed.label === "string" && parsed.label.trim() ? parsed.label.trim() : undefined,
    };
  } catch {
    localStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function clearSavedLocation() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function hasSavedLocation(): boolean {
  return readSavedLocation() !== null;
}
