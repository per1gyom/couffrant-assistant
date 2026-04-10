/**
 * Service Worker Raya — PWA offline + cache
 *
 * Stratégie : Cache-First pour les assets statiques (CSS, JS, icônes).
 * Network-First pour les appels API (/raya, /onboarding, etc.).
 * Si réseau indisponible sur une page HTML → affiche la page offline.
 */

const CACHE_NAME = 'raya-v1';
const CACHE_VERSION = 1;

// Assets mis en cache à l'installation
const PRECACHE_ASSETS = [
  '/chat',
  '/static/chat.css',
  '/static/onboarding.css',
  '/static/chat.js',
  '/static/manifest.json',
  'https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js',
  'https://cdn.jsdelivr.net/npm/dompurify@3.0.6/dist/purify.min.js',
];

// Routes API — toujours réseau, pas de cache
const API_ROUTES = [
  '/raya',
  '/onboarding',
  '/feedback',
  '/token-status',
  '/memory',
  '/admin',
];

// ─── INSTALL : précache des assets statiques ───
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

// ─── ACTIVATE : nettoyage des anciens caches ───
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ─── FETCH : stratégie selon le type de requête ───
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // API → Network-First, pas de cache
  if (API_ROUTES.some(r => url.pathname.startsWith(r))) {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(JSON.stringify({ error: 'offline' }), {
          headers: { 'Content-Type': 'application/json' },
          status: 503,
        })
      )
    );
    return;
  }

  // Assets statiques → Cache-First
  if (event.request.destination === 'script' ||
      event.request.destination === 'style' ||
      event.request.destination === 'image' ||
      event.request.destination === 'font') {
    event.respondWith(
      caches.match(event.request).then(cached =>
        cached || fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
      )
    );
    return;
  }

  // Navigation HTML → Network-First avec fallback cache
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match('/chat') || caches.match('/'))
    );
  }
});
