/* يخزّن ملفات الواجهة ليعمل التطبيق بدون إنترنت.
   بيانات المحتوى تُخزَّن في localStorage وليس هنا. */

const CACHE = 'radar-shell-v4';
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

  /* الواجهة: الشبكة أولاً ثم الكاش.
     الكاش أولاً كان يعني بقاء نسخة قديمة من التطبيق بعد كل تحديث حتى الفتحة
     التالية؛ والتطبيق يحتاج الشبكة أصلاً، فالكاش دوره الاحتياط عند انقطاعها. */
  e.respondWith(
    fetch(req)
      .then(res => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then(c => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req).then(hit => hit || caches.match('./index.html')))
  );
});
