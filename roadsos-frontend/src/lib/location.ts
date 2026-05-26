// ─── Location service ────────────────────────────────────────────
// Priority order:
//   1. User-chosen override from localStorage  (always wins)
//   2. Browser Geolocation API (high accuracy)
//   3. IP-based geolocation (ipapi.co)
//   4. Hardcoded fallback (Madurai — 9.9252, 78.1198)

const STORAGE_KEY = "roadsos_user_location";

export async function getLocation(): Promise<{ lat: number; lng: number }> {
  // 1. Check localStorage for saved user-chosen location
  const saved = getSavedLocation();
  if (saved) return saved;

  // 2. Try browser geolocation with high accuracy
  const browserCoords = await tryBrowserGeolocation();
  if (browserCoords) return browserCoords;

  // 3. Try IP-based geolocation
  const ipCoords = await tryIPGeolocation();
  if (ipCoords) return ipCoords;

  // 4. Ultimate fallback
  return { lat: 9.9252, lng: 78.1198 }; // Madurai
}

async function tryBrowserGeolocation(): Promise<{ lat: number; lng: number } | null> {
  if (typeof window === "undefined" || !("geolocation" in navigator)) return null;

  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 5000, maximumAge: 0 }
    );
  });
}

async function tryIPGeolocation(): Promise<{ lat: number; lng: number } | null> {
  try {
    const res = await fetch("https://ipapi.co/json/");
    if (!res.ok) return null;
    const data = await res.json();
    if (data.latitude && data.longitude) {
      return { lat: data.latitude, lng: data.longitude };
    }
  } catch {
    // silently fail
  }
  return null;
}

// ─── Override helpers ────────────────────────────────────────────

export function saveLocation(lat: number, lng: number) {
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ lat, lng }));
  }
}

export function getSavedLocation(): { lat: number; lng: number } | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed.lat === "number" && typeof parsed.lng === "number") {
      return parsed;
    }
  } catch {
    // ignore
  }
  return null;
}

export function clearSavedLocation() {
  if (typeof window !== "undefined") {
    localStorage.removeItem(STORAGE_KEY);
  }
}

export function hasSavedLocation(): boolean {
  return getSavedLocation() !== null;
}
