# backend/jumuiya/elimu/library/routes.py
"""Authenticated API routes for the optional school library workspace."""
from __future__ import annotations

from flask import Blueprint, request

from backend.jumuiya.core.errors import APIError
from backend.jumuiya.core.permissions import current_user_id, require_authenticated
from backend.jumuiya.core.responses import created, ok
from . import services

library_bp = Blueprint("jumuiya_elimu_library", __name__, url_prefix="/library")


def _body() -> dict:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise APIError("A JSON object is required.", 400, "invalid_json")
    return value


@library_bp.get("/books")
@require_authenticated
def get_books():
    return ok(services.list_books(current_user_id()))


@library_bp.post("/books")
@require_authenticated
def post_book():
    return created(services.create_book(current_user_id(), _body()), "Library book added.")


@library_bp.patch("/books/<book_id>")
@require_authenticated
def patch_book(book_id: str):
    return ok(services.update_book(current_user_id(), book_id, _body()), "Library book updated.")


@library_bp.get("/loans")
@require_authenticated
def get_loans():
    return ok(services.list_loans(current_user_id(), request.args.get("status")))


@library_bp.post("/loans")
@require_authenticated
def post_loan():
    return created(services.create_loan(current_user_id(), _body()), "Book issued to borrower.")


@library_bp.post("/loans/<loan_id>/return")
@require_authenticated
def return_loan(loan_id: str):
    return ok(services.return_loan(current_user_id(), loan_id, _body()), "Book returned to the school library.")
