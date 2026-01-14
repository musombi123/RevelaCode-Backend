import requests
import json
from datetime import datetime, timedelta, timezone
import os
import argparse
import logging

# === CONFIG ===
API_KEY = "69a21d7398a04d948a0e881e0fea9793"
ENDPOINT = "https://newsapi.org/v2/everything"
PAGE_SIZE = 100

# 🔒 NewsAPI free plan supports ONLY page 1
MAX_PAGES = 1

SAVE_DIR = "./events"

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# === FETCH ===
def fetch_articles(api_key, query):
    all_articles = []

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    # ✅ Timezone-aware UTC (fixes deprecation warning)
    to_date = datetime.now(timezone.utc)
    from_date = to_date - timedelta(days=7)

    for page in range(1, MAX_PAGES + 1):
        params = {
            "apiKey": api_key,
            "q": query,
            "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": to_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": PAGE_SIZE,
            "page": page
        }

        logging.info(f"📄 Fetching page {page} for query '{query}'...")

        try:
            response = requests.get(
                ENDPOINT,
                params=params,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 426:
                logging.warning(
                    "⚠️ NewsAPI free plan pagination limit reached "
                    "(page > 1 requires paid plan)."
                )
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

# === SAVE ===
def save_to_json(articles, query):
    os.makedirs(SAVE_DIR, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    safe_query = query.replace(" ", "_").replace('"', "")
    filename = f"{SAVE_DIR}/events_{safe_query}_{today}.json"

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
    parser = argparse.ArgumentParser(
        description="Fetch news using NewsAPI /everything endpoint."
    )
    parser.add_argument(
        "-q", "--query",
        type=str,
        default="prophecy",
        help="Search keyword(s)"
    )
    args = parser.parse_args()

    if not API_KEY or API_KEY == "your_api_key_here":
        logging.warning("API_KEY is missing or invalid. Please set a real API key.")
    else:
        formatted_query = args.query
        articles = fetch_articles(API_KEY, formatted_query)

        if articles:
            save_to_json(articles, formatted_query)
        else:
            logging.warning("⚠️ No articles fetched; nothing to save.")
