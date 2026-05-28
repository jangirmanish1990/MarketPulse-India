const CACHE_NAME = "marketpulse-v1";
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/manifest.json",
];

// Cache static assets on install
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll(STATIC_ASSETS)
    )
  );
  self.skipWaiting();
});

// Clean old caches on activate
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== CACHE_NAME)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// Network-first for API calls, cache-first for static assets
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API calls — network only, no cache
  if (url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/ws/")) {
    return;
  }

  // Signal history — cache for 5 minutes
  if (url.pathname.startsWith("/api/signals")) {
    event.respondWith(
      caches.open(CACHE_NAME).then(async (cache) => {
        const cached = await cache.match(event.request);
        const now = Date.now();
        if (cached) {
          const cachedAt = cached.headers.get("sw-cached-at");
          if (cachedAt && now - parseInt(cachedAt) < 5 * 60 * 1000) {
            return cached;
          }
        }
        const response = await fetch(event.request);
        const cloned = response.clone();
        const headers = new Headers(cloned.headers);
        headers.append("sw-cached-at", now.toString());
        const modified = new Response(await cloned.blob(), {
          status: cloned.status,
          headers,
        });
        cache.put(event.request, modified);
        return response;
      })
    );
    return;
  }

  // Static assets — cache first
  event.respondWith(
    caches.match(event.request).then(
      (cached) => cached || fetch(event.request)
    )
  );
});
