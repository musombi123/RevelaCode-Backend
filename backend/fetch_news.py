import os
import json
import shutil
import logging
from datetime import datetime, timedelta, timezone
import requests
from backend.alert_engine import process_events
import feedparser
from urllib.parse import urlparse

# === CONFIG / ENVIRONMENT VARIABLES ===
# === GLOBAL RSS SOURCES ===
RSS_SOURCES = [
    # GLOBAL CORE
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",

    # AFRICA
    "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
    "https://www.standardmedia.co.ke/rss/headlines.php",

    # EUROPE
    "https://www.france24.com/en/rss",
    "https://www.dw.com/en/top-stories/rss",

    # ASIA
    "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",
    "https://www.scmp.com/rss/91/feed",

    # AMERICAS
    "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "https://feeds.a.dj.com/rss/RSSWorldNews.xml"
]

# === VIDEO SOURCES (prophecy + geopolitics) ===
VIDEO_RSS_SOURCES = [
    "https://news.google.com/rss/search?q=prophecy+end+times+when:1d&tbm=vid",
    "https://news.google.com/rss/search?q=israel+war+news+video&tbm=vid",
    "https://news.google.com/rss/search?q=middle+east+conflict+video&tbm=vid",
]

REGION_MAP = {
    "africa": [
        "nigeria", "kenya", "south africa", "ethiopia", "ghana", "africa"
    ],
    "asia": [
        "china", "india", "japan", "korea", "pakistan", "philippines"
    ],
    "europe": [
        "france", "germany", "uk", "europe", "italy", "spain", "russia"
    ],
    "americas": [
        "usa", "united states", "canada", "brazil", "mexico"
    ],
    "middle_east": [
        "israel", "iran", "iraq", "syria", "saudi", "yemen", "gaza"
    ],
    "oceania": [
        "australia", "new zealand"
    ]
}

# NewsAPI is optional; RSS ingestion must work without a paid API key.
API_KEY = os.environ.get("NEWS_API_KEY")

QUERY = os.environ.get("NEWS_QUERY", "prophecy")
EVENTS_DIR = os.environ.get("EVENTS_DIR", "./events")
ARCHIVED_DIR = os.environ.get("ARCHIVED_DIR", "./archived")
PAGE_SIZE = int(os.environ.get("NEWS_PAGE_SIZE", 100))
MAX_PAGES = int(os.environ.get("NEWS_MAX_PAGES", 1))  # NewsAPI free plan only page 1
ENDPOINT = "https://newsapi.org/v2/everything"

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# === ENSURE DIRECTORIES EXIST ===
os.makedirs(EVENTS_DIR, exist_ok=True)
os.makedirs(ARCHIVED_DIR, exist_ok=True)

# === ARCHIVE LOG FILE ===
LOG_FILE = os.path.join(ARCHIVED_DIR, "archive_log.json")

# === HIGH-LEVEL FUNCTIONS ===
def fetch_rss(url, content_type="article"):
    """Fetch RSS headlines while preserving the publisher's identity."""
    items = []
    try:
        feed = feedparser.parse(url)
    except Exception as exc:
        logging.warning("RSS fetch failed for %s: %s", url, exc)
        return items

    publisher = ""
    try:
        publisher = str(feed.feed.get("title", "") or "").strip()
    except Exception:
        publisher = ""

    if not publisher:
        publisher = urlparse(url).netloc or "Unknown publisher"

    if getattr(feed, "bozo", False):
        logging.warning(
            "RSS feed returned a parsing warning for %s: %s",
            url,
            getattr(feed, "bozo_exception", "unknown feed error"),
        )

    for entry in feed.entries:
        article_url = str(entry.get("link", "") or "").strip()
        title = str(entry.get("title", "") or "").strip()
        if not article_url or not title:
            continue

        items.append({
            "type": content_type,
            "title": title,
            "description": entry.get("summary", ""),
            "url": article_url,
            "publishedAt": entry.get("published", "") or entry.get("updated", ""),
            "source": publisher,
            "source_url": url,

            # Preserve the existing frontend article/video contract.
            "media_type": content_type,
            "video_url": article_url if content_type == "video" else None,
        })

    return items

