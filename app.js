/* رادار البرمجة — تجميع وتصنيف محتوى برمجي بالعربي والإنجليزي.
   يعمل كلياً داخل المتصفح (بدون خادم)، ويحدّث نفسه تلقائياً كل يوم. */

'use strict';

/* ============================ إعدادات ============================ */

const CACHE_KEY = 'radar.items.v4';
const LIB_KEY   = 'radar.library.v1';   // { url: {state, at, item} }
const PREF_KEY  = 'radar.prefs.v1';
const VISIT_KEY = 'radar.lastVisit.v1';
const STALE_MS  = 6 * 60 * 60 * 1000;   // يعاد الجلب إذا مضت ٦ ساعات أو تغيّر اليوم
const PAGE_SIZE = 30;
const MAX_STORE = 800;

const CAPS = { pypi:15, blogs:50, devto:45, hn:40, so:30, github:25, reddit:30, fcc:20 };

/* ---------- لغات البرمجة ---------- */
const TECHS = [
  { id:'python', name:'بايثون', hn:'python', so:'python', gh:'python',
    devto:['python','django','fastapi'], reddit:['Python','learnpython'],
    blogs:['https://realpython.com/atom.xml','https://planetpython.org/rss20.xml','https://blog.python.org/feeds/posts/default'],
    ar:['برمجة بايثون OR "تعلم بايثون" OR "لغة بايثون"','"بايثون" (دورة OR شرح OR كورس OR مشروع)'],
    match:/\bpython\b|بايثون|بايثن|\bdjango\b|جانغو|\bflask\b|فلاسك|\bfastapi\b|\bpandas\b|\bnumpy\b/i },

  { id:'javascript', name:'جافاسكربت', hn:'javascript', so:'javascript', gh:'javascript',
    devto:['javascript','react','nodejs'], reddit:['javascript','learnjavascript'], blogs:[],
    ar:['"جافاسكربت" OR "جافا سكريبت" برمجة','"جافاسكربت" (دورة OR شرح OR مشروع)'],
    match:/\bjavascript\b|\bjs\b|جافاسكربت|جافا سكريبت|\breact\b|\bnode\.?js\b|\btypescript\b|رياكت/i },

  { id:'sql', name:'SQL', hn:'sql database', so:'sql', gh:'sql',
    devto:['sql','database'], reddit:['SQL','learnSQL'], blogs:[],
    ar:['"قواعد البيانات" SQL تعلم','"لغة SQL" شرح OR دورة'],
    match:/\bsql\b|\bpostgres\b|\bmysql\b|\bsqlite\b|قواعد البيانات|قاعدة بيانات/i },

  { id:'cpp', name:'C / C++', hn:'c++', so:'c%2B%2B', gh:'c%2B%2B',
    devto:['cpp','c'], reddit:['cpp','C_Programming'], blogs:[],
    ar:['"سي بلس بلس" OR "لغة سي" برمجة','"++C" شرح OR دورة'],
    match:/\bc\+\+\b|\bcpp\b|سي بلس بلس|لغة سي\b/i },

  { id:'java', name:'جافا', hn:'java', so:'java', gh:'java',
    devto:['java'], reddit:['java','learnjava'], blogs:[],
    ar:['"لغة جافا" برمجة OR تعلم','"جافا" (دورة OR شرح) برمجة'],
    match:/\bjava\b(?!script)|لغة جافا|جافا\b(?! ?سكريبت|سكربت)/i },

  { id:'go', name:'Go', hn:'golang', so:'go', gh:'go',
    devto:['go'], reddit:['golang'], blogs:[],
    ar:['"لغة Go" OR "جولانج" برمجة'],
    match:/\bgolang\b|\bgo\b lang|جولانج|لغة go/i },

  { id:'rust', name:'Rust', hn:'rust', so:'rust', gh:'rust',
    devto:['rust'], reddit:['rust'], blogs:[],
    ar:['"لغة رست" OR Rust برمجة'],
    match:/\brust\b|لغة رست|رست\b/i },

  { id:'bash', name:'Bash / Shell', hn:'bash shell scripting', so:'bash', gh:'shell',
    devto:['bash','linux'], reddit:['bash','linuxadmin'], blogs:[],
    ar:['"سطر الأوامر" لينكس سكربت','"باش" OR "شل" برمجة لينكس'],
    match:/\bbash\b|\bshell\b|\bzsh\b|سطر الأوامر|سكربت|لينكس/i },
];
const techById = id => TECHS.find(t => t.id === id);

