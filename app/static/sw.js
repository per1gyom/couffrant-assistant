/**
 * Service Worker Raya — Phase 4 (PWA)
 *
 * Stratégie :
 *   - Assets statiques (CSS, JS) : Cache-first avec fallback réseau
 *   - API calls (/raya, /token-status…) : Network-first, jamais mis en cache
 *   - Pages HTML : Network-first, fallback cache si hors-ligne
 *
 * Le SW ne met PAS en cache les réponses LLM.
 * Les conversations nécessitent une connexion active.
 */

const CACHE_NAME = 'raya-v1';

const PRECACHE_ASSETS = [
  '/static/chat.css',
  '/static/onboarding.css',
  '/static/chat.js',
  '/static/manifest.json',
];

const NEVER_CACHE = [
  '/raya', '/raya/', '/onboarding/', '/token-status',
  '/speak', '/synth', '/build-memory', '/admin/', '/logout',
];

function shouldNeverCache(pathname) {
  return NEVER_CACHE.some(p => pathname === p || pathname.startsWith(p));
}

// ── INSTALL ──
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
      .catch(err => console.warn('[SW] Précache partiel :', err))
  );
});

// ── ACTIVATE ──
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// ── FETCH ──
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;
  if (shouldNeverCache(url.pathname)) {
    event.respondWith(fetch(request).catch(() => offlineResponse()));
    return;
  }

  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          caches.open(CACHE_NAME).then(c => c.put(request, res.clone()));
          return res;
        });
      })
    );
    return;
  }

  event.respondWith(
    fetch(request)
      .then(res => {
        caches.open(CACHE_NAME).then(c => c.put(request, res.clone()));
        return res;
      })
      .catch(() => caches.match(request).then(c => c || offlineResponse()))
  );
});

function offlineResponse() {
  return new Response(
    '<html><meta charset="utf-8"><body style="font-family:sans-serif;text-align:center;padding:40px">'
    + '<h2>✦ Raya</h2><p>Connexion requise.</p>'
    + '<button onclick="location.reload()">Réessayer</button>'
    + '</body></html>',
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}
