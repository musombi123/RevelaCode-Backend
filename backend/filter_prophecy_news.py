import json

HIGH_WEIGHT = {
    "israel": 5,
    "jerusalem": 5,
    "third temple": 10,
    "red heifer": 10,
    "euphrates": 8,
    "gog and magog": 10,
    "mark of the beast": 10,
    "antichrist": 9,
}

MEDIUM_WEIGHT = {
    "war": 3,
    "conflict": 3,
    "invasion": 4,
    "peace deal": 6,
    "treaty": 4,
    "earthquake": 3,
    "famine": 3,
    "pestilence": 3,
    "global crisis": 4,
    "missile": 3,
    "nuclear": 5,
}

LOW_WEIGHT_CONTEXT = {
    "middle east": 2,
    "iran": 3,
    "syria": 3,
    "gaza": 3,
    "russia": 3,
    "china": 2,
    "usa": 2,
    "united nations": 3,
    "economy collapse": 3,
}

IGNORE_TOPICS = [
    "celebrity", "sports", "football", "nba", "music",
    "movie", "entertainment", "fashion", "stock", "crypto"
]


def calculate_score(text):
    text = text.lower()
    score = 0

    for k, v in HIGH_WEIGHT.items():
        if k in text:
            score += v

    for k, v in MEDIUM_WEIGHT.items():
        if k in text:
            score += v

    for k, v in LOW_WEIGHT_CONTEXT.items():
        if k in text:
            score += v

    return score


def is_noise(text):
    return any(word in text.lower() for word in IGNORE_TOPICS)


def extract_entities(text):
    countries = ["israel", "iran", "usa", "russia", "china", "turkey", "syria", "egypt"]
    return [c for c in countries if c in text.lower()]


def filter_prophetic_events(events, threshold=6):
    filtered = []

    for article in events:
        text = (article.get("headline", "") + " " + article.get("description", "")).lower()

        if is_noise(text):
            continue

        score = calculate_score(text)

        if score >= threshold:
            article["prophecy_score"] = score
            article["entities"] = extract_entities(text)
            filtered.append(article)

    return filtered