/* ---------- مسار التعلّم ---------- */
const STAGES = [
  { id:'',        name:'— لم أحدّد مرحلتي —', re:null },
  { id:'basics',  name:'الأساسيات وأنواع البيانات', re:/أساسيات|اساسيات|متغير|أنواع البيانات|\bbasics?\b|\bsyntax\b|data types|variables/i },
  { id:'flow',    name:'الشروط والحلقات',           re:/شرط|شروط|حلقات|تكرار|\bloops?\b|\bif\b|\bfor\b|\bwhile\b|conditionals/i },
  { id:'func',    name:'الدوال',                    re:/دالة|دوال|\bfunctions?\b|\blambda\b|\bdef\b|arguments/i },
  { id:'coll',    name:'القوائم والقواميس',         re:/قوائم|قائمة|قاموس|قواميس|\blists?\b|\bdict|\btuples?\b|\bsets?\b|comprehension|arrays?/i },
  { id:'files',   name:'النصوص والملفات',           re:/نصوص|ملفات|\bstrings?\b|\bfiles?\b|\bjson\b|\bcsv\b|\bregex\b|تعبير نمطي/i },
  { id:'oop',     name:'البرمجة كائنية التوجه (OOP)', re:/\boop\b|كائني|كائنية|\bclass(es)?\b|كلاس|وراثة|inheritance|polymorph|encapsul|\bobjects?\b/i },
  { id:'modules', name:'الوحدات والحزم',            re:/وحدات|حزم|\bmodules?\b|\bpackages?\b|\bpip\b|\bnpm\b|\bvenv\b|virtualenv|\bimport\b/i },
  { id:'test',    name:'الأخطاء والاختبارات',       re:/أخطاء|استثناء|اختبار|\berrors?\b|\bexceptions?\b|\btry\b|\btests?\b|\bpytest\b|unittest|debugg/i },
  { id:'async',   name:'التزامن والأداء',           re:/\basync\b|\bawait\b|asyncio|\bthreads?\b|concurren|parallel|أداء|تزامن|multiprocess/i },
  { id:'web',     name:'الويب وواجهات API',         re:/\bweb\b|\bapi\b|\bdjango\b|\bflask\b|\bfastapi\b|\brest\b|جانغو|فلاسك|ويب|واجهة برمجية/i },
  { id:'data',    name:'البيانات والذكاء الاصطناعي', re:/\bpandas\b|\bnumpy\b|\bdata\b|machine learning|\bml\b|\bai\b|بيانات|ذكاء اصطناعي|تعلم الآلة|تحليل/i },
  { id:'db',      name:'قواعد البيانات',            re:/\bsql\b|\bdatabase\b|\bpostgres\b|\bmysql\b|\bsqlite\b|\borm\b|قواعد البيانات/i },
];

