import requests
import os

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_alert(event):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ Telegram not configured")
        return

    message = f"""
🚨 PROPHECY SIGNAL DETECTED

📌 {event.get('headline', '')}

📊 Score: {event.get('score', 0)}

🧭 Source: {event.get('source', '')}

🔗 Link: {event.get('url', '')}
"""

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=payload)