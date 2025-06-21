import json
import logging
from pathlib import Path
import shutil

# --- CONFIGURATION ---
BASE_DIR = Path("/mnt/data")
PROJECT_NAME = "RevelaCode_CloudRun"
CLOUD_RUN_ROOT = BASE_DIR / PROJECT_NAME
BACKEND_PATH = CLOUD_RUN_ROOT / "backend"
SYMBOLS_FILENAME = "symbols_data.json"
DECODER_FILENAME = "bible_decoder.py"
ZIP_NAME = f"{PROJECT_NAME}.zip"
ZIP_PATH = BASE_DIR / ZIP_NAME
REQUIREMENTS = ["fastapi", "uvicorn", "python-dotenv"]

# --- SETUP LOGGING ---
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# --- CHECK MODEL PATH ---
model_path = Path("~/.codemate/_internal/litellm/model").expanduser()
logging.info(f"Model path exists? {model_path.exists()}")

# --- CREATE DIRECTORIES ---
BACKEND_PATH.mkdir(parents=True, exist_ok=True)

# --- SYMBOL DATA ---
symbols_data = {
    "666": "Represents the number of man; symbolic of imperfection and rebellion against God (Revelation 13:18)",
    "beast": "Symbol of oppressive political or religious powers opposing God (Revelation 13)",
    "false prophet": "Represents deceptive religious systems that lead people away from truth (Revelation 13:11-18)",
    "dragon": "Symbol of Satan, the ancient serpent and deceiver (Revelation 12:9)",
    "mark of the beast": "Represents allegiance to worldly powers and rejection of God's truth (Revelation 13:16-17)",
    "seven seals": "Each seal reveals divine judgments or events leading to the end times (Revelation 6)",
    "seven trumpets": "Judgment events that warn and call for repentance (Revelation 8-11)",
    "Babylon": "Symbolic of a corrupt, idolatrous system opposed to God (Revelation 17-18)",
    "144000": "Symbolic or literal representation of God’s sealed servants (Revelation 7:4)",
    "new Jerusalem": "Represents the eternal dwelling of God with His people (Revelation 21)",
    "lake of fire": "The final judgment and eternal separation from God (Revelation 20:14-15)",
    "white horse": "Often represents conquest or Christ's return in judgment (Revelation 6:2, 19:11)"
}

# --- BIBLE DECODER PYTHON CODE ---
bible_decoder_code = '''import json
import os
import re

filepath = os.path.join(os.path.dirname(__file__), 'symbols_data.json')
try:
    with open(filepath, 'r', encoding='utf-8') as f:
        SYMBOLS = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"[ERROR] Failed to load symbols: {e}")
    SYMBOLS = {}

def decode_verse(verse):
    if not SYMBOLS:
        return {"error": "Symbol data could not be loaded."}

    decoded_parts = []
    verse_lower = verse.lower()

    for symbol, meaning in SYMBOLS.items():
        if re.search(r'\\b' + re.escape(symbol.lower()) + r'\\b', verse_lower):
            decoded_parts.append({symbol: meaning})

    return {"decoded": decoded_parts or "No symbolic content found."}
'''

# --- FASTAPI APP ---
main_py = '''from fastapi import FastAPI
from pydantic import BaseModel
from backend.bible_decoder import decode_verse

app = FastAPI()

class DecodeRequest(BaseModel):
    verse: str

@app.post("/decode")
async def decode(req: DecodeRequest):
    return decode_verse(req.verse)
'''

# --- WRITE PROJECT FILES ---
try:
    (BACKEND_PATH / DECODER_FILENAME).write_text(bible_decoder_code, encoding='utf-8')
    (BACKEND_PATH / SYMBOLS_FILENAME).write_text(json.dumps(symbols_data, indent=2), encoding='utf-8')
    (CLOUD_RUN_ROOT / "main.py").write_text(main_py, encoding='utf-8')
    (CLOUD_RUN_ROOT / "requirements.txt").write_text("\n".join(REQUIREMENTS), encoding='utf-8')
    logging.info("Project files written successfully.")
except Exception as e:
    logging.error(f"Failed to write files: {e}")

# --- ZIP THE PROJECT ---
try:
    shutil.make_archive(str(ZIP_PATH.with_suffix('')), 'zip', CLOUD_RUN_ROOT)
    logging.info(f"Project zipped successfully at: {ZIP_PATH}")
except Exception as e:
    logging.error(f"Error zipping the project: {e}")