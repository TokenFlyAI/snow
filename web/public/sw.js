/* Service worker for the /snow/ PWA (scope = the directory this file is served from).
 *  - pages:            network first, fall back to cache (offline: last visited version)
 *  - hashed assets:    cache first (immutable file names)
 *  - forecast JSON:    stale-while-revalidate (instant paint, refresh in the background)
 */
const VERSION = "v1";
const SHELL = `snow-shell-${VERSION}`;
const DATA = `snow-data-${VERSION}`;
const SCOPE = new URL(self.registration.scope).pathname;          // "/snow/"
const PRECACHE = ["", "resorts/", "about/", "manifest.webmanifest", "icon.svg"].map((p) => SCOPE + p);

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(PRECACHE)).catch(() => undefined).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL, DATA]);
    for (const k of await caches.keys()) if (k.startsWith("snow-") && !keep.has(k)) await caches.delete(k);
    await self.clients.claim();
  })());
});

const isData = (url) => /\/data\/v\d+\/.+\.json$/.test(url.pathname);

async function networkFirst(request) {
  const cache = await caches.open(SHELL);
  try {
    const res = await fetch(request);
    if (res.ok) cache.put(request, res.clone());
    return res;
  } catch (err) {
    const hit = (await cache.match(request)) || (await cache.match(SCOPE));
    if (hit) return hit;
    throw err;
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(SHELL);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok) cache.put(request, res.clone());
  return res;
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(DATA);
  const hit = await cache.match(request.url);
  const refresh = fetch(request).then((res) => { if (res.ok) cache.put(request.url, res.clone()); return res; });
  if (hit) { refresh.catch(() => undefined); return hit; }
  return refresh;
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (isData(url)) { event.respondWith(staleWhileRevalidate(request)); return; }
  if (url.origin !== self.location.origin || !url.pathname.startsWith(SCOPE)) return;
  if (url.pathname.includes("/_next/static/")) { event.respondWith(cacheFirst(request)); return; }
  event.respondWith(networkFirst(request));
});
