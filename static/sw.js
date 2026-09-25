/* POLARLOGIX service worker.
 * Strategy:
 *  - App shell (HTML/CSS/JS/manifest): cache-first, so the UI itself loads offline.
 *  - /api/* : always network. We do NOT cache API responses, because stale operational
 *    data (missed check-ins, cold-chain readings) is worse than an honest "can't reach
 *    the server right now" — the app already handles that via api.js's `offline` flag.
 *  - Everything else: network-first, falling back to cache if present.
 */
const CACHE = 'polarlogix-shell-v1';
const SHELL = [
  '/', '/login.html',
  '/static/css/app.css',
  '/static/js/api.js', '/static/js/db.js', '/static/js/sync.js', '/static/js/map.js', '/static/js/app.js',
  '/manifest.webmanifest',
];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET') return; // never intercept writes
  if (url.pathname.startsWith('/api/')) return; // API calls always hit the network directly

  if (SHELL.includes(url.pathname) || url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
        return res;
      }))
    );
    return;
  }

  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request).then((c) => c || caches.match('/')))
  );
});