def log_archive(filename):
    log_entry = {"filename": filename, "archived_at": datetime.now().isoformat()}
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    else:
        log_data = []
    log_data.append(log_entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

# === ARCHIVE OLD EVENTS (>7 DAYS) ===
def archive_old_events():
    for filename in os.listdir(EVENTS_DIR):
        if filename.startswith("events_") and filename.endswith(".json"):
            date_str = filename.replace("events_", "").replace(".json", "")
            for fmt in ("%Y-%m-%d", "%Y_%m_%d"):
                try:
                    file_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                logging.warning(f"⚠️ Skipping invalid date file: {filename}")
                continue

            if (datetime.now() - file_date).days > 7:
                src = os.path.join(EVENTS_DIR, filename)
                dst = os.path.join(ARCHIVED_DIR, filename)
                shutil.move(src, dst)
                log_archive(filename)
                logging.info(f"📦 Archived: {filename}")

# === FETCH ARTICLES FROM RSS SOURCES ===
def fetch_video_feeds():
    videos = []

    for url in VIDEO_RSS_SOURCES:
        videos.extend(fetch_rss(url, "video"))

    logging.info(f"🎥 Fetched videos: {len(videos)}")
    return videos

def fetch_global_rss():
    articles = []

    for url in RSS_SOURCES:
        articles.extend(fetch_rss(url, "article"))

    logging.info(f"🌍 RSS articles fetched: {len(articles)}")
    return articles

# === FETCH ARTICLES FROM NEWSAPI ===
def fetch_articles(api_key, query):
    all_articles = []
    if not api_key:
        logging.info(
            "NEWS_API_KEY is not configured; skipping NewsAPI and continuing with RSS sources."
        )
        return all_articles

    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=7)
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    for page in range(1, MAX_PAGES + 1):
        params = {
            "apiKey": api_key,
            "q": query,
            "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": to_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": PAGE_SIZE,
            "page": page,
        }

        logging.info(f"📄 Fetching page {page} for query '{query}'...")
        try:
            response = requests.get(ENDPOINT, params=params, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 426:
                logging.warning("⚠️ NewsAPI free plan pagination limit reached (page > 1 requires paid plan).")
            else:
                logging.error(f"❌ Failed to fetch page {page}: {e}")
            break
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Request failed on page {page}: {e}")
            break

        data = response.json()
        articles = data.get("articles", [])
        if not articles:
            break
        all_articles.extend(articles)

    logging.info(f"✅ Total fetched articles: {len(all_articles)}")
    return all_articles

# === SAVE ARTICLES TO EVENTS_DIR ===
def save_to_json(articles, query):
    os.makedirs(EVENTS_DIR, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    safe_query = query.replace(" ", "_").replace('"', "")
    filename = os.path.join(EVENTS_DIR, f"events_{safe_query}_{today}.json")

    events = []

    for article in articles:
        source = article.get("source", "")

        if isinstance(source, dict):
           source_name = source.get("name", "")
           source_id = source.get("id", "")
        else:
           source_name = str(source)
           source_id = ""

        events.append({
           "type": article.get("type", "article"),
           "headline": (
               article.get("headline")
               or article.get("title", "")
            ),
            "description": article.get("description", ""),
            "content": article.get("content", ""),
            "author": article.get("author", ""),
            "url": article.get("url", ""),
            "urlToImage": article.get("urlToImage", ""),
            "publishedAt": article.get("publishedAt", ""),
            "source": source_name,
            "source_id": source_id,
       })

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    logging.info(f"💾 Saved {len(events)} events to {filename}")

def normalize_event(item):
    headline = item.get("headline") or item.get("title") or ""

    source = item.get("source", "")
    if isinstance(source, dict):
        source = source.get("name", "")

    return {
        "type": item.get("type", "article"),
        "headline": headline,
        "description": item.get("description", ""),
        "content": item.get("content", ""),
        "author": item.get("author", ""),
        "url": item.get("url", ""),
        "urlToImage": item.get("urlToImage", ""),
        "publishedAt": item.get("publishedAt", ""),
        "source": source,
        "source_id": item.get("source_id", ""),

        # 🔥 ADD THIS
        "media_type": item.get("type", "article"),  # article | video
    }

def detect_region(text):
    text = text.lower()

    for region, keywords in REGION_MAP.items():
        if any(k in text for k in keywords):
            return region

    return "global"



# === MAIN ===
if __name__ == "__main__":
    archive_old_events()

    articles_api = fetch_articles(API_KEY, QUERY)
    articles_rss = fetch_global_rss()
    videos = fetch_video_feeds()

    raw_data = []

    if articles_api:
        raw_data.extend(articles_api)

    if articles_rss:
        raw_data.extend(articles_rss)

    if videos:
        raw_data.extend(videos)

    # 🔥 NORMALIZE EVERYTHING
    all_data = [normalize_event(item) for item in raw_data]

    from backend.media_extractor import extract_media

    for item in all_data:

        if not item.get("url"):
            continue

        # Skip only if we already have both an image and a video
        if item.get("urlToImage") and item.get("video_url"):
            continue

        try:
            media = extract_media(item["url"])

            item["media"] = media

            # Fill missing image only
            if not item.get("urlToImage") and media["images"]:
                item["urlToImage"] = media["images"][0]

            # Fill missing video only
            if not item.get("video_url") and media["videos"]:
                item["media_type"] = "video"
                item["video_url"] = media["videos"][0]

        except Exception as e:
            logging.warning(
                f"Media extraction failed for {item.get('url')}: {e}"
            )

    # 🔥 ADD REGION HERE
    for item in all_data:
        text = f"{item.get('headline','')} {item.get('description','')}"
        item["region"] = detect_region(text)

    unique = {}

    for item in all_data:
        url = item.get("url")

        if url:
            unique[url] = item

    all_data = list(unique.values())

    logging.info(
        f"🧹 Unique events after deduplication: {len(all_data)}"
    )

    # 💾 SAVE FIRST (important for debugging + audit trail)
    if all_data:
        save_to_json(all_data, QUERY)
    else:
        logging.warning("⚠️ No content fetched")

    logging.info("✅ Multi-source ingestion complete")