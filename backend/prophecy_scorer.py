# backend/prophecy_scorer.py

from typing import Dict, List

# ======================================================
# HIGH PROPHECY SIGNALS
# ======================================================

HIGH = {
    "israel": 5,
    "jerusalem": 5,
    "third temple": 10,
    "red heifer": 10,
    "euphrates": 8,
    "gog and magog": 10,
    "mark of the beast": 10,
    "antichrist": 9,
}

# ======================================================
# MEDIUM PROPHECY SIGNALS
# ======================================================

MEDIUM = {
    "war": 3,
    "conflict": 3,
    "invasion": 4,
    "peace treaty": 6,
    "peace deal": 6,
    "earthquake": 3,
    "famine": 3,
    "pestilence": 3,
    "nuclear": 5,
    "middle east": 2,
    "global crisis": 4,
    "missile": 3,
}

# ======================================================
# LOW CONTEXT SIGNALS
# ======================================================

LOW = {
    "iran": 3,
    "syria": 3,
    "gaza": 3,
    "russia": 3,
    "china": 2,
    "usa": 2,
    "united nations": 3,
    "economy collapse": 3,
    "red sea": 3,
}

# ======================================================
# ENTITY EXTRACTION
# ======================================================

COUNTRIES = [
    "israel",
    "iran",
    "usa",
    "russia",
    "china",
    "turkey",
    "syria",
    "egypt",
    "gaza"
]

# ======================================================
# SCORE FUNCTION
# ======================================================

def score(text: str) -> int:
    """
    Returns a prophecy score based on keyword weights.
    """

    text = (text or "").lower()

    total = 0

    for keyword, weight in HIGH.items():
        if keyword in text:
            total += weight

    for keyword, weight in MEDIUM.items():
        if keyword in text:
            total += weight

    for keyword, weight in LOW.items():
        if keyword in text:
            total += weight

    return total


# ======================================================
# ENTITY EXTRACTION
# ======================================================

def extract_entities(text: str) -> List[str]:
    text = (text or "").lower()

    return [
        country
        for country in COUNTRIES
        if country in text
    ]


# ======================================================
# FULL ANALYSIS
# ======================================================

def analyze(text: str) -> Dict:
    text = (text or "").lower()

    s = score(text)

    if s >= 15:
        level = "critical"
    elif s >= 10:
        level = "high"
    elif s >= 6:
        level = "medium"
    else:
        level = "low"

    return {
        "score": s,
        "level": level,
        "entities": extract_entities(text)
    }


# ======================================================
# TESTING
# ======================================================

if __name__ == "__main__":
    sample = """
    Israel launches missile strikes against Iran
    amid escalating Middle East conflict.
    """

    result = analyze(sample)

    print(result)