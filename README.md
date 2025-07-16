# RevelaCode

✨ **RevelaCode** is an AI-powered faith-tech project that decodes biblical verses, prophecies & global events into meaningful Gen Z insights.  
Built with Python backend, planned interactive frontend, and daily data scrapers.

## 🚀 Features
- Daily global events fetcher & categorizer
- Decoding engine with biblical prophecy matching
- Guest mode & user accounts (secure JSON-based)
- Planned dashboard: theme switcher, font size control, social linking

## 🛠 Tech stack
- Python 3
- JSON storage
- (Planned) React / HTML frontend
- Git for version control

## ⚙ Project structure
```plaintext
/backend
  ├── events/
  │   └── events_YYYY-MM-DD.json         # Raw daily news fetched
  ├── events_tagged/
  │   └── events_YYYY-MM-DD.json         # News tagged by category
  ├── events_decoded/
  │   └── events_YYYY-MM-DD.json         # Final decoded events (with matched verses)
  ├── symbols_data.json                  # Core file: keywords, symbols, and verses
  ├── decode_news.py                     # Script to decode tagged events
  ├── fetch_news.py                      # (To be added) script to fetch daily news
  └── categorize.py                      # (To be added) script to tag categories