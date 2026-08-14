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
PODCAST_QUOTA = 10      # حصة البودكاست، وإلا أزاحته عناصر اليوم الأحدث
TIMEOUT = 25

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

ARABIC = re.compile(r"[؀-ۿ]")
TAGS = re.compile(r"<[^>]+>")
NOISE = re.compile(r"ثعب|أفع|افع|سيارة|طائرة|صاروخ|دبابة|مسدس|كوبرا|حديقة الحيوان")
# أسماء اللغات تشترك مع أشياء كثيرة بالإنجليزية (Python ثعبان، Swift مغنية،
# Ruby حجر كريم) — فلتر الضوضاء العربي وحده كان يترك هذه النتائج تمرّ.
NOISE_EN = re.compile(
    r"ball python|python (snake|morph|breed)|snakes?|reptiles?|terrarium|boa constrictor|pet (care|shop|store)|breeder|taylor swift|gemstones?|jewel(ry|lery)|necklace|espresso|recipes?|coffee bean|workouts?|horoscope|zodiac|movie|casino|fishing|hunting",
    re.IGNORECASE,
)
STRONG_PROG_EN = re.compile(
    r"\bprogramming\b|\bcode\b|\bcoding\b|\bdeveloper\b|\bsoftware\b|\bframework\b|\bfunctions?\b|\bapi\b|\bcompiler\b|\bscript(ing)?\b|\bsyntax\b|\bdebug|\balgorithm|\bdatabase\b|\bserver\b|\bapp\b",
    re.IGNORECASE,
)
PROG = re.compile(
    r"برمج|مبرمج|لغة|كود|تطوير|تعلّ?م|دورة|كورس|شرح|مكتب(ة|ات)|تطبيق|مشروع"
    r"|بيانات|ذكاء اصطناعي|خوارزم|\bcode\b|\bprogramming\b",
    re.IGNORECASE,
)
CAPS = {"ar-yt": 160, "yt": 70, "blogs": 40, "devto": 35, "fcc": 15,
        "medium": 15, "podcast": 12}
# المصادر التعليمية المسموح بها — ما عداها يُستبعد (أخبار ونقاش ومستودعات)
EDU_SOURCES = {"blogs", "devto", "fcc", "yt", "ar-yt", "medium", "podcast"}

