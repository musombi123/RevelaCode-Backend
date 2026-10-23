# backend/jumuiya/elimu/library/services.py
"""School-scoped catalogue and book circulation for the optional Librarian role."""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from backend.jumuiya.core.database import collection
from backend.jumuiya.core.errors import APIError
from backend.jumuiya.elimu.permissions import authorize

BOOKS = "jumuiya_elimu_library_books"
LOANS = "jumuiya_elimu_library_loans"


def _now():
    return datetime.now(timezone.utc)


def _text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip()[:limit]


def _number(value: Any, field: str, *, minimum: float = 0, maximum: float = 1_000_000) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise APIError(f"{field} must be a number.", 422, "validation_error")
    if not isfinite(parsed) or parsed < minimum or parsed > maximum:
        raise APIError(f"{field} must be between {minimum:g} and {maximum:g}.", 422, "validation_error")
    return parsed


def _id_candidates(value: Any) -> list[Any]:
    normalized = _text(value, 160)
    if not normalized:
        return []
    values: list[Any] = [normalized]
    if ObjectId.is_valid(normalized):
        values.append(ObjectId(normalized))
    return values


def _serialize(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


def _doc(value: dict | None) -> dict | None:
    if not value:
        return None
    output = _serialize(value)
    output["id"] = str(value.get("_id") or value.get("id") or "")
    return output


def _context(user_id: Any, permission: str) -> tuple[dict, str]:
    member = authorize(user_id, permission)
    school_id = _text(member.get("school_id"), 160)
    if not school_id:
        raise APIError("An active school membership is required.", 403, "school_membership_required")
    return member, school_id


def list_books(user_id: Any) -> dict:
    _, school_id = _context(user_id, "library.view")
    books = list(collection(BOOKS).find({"school_id": school_id}).sort([("title", 1)]).limit(1000))
    return {"books": [_doc(book) for book in books], "count": len(books)}


def create_book(user_id: Any, data: dict) -> dict:
    _, school_id = _context(user_id, "library.manage")
    title = _text(data.get("title"), 200)
    if not title:
        raise APIError("Book title is required.", 422, "validation_error")
    try:
        total = int(_number(data.get("copies_total", 1), "Total copies", minimum=1, maximum=100000))
    except (TypeError, ValueError):
        raise APIError("Total copies must be a positive whole number.", 422, "validation_error")
    if total < 1:
        raise APIError("Total copies must be at least 1.", 422, "validation_error")
    now = _now()
    book = {
        "school_id": school_id,
        "title": title,
        "author": _text(data.get("author"), 180),
        "isbn": _text(data.get("isbn"), 80),
        "category": _text(data.get("category") or "General", 100),
        "shelf_location": _text(data.get("shelf_location"), 100),
        "description": _text(data.get("description"), 2000),
        "copies_total": total,
        "copies_available": total,
        "created_by_user_id": _text(user_id, 160),
        "updated_by_user_id": _text(user_id, 160),
        "created_at": now,
        "updated_at": now,
    }
    result = collection(BOOKS).insert_one(book)
    book["_id"] = result.inserted_id
    return {"book": _doc(book)}


def update_book(user_id: Any, book_id: Any, data: dict) -> dict:
    _, school_id = _context(user_id, "library.manage")
    candidates = _id_candidates(book_id)
    if not candidates:
        raise APIError("A valid book ID is required.", 422, "invalid_book_id")
    updates = {}
    for field, limit in (("title", 200), ("author", 180), ("isbn", 80), ("category", 100), ("shelf_location", 100), ("description", 2000)):
        if field in data:
            updates[field] = _text(data[field], limit)
    if "copies_total" in data:
        total = int(_number(data["copies_total"], "Total copies", minimum=1, maximum=100000))
        current = collection(BOOKS).find_one({"school_id": school_id, "_id": {"$in": candidates}})
        if not current:
            raise APIError("Book was not found in this school.", 404, "book_not_found")
        borrowed = int(current.get("copies_total", 0) or 0) - int(current.get("copies_available", 0) or 0)
        if total < borrowed:
            raise APIError("Total copies cannot be less than the number of copies currently on loan.", 409, "book_copies_on_loan")
        updates["copies_total"] = total
        updates["copies_available"] = total - borrowed
    if not updates:
        raise APIError("At least one book field is required.", 422, "empty_update")
    if "title" in updates and not updates["title"]:
        raise APIError("Book title cannot be blank.", 422, "validation_error")
    updates.update({"updated_by_user_id": _text(user_id, 160), "updated_at": _now()})
    book = collection(BOOKS).find_one_and_update({"school_id": school_id, "_id": {"$in": candidates}}, {"$set": updates}, return_document=ReturnDocument.AFTER)
    if not book:
        raise APIError("Book was not found in this school.", 404, "book_not_found")
    return {"book": _doc(book)}


def list_loans(user_id: Any, status: str | None = None) -> dict:
    _, school_id = _context(user_id, "library.view")
    query = {"school_id": school_id}
    normalized = _text(status, 20).lower()
    if normalized in {"active", "returned", "overdue"}:
        query["status"] = normalized
    loans = list(collection(LOANS).find(query).sort([("created_at", -1)]).limit(1000))
    now = _now()
    output = []
    for loan in loans:
        item = dict(loan)
        due = loan.get("due_date")
        if loan.get("status") == "active" and due:
            try:
                due_date = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
                if due_date.tzinfo is None:
                    due_date = due_date.replace(tzinfo=timezone.utc)
                if due_date < now:
                    item["status"] = "overdue"
            except (TypeError, ValueError):
                pass
        output.append(_doc(item))
    return {"loans": output, "count": len(output)}


def create_loan(user_id: Any, data: dict) -> dict:
    _, school_id = _context(user_id, "library.manage")
    book_id = data.get("book_id") or data.get("bookId")
    candidates = _id_candidates(book_id)
    if not candidates:
        raise APIError("Choose a book to issue.", 422, "invalid_book_id")
    borrower = _text(data.get("borrower_name") or data.get("student_name"), 160)
    admission_number = _text(data.get("admission_number"), 80)
    due_date = _text(data.get("due_date"), 40)
    if not borrower:
        raise APIError("Borrower name is required.", 422, "validation_error")
    book = collection(BOOKS).find_one_and_update(
        {"school_id": school_id, "_id": {"$in": candidates}, "copies_available": {"$gte": 1}},
        {"$inc": {"copies_available": -1}, "$set": {"updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not book:
        exists = collection(BOOKS).find_one({"school_id": school_id, "_id": {"$in": candidates}})
        if not exists:
            raise APIError("Book was not found in this school.", 404, "book_not_found")
        raise APIError("No copies of this book are currently available.", 409, "book_unavailable")
    now = _now()
    loan = {
        "school_id": school_id,
        "book_id": str(book.get("_id")),
        "book_title": book.get("title", ""),
        "borrower_name": borrower,
        "admission_number": admission_number,
        "issued_by_user_id": _text(user_id, 160),
        "issued_at": now,
        "due_date": due_date,
        "status": "active",
        "returned_at": None,
        "returned_by_user_id": "",
        "notes": _text(data.get("notes"), 1000),
        "created_at": now,
        "updated_at": now,
    }
    result = collection(LOANS).insert_one(loan)
    loan["_id"] = result.inserted_id
    return {"loan": _doc(loan), "book": _doc(book)}


def return_loan(user_id: Any, loan_id: Any, data: dict | None = None) -> dict:
    _, school_id = _context(user_id, "library.manage")
    candidates = _id_candidates(loan_id)
    if not candidates:
        raise APIError("A valid loan ID is required.", 422, "invalid_loan_id")
    loan = collection(LOANS).find_one_and_update(
        {"school_id": school_id, "_id": {"$in": candidates}, "status": "active"},
        {"$set": {"status": "returned", "returned_at": _now(), "returned_by_user_id": _text(user_id, 160), "return_notes": _text((data or {}).get("notes"), 1000), "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not loan:
        existing = collection(LOANS).find_one({"school_id": school_id, "_id": {"$in": candidates}})
        if not existing:
            raise APIError("Loan was not found in this school.", 404, "loan_not_found")
        raise APIError("This loan has already been returned.", 409, "loan_already_returned")
    book = collection(BOOKS).find_one_and_update(
        {"school_id": school_id, "_id": {"$in": _id_candidates(loan.get("book_id"))}},
        {"$inc": {"copies_available": 1}, "$set": {"updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not book:
        raise APIError("Loan was returned, but its catalogue record is missing. Contact the school administrator.", 409, "book_missing")
    return {"loan": _doc(loan), "book": _doc(book)}
