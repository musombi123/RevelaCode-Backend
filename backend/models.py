# models.py
# lightweight validators for incoming post payloads

def validate_post_payload(payload: dict):
    if not isinstance(payload, dict):
        return False, 'payload must be an object'
    faith = payload.get('faith','other')
    if faith not in ('bible','quran','other'):
        return False, 'faith must be one of bible|quran|other'
    decoded = payload.get('decoded')
    if decoded is None or not isinstance(decoded, dict):
        return False, 'decoded must be an object with at least a "text" field'
    if not decoded.get('text'):
        return False, 'decoded.text is required'
    # optional: more validations: source shape, tags type etc.
    return True, ''
