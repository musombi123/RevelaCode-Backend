from __future__ import annotations

def parse_pagination(args, default_limit=20, max_limit=100):
    try:
        page = max(int(args.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        limit = min(max(int(args.get("limit", default_limit)), 1), max_limit)
    except (TypeError, ValueError):
        limit = default_limit
    return page, limit, (page - 1) * limit

def page_meta(page, limit, total):
    pages = (total + limit - 1) // limit if total else 0
    return {"page": page, "limit": limit, "total": total, "pages": pages, "has_next": page < pages, "has_previous": page > 1}
