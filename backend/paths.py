import os

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

EVENTS_DIR = os.path.join(BASE_DIR, "events")
TAGGED_DIR = os.path.join(BASE_DIR, "events_tagged")
DECODED_DIR = os.path.join(BASE_DIR, "events_decoded")
ARCHIVED_DIR = os.path.join(BASE_DIR, "archived")