import { useEffect } from "react";

const BASE = (import.meta as any).env?.VITE_API_URL ?? "http://127.0.0.1:8000";

export function usePushNotifications() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) return;
    if (Notification.permission === "denied") return;

    let cancelled = false;

    async function subscribe() {
      try {
        const keyResponse = await fetch(`${BASE}/api/push/vapid-public-key`);
        if (!keyResponse.ok) return;
        const { publicKey } = (await keyResponse.json()) as { publicKey?: string };
        if (!publicKey || cancelled) return;

        const permission = Notification.permission === "granted"
          ? "granted"
          : await Notification.requestPermission();
        if (permission !== "granted" || cancelled) return;

        const registration = await navigator.serviceWorker.register("/sw.js");
        const existing = await registration.pushManager.getSubscription();
        const subscription = existing ?? await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey),
        });

        await fetch(`${BASE}/api/push/subscribe`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(subscription.toJSON()),
        });
      } catch {
        // Existing in-app danger-zone toasts remain the fallback.
      }
    }

    subscribe();

    return () => {
      cancelled = true;
    };
  }, []);
}

function urlBase64ToUint8Array(base64String: string) {
  const padding = "=".repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; i += 1) {
    outputArray[i] = rawData.charCodeAt(i);
  }

  return outputArray;
}