# قنوات يوتيوب — مصدر المشاهدات والتقييم (تغذية القناة تحملها، بخلاف نتائج البحث).
#
# أضِف قنواتك هنا بأي صيغة:
#   "@ElzeroWebSchool"                                  اسم القناة
#   "UC8OxKsmAyrGAfBiluhpLkbA"                          المعرّف مباشرة
#   "https://www.youtube.com/@SomeChannel"              رابط كامل
#   "https://www.youtube.com/channel/UCxxxxxxxxxxxx"    رابط بالمعرّف
#
# ملاحظة: لا تُخمَّن الأسماء — اسم القناة على يوتيوب قد يعود لقناة مختلفة تماماً
# (‏@Codezilla مثلاً قناة فلوجات لا برمجة). انسخ الرابط من القناة نفسها.
CHANNELS: list[str] = [
    # Arabic Competitive Programming — د. مصطفى سعد إبراهيم (خوارزميات وهياكل بيانات و C++)
    "https://www.youtube.com/channel/UC8OxKsmAyrGAfBiluhpLkbA",
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
        "medium": "python",
        "podcasts": ["https://talkpython.fm/episodes/rss", "https://pythonbytes.fm/episodes/rss"],
    },
    "javascript": {
        "name": "جافاسكربت", "hn": "javascript", "so": "javascript", "gh": "javascript",
        "devto": ["javascript", "react", "nodejs"], "reddit": ["javascript", "learnjavascript"],
        "blogs": [],
        "ar": ['"جافاسكربت" OR "جافا سكريبت" برمجة', '"جافاسكربت" (دورة OR شرح OR مشروع)'],
        "match": r"\bjavascript\b|\bjs\b|جافاسكربت|جافا سكريبت|\breact\b|\bnode\.?js\b|\btypescript\b|رياكت",
        "medium": "javascript",
        "podcasts": ["https://feed.syntax.fm/rss"],
    },
    "sql": {
        "name": "SQL", "hn": "sql", "so": "sql", "gh": "sql",
        "devto": ["sql", "database"], "reddit": ["SQL", "learnSQL"], "blogs": [],
        "ar": ['"قواعد البيانات" SQL تعلم', '"لغة SQL" شرح OR دورة'],
        "match": (r"\bsql\b|\bpostgres\b|\bmysql\b|\bsqlite\b|\bdatabases?\b|\borm\b"
                  r"|قواعد البيانات|قاعدة بيانات"),
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
    "cyber": {
        "name": "أمن سيبراني", "hn": "cybersecurity", "so": "security", "gh": "",
        "devto": ["security", "cybersecurity", "hacking"],
        "reddit": ["netsec", "HowToHack", "AskNetsec"], "blogs": [],
        "ar": ['"الأمن السيبراني" (اختبار اختراق OR "كالي لينكس" OR "اختراق أخلاقي")',
               '"أمن المعلومات" (دورة OR شرح OR مشروع) اختراق'],
        "match": (r"أمن سيبراني|أمن المعلومات|اختراق|كالي لينكس|اختبار اختراق|ثغر|تشفير"
                  r"|\bsecurity\b|\bpentest|\bkali\b|tryhackme|hack ?the ?box|\bctf\b|\bnmap\b"
                  r"|metasploit|burp ?suite|\bowasp\b|\bxss\b|sql ?injection|\bmalware\b|\bforensics\b"),
        "medium": "cybersecurity",
        "podcasts": ["https://feeds.megaphone.fm/darknetdiaries"],
    },
    "bash": {
        "name": "الطرفية و Bash", "hn": "bash", "so": "bash", "gh": "shell",
        "devto": ["bash", "linux"], "reddit": ["bash", "commandline", "linuxadmin"], "blogs": [],
        "ar": ['"سطر الأوامر" لينكس سكربت', '"باش" OR "الطرفية" OR "تيرمنال" شرح'],
        "match": (r"\bbash\b|\bshell\b|\bzsh\b|\bterminal\b|سطر الأوامر|الطرفية|تيرمنال"
                  r"|سكربت|\bgrep\b|\bsed\b|\bawk\b|\btmux\b|\bvim\b"),
        "medium": "bash",
    },
    "csharp": {
        "name": "‏#C و‏.NET", "hn": "dotnet", "so": "c%23", "gh": "c%23",
        "devto": ["csharp", "dotnet"], "reddit": ["csharp", "dotnet"], "blogs": [],
        "ar": ['"سي شارب" OR "#C" برمجة', '"دوت نت" OR ".NET" دورة OR شرح'],
        "match": r"\bc#|c ?sharp|\.net\b|dotnet|سي شارب|\bunity\b|يونيتي|\bblazor\b|\basp\.net",
        "medium": "csharp",
    },
    "php": {
        "name": "PHP", "hn": "php", "so": "php", "gh": "php",
        "devto": ["php", "laravel"], "reddit": ["PHP", "laravel"], "blogs": [],
        "ar": ['"بي اتش بي" OR "PHP" برمجة موقع', '"لارافيل" OR "Laravel" دورة OR شرح'],
        "match": r"\bphp\b|laravel|لارافيل|بي ?اتش ?بي|\bwordpress\b|ووردبريس|symfony",
        "medium": "php",
    },
    "ruby": {
        "name": "Ruby", "hn": "ruby", "so": "ruby", "gh": "ruby",
        "devto": ["ruby", "rails"], "reddit": ["ruby", "rails"], "blogs": [],
        "ar": ['"لغة روبي" OR Ruby برمجة'],
        "match": r"\bruby\b|\brails\b|روبي",
        "medium": "ruby",
    },
    "swift": {
        "name": "Swift للآيفون", "hn": "swift", "so": "swift", "gh": "swift",
        "devto": ["swift", "ios"], "reddit": ["swift", "iOSProgramming"], "blogs": [],
        "ar": ['"تطبيقات الآيفون" OR "سويفت" برمجة', '"iOS" تطوير تطبيقات دورة OR شرح'],
        "match": r"\bswift(ui)?\b|\bios\b|\bxcode\b|سويفت|الآيفون|الايفون|تطبيقات ابل|\bapp ?store\b",
        "medium": "ios-app-development",
    },
    "kotlin": {
        "name": "Kotlin للأندرويد", "hn": "kotlin", "so": "kotlin", "gh": "kotlin",
        "devto": ["kotlin", "android"], "reddit": ["Kotlin", "androiddev"], "blogs": [],
        "ar": ['"تطبيقات الأندرويد" برمجة كوتلن', '"أندرويد" تطوير تطبيقات دورة OR شرح'],
        "match": r"\bkotlin\b|\bandroid\b|كوتلن|أندرويد|اندرويد|jetpack ?compose|android ?studio",
        "medium": "android",
    },
    "flutter": {
        "name": "Flutter", "hn": "flutter", "so": "flutter", "gh": "dart",
        "devto": ["flutter", "dart"], "reddit": ["FlutterDev"], "blogs": [],
        "ar": ['"فلاتر" OR Flutter تطبيقات برمجة', '"دارت" OR Dart لغة شرح'],
        "match": r"\bflutter\b|\bdart\b|فلاتر|دارت",
        "medium": "flutter",
    },
    "windows": {
        "name": "ويندوز و PowerShell", "hn": "powershell", "so": "powershell", "gh": "powershell",
        "devto": ["powershell", "windows"], "reddit": ["PowerShell", "sysadmin", "Windows10"], "blogs": [],
        "ar": ['"باور شيل" OR PowerShell ويندوز شرح', '"ويندوز" (سطر الأوامر OR سكربت OR أتمتة)'],
        "match": (r"powershell|باور ?شيل|\bwindows\b|ويندوز|\bwsl\b|\bcmd\b|\bwinget\b"
                  r"|\.bat\b|active directory"),
        "medium": "powershell",
    },
    "linux": {
        "name": "لينكس وتوزيعاته", "hn": "linux", "so": "linux", "gh": "",
        "devto": ["linux", "ubuntu"], "reddit": ["linux", "linux4noobs", "archlinux", "Ubuntu"], "blogs": [],
        "ar": ['"لينكس" (توزيعة OR شرح OR دورة)', '"أوبونتو" OR "أرش لينكس" OR "ديبيان" شرح'],
        "match": (r"\blinux\b|لينكس|\bubuntu\b|أوبونتو|اوبونتو|debian|ديبيان|\barch\b|أرش"
                  r"|fedora|فيدورا|centos|\bmint\b|توزيع|\bsystemd\b|\bgrub\b"),
        "medium": "linux",
    },
    "kali": {
        "name": "كالي وأدوات الاختراق", "hn": "kali linux", "so": "", "gh": "",
        "devto": ["hacking", "security", "pentesting"],
        "reddit": ["Kalilinux", "HowToHack", "oscp", "AskNetsec"], "blogs": [],
        "ar": ['"كالي لينكس" أدوات اختبار الاختراق شرح',
               '"اختراق أخلاقي" (nmap OR metasploit OR burp) شرح'],
        "match": (r"كالي|\bkali\b|\bnmap\b|metasploit|\bmsfvenom\b|burp ?suite|wireshark|aircrack"
                  r"|\bhydra\b|john the ripper|sqlmap|\bnikto\b|hashcat|\bgobuster\b|\bnetcat\b"
                  r"|أدوات اختراق|اختبار الاختراق"),
        "medium": "penetration-testing",
        "podcasts": ["https://feeds.megaphone.fm/darknetdiaries"],
    },
    "typescript": {
        "name": "TypeScript", "hn": "typescript", "so": "", "gh": "",
        "devto": ["typescript"], "reddit": [], "blogs": [],
        "ar": ['"تايب سكريبت" OR TypeScript شرح OR دورة'],
        "match": r"\btypescript\b|تايب ?سكريبت|تايب ?سكربت|\bts\b تايب",
        "medium": "typescript",
    },
    "web": {
        "name": "HTML و CSS", "hn": "html css", "so": "", "gh": "",
        "devto": ["html", "css", "webdev"], "reddit": [], "blogs": [],
        "ar": ['"HTML" OR "CSS" تصميم موقع شرح', '"تصميم المواقع" HTML CSS دورة'],
        "match": r"\bhtml\b|\bcss\b|\bsass\b|\bscss\b|tailwind|bootstrap|تصميم موقع|تصميم المواقع|واجهة أمامية|frontend",
        "medium": "css",
    },
    "reactnative": {
        "name": "React Native", "hn": "react native", "so": "", "gh": "",
        "devto": ["reactnative", "react"], "reddit": [], "blogs": [],
        "ar": ['"رياكت نيتف" OR "React Native" تطبيقات شرح'],
        "match": r"react ?native|رياكت ?نيتف",
        "medium": "react-native",
    },
    "lua": {
        "name": "Lua", "hn": "lua", "so": "", "gh": "",
        "devto": ["lua"], "reddit": [], "blogs": [],
        "ar": ['"لغة لوا" OR Lua برمجة شرح'],
        "match": r"\blua\b|لغة لوا|\broblox\b|\blove2d\b",
        "medium": "lua",
    },
    "r": {
        "name": "R للإحصاء", "hn": "rstats", "so": "", "gh": "",
        "devto": ["rstats", "datascience"], "reddit": [], "blogs": [],
        "ar": ['"لغة R" تحليل بيانات شرح OR دورة'],
        "match": r"\brstats\b|\bggplot\b|\btidyverse\b|لغة ار|لغة R\b",
        "medium": "r",
    },
    "scala": {
        "name": "Scala", "hn": "scala", "so": "", "gh": "",
        "devto": ["scala"], "reddit": [], "blogs": [],
        "ar": ['"سكالا" OR Scala برمجة شرح'],
        "match": r"\bscala\b|سكالا|\bakka\b|apache spark",
        "medium": "scala",
    },
    "perl": {
        "name": "Perl", "hn": "perl", "so": "", "gh": "",
        "devto": ["perl"], "reddit": [], "blogs": [],
        "ar": ['"بيرل" OR Perl لغة برمجة شرح'],
        "match": r"\bperl\b|بيرل",
        "medium": "perl",
    },
    "elixir": {
        "name": "Elixir", "hn": "elixir", "so": "", "gh": "",
        "devto": ["elixir"], "reddit": [], "blogs": [],
        "ar": ['"إليكسير" OR Elixir برمجة شرح'],
        "match": r"\belixir\b|\bphoenix framework\b|إليكسير|اليكسير",
        "medium": "elixir",
    },
    "solidity": {
        "name": "Solidity والعقود الذكية", "hn": "solidity", "so": "", "gh": "",
        "devto": ["solidity", "blockchain"], "reddit": [], "blogs": [],
        "ar": ['"سوليديتي" OR "العقود الذكية" برمجة شرح'],
        "match": r"\bsolidity\b|سوليديتي|عقود ذكية|العقود الذكية|smart contract|\bweb3\b|\bethereum\b",
        "medium": "solidity",
    },
    "assembly": {
        "name": "لغة التجميع", "hn": "assembly", "so": "", "gh": "",
        "devto": ["assembly", "c"], "reddit": [], "blogs": [],
        "ar": ['"لغة التجميع" OR "أسمبلي" شرح'],
        "match": r"\bassembly\b|أسمبلي|اسمبلي|لغة التجميع|\bx86\b|\bnasm\b|\bmasm\b",
        "medium": "assembly",
    },
    "matlab": {
        "name": "MATLAB", "hn": "matlab", "so": "", "gh": "",
        "devto": ["matlab"], "reddit": [], "blogs": [],
        "ar": ['"ماتلاب" OR MATLAB شرح OR دورة'],
        "match": r"\bmatlab\b|ماتلاب|\bsimulink\b|\boctave\b",
        "medium": "matlab",
    },
    "objectivec": {
        "name": "Objective-C", "hn": "objective c", "so": "", "gh": "",
        "devto": ["objectivec", "ios"], "reddit": [], "blogs": [],
        "ar": ['"أوبجكتف سي" OR "Objective-C" برمجة'],
        "match": r"objective-? ?c\b|أوبجكتف",
        "medium": "objective-c",
    },
    "haskell": {
        "name": "Haskell", "hn": "haskell", "so": "", "gh": "",
        "devto": ["haskell", "functional"], "reddit": [], "blogs": [],
        "ar": ['"هاسكل" OR Haskell برمجة دالية شرح'],
        "match": r"\bhaskell\b|هاسكل|برمجة دالية|functional programming",
        "medium": "haskell",
    },
    "julia": {
        "name": "Julia", "hn": "julialang", "so": "", "gh": "",
        "devto": ["julia"], "reddit": [], "blogs": [],
        "ar": ['"جوليا" OR Julia لغة برمجة شرح'],
        "match": r"\bjulia(lang)?\b|جوليا",
        "medium": "julia",
    },
    "vb": {
        "name": "Visual Basic", "hn": "visual basic", "so": "", "gh": "",
        "devto": ["vb", "dotnet"], "reddit": [], "blogs": [],
        "ar": ['"فيجوال بيسك" OR "Visual Basic" شرح'],
        "match": r"visual ?basic|\bvb\.net\b|\bvba\b|فيجوال ?بيسك",
        "medium": "visual-basic",
    },
    "dart": {
        "name": "Dart", "hn": "dart language", "so": "", "gh": "",
        "devto": ["dart"], "reddit": [], "blogs": [],
        "ar": ['"لغة دارت" OR Dart برمجة شرح'],
        "match": r"\bdart\b|لغة دارت|دارت\b",
        "medium": "dart",
    },
    "c": {
        "name": "لغة C", "hn": "c programming", "so": "", "gh": "",
        "devto": ["c", "clanguage"], "reddit": [], "blogs": [],
        "ar": ['"لغة سي" C برمجة شرح OR دورة'],
        "match": r"\blegacy c\b|لغة سي\b|\bansi c\b|\bc99\b|\bpointers?\b|مؤشرات",
        "medium": "c-programming",
    },
    "groovy": {
        "name": "Groovy", "hn": "groovy", "so": "", "gh": "",
        "devto": ["groovy", "java"], "reddit": [], "blogs": [],
        "ar": ['"جروفي" OR Groovy برمجة'],
        "match": r"\bgroovy\b|جروفي|\bgradle\b",
        "medium": "groovy",
    },
    "clojure": {
        "name": "Clojure", "hn": "clojure", "so": "", "gh": "",
        "devto": ["clojure"], "reddit": [], "blogs": [],
        "ar": ['"كلوجر" OR Clojure برمجة'],
        "match": r"\bclojure\b|كلوجر",
        "medium": "clojure",
    },
    "fsharp": {
        "name": "‏#F", "hn": "fsharp", "so": "", "gh": "",
        "devto": ["fsharp", "dotnet"], "reddit": [], "blogs": [],
        "ar": ['"إف شارب" OR "#F" برمجة'],
        "match": r"\bf#|f ?sharp\b|إف شارب",
        "medium": "fsharp",
    },
    "erlang": {
        "name": "Erlang", "hn": "erlang", "so": "", "gh": "",
        "devto": ["erlang"], "reddit": [], "blogs": [],
        "ar": ['"إرلانج" OR Erlang برمجة'],
        "match": r"\berlang\b|إرلانج|ارلانج|\botp\b",
        "medium": "erlang",
    },
    "ocaml": {
        "name": "OCaml", "hn": "ocaml", "so": "", "gh": "",
        "devto": ["ocaml"], "reddit": [], "blogs": [],
        "ar": ['"أوكامل" OR OCaml برمجة'],
        "match": r"\bocaml\b|أوكامل|اوكامل",
        "medium": "ocaml",
    },
    "fortran": {
        "name": "Fortran", "hn": "fortran", "so": "", "gh": "",
        "devto": ["fortran"], "reddit": [], "blogs": [],
        "ar": ['"فورتران" OR Fortran برمجة'],
        "match": r"\bfortran\b|فورتران",
        "medium": "fortran",
    },
    "cobol": {
        "name": "COBOL", "hn": "cobol", "so": "", "gh": "",
        "devto": ["cobol"], "reddit": [], "blogs": [],
        "ar": ['"كوبول" OR COBOL برمجة'],
        "match": r"\bcobol\b|كوبول|mainframe",
        "medium": "cobol",
    },
    "pascal": {
        "name": "Pascal و Delphi", "hn": "pascal delphi", "so": "", "gh": "",
        "devto": ["pascal", "delphi"], "reddit": [], "blogs": [],
        "ar": ['"باسكال" OR "دلفي" برمجة شرح'],
        "match": r"\bpascal\b|\bdelphi\b|باسكال|دلفي",
        "medium": "pascal",
    },
    "zig": {
        "name": "Zig", "hn": "zig language", "so": "", "gh": "",
        "devto": ["zig"], "reddit": [], "blogs": [],
        "ar": ['"زيج" OR Zig لغة برمجة'],
        "match": r"\bzig\b lang|\bziglang\b|لغة زيج",
        "medium": "zig",
    },
    "nim": {
        "name": "Nim", "hn": "nim language", "so": "", "gh": "",
        "devto": ["nim"], "reddit": [], "blogs": [],
        "ar": ['"نيم" OR Nim لغة برمجة'],
        "match": r"\bnim\b lang|\bnimlang\b|لغة نيم",
        "medium": "nim",
    },
    "crystal": {
        "name": "Crystal", "hn": "crystal language", "so": "", "gh": "",
        "devto": ["crystal"], "reddit": [], "blogs": [],
        "ar": ['"كريستال" Crystal لغة برمجة'],
        "match": r"crystal ?lang|لغة كريستال",
        "medium": "crystal",
    },
    "lisp": {
        "name": "Lisp و Scheme", "hn": "lisp scheme", "so": "", "gh": "",
        "devto": ["lisp"], "reddit": [], "blogs": [],
        "ar": ['"ليسب" OR Lisp برمجة'],
        "match": r"\blisp\b|\bscheme\b lang|\bracket\b lang|ليسب|سكيم",
        "medium": "lisp",
    },
    "prolog": {
        "name": "Prolog", "hn": "prolog", "so": "", "gh": "",
        "devto": ["prolog"], "reddit": [], "blogs": [],
        "ar": ['"برولوج" OR Prolog برمجة منطقية'],
        "match": r"\bprolog\b|برولوج|برمجة منطقية",
        "medium": "prolog",
    },
    "scratch": {
        "name": "سكراتش للمبتدئين", "hn": "scratch programming kids", "so": "", "gh": "",
        "devto": ["scratch", "beginners"], "reddit": [], "blogs": [],
        "ar": ['"سكراتش" برمجة الأطفال شرح'],
        "match": r"\bscratch\b|سكراتش|برمجة الأطفال",
        "medium": "scratch",
    },
    "arduino": {
        "name": "أردوينو والمدمجة", "hn": "arduino embedded", "so": "", "gh": "",
        "devto": ["arduino", "iot"], "reddit": [], "blogs": [],
        "ar": ['"أردوينو" OR Arduino شرح مشروع', '"الأنظمة المدمجة" برمجة شرح'],
        "match": r"\barduino\b|أردوينو|اردوينو|\besp32\b|\braspberry\b|أنظمة مدمجة|الأنظمة المدمجة|\bembedded\b|\biot\b",
        "medium": "arduino",
    },
    "verilog": {
        "name": "VHDL و Verilog", "hn": "verilog vhdl fpga", "so": "", "gh": "",
        "devto": ["verilog", "hardware"], "reddit": [], "blogs": [],
        "ar": ['"فيريلوج" OR VHDL تصميم رقمي شرح'],
        "match": r"\bverilog\b|\bvhdl\b|\bfpga\b|فيريلوج|تصميم رقمي",
        "medium": "verilog",
    },
    "graphql": {
        "name": "GraphQL", "hn": "graphql", "so": "", "gh": "",
        "devto": ["graphql", "api"], "reddit": [], "blogs": [],
        "ar": ['"جراف كيو ال" OR GraphQL شرح'],
        "match": r"\bgraphql\b|جراف ?كيو",
        "medium": "graphql",
    },
    "sass": {
        "name": "Sass و Tailwind", "hn": "tailwind sass css framework", "so": "", "gh": "",
        "devto": ["tailwindcss", "sass"], "reddit": [], "blogs": [],
        "ar": ['"تيلويند" OR Tailwind تصميم شرح', '"ساس" OR Sass CSS شرح'],
        "match": r"\bsass\b|\bscss\b|\bless\b css|tailwind|تيلويند|بوتستراب|\bbootstrap\b",
        "medium": "tailwind-css",
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
        if NOISE_EN.search(blob) and not STRONG_PROG_EN.search(blob):
            continue

        via = ""
        if source_id.startswith(("ar-", "yt")):
            m = re.match(r"^(.*)\s+[-–]\s+([^-–]{2,40})$", title)
            if m:
                title, via = m.group(1).strip(), m.group(2).strip()

        # مصادر يوتيوب: يوتيوب حصراً — ناشر آخر يعني موقعاً لا علاقة له بالدروس
        if source_id.startswith(("ar-yt", "yt")) and "youtube" not in via.lower():
            continue

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
    + r"|برمج|مبرمج|كود|تطوير|خوارزم|هيكل بيانات|قواعد بيانات|شبكات|تشفير|أمن سيبراني"
      r"|\bprogramming\b|\bdeveloper\b|\bcoding\b|\bsoftware\b|\balgorithm|data structure"
      r"|\bdatabase\b|machine learning|reinforcement learning|\bcompiler\b|\bnetworking\b"
      r"|cyber ?security|\bdevops\b|\bapi\b|\bframework\b",
    re.IGNORECASE,
)

CHANNEL_ID_RE = re.compile(r"(UC[\w-]{20,})")
HANDLE_RE = re.compile(r"youtube\.com/@([\w.\-]+)|^@?([\w.\-]+)$")


def programming_ratio(channel_id: str) -> tuple[int, int]:
    """كم فيديو برمجي من آخر ما نشرته القناة — للتنبيه فقط، لا للرفض."""
    try:
        items = parse_feed(get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
                               attempts=1),
                           "ar-yt", "يوتيوب", "python", None)
    except Exception:  # noqa: BLE001
        return (0, 0)
    return (sum(1 for i in items if ANY_PROG.search(i["title"] + " " + i["summary"])), len(items))


