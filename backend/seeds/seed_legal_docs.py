from pymongo import MongoClient
import os

MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=False)
db = client["revelacode"]
legal_docs = db["legal_docs"]

docs = [
    {
        "type": "privacy",
        "content": "## Privacy Policy\n\nEffective Date: July 25, 2025\n...",
        "version": "1.0"
    },
    {
        "type": "terms",
        "content": "## Terms of Service\n\nEffective Date: July 25, 2025\n...",
        "version": "1.0"
    }
]

legal_docs.delete_many({})
legal_docs.insert_many(docs)

print("✅ Legal docs seeded successfully!")