/* ---------- تصنيف المستوى والنوع ---------- */
const LEVEL_RE = {
  beginner: /مبتدئ|للمبتدئين|من الصفر|أساسيات|اساسيات|مقدمة|البداية|أول درس|شرح مبسط|\bbeginners?\b|\bintro\b|introduction|\bbasics?\b|getting started|crash course|\b101\b|from scratch|first steps/i,
  advanced: /متقدم|متقدمة|احتراف|احترافي|متعمق|معمّق|تحت الغطاء|\badvanced\b|deep dive|\binternals\b|under the hood|optimiz|performance|architecture|design patterns?|scalab|concurrency|metaclass|\bcpython\b|profiling/i,
};
const KIND_RE = [
  ['course',    /دورة|كورس|بوتكامب|سلسلة كاملة|منهج|كامل\b|\bfull course\b|complete course|bootcamp|roadmap|curriculum|playlist/i],
  ['challenge', /تحدي|تحديات|حل مسائل|تمارين|تمرين|مسألة|\bchallenges?\b|exercises?|leetcode|codewars|\bkata\b|advent of code|\bpuzzle/i],
  ['interview', /مقابلة|مقابلات|انترفيو|أسئلة وظيف|وظيفة|توظيف|\binterviews?\b|hiring|\bresume\b|\bcareer\b|job questions/i],
  ['project',   /مشروع|مشاريع|تطبيق عملي|نبني|ننشئ|\bprojects?\b|let'?s build|building an?\b|build an?\b|\bclone\b|hands-?on/i],
  ['tutorial',  /شرح|درس|دروس|تعلم|تعلّم|كيفية|طريقة|\btutorials?\b|how to|\bguide\b|explained|\blessons?\b|\blearn\b|\bcourse\b/i],
  ['news',      /إطلاق|إصدار|أعلنت|\brelease[sd]?\b|announcing|\bv?\d+\.\d+|introducing|changelog|\bnews\b/i],
];
/* محتوى عربي يشرح مادة إنجليزية (مترجَم أو مشروح بالعربي) — يُشترط اجتماع
   الخطّين العربي واللاتيني حتى لا يُصنَّف كل محتوى عربي على أنه مترجم. */
const TRANSLATED_RE = /مترجم|مترجمة|مدبلج|ترجمة|بالعربي|بالعربية|arabic sub/i;
const LATIN_RE = /[A-Za-z]{3,}/;
const NOISE = /ثعب|أفع|افع|سيارة|طائرة|صاروخ|دبابة|مسدس|كوبرا|حديقة الحيوان/;
const PROG  = /برمج|مبرمج|لغة|كود|تطوير|تعلم|دورة|كورس|شرح|مكتبة|مكتبات|تطبيق|مشروع|بيانات|ذكاء اصطناعي|خوارزم|\bcode\b|\bprogramming\b/i;

/* ---------- بروكسي CORS ---------- */
let localProxyOK = false;
const PROXIES = [
  u => `proxy?url=${encodeURIComponent(u)}`,                       // serve.py إن وُجد
  u => `https://api.codetabs.com/v1/proxy?quest=${encodeURIComponent(u)}`,
  u => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
  u => `https://corsproxy.io/?url=${encodeURIComponent(u)}`,
];

const gnews = (q, lang) => lang === 'ar'
  ? `https://news.google.com/rss/search?q=${encodeURIComponent(q)}&hl=ar&gl=EG&ceid=EG:ar`
  : `https://news.google.com/rss/search?q=${encodeURIComponent(q)}&hl=en-US&gl=US&ceid=US:en`;

/* ============================ أدوات ============================ */

const $  = s => document.querySelector(s);
const el = (t, c) => { const n = document.createElement(t); if (c) n.className = c; return n; };
const isArabic = s => /[؀-ۿ]/.test(s || '');
const stripTags = s => (s || '').replace(/<[^>]*>/g, ' ').replace(/&[a-z]+;|&#\d+;/gi, ' ').replace(/\s+/g, ' ').trim();
const keyOf = i => (i.title || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '').slice(0, 70);

function load(key, fallback){
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function save(key, val){
  try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
}

async function timedFetch(url, ms = 15000, opts = {}){
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), ms);
  try { return await fetch(url, { ...opts, signal: c.signal, cache: 'no-store' }); }
  finally { clearTimeout(t); }
}

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

/* ============================ التصنيف ============================ */

function classify(item){
  const blob = `${item.title} ${item.summary || ''}`;

  if (!item.level){
    if (LEVEL_RE.beginner.test(blob))      item.level = 'beginner';
    else if (LEVEL_RE.advanced.test(blob)) item.level = 'advanced';
  }
  if (!item.kind){
    for (const [kind, re] of KIND_RE) if (re.test(blob)) { item.kind = kind; break; }
  }
  // المحتوى التعليمي بلا إشارة مستوى يُعد متوسطاً
  if (!item.level && ['course','tutorial','project','challenge'].includes(item.kind)) item.level = 'intermediate';

  item.translated = TRANSLATED_RE.test(blob) && LATIN_RE.test(blob) && isArabic(blob);
  item.stages = STAGES.filter(s => s.re && s.re.test(blob)).map(s => s.id);

  if (!item.tech){
    const hit = TECHS.find(t => t.match.test(blob));
    if (hit) item.tech = hit.id;
  }
  return item;
}

/* ============================ تحليل التغذيات ============================ */

function parseFeed(xmlText){
  const doc = new DOMParser().parseFromString(xmlText, 'text/xml');
  if (doc.querySelector('parsererror')) return [];

  return [...doc.querySelectorAll('item, entry')].map(n => {
    const get = tag => n.querySelector(tag)?.textContent?.trim() || '';
    let link = get('link');
    if (!link) link = n.querySelector('link[href]')?.getAttribute('href') || '';

    const date = get('pubDate') || get('published') || get('updated') || get('date');
    const out = {
      title: stripTags(get('title')),
      url: link,
      date: date ? new Date(date).toISOString() : null,
      summary: stripTags(get('description') || get('summary') || get('content')).slice(0, 240),
    };

    // تغذية قناة يوتيوب تحمل المشاهدات والتقييم والصورة
    const stats  = n.getElementsByTagName('media:statistics')[0];
    const rating = n.getElementsByTagName('media:starRating')[0];
    const thumb  = n.getElementsByTagName('media:thumbnail')[0];
    if (stats)  out.views  = +stats.getAttribute('views') || 0;
    if (rating){ out.rating = +rating.getAttribute('average') || 0; out.raters = +rating.getAttribute('count') || 0; }
    if (thumb)  out.thumb  = thumb.getAttribute('url') || '';

    return out;
  }).filter(i => i.title && i.url);
}

/** يجمع عدة تغذيات RSS في مصدر واحد. */
async function fetchFeeds(urls, sourceId, sourceName, tech, checkRelevance){
  const t = techById(tech);
  const results = await Promise.allSettled(urls.map(u => viaProxy(u).then(parseFeed)));
  const out = [];

  for (const r of results){
    if (r.status !== 'fulfilled') continue;
    for (const it of r.value){
      let title = it.title, via = '';
      const m = title.match(/^(.*)\s+[-–]\s+([^-–]{2,40})$/);
      if (m && sourceId.startsWith('ar-')){ title = m[1].trim(); via = m[2].trim(); }

      const blob = `${title} ${it.summary || ''}`;
      if (checkRelevance && t && !t.match.test(blob)) continue;
      if (NOISE.test(blob) && !PROG.test(blob)) continue;

      out.push(classify({
        ...it, title, tech,
        sourceId, source: via || sourceName,
        lang: isArabic(title) ? 'ar' : 'en',
      }));
    }
  }
  return out;
}

/* ============================ المصادر ============================ */

function decodeHTML(s){
  const t = document.createElement('textarea');
  t.innerHTML = s || '';
  return t.value;
}

async function fetchHN(t){
  const since = Math.floor((Date.now() - 21 * 864e5) / 1000);
  const url = `https://hn.algolia.com/api/v1/search_by_date?query=${encodeURIComponent(t.hn)}`
            + `&tags=story&hitsPerPage=40&numericFilters=created_at_i>${since}`;
  const d = await (await timedFetch(url)).json();
  return (d.hits || []).filter(h => h.title).map(h => classify({
    title: h.title,
    url: h.url || `https://news.ycombinator.com/item?id=${h.objectID}`,
    date: h.created_at,
    summary: stripTags(h.story_text || '').slice(0, 200),
    points: h.points || 0,
    tech: t.id, sourceId: 'hn', source: 'Hacker News', lang: 'en',
  }));
}

async function fetchDevTo(t){
  const arr = await Promise.allSettled(t.devto.map(tag =>
    timedFetch(`https://dev.to/api/articles?tag=${tag}&per_page=15`).then(r => r.json())
  ));
  const out = [];
  for (const r of arr){
    if (r.status !== 'fulfilled' || !Array.isArray(r.value)) continue;
    for (const a of r.value) out.push(classify({
      title: a.title, url: a.url, date: a.published_at,
      summary: (a.description || '').slice(0, 220),
      points: a.positive_reactions_count || 0,
      tech: t.id, sourceId: 'devto', source: 'DEV.to',
      lang: isArabic(a.title) ? 'ar' : 'en',
    }));
  }
  return out;
}

async function fetchSO(t){
  const url = 'https://api.stackexchange.com/2.3/questions?order=desc&sort=votes'
            + `&tagged=${t.so}&site=stackoverflow&pagesize=30`
            + `&fromdate=${Math.floor((Date.now() - 7 * 864e5) / 1000)}`;
  const d = await (await timedFetch(url)).json();
  return (d.items || []).map(q => classify({
    title: decodeHTML(q.title), url: q.link,
    date: new Date(q.creation_date * 1000).toISOString(),
    summary: (q.tags || []).join('، '),
    points: q.score || 0,
    tech: t.id, sourceId: 'so', source: 'Stack Overflow', lang: 'en',
  }));
}

async function fetchGitHub(t){
  const d0 = new Date(Date.now() - 21 * 864e5).toISOString().slice(0, 10);
  const url = `https://api.github.com/search/repositories?q=language:${t.gh}+pushed:>${d0}`
            + '&sort=stars&order=desc&per_page=25';
  const d = await (await timedFetch(url)).json();
  return (d.items || []).map(r => classify({
    title: r.full_name, url: r.html_url, date: r.pushed_at,
    summary: r.description || '', points: r.stargazers_count || 0,
    tech: t.id, sourceId: 'github', source: 'GitHub', lang: 'en', kind: 'news',
  }));
}

async function fetchPyPI(){
  const txt = await (await timedFetch('https://pypi.org/rss/updates.xml')).text();
  return parseFeed(txt).slice(0, 20).map(i => classify({
    ...i, tech: 'python', sourceId: 'pypi', source: 'PyPI', lang: 'en', kind: 'news',
  }));
}

/** يبني قائمة المهام لجلب لغة برمجة واحدة. */
function jobsFor(techId){
  const t = techById(techId);
  if (!t) return [];

  const jobs = [
    { name:'Hacker News',    fn:() => fetchHN(t) },
    { name:'DEV.to',         fn:() => fetchDevTo(t) },
    { name:'Stack Overflow', fn:() => fetchSO(t) },
    { name:'GitHub',         fn:() => fetchGitHub(t) },
    { name:'مقالات عربية',   fn:() => fetchFeeds(t.ar.map(q => gnews(q, 'ar')), 'ar-news', 'مقالات عربية', t.id, true) },
    { name:'فيديوهات عربية', fn:() => fetchFeeds([gnews(`${t.ar[0]} site:youtube.com`, 'ar')], 'ar-yt', 'فيديوهات ودروس', t.id, true) },
  ];
  if (t.reddit.length)
    jobs.push({ name:'Reddit', fn:() => fetchFeeds(
      t.reddit.map(s => `https://www.reddit.com/r/${s}/hot/.rss?limit=25`), 'reddit', 'Reddit', t.id, false) });
  if (t.blogs.length)
    jobs.push({ name:'مدونات', fn:() => fetchFeeds(t.blogs, 'blogs', 'مدونات', t.id, false) });
  // freeCodeCamp تغطي كل اللغات — تُرشَّح حسب لغة البرمجة الحالية
  jobs.push({ name:'freeCodeCamp', fn:() => fetchFeeds(
    ['https://www.freecodecamp.org/news/rss/'], 'fcc', 'freeCodeCamp', t.id, true) });
  if (t.id === 'python')
    jobs.push({ name:'PyPI', fn:fetchPyPI });

  return jobs;
}

/* ============================ الحالة ============================ */

const prefs = Object.assign({
  techs: ['python'], lang: 'all', level: 'all', kind: 'all',
  sort: 'date', source: 'all', stage: '', stageOnly: false,
}, load(PREF_KEY, {}));

const state = {
  items: [],
  library: load(LIB_KEY, {}),
  lastVisit: load(VISIT_KEY, 0) || Date.now() - 864e5,
  q: '',
  shown: PAGE_SIZE,
  updatedAt: 0,
  loading: false,
  shelf: 'saved',
};

const savePrefs = () => save(PREF_KEY, prefs);

/* ============================ الجلب ============================ */

async function refresh(force = false){
  if (state.loading) return;

  const cached = load(CACHE_KEY, null);
  const sameDay = cached && new Date(cached.ts).toDateString() === new Date().toDateString();
  const fresh   = cached && sameDay && (Date.now() - cached.ts) < STALE_MS
                  && (cached.techs || []).join() === prefs.techs.join();

  if (cached && !force){
    state.items = cached.items.map(classify);
    state.updatedAt = cached.ts;
    render();
    if (fresh){ setStatus(''); return; }
  }

  state.loading = true;
  $('#btn-refresh').classList.add('spin');
  if (!state.items.length) skeletons();

  const jobs = prefs.techs.flatMap(id => jobsFor(id));
  let done = 0, got = 0;
  const failed = new Set();

  const absorb = items => {
    const clean = (items || []).filter(i => i && i.title && i.url);
    if (!clean.length) return;
    got += clean.length;
    state.items = merge(state.items, clean.map(classify));
    state.updatedAt = Date.now();
    render();
  };

  // اللقطة اليومية الجاهزة (تنتجها GitHub Actions) — اختيارية، تفشل بصمت
  const daily = Promise.allSettled(prefs.techs.map(id =>
    timedFetch(`data/feed-${id}.json`, 8000)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && Array.isArray(d.items)) absorb(d.items); })
  ));

  setStatus('جارٍ التحميل…');
  await Promise.allSettled([daily, ...jobs.map(async j => {
    try { absorb(await j.fn()); }
    catch { failed.add(j.name); }
    done++;
    setStatus(`جارٍ التحميل… ${done}/${jobs.length}`);
  })]);

  if (got) save(CACHE_KEY, { ts: state.updatedAt, techs: [...prefs.techs], items: state.items.slice(0, MAX_STORE) });

  state.loading = false;
  $('#btn-refresh').classList.remove('spin');
  render();
  setStatus(failed.size ? `تعذّر الوصول إلى: ${[...failed].join('، ')}` : '');
  if (failed.size) setTimeout(() => setStatus(''), 6000);
}

