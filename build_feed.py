"""يبني لقطات المحتوى اليومية في مجلد data/ — ملف لكل لغة برمجة.

فائدته: عند رفع التطبيق على استضافة ثابتة (GitHub Pages) يقرأ المتصفح هذه
الملفات مباشرة بدون الحاجة إلى بروكسي، فيكون التحميل أسرع وأثبت.
يُشغَّل تلقائياً كل يوم عبر .github/workflows/daily.yml

التشغيل يدوياً:
    python build_feed.py             # كل اللغات
    python build_feed.py python sql  # لغات محددة

لا يحتاج أي مكتبات خارجية.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

DATA = Path(__file__).resolve().parent / "data"
CHANNELS_FILE = DATA / "channels.json"
MAX_PER_TECH = 220
AR_QUOTA = 110          # أقصى ما يُحجز للمحتوى العربي قبل تعبئة الباقي بالإنجليزي
TIMEOUT = 25

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

ARABIC = re.compile(r"[؀-ۿ]")
TAGS = re.compile(r"<[^>]+>")
NOISE = re.compile(r"ثعب|أفع|افع|سيارة|طائرة|صاروخ|دبابة|مسدس|كوبرا|حديقة الحيوان")
PROG = re.compile(
    r"برمج|مبرمج|لغة|كود|تطوير|تعلّ?م|دورة|كورس|شرح|مكتب(ة|ات)|تطبيق|مشروع"
    r"|بيانات|ذكاء اصطناعي|خوارزم|\bcode\b|\bprogramming\b",
    re.IGNORECASE,
)
CAPS = {"pypi": 15, "blogs": 50, "devto": 45, "hn": 40, "so": 30, "github": 25,
        "reddit": 30, "fcc": 20}

# قنوات يوتيوب عربية — تُحلّ معرّفاتها مرة واحدة وتُخزَّن في data/channels.json.
# تغذية القناة تحمل المشاهدات والتقييم والصورة، بخلاف نتائج البحث.
CHANNEL_HANDLES = [
    "ElzeroWebSchool", "Elzero", "codezillaa", "AdelNasim", "TheNewBaghdad",
    "tarmeezacademy", "Almdrasa", "MoslemDev", "Hassouna-Academy", "arabiccoders",
    "NourHomsi", "MuhammedEssa", "DevMohamedElsayed", "AhmedSamirDev",
]

# ----------------------------------------------------------------------------

TECHS = {
    "python": {
        "name": "بايثون", "hn": "python", "so": "python", "gh": "python",
        "devto": ["python", "django", "fastapi"], "reddit": ["Python", "learnpython"],
        "blogs": ["https://realpython.com/atom.xml", "https://planetpython.org/rss20.xml",
                  "https://blog.python.org/feeds/posts/default"],
        "ar": ['برمجة بايثون OR "تعلم بايثون" OR "لغة بايثون"',
               '"بايثون" (دورة OR شرح OR كورس OR مشروع)'],
        "match": r"\bpython\b|بايثون|بايثن|\bdjango\b|جانغو|\bflask\b|فلاسك|\bfastapi\b|\bpandas\b|\bnumpy\b",
        "pypi": True,
    },
    "javascript": {
        "name": "جافاسكربت", "hn": "javascript", "so": "javascript", "gh": "javascript",
        "devto": ["javascript", "react", "nodejs"], "reddit": ["javascript", "learnjavascript"],
        "blogs": [],
        "ar": ['"جافاسكربت" OR "جافا سكريبت" برمجة', '"جافاسكربت" (دورة OR شرح OR مشروع)'],
        "match": r"\bjavascript\b|\bjs\b|جافاسكربت|جافا سكريبت|\breact\b|\bnode\.?js\b|\btypescript\b|رياكت",
    },
    "sql": {
        "name": "SQL", "hn": "sql database", "so": "sql", "gh": "sql",
        "devto": ["sql", "database"], "reddit": ["SQL", "learnSQL"], "blogs": [],
        "ar": ['"قواعد البيانات" SQL تعلم', '"لغة SQL" شرح OR دورة'],
        "match": r"\bsql\b|\bpostgres\b|\bmysql\b|\bsqlite\b|قواعد البيانات|قاعدة بيانات",
    },
    "cpp": {
        "name": "C / C++", "hn": "c++", "so": "c%2B%2B", "gh": "c%2B%2B",
        "devto": ["cpp", "c"], "reddit": ["cpp", "C_Programming"], "blogs": [],
        "ar": ['"سي بلس بلس" OR "لغة سي" برمجة', '"++C" شرح OR دورة'],
        "match": r"\bc\+\+\b|\bcpp\b|سي بلس بلس|لغة سي\b",
    },
    "java": {
        "name": "جافا", "hn": "java", "so": "java", "gh": "java",
        "devto": ["java"], "reddit": ["java", "learnjava"], "blogs": [],
        "ar": ['"لغة جافا" برمجة OR تعلم', '"جافا" (دورة OR شرح) برمجة'],
        "match": r"\bjava\b(?!script)|لغة جافا",
    },
    "go": {
        "name": "Go", "hn": "golang", "so": "go", "gh": "go",
        "devto": ["go"], "reddit": ["golang"], "blogs": [],
        "ar": ['"لغة Go" OR "جولانج" برمجة'],
        "match": r"\bgolang\b|جولانج|لغة go",
    },
    "rust": {
        "name": "Rust", "hn": "rust", "so": "rust", "gh": "rust",
        "devto": ["rust"], "reddit": ["rust"], "blogs": [],
        "ar": ['"لغة رست" OR Rust برمجة'],
        "match": r"\brust\b|لغة رست|رست\b",
    },
    "bash": {
        "name": "Bash / Shell", "hn": "bash shell scripting", "so": "bash", "gh": "shell",
        "devto": ["bash", "linux"], "reddit": ["bash", "linuxadmin"], "blogs": [],
        "ar": ['"سطر الأوامر" لينكس سكربت', '"باش" OR "شل" برمجة لينكس'],
        "match": r"\bbash\b|\bshell\b|\bzsh\b|سطر الأوامر|سكربت|لينكس",
    },
}


def gnews(query: str, lang: str = "ar") -> str:
    q = urllib.parse.quote(query)
    if lang == "ar":
        return f"https://news.google.com/rss/search?q={q}&hl=ar&gl=EG&ceid=EG:ar"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def get(url: str, attempts: int = 3) -> bytes:
    """يجلب الرابط مع إعادة محاولة متدرّجة — مصادر البحث ترد 429 عند الضغط."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/xml, application/json;q=0.9, */*;q=0.5",
        "Accept-Language": "ar,en;q=0.8",
        "Accept-Encoding": "gzip",
    })
    last: Exception | None = None
    for n in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                data = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except Exception as e:  # noqa: BLE001, PERF203
            last = e
            if n < attempts - 1:
                time.sleep(3 * (n + 1))
    raise last  # type: ignore[misc]


