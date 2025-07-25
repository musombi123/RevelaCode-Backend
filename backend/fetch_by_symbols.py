import requests
import json
from datetime import datetime, timedelta
import os
import logging

# === CONFIG ===
API_KEY = "69a21d7398a04d948a0e881e0fea9793"
ENDPOINT = "https://newsapi.org/v2/everything"
PAGE_SIZE = 100
MAX_PAGES = 5
SAVE_DIR = "./events"
SYMBOLS_FILE = "symbols_keywords.json"

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def fetch_articles(query):
    all_articles = []
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json"
    }

    to_date = datetime.utcnow()
    from_date = to_date - timedelta(days=7)  # Expanded to 7 days

    for page in range(1, MAX_PAGES + 1):
        params = {
            "apiKey": API_KEY,
            "q": query,
            "from": from_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": to_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": PAGE_SIZE,
            "page": page
        }

        try:
            logging.info(f"📄 Fetching page {page} for: {query}")
            response = requests.get(ENDPOINT, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            articles = data.get("articles", [])
            if not articles:
                break
            all_articles.extend(articles)
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Request failed for '{query}' (page {page}): {e}")
            break

    return all_articles

def save_articles(articles, symbol_slug):
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"{SAVE_DIR}/events_{symbol_slug}_{today}.json"

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

    logging.info(f"💾 Saved {len(events)} articles to {filename}")

def run_batch_search():
    if not os.path.exists(SYMBOLS_FILE):
        logging.error(f"Missing symbols file: {SYMBOLS_FILE}")
        return

    with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        symbols = data.get("symbols", [])

    for entry in symbols:
        symbol_name = entry.get("symbol", "unknown")
        keywords = entry.get("keywords", [])
        if not keywords:
            continue

        # Wrap multi-word keywords in quotes
        formatted_keywords = [f'"{kw}"' if " " in kw else kw for kw in keywords]
        query = " OR ".join(formatted_keywords)
        slug = symbol_name.lower().replace(" ", "_").replace("/", "_")

        logging.info(f"=== 🔎 Searching for symbol: {symbol_name} ===")
        articles = fetch_articles(query)
        if articles:
            save_articles(articles, slug)
        else:
            logging.info(f"⚠️ No results for {symbol_name}")

if __name__ == "__main__":
    run_batch_search()
