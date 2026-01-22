from pymongo import MongoClient
from datetime import datetime
import os

# ---------- ENV ----------
MONGO_URI = os.environ.get("MONGO_URI")
DB_NAME = os.environ.get("MONGO_DB_NAME", "revelacode")

if not MONGO_URI:
    raise Exception("❌ MONGO_URI is missing in environment variables")

# ---------- CONNECT ----------
client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsAllowInvalidCertificates=False
)

db = client[DB_NAME]
legal_docs = db["legal_docs"]

# ---------- DOCS TO SEED ----------
docs = [
    {
        "type": "privacy",
        "content": """
## Privacy Policy

**Effective Date:** July 25, 2025

At **RevelaCode**, your privacy is important to us. This Privacy Policy explains how we collect, use, and protect your personal data when you use our platform.

### Information We Collect
- Account details (e.g., email or phone)
- Usage data (e.g., logs, device info)
- Any content you choose to save (e.g., decoded prophecies, notes)

### How We Use Your Data
- To provide and improve the RevelaCode experience
- To personalize your content based on your preferences
- For security, support, and analytics

### Data Sharing
We do **not** sell your data. We only share data with trusted services required to operate the platform, under strict confidentiality.

### Your Rights
- You can request access, updates, or deletion of your data
- You can withdraw consent where applicable

### Contact
If you have questions, contact us at: **support@revelacode.com**
        """.strip(),
        "version": "1.0",
        "lastUpdated": datetime.utcnow()
    },
    {
        "type": "terms",
        "content": """
## Terms of Service

**Effective Date:** July 25, 2025

Welcome to **RevelaCode**. By using this platform, you agree to these Terms of Service.

### 1. Use of Service
- You must be at least 13 years old
- You must not misuse RevelaCode (e.g., hacking, spamming, scraping)

### 2. Content
- You retain ownership of your saved decodes and notes
- RevelaCode may use anonymized data to improve the platform

### 3. Account
- Keep your credentials confidential
- You are responsible for all activity under your account

### 4. Termination
We may suspend or terminate access if you violate these Terms.

### 5. Disclaimer
RevelaCode is provided **“as is”** without warranties. We are not liable for indirect damages.

### Contact
Questions? Email: **support@revelacode.com**
        """.strip(),
        "version": "1.0",
        "lastUpdated": datetime.utcnow()
    }
]

# ---------- SEED ----------
legal_docs.delete_many({})   # wipe old docs
legal_docs.insert_many(docs)

print("✅ Legal docs seeded successfully!")
print(f"📌 Database: {DB_NAME}")
print("📌 Collection: legal_docs")
