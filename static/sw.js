const CACHE_NAME = "rain-check-v2";
const STATIC_ASSETS = [
  "/",
  "/manifest.json",
  "/static/styles.css",
  "/static/app.js",
  "/static/icons/icon-180.png",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => {})
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  // Network-first para chamadas de API e páginas, fallback para cache offline
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res && res.status === 200 && !req.url.includes("/api/")) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
        }
        return res;
      })
      .catch(() => caches.match(req))
  );
});

// Recebimento de Notificação Push em Background (iOS 16.4+ Web Push / APNs)
self.addEventListener("push", (event) => {
  let payload = {
    title: "🌧️ Rain Check — Previsão de Amanhã",
    body: "Toque para conferir se vai chover amanhã na sua localização.",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/badge-72.png",
    url: "/?from=push"
  };

  if (event.data) {
    try {
      const parsed = event.data.json();
      payload = { ...payload, ...parsed };
    } catch (e) {
      payload.body = event.data.text();
    }
  }

  const options = {
    body: payload.body,
    icon: payload.icon || "/static/icons/icon-192.png",
    badge: payload.badge || "/static/icons/badge-72.png",
    tag: "rain-check-daily-forecast",
    renotify: true,
    data: {
      url: payload.url || "/?from=push"
    }
  };

  event.waitUntil(self.registration.showNotification(payload.title, options));
});

// Clique na notificação abre ou foca o app na tela de previsão de amanhã
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) {
          client.postMessage({ type: "REFRESH_WEATHER_FROM_PUSH" });
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
