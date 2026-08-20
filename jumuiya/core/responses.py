from flask import jsonify

def ok(data=None, message=None, status_code=200, meta=None):
    payload = {"success": True}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    if meta is not None:
        payload["meta"] = meta
    return jsonify(payload), status_code

def created(data=None, message="Created successfully"):
    return ok(data, message, 201)