/** يدمج بلا تكرار، يرتّب بالأحدث، ويطبّق حداً لكل مصدر. */
function merge(oldItems, newItems){
  const map = new Map();
  for (const i of [...newItems, ...oldItems]){
    const k = keyOf(i);
    if (!k || map.has(k)) continue;
    map.set(k, i);
  }
  const sorted = [...map.values()].sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));

  const per = new Map();
  const out = [];
  for (const i of sorted){
    const key = i.tech + ':' + i.sourceId;
    const n = per.get(key) || 0;
    if (n >= (CAPS[i.sourceId] ?? 999)) continue;
    per.set(key, n + 1);
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
  if (min < 60) return rtf.format(-min, 'minute');
  const hr = Math.round(min / 60);
  if (hr < 24) return rtf.format(-hr, 'hour');
  const day = Math.round(hr / 24);
  if (day < 30) return rtf.format(-day, 'day');
  return rtf.format(-Math.round(day / 30), 'month');
}
const nf = new Intl.NumberFormat('ar-EG', { notation: 'compact', maximumFractionDigits: 1 });

const LEVEL_NAME = { beginner:'مبتدئ', intermediate:'متوسط', advanced:'متقدم' };
const KIND_NAME  = { course:'دورة كاملة', tutorial:'شرح', project:'مشروع', challenge:'تحدي', interview:'مقابلة عمل', news:'أداة / خبر' };

