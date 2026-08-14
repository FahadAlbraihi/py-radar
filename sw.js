/* يخزّن ملفات الواجهة ليعمل التطبيق بدون إنترنت.
   بيانات المحتوى تُخزَّن في localStorage وليس هنا. */

const CACHE = 'pyradar-shell-v3';
const SHELL = ['./', './index.html', './styles.css', './app.js', './manifest.webmanifest'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  // طلبات المحتوى والبروكسي: من الشبكة دائماً
  if (url.origin !== location.origin || url.pathname.endsWith('/proxy')) return;

  // الواجهة: الكاش أولاً ثم الشبكة (مع تحديث الكاش في الخلفية)
  e.respondWith(
    caches.match(req).then(hit => {
      const net = fetch(req).then(res => {
        if (res.ok) caches.open(CACHE).then(c => c.put(req, res.clone()));
        return res;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
