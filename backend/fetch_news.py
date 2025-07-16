import requests
import json
from datetime import datetime
import os
import argparse
import logging

# === CONFIG ===
API_KEY = "69a21d7398a04d948a0e881e0fea9793"
ENDPOINT = "https://newsapi.org/v2/top-headlines"
DEFAULT_COUNTRY = "us"
PAGE_SIZE = 100   # Max allowed by API
MAX_PAGES = 5     # 5 × 100 = 500 articles max
SAVE_DIR = "./events"

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# === FETCH ===
def fetch_headlines(api_key, country):
    all_articles = []
    for page in range(1, MAX_PAGES + 1):
        params = {
            "apiKey": api_key,
            "country": country,
            "pageSize": PAGE_SIZE,
            "page": page
        }
        logging.info(f"📄 Fetching page {page} for country '{country}'...")
        try:
            response = requests.get(ENDPOINT, params=params, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Failed to fetch page {page}: {e}")
            break

        data = response.json()
        articles = data.get("articles", [])
        if not articles:
            break
        all_articles.extend(articles)
    logging.info(f"✅ Total fetched articles: {len(all_articles)}")
    return all_articles

# === SAVE ===
def save_to_json(articles):
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{SAVE_DIR}/events_{today}.json"
    events = []

    for article in articles:
        event = {
            "headline": article.get("title", ""),
            "description": article.get("description", ""),
            "content": article.get("content", ""),
            "author": article.get("author", ""),
            "url": article.get("url", ""),
            "urlToImage": article.get("urlToImage", ""),
            "publishedAt": article.get("publishedAt", ""),
            "source": article.get("source", {}).get("name", ""),
            "source_id": article.get("source", {}).get("id", "")
        }
        events.append(event)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    logging.info(f"💾 Saved {len(events)} events to {filename}")

# === MAIN ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch latest news headlines and save to JSON.")
    parser.add_argument("--country", type=str, default=DEFAULT_COUNTRY, help="Country code (e.g., us, ke, gb)")
    args = parser.parse_args()

    if not API_KEY or API_KEY == "your_api_key_here":
        logging.warning("API_KEY is missing or invalid. Please set a real API key.")
    else:
        headlines = fetch_headlines(API_KEY, args.country)
        if headlines:
            save_to_json(headlines)
        else:
            logging.warning("⚠️ No articles fetched; nothing to save.")
