import requests
import json
from datetime import datetime
import os

# === CONFIG ===
API_KEY = "69a21d7398a04d948a0e881e0fea9793"
ENDPOINT = "https://newsapi.org/v2/top-headlines"
COUNTRY = "us"  # or "gb", "ke", "world" depending on your focus
SAVE_DIR = "./events"

# === FETCH ===
def fetch_headlines():
    params = {
        "apiKey": API_KEY,
        "country": COUNTRY,
        "pageSize": 20  # max headlines to pull
    }
    response = requests.get(ENDPOINT, params=params)
    if response.status_code == 200:
        data = response.json()
        articles = data.get("articles", [])
        return articles
    else:
        print(f"Error: {response.status_code}")
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
            "headline": article["title"],
            "description": article["description"],
            "url": article["url"],
            "publishedAt": article["publishedAt"],
            "source": article["source"]["name"]
        }
        events.append(event)

    with open(filename, "w") as f:
        json.dump(events, f, indent=2)
    print(f"Saved {len(events)} events to {filename}")

# === MAIN ===
if __name__ == "__main__":
    headlines = fetch_headlines()
    save_to_json(headlines)
