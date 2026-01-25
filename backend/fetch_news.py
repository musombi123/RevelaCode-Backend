import os
import json
import shutil
import logging
from datetime import datetime, timedelta, timezone
import requests

# === CONFIG / ENVIRONMENT VARIABLES ===
API_KEY = os.environ.get("NEWS_API_KEY")
if not API_KEY:
    raise ValueError("❌ NEWS_API_KEY not set in environment variables!")

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

# === FETCH ARTICLES FROM NEWSAPI ===
def fetch_articles(api_key, query):
    all_articles = []
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
        events.append({
            "headline": article.get("title", ""),
            "description": article.get("description", ""),
            "content": article.get("content", ""),
            "author": article.get("author", ""),
            "url": article.get("url", ""),
            "urlToImage": article.get("urlToImage", ""),
            "publishedAt": article.get("publishedAt", ""),
            "source": article.get("source", {}).get("name", ""),
            "source_id": article.get("source", {}).get("id", "")
        })

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    logging.info(f"💾 Saved {len(events)} events to {filename}")

# === MAIN ===
if __name__ == "__main__":
    archive_old_events()
    articles = fetch_articles(API_KEY, QUERY)
    if articles:
        save_to_json(articles, QUERY)
    else:
        logging.warning("⚠️ No articles fetched; nothing to save.")

    logging.info("✅ Events fetch and archive complete. Ready for Render deployment.")
