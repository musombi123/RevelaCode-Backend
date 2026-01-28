# backend/user_data/user_functions.py

from .store import (
    create_user,
    authenticate
)

def register_user(email: str, password: str):
    """
    Creates a new user account.
    Raises ValueError if user already exists.
    """
    return create_user(email=email, password=password)


def login_user(email: str, password: str):
    """
    Authenticates a user.
    Returns user dict or None.
    """
    return authenticate(email=email, password=password)
