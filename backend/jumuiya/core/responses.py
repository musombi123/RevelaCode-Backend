from flask import jsonify

def ok(data=None, message=None, status_code=200):
    payload = {"success": True}
    if message:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status_code

def created(data=None, message="Created successfully"):
    return ok(data, message, 201)
