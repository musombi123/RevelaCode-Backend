import requests
import os
import logging

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

logger = logging.getLogger(__name__)

# ======================================================
# TELEGRAM ALERT SENDER
# ======================================================

def send_alert(event):
    """
    Sends a prophecy alert to Telegram.
    Safe against missing fields and API failures.
    """

    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("⚠️ Telegram not configured (missing BOT_TOKEN or CHAT_ID)")
        return

    headline = event.get("headline") or "No headline"
    score = event.get("score", 0)
    source = event.get("source") or "unknown"
    url = event.get("url") or "N/A"
    level = event.get("level") or "unknown"

    message = (
        "🚨 PROPHECY SIGNAL DETECTED\n\n"
        f"📌 {headline}\n\n"
        f"📊 Score: {score} | Level: {level}\n\n"
        f"🧭 Source: {source}\n\n"
        f"🔗 Link: {url}"
    )

    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    }

    try:
        response = requests.post(telegram_url, data=payload, timeout=10)
        response.raise_for_status()
        logger.info("📡 Telegram alert sent successfully")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send Telegram alert: {e}")