# Jumuiya integration

Apply the supplied Jumuiya package under `backend/jumuiya/`. The repository's current Jumuiya package already contains Biashara; these files harden the shared core and make JWT-based identity available to all hubs.

## 1. Existing JWT helper
Replace `backend/auth/jwt_utils.py` with the version in `auth_jwt_utils.py`. The token remains HS256 but now carries `sub` (user id), `contact`, and `role`.

## 2. Existing auth gate login
In `backend/auth_gate.py`, import `generate_token`:

```python
from backend.auth.jwt_utils import generate_token
```

Inside `login()`, after `role = user.get("role", "user")`, generate:

```python
user_id = str(user.get("_id") or user.get("id") or user.get("user_id") or user.get("contact"))
token = generate_token(role=role, user_id=user_id, contact=user.get("contact"))
```

Then add `token=token` to the successful `jsonify(...)` response. This preserves the current response fields while giving Jumuiya a real authenticated request context.

## 3. Existing main.py
After the existing auth/account blueprint registrations, add:

```python
try:
    from backend.jumuiya.integration.register import register_jumuiya
    register_jumuiya(app)
    logger.info("Jumuiya platform registered")
except Exception as e:
    logger.exception("Jumuiya registration failed: %s", e)
```

This registers:
`/api/jumuiya/health` and `/api/jumuiya/biashara/...`

## 4. Environment
Ensure Render has a strong `JWT_SECRET`. Do not use the default `change-me`.

## 5. Client
After login, store the returned token and send:
`Authorization: Bearer <token>`
for protected Jumuiya requests.
