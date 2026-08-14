"""يبني ملف data/feed.json — لقطة يومية جاهزة من محتوى بايثون بالعربي والإنجليزي.

فائدته: عند رفع التطبيق على استضافة ثابتة (GitHub Pages مثلاً) يقرأ المتصفح
هذا الملف مباشرة بدون الحاجة إلى بروكسي، فيكون التحميل أسرع وأثبت.
يُشغَّل تلقائياً كل يوم عبر .github/workflows/daily.yml

التشغيل يدوياً:
    python build_feed.py

لا يحتاج أي مكتبات خارجية.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
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

OUT = Path(__file__).resolve().parent / "data" / "feed.json"
MAX_ITEMS = 400
TIMEOUT = 25

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

RELEVANT = re.compile(
    r"\bpython\b|بايثون|بايثن|\bdjango\b|جانغو|\bflask\b|فلاسك|\bfastapi\b"
    r"|\bpandas\b|\bnumpy\b|\bpytorch\b|\bstreamlit\b",
    re.IGNORECASE,
)
ARABIC = re.compile(r"[؀-ۿ]")
TAGS = re.compile(r"<[^>]+>")

# "بايثون" اسم ثعبان وسيارة أيضاً — نستبعد هذه الأخبار ما لم تحمل إشارة برمجية واضحة
NOISE = re.compile(r"ثعب|أفع|افع|حي(ة|ات)\s|سيارة|طائرة|صاروخ|دبابة|مسدس|كوبرا|حديقة الحيوان")
PROG = re.compile(
    r"برمج|مبرمج|لغة|كود|تطوير|تعلّ?م|دورة|كورس|شرح|مكتب(ة|ات)|تطبيق|مشروع"
    r"|بيانات|ذكاء اصطناعي|خوارزم|\bpython\b|\bcode\b|\bai\b",
    re.IGNORECASE,
)
# أقصى عدد عناصر لكل مصدر حتى لا يطغى مصدر واحد على البقية
CAPS = {"pypi": 25, "blogs": 60, "devto": 45, "hn": 40, "so": 30, "github": 25, "reddit": 30}


def gnews(query: str, lang: str) -> str:
    q = urllib.parse.quote(query)
    if lang == "ar":
        return f"https://news.google.com/rss/search?q={q}&hl=ar&gl=EG&ceid=EG:ar"
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


# (رابط، معرّف المصدر، اسم المصدر، هل نتحقق من صلة المحتوى ببايثون)
FEEDS = [
    (gnews('برمجة بايثون OR "تعلم بايثون" OR "لغة بايثون"', "ar"), "ar-news", "مقالات عربية", True),
    (gnews('"بايثون" (دورة OR شرح OR كورس OR مشروع)', "ar"), "ar-news", "مقالات عربية", True),
    (gnews("بايثون (جانغو OR فلاسك OR الذكاء الاصطناعي)", "ar"), "ar-news", "مقالات عربية", True),
    (gnews("بايثون site:youtube.com", "ar"), "ar-yt", "فيديوهات ودروس", True),
    ("https://www.bing.com/news/search?q=%D8%A8%D8%B1%D9%85%D8%AC%D8%A9+%D8%A8%D8%A7%D9%8A%D8%AB%D9%88%D9%86&format=RSS",
     "ar-news", "مقالات عربية", True),
    ("https://realpython.com/atom.xml", "blogs", "Real Python", False),
    ("https://planetpython.org/rss20.xml", "blogs", "Planet Python", False),
    ("https://blog.python.org/feeds/posts/default", "blogs", "Python Blog", False),
    ("https://www.reddit.com/r/Python/hot/.rss?limit=25", "reddit", "r/Python", False),
    ("https://www.reddit.com/r/learnpython/hot/.rss?limit=25", "reddit", "r/learnpython", False),
    ("https://pypi.org/rss/updates.xml", "pypi", "PyPI", False),
]


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/xml, application/json;q=0.9, */*;q=0.5",
        "Accept-Language": "ar,en;q=0.8",
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data


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


def parse_feed(xml: bytes, source_id: str, source: str, check: bool) -> list[dict]:
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
        summary = clean(fields.get("description") or fields.get("summary") or fields.get("content"))[:260]
        if not title or not link:
            continue
        blob = title + " " + summary
        if check and not RELEVANT.search(blob):
            continue
        if NOISE.search(blob) and not PROG.search(blob):
            continue

        via = ""
        if source_id.startswith("ar-"):
            m = re.match(r"^(.*)\s+[-–]\s+([^-–]{2,40})$", title)
            if m:
                title, via = m.group(1).strip(), m.group(2).strip()

        items.append({
            "title": title,
            "url": link,
            "date": iso(fields.get("pubDate") or fields.get("published") or fields.get("updated")),
            "summary": summary,
            "sourceId": source_id,
            "source": via or source,
            "lang": "ar" if ARABIC.search(title) else "en",
        })
    return items


# ----------------------- مصادر JSON -----------------------

def fetch_hn() -> list[dict]:
    since = int((datetime.now(timezone.utc) - timedelta(days=14)).timestamp())
    url = ("https://hn.algolia.com/api/v1/search_by_date?query=python&tags=story"
           f"&hitsPerPage=40&numericFilters=created_at_i>{since}")
    hits = json.loads(get(url)).get("hits", [])
    return [{
        "title": h["title"],
        "url": h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}",
        "date": iso(h.get("created_at")),
        "summary": clean(h.get("story_text"))[:200],
        "points": h.get("points", 0),
        "sourceId": "hn", "source": "Hacker News", "lang": "en",
    } for h in hits if h.get("title")]


def fetch_devto() -> list[dict]:
    out = []
    for tag in ("python", "django", "fastapi"):
        try:
            arts = json.loads(get(f"https://dev.to/api/articles?tag={tag}&per_page=15"))
        except Exception:  # noqa: BLE001, PERF203
            continue
        for a in arts:
            out.append({
                "title": a["title"],
                "url": a["url"],
                "date": iso(a.get("published_at")),
                "summary": (a.get("description") or "")[:220],
                "points": a.get("positive_reactions_count", 0),
                "sourceId": "devto", "source": "DEV.to",
                "lang": "ar" if ARABIC.search(a["title"]) else "en",
            })
    return out


def fetch_so() -> list[dict]:
    frm = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    url = ("https://api.stackexchange.com/2.3/questions?order=desc&sort=votes&tagged=python"
           f"&site=stackoverflow&pagesize=30&fromdate={frm}")
    items = json.loads(get(url)).get("items", [])
    return [{
        "title": clean(q["title"]),
        "url": q["link"],
        "date": datetime.fromtimestamp(q["creation_date"], timezone.utc).isoformat(),
        "summary": "، ".join(q.get("tags", [])),
        "points": q.get("score", 0),
        "sourceId": "so", "source": "Stack Overflow", "lang": "en",
    } for q in items]


def fetch_github() -> list[dict]:
    day = (datetime.now(timezone.utc) - timedelta(days=21)).date().isoformat()
    url = (f"https://api.github.com/search/repositories?q=language:python+pushed:>{day}"
           "&sort=stars&order=desc&per_page=25")
    items = json.loads(get(url)).get("items", [])
    return [{
        "title": r["full_name"],
        "url": r["html_url"],
        "date": iso(r.get("pushed_at")),
        "summary": r.get("description") or "",
        "points": r.get("stargazers_count", 0),
        "sourceId": "github", "source": "GitHub", "lang": "en",
    } for r in items]


# ----------------------- التجميع -----------------------

def dedupe_key(item: dict) -> str:
    text = unicodedata.normalize("NFKC", item["title"]).lower()
    return re.sub(r"[^\w؀-ۿ]+", "", text)[:70]


def sort_key(item: dict) -> str:
    return item.get("date") or ""


def main() -> None:
    jobs = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for url, sid, name, check in FEEDS:
            jobs.append(pool.submit(lambda u=url, s=sid, n=name, c=check:
                                    parse_feed(get(u), s, n, c)))
        for fn in (fetch_hn, fetch_devto, fetch_so, fetch_github):
            jobs.append(pool.submit(fn))

        collected: list[dict] = []
        for job in jobs:
            try:
                collected.extend(job.result())
            except Exception as e:  # noqa: BLE001, PERF203
                print(f"  تخطّي مصدر: {e}")

    seen: dict[str, dict] = {}
    per_source: dict[str, int] = {}
    for item in sorted(collected, key=sort_key, reverse=True):
        key = dedupe_key(item)
        if not key or key in seen:
            continue
        sid = item["sourceId"]
        if per_source.get(sid, 0) >= CAPS.get(sid, 999):
            continue
        per_source[sid] = per_source.get(sid, 0) + 1
        seen[key] = item

    items = list(seen.values())[:MAX_ITEMS]
    ar = sum(1 for i in items if i["lang"] == "ar")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"generated": datetime.now(timezone.utc).isoformat(), "count": len(items), "items": items},
        ensure_ascii=False, indent=1,
    ), encoding="utf-8")

    print(f"تم إنشاء {OUT} — {len(items)} عنصر ({ar} عربي / {len(items) - ar} إنجليزي)")


if __name__ == "__main__":
    main()
