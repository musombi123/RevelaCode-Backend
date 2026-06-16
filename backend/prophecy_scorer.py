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

MEDIUM = {
    "war": 3,
    "conflict": 3,
    "invasion": 4,
    "peace treaty": 6,
    "earthquake": 3,
    "famine": 3,
    "nuclear": 5,
    "middle east": 2,
}

def score(text: str) -> int:
    text = text.lower()
    total = 0

    for k, v in HIGH.items():
        if k in text:
            total += v

    for k, v in MEDIUM.items():
        if k in text:
            total += v

    return total