def clean(text: str | None) -> str:
    if not text:
        return ""
    text = TAGS.sub(" ", text)
    text = re.sub(r"&(nbsp|amp|lt|gt|quot|#\d+);", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def iso(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    for parse in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            dt = parse(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:  # noqa: BLE001, PERF203
            continue
    return None


def tag_name(el: ET.Element) -> str:
    return el.tag.split("}")[-1]


MEDIA = "{http://search.yahoo.com/mrss/}"


def parse_feed(xml: bytes, source_id: str, source: str, tech: str,
               match: re.Pattern | None) -> list[dict]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []

    items: list[dict] = []
    for node in root.iter():
        if tag_name(node) not in ("item", "entry"):
            continue

        fields: dict[str, str] = {}
        link = ""
        for child in node:
            name = tag_name(child)
            if name == "link":
                link = link or (child.get("href") or (child.text or "").strip())
            elif name not in fields:
                fields[name] = child.text or ""

        title = clean(fields.get("title"))
        summary = clean(fields.get("description") or fields.get("summary") or fields.get("content"))[:240]
        if not title or not link:
            continue

        blob = title + " " + summary
        if match and not match.search(blob):
            continue
        if NOISE.search(blob) and not PROG.search(blob):
            continue

        via = ""
        if source_id.startswith("ar-"):
            m = re.match(r"^(.*)\s+[-–]\s+([^-–]{2,40})$", title)
            if m:
                title, via = m.group(1).strip(), m.group(2).strip()

        item = {
            "title": title,
            "url": link,
            "date": iso(fields.get("pubDate") or fields.get("published") or fields.get("updated")),
            "summary": summary,
            "tech": tech,
            "sourceId": source_id,
            "source": via or source,
            "lang": "ar" if ARABIC.search(title) else "en",
        }

        # تغذية قناة يوتيوب: مشاهدات وتقييم وصورة مصغّرة
        group = node.find(MEDIA + "group")
        if group is not None:
            stats = group.find(MEDIA + "community/" + MEDIA + "statistics")
            rating = group.find(MEDIA + "community/" + MEDIA + "starRating")
            thumb = group.find(MEDIA + "thumbnail")
            if stats is not None:
                item["views"] = int(stats.get("views") or 0)
            if rating is not None:
                item["rating"] = float(rating.get("average") or 0)
                item["raters"] = int(rating.get("count") or 0)
            if thumb is not None:
                item["thumb"] = thumb.get("url") or ""

        items.append(item)
    return items


# ----------------------- مصادر JSON -----------------------

def fetch_hn(tech: str, cfg: dict) -> list[dict]:
    since = int((datetime.now(timezone.utc) - timedelta(days=21)).timestamp())
    url = ("https://hn.algolia.com/api/v1/search_by_date?query="
           + urllib.parse.quote(cfg["hn"])
           + f"&tags=story&hitsPerPage=40&numericFilters=created_at_i>{since}")
    hits = json.loads(get(url)).get("hits", [])
    return [{
        "title": h["title"],
        "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
        "date": iso(h.get("created_at")),
        "summary": clean(h.get("story_text"))[:200],
        "points": h.get("points", 0),
        "tech": tech, "sourceId": "hn", "source": "Hacker News", "lang": "en",
    } for h in hits if h.get("title")]


def fetch_devto(tech: str, cfg: dict) -> list[dict]:
    out = []
    for tag in cfg["devto"]:
        try:
            arts = json.loads(get(f"https://dev.to/api/articles?tag={tag}&per_page=15"))
        except Exception:  # noqa: BLE001, PERF203
            continue
        for a in arts:
            out.append({
                "title": a["title"], "url": a["url"], "date": iso(a.get("published_at")),
                "summary": (a.get("description") or "")[:220],
                "points": a.get("positive_reactions_count", 0),
                "tech": tech, "sourceId": "devto", "source": "DEV.to",
                "lang": "ar" if ARABIC.search(a["title"]) else "en",
            })
    return out


def fetch_so(tech: str, cfg: dict) -> list[dict]:
    frm = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    url = ("https://api.stackexchange.com/2.3/questions?order=desc&sort=votes"
           f"&tagged={cfg['so']}&site=stackoverflow&pagesize=30&fromdate={frm}")
    items = json.loads(get(url)).get("items", [])
    return [{
        "title": clean(q["title"]), "url": q["link"],
        "date": datetime.fromtimestamp(q["creation_date"], timezone.utc).isoformat(),
        "summary": "، ".join(q.get("tags", [])),
        "points": q.get("score", 0),
        "tech": tech, "sourceId": "so", "source": "Stack Overflow", "lang": "en",
    } for q in items]


def fetch_github(tech: str, cfg: dict) -> list[dict]:
    day = (datetime.now(timezone.utc) - timedelta(days=21)).date().isoformat()
    url = (f"https://api.github.com/search/repositories?q=language:{cfg['gh']}+pushed:>{day}"
           "&sort=stars&order=desc&per_page=25")
    items = json.loads(get(url)).get("items", [])
    return [{
        "title": r["full_name"], "url": r["html_url"], "date": iso(r.get("pushed_at")),
        "summary": r.get("description") or "", "points": r.get("stargazers_count", 0),
        "tech": tech, "sourceId": "github", "source": "GitHub", "lang": "en", "kind": "news",
    } for r in items]


def fetch_pypi(tech: str, cfg: dict) -> list[dict]:
    items = parse_feed(get("https://pypi.org/rss/updates.xml"), "pypi", "PyPI", tech, None)
    for i in items:
        i["kind"] = "news"
    return items[:20]


# ----------------------- قنوات يوتيوب -----------------------

ANY_PROG = re.compile(
    "|".join(cfg["match"] for cfg in TECHS.values())
    + r"|برمج|مبرمج|كود|تطوير الويب|خوارزم|\bprogramming\b|\bdeveloper\b|\bcoding\b",
    re.IGNORECASE,
)


def is_programming_channel(channel_id: str) -> bool:
    """يتأكد أن القناة تنشر محتوى برمجياً فعلاً — اسم القناة وحده غير كافٍ."""
    try:
        items = parse_feed(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"),
                           "ar-yt", "يوتيوب", "python", None)
    except Exception:  # noqa: BLE001
        return False
    if not items:
        return False
    hits = sum(1 for i in items if ANY_PROG.search(i["title"] + " " + i["summary"]))
    return hits >= max(3, len(items) // 4)


def resolve_channels() -> dict[str, str]:
    """يحوّل أسماء القنوات إلى معرّفات ويتحقق من محتواها، ويحفظ ما نجح.

    الملف يحفظ أيضاً القنوات المرفوضة (بقيمة فارغة) حتى لا تُعاد محاولتها كل يوم.
    """
    known: dict[str, str] = {}
    if CHANNELS_FILE.exists():
        try:
            known = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            known = {}

    for handle in CHANNEL_HANDLES:
        if handle in known:
            continue
        try:
            html = get(f"https://www.youtube.com/@{handle}", attempts=1).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001, PERF203
            continue                      # تعذّر الوصول — يُعاد غداً
        m = re.search(r'"channelId":"(UC[\w-]{20,})"', html)
        if not m:
            continue
        cid = m.group(1)
        if is_programming_channel(cid):
            known[handle] = cid
            print(f"  ✓ قناة برمجية: @{handle} -> {cid}")
        else:
            known[handle] = ""            # ليست قناة برمجة — تُستبعد نهائياً
            print(f"  ✗ استُبعدت: @{handle} (محتواها غير برمجي)")
        time.sleep(1)

    if known:
        DATA.mkdir(parents=True, exist_ok=True)
        CHANNELS_FILE.write_text(json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")

    return {h: cid for h, cid in known.items() if cid}


def fetch_channel(channel_id: str, tech: str, match: re.Pattern) -> list[dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    return parse_feed(get(url), "ar-yt", "يوتيوب", tech, match)


# ----------------------- التجميع -----------------------

def dedupe_key(item: dict) -> str:
    text = unicodedata.normalize("NFKC", item["title"]).lower()
    return re.sub(r"[^\w؀-ۿ]+", "", text)[:70]


def load_previous(tech: str) -> list[dict]:
    """محتوى آخر بناء ناجح لهذه اللغة، إن وُجد."""
    path = DATA / f"feed-{tech}.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        return []


def build_tech(tech: str, cfg: dict, channels: dict[str, str]) -> int:
    match = re.compile(cfg["match"], re.IGNORECASE)
    collected: list[dict] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [
            pool.submit(fetch_hn, tech, cfg),
            pool.submit(fetch_devto, tech, cfg),
            pool.submit(fetch_so, tech, cfg),
            pool.submit(fetch_github, tech, cfg),
        ]
        if cfg.get("pypi"):
            jobs.append(pool.submit(fetch_pypi, tech, cfg))

        for sub in cfg["reddit"]:
            jobs.append(pool.submit(
                lambda s=sub: parse_feed(get(f"https://www.reddit.com/r/{s}/hot/.rss?limit=25"),
                                         "reddit", f"r/{s}", tech, None)))
        for url in cfg["blogs"]:
            jobs.append(pool.submit(
                lambda u=url: parse_feed(get(u), "blogs", "مدونات", tech, None)))
        # freeCodeCamp تغطي كل اللغات — تُرشَّح حسب لغة البرمجة الحالية
        jobs.append(pool.submit(
            lambda: parse_feed(get("https://www.freecodecamp.org/news/rss/"),
                               "fcc", "freeCodeCamp", tech, match)))
        for cid in channels.values():
            jobs.append(pool.submit(fetch_channel, cid, tech, match))

        for job in jobs:
            try:
                collected.extend(job.result())
            except Exception as e:  # noqa: BLE001, PERF203
                print(f"  [{tech}] تخطّي مصدر: {e}")

    # بحث أخبار جوجل يُنفَّذ بالتتابع — الطلبات المتوازية على نفس المضيف تُقابَل بـ 429
    ar_queries = [(q, "ar-news", "مقالات عربية") for q in cfg["ar"]]
    ar_queries.append((cfg["ar"][0] + " site:youtube.com", "ar-yt", "فيديوهات ودروس"))
    for query, sid, sname in ar_queries:
        try:
            collected.extend(parse_feed(get(gnews(query)), sid, sname, tech, match))
        except Exception as e:  # noqa: BLE001, PERF203
            print(f"  [{tech}] تخطّي بحث عربي: {e}")
        time.sleep(1.5)

    # نضمّ محتوى الملف السابق: تعثّر شبكي في تشغيل واحد يجب ألّا يمسح ما نُشر
    previous = load_previous(tech)
    if previous:
        print(f"  [{tech}] ضمّ {len(previous)} عنصراً من الملف السابق")
    collected.extend(previous)

    seen: dict[str, dict] = {}
    per_source: dict[str, int] = {}
    for item in sorted(collected, key=lambda i: i.get("date") or "", reverse=True):
        key = dedupe_key(item)
        if not key or key in seen:
            continue
        sid = item["sourceId"]
        if per_source.get(sid, 0) >= CAPS.get(sid, 999):
            continue
        per_source[sid] = per_source.get(sid, 0) + 1
        seen[key] = item

    # المحتوى العربي أندر بكثير — نضمن له حصة قبل أن تزحمه المصادر الإنجليزية الغزيرة
    ordered = list(seen.values())
    arabic = [i for i in ordered if i["lang"] == "ar"][:AR_QUOTA]
    english = [i for i in ordered if i["lang"] != "ar"][:MAX_PER_TECH - len(arabic)]
    items = sorted(arabic + english, key=lambda i: i.get("date") or "", reverse=True)
    ar = len(arabic)

    if not items:
        print(f"{cfg['name']:<14} فشل الجلب — أُبقي الملف السابق كما هو")
        return 0

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / f"feed-{tech}.json").write_text(json.dumps(
        {"generated": datetime.now(timezone.utc).isoformat(), "tech": tech,
         "count": len(items), "items": items},
        ensure_ascii=False, indent=1,
    ), encoding="utf-8")

    print(f"{cfg['name']:<14} {len(items):>4} عنصر  ({ar} عربي / {len(items) - ar} إنجليزي)")
    return len(items)


def main() -> None:
    wanted = [a for a in sys.argv[1:] if a in TECHS] or list(TECHS)
    print("حلّ معرّفات قنوات يوتيوب…")
    channels = resolve_channels()
    print(f"  قنوات متاحة: {len(channels)}\n")

    total = 0
    for tech in wanted:
        total += build_tech(tech, TECHS[tech], channels)

    (DATA / "index.json").write_text(json.dumps(
        {"generated": datetime.now(timezone.utc).isoformat(),
         "techs": [{"id": t, "name": TECHS[t]["name"]} for t in wanted]},
        ensure_ascii=False, indent=1,
    ), encoding="utf-8")

    print(f"\nالمجموع: {total} عنصر في {len(wanted)} لغة.")


if __name__ == "__main__":
    main()