const isNew = i => i.date && new Date(i.date).getTime() > state.lastVisit;

function visible(){
  const q = state.q.trim().toLowerCase();
  const stage = STAGES.find(s => s.id === prefs.stage);

  let list = state.items.filter(i => {
    if (!prefs.techs.includes(i.tech)) return false;
    if (prefs.lang === 'ar' && i.lang !== 'ar') return false;
    if (prefs.lang === 'en' && i.lang !== 'en') return false;
    if (prefs.lang === 'translated' && !i.translated) return false;
    if (prefs.level !== 'all' && i.level !== prefs.level) return false;
    if (prefs.kind !== 'all' && i.kind !== prefs.kind) return false;
    if (prefs.source !== 'all' && i.sourceId !== prefs.source) return false;
    if (prefs.stageOnly && stage?.id && !(i.stages || []).includes(stage.id)) return false;
    if (q && !`${i.title} ${i.summary || ''} ${i.source}`.toLowerCase().includes(q)) return false;
    return true;
  });

  const num = v => typeof v === 'number' ? v : -1;
  const byDate = (a, b) => new Date(b.date || 0) - new Date(a.date || 0);
  const score  = i => num(i.rating) * Math.log10(1 + num(i.raters || 0));   // تقييم مرجّح بعدد المقيّمين
  const COMPARE = {
    date:   byDate,
    points: (a, b) => num(b.points) - num(a.points) || byDate(a, b),
    views:  (a, b) => num(b.views)  - num(a.views)  || byDate(a, b),
    rating: (a, b) => score(b) - score(a) || byDate(a, b),
  };

  list.sort(COMPARE[prefs.sort] || byDate);

  // ترقية محتوى المرحلة الحالية إلى الأعلى (دون إخفاء الباقي)
  if (stage?.id && !prefs.stageOnly){
    const inStage = list.filter(i => (i.stages || []).includes(stage.id));
    const rest    = list.filter(i => !(i.stages || []).includes(stage.id));
    list = [...inStage, ...rest];
  }
  return list;
}

