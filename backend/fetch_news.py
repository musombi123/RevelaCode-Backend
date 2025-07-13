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
DEFAULT_PAGE_SIZE = 20
SAVE_DIR = "./events"

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# === FETCH ===
def fetch_headlines(api_key, country, page_size):
    params = {
        "apiKey": api_key,
        "country": country,
        "pageSize": page_size
    }
    logging.info(f"Fetching top {page_size} headlines for country '{country}'...")
    response = requests.get(ENDPOINT, params=params)
    if response.status_code == 200:
        data = response.json()
        articles = data.get("articles", [])
        logging.info(f"Fetched {len(articles)} articles.")
        return articles
    else:
        logging.error(f"Failed to fetch data: {response.status_code} {response.text}")
        return []

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
            "url": article.get("url", ""),
            "publishedAt": article.get("publishedAt", ""),
            "source": article.get("source", {}).get("name", "")
        }
        events.append(event)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)

    logging.info(f"Saved {len(events)} events to {filename}")

# === MAIN ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch latest news headlines and save to JSON.")
    parser.add_argument("--country", type=str, default=DEFAULT_COUNTRY, help="Country code (e.g., us, ke, gb)")
    parser.add_argument("--pagesize", type=int, default=DEFAULT_PAGE_SIZE, help="Number of articles to fetch (max 100)")
    args = parser.parse_args()

    if not API_KEY or API_KEY == "your_api_key_here":
        logging.warning("API_KEY is missing or default. Please set a real API key.")

    headlines = fetch_headlines(API_KEY, args.country, args.pagesize)
    if headlines:
        save_to_json(headlines)
    else:
        logging.warning("No articles fetched; nothing to save.")
