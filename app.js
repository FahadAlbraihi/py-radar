/* رادار بايثون — تجميع محتوى بايثون بالعربي والإنجليزي من مصادر متعددة.
   يعمل كلياً داخل المتصفح (بدون خادم)، ويحدّث نفسه تلقائياً كل يوم. */

'use strict';

/* ============================ إعدادات ============================ */

const CACHE_KEY  = 'pyradar.items.v3';
const SAVED_KEY  = 'pyradar.saved.v1';
const STALE_MS   = 6 * 60 * 60 * 1000;   // يعاد الجلب إذا مضى ٦ ساعات أو تغيّر اليوم
const PAGE_SIZE  = 30;
const MAX_STORE  = 500;

// حد أقصى لكل مصدر حتى لا يغرق مصدر سريع النشر (مثل PyPI) بقية المحتوى
const CAPS = { pypi:15, blogs:60, devto:45, hn:40, so:30, github:25, reddit:30 };

// كلمات تدل على أن المحتوى فعلاً عن بايثون (تُطبّق على مصادر الأخبار العامة فقط)
const RELEVANT = /\bpython\b|بايثون|بايثن|باثيون|\bdjango\b|جانغو|جانجو|\bflask\b|فلاسك|\bfastapi\b|\bpandas\b|\bnumpy\b|\bpytorch\b|\bstreamlit\b/i;

// "بايثون" اسم ثعبان وسيارة أيضاً — نستبعد هذه الأخبار ما لم تحمل إشارة برمجية
const NOISE = /ثعب|أفع|افع|سيارة|طائرة|صاروخ|دبابة|مسدس|كوبرا|حديقة الحيوان/;
const PROG  = /برمج|مبرمج|لغة|كود|تطوير|تعلم|تعلّم|دورة|كورس|شرح|مكتبة|مكتبات|تطبيق|مشروع|بيانات|ذكاء اصطناعي|خوارزم|\bpython\b|\bcode\b/i;

/* ---------- بروكسي CORS: كثير من مواقع RSS لا تسمح بالقراءة المباشرة ----------
   الترتيب: الخادم المحلي (serve.py) إن وُجد، ثم خدمات عامة كبديل. */
let localProxyOK = false;

const PROXIES = [
  u => `proxy?url=${encodeURIComponent(u)}`,                        // serve.py (يُستخدم فقط إذا كان متاحاً)
  u => `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(u)}`,
  u => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
  u => `https://corsproxy.io/?url=${encodeURIComponent(u)}`,
  u => `https://thingproxy.freeboard.io/fetch/${u}`,
];

/* ---------- المصادر ---------- */
const gnews = (q, lang) => lang === 'ar'
  ? `https://news.google.com/rss/search?q=${encodeURIComponent(q)}&hl=ar&gl=EG&ceid=EG:ar`
  : `https://news.google.com/rss/search?q=${encodeURIComponent(q)}&hl=en-US&gl=US&ceid=US:en`;

const SOURCES = [
  // — مصادر تعمل مباشرة من المتصفح (بدون بروكسي) —
  { id:'hn',      name:'Hacker News',    lang:'en', direct:true, fn:fetchHN },
  { id:'devto',   name:'DEV.to',         lang:'en', direct:true, fn:fetchDevTo },
  { id:'so',      name:'Stack Overflow', lang:'en', direct:true, fn:fetchSO },
  { id:'github',  name:'GitHub',         lang:'en', direct:true, fn:fetchGitHub },
  { id:'pypi',    name:'PyPI',           lang:'en', direct:true, fn:fetchPyPI },

  // — مصادر عربية (عبر بروكسي): بحث أخبار جوجل يغطي مواقع عربية كثيرة —
  { id:'ar-news', name:'مقالات عربية',   lang:'ar', fn:() => fetchFeeds([
      gnews('برمجة بايثون OR "تعلم بايثون" OR "لغة بايثون"', 'ar'),
      gnews('"بايثون" (دورة OR شرح OR كورس OR مشروع)', 'ar'),
      gnews('بايثون (جانغو OR فلاسك OR "الذكاء الاصطناعي")', 'ar'),
      'https://www.bing.com/news/search?q=%D8%A8%D8%B1%D9%85%D8%AC%D8%A9+%D8%A8%D8%A7%D9%8A%D8%AB%D9%88%D9%86&format=RSS',
    ], 'ar-news', 'مقالات عربية', true) },

  { id:'ar-yt',   name:'فيديوهات عربية', lang:'ar', fn:() => fetchFeeds([
      gnews('بايثون site:youtube.com', 'ar'),
      gnews('"شرح بايثون" OR "كورس بايثون"', 'ar'),
    ], 'ar-yt', 'فيديوهات ودروس', true) },

  // — مدونات إنجليزية (عبر بروكسي) —
  { id:'blogs',   name:'مدونات',         lang:'en', fn:() => fetchFeeds([
      'https://realpython.com/atom.xml',
      'https://planetpython.org/rss20.xml',
      'https://blog.python.org/feeds/posts/default',
    ], 'blogs', 'مدونات بايثون', false) },

  { id:'reddit',  name:'Reddit',         lang:'en', fn:() => fetchFeeds([
      'https://www.reddit.com/r/Python/hot/.rss?limit=25',
      'https://www.reddit.com/r/learnpython/hot/.rss?limit=25',
    ], 'reddit', 'Reddit', false) },
];