function render(){
  const items = visible();
  const list = $('#list');
  list.textContent = '';
  for (const i of items.slice(0, state.shown)) list.appendChild(card(i));

  $('#empty').hidden = items.length > 0 || state.loading;
  $('#btn-more').hidden = items.length <= state.shown;

  const fresh = items.filter(isNew).length;
  $('#meta').textContent = state.updatedAt
    ? `${items.length} نتيجة${fresh ? ` · ${fresh} جديد` : ''} · آخر تحديث ${ago(new Date(state.updatedAt).toISOString())}`
    : '';

  renderTechChips();
  renderSourceChips();
  renderActiveFilters();
  renderBadges();
}

function card(i){
  const c = el('div', 'card');
  const st = state.library[i.url]?.state;
  if (st === 'done') c.classList.add('is-done');

  const main = el('div', 'card-main');
  if (i.thumb){
    const im = el('img', 'thumb');
    im.src = i.thumb; im.alt = ''; im.loading = 'lazy';
    im.onerror = () => im.remove();
    main.appendChild(im);
  }

  const body = el('div');
  body.style.minWidth = '0';
  const a = el('a', 't');
  a.href = i.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
  a.textContent = i.title;
  body.appendChild(a);

  if (i.summary){
    const s = el('div', 's');
    s.textContent = i.summary;
    body.appendChild(s);
  }
  main.appendChild(body);
  c.appendChild(main);

  const row = el('div', 'row');
  const add = (cls, text) => { const t = el('span', 'tag ' + cls); t.textContent = text; row.appendChild(t); };

  if (isNew(i)) add('new', 'جديد');
  add(i.lang, i.lang === 'ar' ? 'عربي' : (i.translated ? 'مترجم' : 'إنجليزي'));
  if (i.level) add(i.level, LEVEL_NAME[i.level]);
  if (i.kind)  add('kind', KIND_NAME[i.kind]);

  const src = el('span', 'src'); src.textContent = i.source; row.appendChild(src);
  if (i.date){
    const d = el('span', 'dot'); d.textContent = '•'; row.appendChild(d);
    const t = el('span', 'time'); t.textContent = ago(i.date); row.appendChild(t);
  }

  const metric = i.views  ? `👁 ${nf.format(i.views)}`
               : i.rating ? `★ ${i.rating.toFixed(1)}`
               : i.points ? `▲ ${nf.format(i.points)}` : '';
  if (metric){ const m = el('span', 'metric'); m.textContent = metric; row.appendChild(m); }
  c.appendChild(row);

  const acts = el('div', 'card-actions');
  acts.appendChild(actBtn('star', '★', st === 'saved', 'حفظ', () => setShelf(i, 'saved')));
  acts.appendChild(actBtn('later', '⏱', st === 'later', 'أشاهده لاحقاً', () => setShelf(i, 'later')));
  acts.appendChild(actBtn('done', '✓', st === 'done', 'أنهيته', () => setShelf(i, 'done')));
  c.appendChild(acts);

  return c;
}

