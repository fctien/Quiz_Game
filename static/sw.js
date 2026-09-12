/* 金榜問答 Service Worker
   目的：加到主畫面後開得快、離線時仍看得到畫面骨架。
   題目與即時連線一定走網路，不會被快取，所以不會拿到舊題目或舊比分。 */
const CACHE = 'jinbang-v3-1';
const SHELL = ['/', '/host', '/play', '/class', '/static/style.css',
               '/static/icons/icon-192.png', '/static/icons/icon-512.png', '/static/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => Promise.allSettled(SHELL.map(u => c.add(u)))).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/')) return;                 // 題目、作答、即時推播一律走網路

  if (url.pathname.startsWith('/static/')) {                    // 靜態檔：先用快取
    e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(res => {
      const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); return res;
    })));
    return;
  }
  e.respondWith(fetch(req).then(res => {                        // 頁面：先連網，連不到才用快取
    const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); return res;
  }).catch(() => caches.match(req).then(hit => hit || caches.match('/'))));
});
