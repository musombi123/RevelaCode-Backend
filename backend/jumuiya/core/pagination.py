# backend/jumuiya/core/pagination.py

from __future__ import annotations


# =========================================================
# PAGINATION PARSER
# =========================================================

def parse_pagination(
    args,
    default_limit=20,
    max_limit=100,
):
    """
    Parse page/limit query parameters safely.

    Supported:

        ?page=2&limit=20

    Returns:

        page
        limit
        skip
    """

    # -----------------------------------------------------
    # PAGE
    # -----------------------------------------------------

    try:

        page = int(
            args.get(
                "page",
                1,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        page = 1

    page = max(
        page,
        1,
    )

    # -----------------------------------------------------
    # LIMIT
    # -----------------------------------------------------

    try:

        limit = int(
            args.get(
                "limit",
                default_limit,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        limit = default_limit

    limit = min(
        max(
            limit,
            1,
        ),
        max_limit,
    )

    # -----------------------------------------------------
    # SKIP
    # -----------------------------------------------------

    skip = (
        page - 1
    ) * limit

    return (
        page,
        limit,
        skip,
    )


# =========================================================
# PAGE METADATA
# =========================================================

def page_meta(
    page,
    limit,
    total,
):
    """
    Build standard pagination metadata.
    """

    page = max(
        int(page),
        1,
    )

    limit = max(
        int(limit),
        1,
    )

    total = max(
        int(total),
        0,
    )

    pages = (
        (total + limit - 1)
        // limit
        if total
        else 0
    )

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "pages": pages,
        "has_next": (
            page < pages
        ),
        "has_previous": (
            page > 1
        ),
    }


# =========================================================
# PAGINATION WINDOW
# =========================================================

def pagination_window(
    page,
    limit,
    total,
):
    """
    Return the start/end item positions for UI display.

    Example:

        page=2
        limit=20
        total=45

    returns:

        {
            "from": 21,
            "to": 40
        }
    """

    page = max(
        int(page),
        1,
    )

    limit = max(
        int(limit),
        1,
    )

    total = max(
        int(total),
        0,
    )

    if total == 0:

        return {
            "from": 0,
            "to": 0,
        }

    start = (
        (page - 1)
        * limit
    ) + 1

    end = min(
        page * limit,
        total,
    )

    return {
        "from": start,
        "to": end,
    }