function actBtn(cls, glyph, on, label, onClick){
  const b = el('button', 'act ' + cls + (on ? ' on' : ''));
  b.textContent = glyph;
  b.setAttribute('aria-label', label);
  b.onclick = onClick;
  return b;
}

function setShelf(item, shelf){
  const cur = state.library[item.url];
  if (cur?.state === shelf) delete state.library[item.url];
  else state.library[item.url] = { state: shelf, at: Date.now(), item };
  save(LIB_KEY, state.library);
  render();
  if ($('#library-dlg').open) renderLibrary();
}

function renderTechChips(){
  const wrap = $('#tech-chips');
  wrap.textContent = '';
  for (const t of TECHS){
    const on = prefs.techs.includes(t.id);
    const b = el('button', 'chip' + (on ? ' is-on' : ''));
    b.textContent = t.name;
    b.onclick = () => {
      const i = prefs.techs.indexOf(t.id);
      if (i >= 0){ if (prefs.techs.length > 1) prefs.techs.splice(i, 1); }
      else prefs.techs.push(t.id);
      savePrefs();
      state.shown = PAGE_SIZE;
      render();
      refresh(true);
    };
    wrap.appendChild(b);
  }
}

function renderSourceChips(){
  const wrap = $('#source-chips');
  const counts = new Map();
  for (const i of state.items){
    if (!prefs.techs.includes(i.tech)) continue;
    counts.set(i.sourceId, (counts.get(i.sourceId) || 0) + 1);
  }
  const names = { hn:'Hacker News', devto:'DEV.to', so:'Stack Overflow', github:'GitHub',
                  pypi:'PyPI', 'ar-news':'مقالات عربية', 'ar-yt':'فيديوهات عربية',
                  blogs:'مدونات', reddit:'Reddit', fcc:'freeCodeCamp' };

  wrap.textContent = '';
  const defs = [{ id:'all', name:'كل المصادر' },
    ...[...counts.entries()].sort((a, b) => b[1] - a[1])
      .map(([id, n]) => ({ id, name:`${names[id] || id} (${n})` }))];

  for (const d of defs){
    const b = el('button', 'chip' + (prefs.source === d.id ? ' is-on' : ''));
    b.textContent = d.name;
    b.onclick = () => { prefs.source = d.id; savePrefs(); state.shown = PAGE_SIZE; render(); };
    wrap.appendChild(b);
  }
}

function renderActiveFilters(){
  const wrap = $('#active-filters');
  wrap.textContent = '';
  const pills = [];
  if (prefs.level !== 'all')  pills.push([LEVEL_NAME[prefs.level], () => prefs.level = 'all']);
  if (prefs.kind !== 'all')   pills.push([KIND_NAME[prefs.kind],   () => prefs.kind = 'all']);
  if (prefs.source !== 'all') pills.push(['مصدر محدّد',            () => prefs.source = 'all']);
  if (prefs.sort !== 'date')  pills.push([{ points:'الأكثر تفاعلاً', views:'الأكثر مشاهدة', rating:'الأعلى تقييماً' }[prefs.sort],
                                          () => prefs.sort = 'date']);
  if (prefs.stage){
    const s = STAGES.find(x => x.id === prefs.stage);
    pills.push([(prefs.stageOnly ? 'مرحلة: ' : 'أولوية: ') + s.name, () => { prefs.stage = ''; prefs.stageOnly = false; }]);
  }

  for (const [text, clear] of pills){
    const p = el('span', 'pill');
    p.append(text);
    const x = el('button');
    x.textContent = '×';
    x.onclick = () => { clear(); savePrefs(); syncControls(); render(); };
    p.appendChild(x);
    wrap.appendChild(p);
  }
}

function renderBadges(){
  const n = Object.keys(state.library).length;
  const lb = $('#lib-badge');
  lb.hidden = !n; lb.textContent = n;

  const active = (prefs.level !== 'all') + (prefs.kind !== 'all') + (prefs.source !== 'all')
               + (prefs.sort !== 'date') + (prefs.stage ? 1 : 0);
  const fb = $('#filter-badge');
  fb.hidden = !active; fb.textContent = active;
}

function renderLibrary(){
  const entries = Object.values(state.library)
    .filter(e => e.state === state.shelf)
    .sort((a, b) => b.at - a.at);

  const wrap = $('#shelf-list');
  wrap.textContent = '';
  if (!entries.length){
    const p = el('p', 'note');
    p.textContent = 'لا يوجد شيء هنا بعد.';
    wrap.appendChild(p);
  }
  for (const e of entries) wrap.appendChild(card(e.item));

  const done  = Object.values(state.library).filter(e => e.state === 'done');
  const later = Object.values(state.library).filter(e => e.state === 'later');
  const week  = done.filter(e => e.at > Date.now() - 7 * 864e5).length;
  const total = done.length + later.length;

  const box = $('#progress-box');
  box.textContent = '';
  const big = el('div', 'big'); big.textContent = done.length;
  const sub = el('div', 'sub');
  sub.textContent = `أنهيتها${week ? ` · ${week} هذا الأسبوع` : ''}${later.length ? ` · ${later.length} بانتظارك` : ''}`;
  box.append(big, sub);
  if (total){
    const bar = el('div', 'bar'); const fill = el('i');
    fill.style.width = Math.round(done.length / total * 100) + '%';
    bar.appendChild(fill); box.appendChild(bar);
  }

  for (const b of $('#shelf-chips').children) b.classList.toggle('is-on', b.dataset.shelf === state.shelf);
}

