/**
 * Service Worker Raya — PWA offline
 * v15 — Stratégie simplifiée : nos fichiers = toujours réseau.
 * Le SW ne cache QUE les librairies CDN stables.
 */

const CACHE_VERSION = 15;
const CACHE_NAME = 'raya-v' + CACHE_VERSION;

self.addEventListener('install', event => { self.skipWaiting(); });

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // CDN (marked.js, DOMPurify, fonts) → Cache-First
  if (url.origin !== location.origin) {
    event.respondWith(
      caches.match(event.request).then(cached =>
        cached || fetch(event.request).then(resp => {
          const clone = resp.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
          return resp;
        })
      )
    );
    return;
  }

  // Tout le reste (nos fichiers, API, HTML) → Réseau direct, pas de cache SW
  event.respondWith(fetch(event.request));
});