/* ============================ أدوات ============================ */

const $  = s => document.querySelector(s);
const el = (t, c) => { const n = document.createElement(t); if (c) n.className = c; return n; };
const isArabic = s => /[؀-ۿ]/.test(s || '');
const stripTags = s => (s || '').replace(/<[^>]*>/g, ' ').replace(/&[a-z]+;|&#\d+;/gi, ' ').replace(/\s+/g, ' ').trim();

function keyOf(item){
  return (item.title || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '').slice(0, 70);
}

async function timedFetch(url, ms = 15000, opts = {}){
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), ms);
  try { return await fetch(url, { ...opts, signal: c.signal, cache: 'no-store' }); }
  finally { clearTimeout(t); }
}

/** يجلب نصاً عبر سلسلة البروكسيات حتى ينجح أحدها. */
async function viaProxy(url){
  const list = localProxyOK ? PROXIES : PROXIES.slice(1);
  let lastErr;
  for (const build of list){
    try {
      const r = await timedFetch(build(url), 12000);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const text = await r.text();
      if (text && text.length > 120) return text;
      throw new Error('رد فارغ');
    } catch (e) { lastErr = e; }
  }
  throw lastErr || new Error('تعذّر الجلب');
}

/* ---------- تحليل RSS / Atom ---------- */
function parseFeed(xmlText){
  const doc = new DOMParser().parseFromString(xmlText, 'text/xml');
  if (doc.querySelector('parsererror')) return [];
  const nodes = [...doc.querySelectorAll('item, entry')];
  return nodes.map(n => {
    const get = tag => n.querySelector(tag)?.textContent?.trim() || '';
    let link = get('link');
    if (!link){
      const a = n.querySelector('link[href]');
      link = a ? a.getAttribute('href') : '';
    }
    const date = get('pubDate') || get('published') || get('updated') || get('date');
    return {
      title: stripTags(get('title')),
      url: link,
      date: date ? new Date(date).toISOString() : null,
      summary: stripTags(get('description') || get('summary') || get('content')).slice(0, 260),
    };
  }).filter(i => i.title && i.url);
}

/** يجمع عدة تغذيات RSS في مصدر واحد. */
async function fetchFeeds(urls, sourceId, sourceName, needsRelevanceCheck){
  const results = await Promise.allSettled(urls.map(u => viaProxy(u).then(parseFeed)));
  const out = [];
  for (const r of results){
    if (r.status !== 'fulfilled') continue;
    for (const it of r.value){
      // عنوان أخبار جوجل يأتي بصيغة "العنوان - اسم الموقع"
      let title = it.title, via = '';
      const m = title.match(/^(.*)\s+[-–]\s+([^-–]{2,40})$/);
      if (m && sourceId.startsWith('ar-')){ title = m[1].trim(); via = m[2].trim(); }

      const blob = title + ' ' + (it.summary || '');
      if (needsRelevanceCheck && !RELEVANT.test(blob)) continue;
      if (NOISE.test(blob) && !PROG.test(blob)) continue;

      out.push({
        title,
        url: it.url,
        date: it.date,
        summary: it.summary,
        sourceId,
        source: via || sourceName,
        lang: isArabic(title) ? 'ar' : 'en',
      });
    }
  }
  return out;
}