def resolve_channels() -> dict[str, str]:
    """يحوّل مدخلات CHANNELS إلى معرّفات: يقبل المعرّف أو الاسم أو الرابط الكامل.

    ما يُحلّ مرة يُحفظ في data/channels.json فلا يُعاد جلبه كل يوم.
    القناة التي يضيفها المستخدم تُعتمد كما هي؛ ترشيح الفيديوهات حسب لغة البرمجة
    يتكفّل باستبعاد ما لا يخص البرمجة، فلا داعي لرفض القناة كلها.
    """
    known: dict[str, str] = {}
    if CHANNELS_FILE.exists():
        try:
            known = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            known = {}

    for entry in CHANNELS:
        entry = entry.strip()
        if not entry or entry in known:
            continue

        # ‏١) معرّف صريح داخل النص أو الرابط
        direct = CHANNEL_ID_RE.search(entry)
        if direct:
            cid = direct.group(1)
        else:
            # ‏٢) اسم قناة — يحتاج جلب صفحتها لاستخراج المعرّف
            m = HANDLE_RE.search(entry)
            handle = (m.group(1) or m.group(2)) if m else None
            if not handle:
                print(f"  ؟ صيغة غير مفهومة: {entry}")
                continue
            try:
                html = get(f"https://www.youtube.com/@{handle}", attempts=1).decode("utf-8", "replace")
            except Exception as e:  # noqa: BLE001, PERF203
                print(f"  … تعذّر الوصول إلى @{handle} ({e}) — يُعاد غداً")
                continue
            found = re.search(r'"channelId":"(UC[\w-]{20,})"', html)
            if not found:
                print(f"  ؟ لم يُعثر على معرّف لـ @{handle}")
                continue
            cid = found.group(1)
            time.sleep(1)

        hits, total = programming_ratio(cid)
        if total == 0:
            print(f"  ✗ {entry}: التغذية فارغة أو غير متاحة")
            continue
        known[entry] = cid
        mark = "✓" if hits else "⚠"
        note = "" if hits else "  (لا يبدو محتواها الأخير برمجياً — ستُرشَّح فيديوهاتها على أي حال)"
        print(f"  {mark} {entry} -> {cid}  برمجية {hits}/{total}{note}")

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
    """يجمع المصادر التعليمية فقط: دروس يوتيوب ومقالات شرح ومدونات وبودكاست.

    استُبعدت مصادر الأخبار والنقاش والمستودعات (Hacker News، Reddit،
    أخبار جوجل، GitHub، PyPI، Stack Overflow) لأن الموقع للتعليم لا للأخبار.
    """
    match = re.compile(cfg["match"], re.IGNORECASE)
    collected: list[dict] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = [pool.submit(fetch_devto, tech, cfg)]

        for url in cfg["blogs"]:
            jobs.append(pool.submit(
                lambda u=url: parse_feed(get(u), "blogs", "مدونات", tech, None)))
        jobs.append(pool.submit(
            lambda: parse_feed(get("https://www.freecodecamp.org/news/rss/"),
                               "fcc", "freeCodeCamp", tech, match)))
        if cfg.get("medium"):
            jobs.append(pool.submit(
                lambda: parse_feed(get(f"https://medium.com/feed/tag/{cfg['medium']}"),
                                   "medium", "Medium", tech, match)))
        # البودكاست مختار لكل مسار مسبقاً، فلا يُرشَّح بالكلمات
        for feed in cfg.get("podcasts", []):
            jobs.append(pool.submit(
                lambda u=feed: [dict(i, kind="podcast")
                                for i in parse_feed(get(u), "podcast", "بودكاست", tech, None)[:15]]))
        for cid in channels.values():
            jobs.append(pool.submit(fetch_channel, cid, tech, match))

        for job in jobs:
            try:
                collected.extend(job.result())
            except Exception as e:  # noqa: BLE001, PERF203
                print(f"  [{tech}] تخطّي مصدر: {e}")

    # بحث الدروس على يوتيوب بالتتابع — الطلبات المتوازية تُقابَل بـ 429
    searches = [(q + " site:youtube.com", "ar-yt", "دروس عربية", "ar") for q in cfg["ar"]]
    searches.append((cfg["hn"] + " tutorial course site:youtube.com", "yt", "يوتيوب", "en"))
    for query, sid, sname, qlang in searches:
        try:
            collected.extend(parse_feed(get(gnews(query, qlang)), sid, sname, tech, match))
        except Exception as e:  # noqa: BLE001, PERF203
            print(f"  [{tech}] تخطّي بحث: {e}")
        time.sleep(1.5)

    previous = load_previous(tech)
    if previous:
        # الملف السابق قد يحمل مصادر أخبار من نسخة قديمة — تُستبعد
        previous = [i for i in previous if i.get("sourceId") in EDU_SOURCES]
        print(f"  [{tech}] ضمّ {len(previous)} عنصراً تعليمياً من الملف السابق")
    collected.extend(previous)

    seen: dict[str, dict] = {}
    per_source: dict[str, int] = {}
    for item in sorted(collected, key=lambda i: i.get("date") or "", reverse=True):
        key = dedupe_key(item)
        if not key or key in seen:
            continue
        sid = item["sourceId"]
        if sid not in EDU_SOURCES:
            continue
        if per_source.get(sid, 0) >= CAPS.get(sid, 999):
            continue
        per_source[sid] = per_source.get(sid, 0) + 1
        seen[key] = item

    ordered = list(seen.values())
    arabic = [i for i in ordered if i["lang"] == "ar"][:AR_QUOTA]
    taken = {id(i) for i in arabic}
    podcasts = [i for i in ordered if i["sourceId"] == "podcast" and id(i) not in taken][:PODCAST_QUOTA]
    taken |= {id(i) for i in podcasts}
    room = MAX_PER_TECH - len(arabic) - len(podcasts)
    english = [i for i in ordered if id(i) not in taken][:room]

    items = sorted(arabic + podcasts + english, key=lambda i: i.get("date") or "", reverse=True)
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