function skeletons(){
  const list = $('#list');
  list.textContent = '';
  for (let i = 0; i < 6; i++) list.appendChild(el('div', 'sk'));
}
const setStatus = t => { $('#status').textContent = t; };

/* ============================ الأحداث ============================ */

function chipGroup(sel, key, after){
  $(sel).addEventListener('click', e => {
    const b = e.target.closest('.chip');
    if (!b) return;
    prefs[key] = b.dataset[key];
    savePrefs();
    state.shown = PAGE_SIZE;
    syncControls();
    render();
    after?.();
  });
}
chipGroup('#lang-chips', 'lang');
chipGroup('#level-chips', 'level');
chipGroup('#kind-chips', 'kind');
chipGroup('#sort-chips', 'sort');

function syncControls(){
  const mark = (sel, key) => {
    for (const b of $(sel).children) b.classList.toggle('is-on', b.dataset[key] === prefs[key]);
  };
  mark('#lang-chips', 'lang');
  mark('#level-chips', 'level');
  mark('#kind-chips', 'kind');
  mark('#sort-chips', 'sort');
  $('#stage-select').value = prefs.stage;
  $('#stage-only').checked = prefs.stageOnly;
}

$('#btn-refresh').onclick = () => refresh(true);
$('#btn-more').onclick = () => { state.shown += PAGE_SIZE; render(); };

function resetFilters(){
  Object.assign(prefs, { lang:'all', level:'all', kind:'all', sort:'date', source:'all', stage:'', stageOnly:false });
  state.q = ''; $('#q').value = ''; $('#btn-clear').hidden = true;
  state.shown = PAGE_SIZE;
  savePrefs(); syncControls(); render();
}
$('#btn-reset').onclick = resetFilters;
$('#btn-reset2').onclick = resetFilters;

let qTimer;
$('#q').addEventListener('input', e => {
  state.q = e.target.value;
  $('#btn-clear').hidden = !state.q;
  clearTimeout(qTimer);
  qTimer = setTimeout(() => { state.shown = PAGE_SIZE; render(); }, 180);
});
$('#btn-clear').onclick = () => { $('#q').value = ''; state.q = ''; $('#btn-clear').hidden = true; render(); };

$('#btn-filters').onclick = () => { syncControls(); $('#filters-dlg').showModal(); };
$('#btn-library').onclick = () => { renderLibrary(); $('#library-dlg').showModal(); };
$('#btn-install').onclick = () => $('#install-dlg').showModal();

for (const dlg of document.querySelectorAll('dialog.sheet')){
  dlg.addEventListener('click', e => {
    if (e.target.closest('[data-close]') || e.target === dlg) dlg.close();
  });
}
$('#shelf-chips').addEventListener('click', e => {
  const b = e.target.closest('.chip');
  if (!b) return;
  state.shelf = b.dataset.shelf;
  renderLibrary();
});

$('#stage-select').addEventListener('change', e => {
  prefs.stage = e.target.value; savePrefs(); state.shown = PAGE_SIZE; render();
});
$('#stage-only').addEventListener('change', e => {
  prefs.stageOnly = e.target.checked; savePrefs(); state.shown = PAGE_SIZE; render();
});

// السحب للأسفل من أعلى الصفحة = تحديث
let touchY = 0;
addEventListener('touchstart', e => { touchY = e.touches[0].clientY; }, { passive: true });
addEventListener('touchend', e => {
  const dy = e.changedTouches[0].clientY - touchY;
  if (scrollY <= 0 && dy > 110) refresh(true);
}, { passive: true });

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') refresh(false);
});

/* ============================ التشغيل ============================ */

(async function boot(){
  const sel = $('#stage-select');
  for (const s of STAGES){
    const o = document.createElement('option');
    o.value = s.id; o.textContent = s.name;
    sel.appendChild(o);
  }

  try {
    const r = await timedFetch('proxy?ping=1', 1500);
    localProxyOK = r.ok && (await r.text()).trim() === 'pong';
  } catch { localProxyOK = false; }

  if (/iPad|iPhone|iPod/.test(navigator.userAgent) && !navigator.standalone)
    $('#btn-install').hidden = false;

  syncControls();
  await refresh(false);

  save(VISIT_KEY, Date.now());          // بعد أول عرض، حتى تظهر شارة "جديد" لهذه الجلسة
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
})();