/* ---------- المصادر المباشرة ---------- */
async function fetchHN(){
  const since = Math.floor((Date.now() - 14 * 864e5) / 1000);
  const url = `https://hn.algolia.com/api/v1/search_by_date?query=python&tags=story&hitsPerPage=40&numericFilters=created_at_i>${since}`;
  const d = await (await timedFetch(url)).json();
  return (d.hits || []).filter(h => h.title).map(h => ({
    title: h.title,
    url: h.url || `https://news.ycombinator.com/item?id=${h.objectID}`,
    date: h.created_at,
    summary: stripTags(h.story_text || '').slice(0, 200),
    points: h.points || 0,
    sourceId: 'hn', source: 'Hacker News', lang: 'en',
  }));
}

async function fetchDevTo(){
  const tags = ['python', 'django', 'fastapi'];
  const arr = await Promise.allSettled(tags.map(t =>
    timedFetch(`https://dev.to/api/articles?tag=${t}&per_page=15`).then(r => r.json())
  ));
  const out = [];
  for (const r of arr){
    if (r.status !== 'fulfilled' || !Array.isArray(r.value)) continue;
    for (const a of r.value) out.push({
      title: a.title,
      url: a.url,
      date: a.published_at,
      summary: (a.description || '').slice(0, 220),
      points: a.positive_reactions_count || 0,
      sourceId: 'devto', source: 'DEV.to', lang: isArabic(a.title) ? 'ar' : 'en',
    });
  }
  return out;
}

async function fetchSO(){
  const url = 'https://api.stackexchange.com/2.3/questions?order=desc&sort=votes&tagged=python'
            + '&site=stackoverflow&pagesize=30&fromdate=' + Math.floor((Date.now() - 7 * 864e5) / 1000);
  const d = await (await timedFetch(url)).json();
  return (d.items || []).map(q => ({
    title: decodeHTML(q.title),
    url: q.link,
    date: new Date(q.creation_date * 1000).toISOString(),
    summary: (q.tags || []).join('، '),
    points: q.score || 0,
    sourceId: 'so', source: 'Stack Overflow', lang: 'en',
  }));
}

async function fetchGitHub(){
  const d0 = new Date(Date.now() - 21 * 864e5).toISOString().slice(0, 10);
  const url = `https://api.github.com/search/repositories?q=language:python+pushed:>${d0}&sort=stars&order=desc&per_page=25`;
  const d = await (await timedFetch(url)).json();
  return (d.items || []).map(r => ({
    title: r.full_name,
    url: r.html_url,
    date: r.pushed_at,
    summary: r.description || '',
    points: r.stargazers_count || 0,
    sourceId: 'github', source: 'GitHub', lang: 'en',
  }));
}

async function fetchPyPI(){
  const txt = await (await timedFetch('https://pypi.org/rss/updates.xml')).text();
  return parseFeed(txt).slice(0, 25).map(i => ({
    ...i, sourceId: 'pypi', source: 'PyPI', lang: 'en',
  }));
}

function decodeHTML(s){
  const t = document.createElement('textarea');
  t.innerHTML = s || '';
  return t.value;
}

/* ============================ الحالة ============================ */

const state = {
  items: [],
  saved: load(SAVED_KEY, []),
  lang: 'all',
  source: 'all',
  q: '',
  shown: PAGE_SIZE,
  updatedAt: 0,
  loading: false,
};

function load(key, fallback){
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; }
  catch { return fallback; }
}
function save(key, val){
  try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
}

/* ============================ الجلب ============================ */

