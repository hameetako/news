#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_news.py
يجمع آخر المقالات من مصادر إخبارية محددة عبر RSS، ويحفظها في ملف JSON واحد.
هذا الملف هو الذي يلعب دور "الـ API" — يُستضاف على GitHub ويُحدَّث تلقائيًا كل ساعة.
"""

import json
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# كل مصدر: اسمه -> رابطه.
# يفضَّل أن يكون الرابط رابط RSS مباشر (أدق وأسرع).
# لو الرابط رابط الموقع الرئيسي فقط، السكربت يحاول يكتشف رابط RSS تلقائيًا.
SOURCES = {
    "الجزيرة": (
        "https://www.aljazeera.net/aljazeerarss/"
        "a7c186be-1baa-4bd4-9d80-a84db769f779/"
        "73d0e1b4-532f-45ef-b135-bfdff8b8cab9"
    ),
    "العربية": "https://www.alarabiya.net/feed/rss2/ar.xml",
    "BBC عربي": "https://feeds.bbci.co.uk/arabic/rss.xml",
    "CNBC عربية": "https://www.cnbcarabia.com",
    "الحرة": "https://www.alhurra.com",
    "964": "https://964media.com",
}

MAX_PER_SOURCE = 25
OUTPUT_FILE = "news.json"

# مسارات شائعة لخلاصات RSS يتم تجربتها لو الاكتشاف التلقائي فشل
COMMON_FEED_PATHS = [
    "/feed/",
    "/feed",
    "/rss",
    "/rss.xml",
    "/rss/index.xml",
    "/feed/rss2/ar.xml",
    "/feeds/posts/default",
]


def try_parse(url):
    """يحاول قراءة الرابط كخلاصة RSS مباشرة. يرجع parsed أو None لو فشل."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        parsed = feedparser.parse(resp.content)
        if parsed.entries:
            return parsed
    except Exception:
        pass
    return None


def discover_feed(homepage_url):
    """يحاول اكتشاف رابط RSS من كود صفحة الموقع الرئيسية، وإن فشل يجرّب مسارات شائعة."""
    try:
        resp = requests.get(homepage_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for link in soup.find_all("link"):
            link_type = (link.get("type") or "").lower()
            if "rss" in link_type or "atom" in link_type:
                href = link.get("href")
                if href:
                    candidate = urljoin(homepage_url, href)
                    parsed = try_parse(candidate)
                    if parsed:
                        return candidate, parsed
    except Exception:
        pass

    base = homepage_url.rstrip("/")
    for path in COMMON_FEED_PATHS:
        candidate = base + path
        parsed = try_parse(candidate)
        if parsed:
            return candidate, parsed

    return None, None


def get_feed(url):
    """يرجع (feed_url, parsed) لمصدر معيّن، أو (None, None) لو فشل كل شيء."""
    parsed = try_parse(url)
    if parsed:
        return url, parsed
    return discover_feed(url)


def clean_summary(html_text, limit=300):
    """يشيل أكواد HTML من الملخص ويقصّه لطول معقول."""
    if not html_text:
        return ""
    text = BeautifulSoup(html_text, "html.parser").get_text(" ", strip=True)
    return text[:limit]


def entry_timestamp(entry):
    """يرجع timestamp رقمي لاستخدامه في الترتيب حسب الأحدث."""
    for field in ("published_parsed", "updated_parsed"):
        value = entry.get(field)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc).timestamp()
            except Exception:
                continue
    return 0


def main():
    all_articles = []
    sources_report = []

    for name, url in SOURCES.items():
        print(f"[*] جلب الأخبار من: {name}")
        feed_url, parsed = get_feed(url)

        if not parsed:
            print(f"    تعذر العثور على RSS صالح لـ {name}")
            sources_report.append({"source": name, "status": "failed", "count": 0})
            continue

        count = 0
        for entry in parsed.entries[:MAX_PER_SOURCE]:
            all_articles.append(
                {
                    "source": name,
                    "title": (entry.get("title") or "").strip(),
                    "link": entry.get("link", ""),
                    "published": entry.get("published") or entry.get("updated") or "",
                    "summary": clean_summary(entry.get("summary", "")),
                    "_ts": entry_timestamp(entry),
                }
            )
            count += 1

        print(f"    تم جلب {count} مقال (الرابط المستخدم: {feed_url})")
        sources_report.append(
            {"source": name, "status": "ok", "count": count, "feed_url": feed_url}
        )

    # ترتيب حسب الأحدث أولًا، ثم إزالة الحقل المساعد للترتيب
    all_articles.sort(key=lambda a: a["_ts"], reverse=True)
    for article in all_articles:
        del article["_ts"]

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_articles": len(all_articles),
        "sources": sources_report,
        "articles": all_articles,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[✓] تم حفظ {len(all_articles)} مقال في {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
