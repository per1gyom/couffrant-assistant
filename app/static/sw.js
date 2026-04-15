/**
 * Service Worker Raya — PWA offline + cache
 *
 * IMPORTANT : incrémenter CACHE_VERSION à chaque déploiement
 * pour forcer le rechargement des assets modifiés.
 *
 * Stratégie :
 * - Nos fichiers (CSS/JS) → Network-First (prend le frais, cache en fallback)
 * - CDN (marked.js, DOMPurify) → Cache-First (rarement change)
 * - API → Network only
 * - Navigation HTML → Network-First avec fallback cache
 */

const CACHE_VERSION = 13;
const CACHE_NAME = 'raya-v' + CACHE_VERSION;

// Assets mis en cache à l'installation
const PRECACHE_ASSETS = [
  '/chat',
  '/static/chat-base.css',
  '/static/chat-components.css',
  '/static/chat-drawer.css',
  '/static/onboarding.css',
  '/static/mobile.css',
  '/static/chat-core.js',
  '/static/chat-main.js',
  '/static/chat-messages.js',
  '/static/chat-onboarding.js',
  '/static/chat-shortcuts.js',
  '/static/chat-voice.js',
  '/static/chat-feedback.js',
  '/static/chat-triage.js',
  '/static/chat-admin.js',
  '/static/chat-topics.js',
  '/static/manifest.json',
  'https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js',
  'https://cdn.jsdelivr.net/npm/dompurify@3.0.6/dist/purify.min.js',
];

// Routes API — toujours réseau, jamais de cache
const API_ROUTES = [
  '/raya', '/onboarding', '/feedback', '/token-status',
  '/memory', '/admin', '/chat/history', '/health',
  '/profile', '/download',
];

// Nos fichiers qui changent souvent → Network-First
const OWN_ASSETS_PREFIX = '/static/';

// ─── INSTALL : précache + skip waiting immédiat ───
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

// ─── FETCH ───
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // API → Network only, pas de cache
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

  // Nos propres fichiers statiques → Network-First (prend le frais du serveur)
  if (url.pathname.startsWith(OWN_ASSETS_PREFIX) && url.origin === location.origin) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // CDN (marked.js, DOMPurify) → Cache-First (stable, rarement change)
  if (url.origin !== location.origin &&
      (event.request.destination === 'script' || event.request.destination === 'style')) {
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