async function refresh(force = false){
  if (state.loading) return;

  const cached = load(CACHE_KEY, null);
  const sameDay = cached && new Date(cached.ts).toDateString() === new Date().toDateString();
  const fresh   = cached && sameDay && (Date.now() - cached.ts) < STALE_MS;

  if (cached && !force){
    state.items = cached.items;
    state.updatedAt = cached.ts;
    render();
    if (fresh){ setStatus(''); return; }          // محتوى اليوم موجود، لا داعي للجلب
  }

  state.loading = true;
  $('#btn-refresh').classList.add('spin');
  setStatus(state.items.length ? 'جارٍ التحديث…' : 'جارٍ جلب المحتوى…');
  if (!state.items.length) skeletons();

  let done = 0, got = 0;
  const failed = [];

  // كل مصدر يظهر فور وصوله بدل انتظار الجميع
  const absorb = items => {
    const clean = items.filter(i => i && i.title && i.url);
    if (!clean.length) return;
    got += clean.length;
    state.items = merge(state.items, clean);
    state.updatedAt = Date.now();
    render();
  };

  // ملف يومي جاهز (ينتجه build_feed.py عبر GitHub Actions) — اختياري، يفشل بصمت
  const daily = timedFetch('data/feed.json', 8000)
    .then(r => r.ok ? r.json() : null)
    .then(d => { if (d && Array.isArray(d.items)) absorb(d.items); })
    .catch(() => {});

  await Promise.allSettled([daily, ...SOURCES.map(async s => {
    try { absorb(await s.fn()); }
    catch { failed.push(s.name); }
    done++;
    setStatus(`جارٍ التحميل… ${done}/${SOURCES.length}`);
  })]);

  if (got) save(CACHE_KEY, { ts: state.updatedAt, items: state.items.slice(0, MAX_STORE) });

  state.loading = false;
  $('#btn-refresh').classList.remove('spin');
  render();
  setStatus(failed.length ? `تعذّر الوصول إلى: ${failed.join('، ')}` : '');
  if (failed.length) setTimeout(() => setStatus(''), 6000);
}

/** يدمج الجديد مع القديم بلا تكرار، ويرتّب بالأحدث. */
function merge(oldItems, newItems){
  const map = new Map();
  for (const i of [...newItems, ...oldItems]){
    const k = keyOf(i);
    if (!k || map.has(k)) continue;
    map.set(k, i);
  }

  const sorted = [...map.values()].sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));

  const perSource = new Map();
  const out = [];
  for (const i of sorted){
    const n = perSource.get(i.sourceId) || 0;
    if (n >= (CAPS[i.sourceId] ?? 999)) continue;
    perSource.set(i.sourceId, n + 1);
    out.push(i);
    if (out.length >= MAX_STORE) break;
  }
  return out;
}

/* ============================ العرض ============================ */

const rtf = new Intl.RelativeTimeFormat('ar', { numeric: 'auto' });
function ago(iso){
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  if (isNaN(diff)) return '';
  const min = Math.round(diff / 6e4);
  if (min < 60)  return rtf.format(-min, 'minute');
  const hr = Math.round(min / 60);
  if (hr < 24)   return rtf.format(-hr, 'hour');
  const day = Math.round(hr / 24);
  if (day < 30)  return rtf.format(-day, 'day');
  return rtf.format(-Math.round(day / 30), 'month');
}

function visible(){
  const q = state.q.trim().toLowerCase();
  let list = state.lang === 'saved' ? state.saved : state.items;

  return list.filter(i => {
    if (state.lang === 'ar' && i.lang !== 'ar') return false;
    if (state.lang === 'en' && i.lang !== 'en') return false;
    if (state.source !== 'all' && i.sourceId !== state.source) return false;
    if (q && !((i.title + ' ' + (i.summary || '') + ' ' + i.source).toLowerCase().includes(q))) return false;
    return true;
  });
}

function render(){
  const list = $('#list');
  const items = visible();
  list.textContent = '';

  const slice = items.slice(0, state.shown);
  for (const i of slice) list.appendChild(card(i));

  $('#empty').hidden = items.length > 0 || state.loading;
  $('#btn-more').hidden = items.length <= state.shown;
  $('#meta').textContent = state.updatedAt
    ? `${state.items.length} عنصر · آخر تحديث ${ago(new Date(state.updatedAt).toISOString())}`
    : '';
  renderSourceChips();
}

function card(i){
  const c = el('div', 'card');

  const a = el('a', 't');
  a.href = i.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
  a.textContent = i.title;
  c.appendChild(a);

  if (i.summary){
    const s = el('div', 's');
    s.textContent = i.summary;
    c.appendChild(s);
  }

  const row = el('div', 'row');
  const tag = el('span', 'tag ' + i.lang);
  tag.textContent = i.lang === 'ar' ? 'عربي' : 'إنجليزي';
  row.appendChild(tag);

  const src = el('span', 'src'); src.textContent = i.source; row.appendChild(src);

  if (i.date){
    const d = el('span', 'dot'); d.textContent = '•'; row.appendChild(d);
    const t = el('span', 'time'); t.textContent = ago(i.date); row.appendChild(t);
  }
  if (i.points){
    const p = el('span', 'pts'); p.textContent = '▲ ' + i.points; row.appendChild(p);
  }
  c.appendChild(row);

  const star = el('button', 'star');
  const on = state.saved.some(x => keyOf(x) === keyOf(i));
  star.classList.toggle('on', on);
  star.textContent = on ? '★' : '☆';
  star.setAttribute('aria-label', on ? 'إزالة من المحفوظات' : 'حفظ');
  star.onclick = () => toggleSave(i, star);
  c.appendChild(star);

  return c;
}

