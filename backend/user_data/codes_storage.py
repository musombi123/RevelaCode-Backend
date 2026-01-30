import threading
from .user_helpers import load_users, save_users

# Thread lock for safe writes
file_lock = threading.Lock()

# ------------------ CODE STORAGE ------------------

def store_code(contact: str, code_type: str, code: str, expires: str):
    """
    Stores a code (verification/reset/delete) for a user.
    Does NOT generate code — assumes auth_gate.py already has it.
    """
    users = load_users()
    if contact not in users:
        users[contact] = {"contact": contact}

    user = users[contact]

    with file_lock:
        if code_type == "verify":
            user["verification_code"] = code
            user["verification_expires"] = expires
        elif code_type == "reset":
            user["reset_code"] = code
            user["reset_expires"] = expires
        elif code_type == "delete":
            user["delete_code"] = code
            user["delete_expires"] = expires
        else:
            raise ValueError("Invalid code type")

        save_users(users)


def get_code(contact: str, code_type: str):
    """
    Returns (code, expires) for the user, or (None, None) if missing.
    """
    users = load_users()
    user = users.get(contact)
    if not user:
        return None, None

    if code_type == "verify":
        return user.get("verification_code"), user.get("verification_expires")
    elif code_type == "reset":
        return user.get("reset_code"), user.get("reset_expires")
    elif code_type == "delete":
        return user.get("delete_code"), user.get("delete_expires")
    return None, None


def clear_code(contact: str, code_type: str):
    """
    Clears a used code.
    """
    users = load_users()
    user = users.get(contact)
    if not user:
        return

    with file_lock:
        keys = {
            "verify": ["verification_code", "verification_expires"],
            "reset": ["reset_code", "reset_expires"],
            "delete": ["delete_code", "delete_expires"]
        }

        for k in keys.get(code_type, []):
            user.pop(k, None)

        save_users(users)