function toggleSave(item, btn){
  const k = keyOf(item);
  const idx = state.saved.findIndex(x => keyOf(x) === k);
  if (idx >= 0) state.saved.splice(idx, 1); else state.saved.unshift(item);
  save(SAVED_KEY, state.saved);
  const on = idx < 0;
  btn.classList.toggle('on', on);
  btn.textContent = on ? '★' : '☆';
  if (state.lang === 'saved') render();
}

function renderSourceChips(){
  const wrap = $('#source-chips');
  const counts = new Map();
  for (const i of state.items) counts.set(i.sourceId, (counts.get(i.sourceId) || 0) + 1);

  const defs = [{ id:'all', name:'كل المصادر' },
    ...SOURCES.filter(s => counts.get(s.id)).map(s => ({ id:s.id, name:`${s.name} (${counts.get(s.id)})` }))];

  wrap.textContent = '';
  for (const d of defs){
    const b = el('button', 'chip' + (state.source === d.id ? ' is-on' : ''));
    b.textContent = d.name;
    b.onclick = () => { state.source = d.id; state.shown = PAGE_SIZE; render(); window.scrollTo({ top: 0, behavior: 'smooth' }); };
    wrap.appendChild(b);
  }
}

function skeletons(){
  const list = $('#list');
  list.textContent = '';
  for (let i = 0; i < 6; i++) list.appendChild(el('div', 'sk'));
}

function setStatus(t){ $('#status').textContent = t; }

/* ============================ الأحداث ============================ */

$('#btn-refresh').onclick = () => refresh(true);
$('#btn-more').onclick = () => { state.shown += PAGE_SIZE; render(); };
$('#btn-reset').onclick = () => { state.source = 'all'; state.lang = 'all'; state.q = ''; $('#q').value = ''; state.shown = PAGE_SIZE; syncLangChips(); render(); };

let qTimer;
$('#q').addEventListener('input', e => {
  state.q = e.target.value;
  $('#btn-clear').hidden = !state.q;
  clearTimeout(qTimer);
  qTimer = setTimeout(() => { state.shown = PAGE_SIZE; render(); }, 180);
});
$('#btn-clear').onclick = () => { $('#q').value = ''; state.q = ''; $('#btn-clear').hidden = true; render(); };

$('#lang-chips').addEventListener('click', e => {
  const b = e.target.closest('.chip');
  if (!b) return;
  state.lang = b.dataset.lang;
  state.shown = PAGE_SIZE;
  syncLangChips();
  render();
});
function syncLangChips(){
  for (const b of $('#lang-chips').children) b.classList.toggle('is-on', b.dataset.lang === state.lang);
}

$('#btn-install').onclick = () => $('#install-dlg').showModal();

// السحب للأسفل من أعلى الصفحة = تحديث
let touchY = 0;
addEventListener('touchstart', e => { touchY = e.touches[0].clientY; }, { passive: true });
addEventListener('touchend', e => {
  const dy = e.changedTouches[0].clientY - touchY;
  if (scrollY <= 0 && dy > 110) refresh(true);
}, { passive: true });

// إعادة الفحص عند العودة للتطبيق (يضمن محتوى اليوم)
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') refresh(false);
});

/* ============================ التشغيل ============================ */

(async function boot(){
  // هل نعمل خلف serve.py؟ (بروكسي محلي أسرع وأثبت)
  try {
    const r = await timedFetch('proxy?ping=1', 1500);
    localProxyOK = r.ok && (await r.text()).trim() === 'pong';
  } catch { localProxyOK = false; }

  // نصيحة الإضافة للشاشة الرئيسية تظهر على iOS فقط خارج وضع التطبيق
  const iOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
  if (iOS && !navigator.standalone) $('#btn-install').hidden = false;

  syncLangChips();
  await refresh(false);

  if ('serviceWorker' in navigator){
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
})();
