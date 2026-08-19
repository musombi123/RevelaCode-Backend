# backend/routes/prophecy_routes.py

from flask import Blueprint, request, jsonify
from backend.bible_decoder import BibleDecoder

prophecy_bp = Blueprint(
    "prophecy",
    __name__,
    url_prefix="/api/prophecy",
)

# =========================================================
# DECODER
# =========================================================

decoder = BibleDecoder()


# =========================================================
# PROPHECY DECODE
# =========================================================

@prophecy_bp.route("/decode", methods=["POST"])
def decode_prophecy():
    """
    Decode a prophecy query against symbols_data.json.

    Request:
    {
        "verse": "666"
    }

    Response:
    {
        "success": true,
        "schema_version": "2.0",
        "original": "666",
        "query": "666",
        "count": 1,
        "decoded": [
            {
                "symbol": "666",
                "data": {
                    ...
                }
            }
        ]
    }
    """

    try:
        # ---------------------------------------------------
        # REQUEST VALIDATION
        # ---------------------------------------------------

        data = request.get_json(
            silent=True
        ) or {}

        query = str(
            data.get("verse", "")
        ).strip()

        if not query:
            return jsonify(
                {
                    "success": False,
                    "message": "Verse, symbol, or prophecy query is required.",
                }
            ), 400

        # ---------------------------------------------------
        # DECODE
        # ---------------------------------------------------

        result = decoder.decode_text(
            query
        )

        if not isinstance(
            result,
            dict
        ):
            return jsonify(
                {
                    "success": False,
                    "original": query,
                    "query": query,
                    "count": 0,
                    "decoded": [],
                    "message": "Decoder returned an invalid response.",
                }
            ), 500

        decoded = result.get(
            "decoded",
            []
        )

        if not isinstance(
            decoded,
            list
        ):
            decoded = []

        # ---------------------------------------------------
        # NORMALIZE DECODER OUTPUT
        #
        # Convert:
        #
        # {"666": {...}}
        #
        # into:
        #
        # {
        #   "symbol": "666",
        #   "data": {...}
        # }
        # ---------------------------------------------------

        normalized = []

        for item in decoded:
            if not isinstance(
                item,
                dict
            ):
                continue

            # Error/message record

            if "message" in item:
                normalized.append(
                    {
                        "message": item[
                            "message"
                        ]
                    }
                )
                continue

            # Normal symbol record

            for symbol, symbol_data in item.items():
                if not isinstance(
                    symbol_data,
                    dict
                ):
                    continue

                normalized.append(
                    {
                        "symbol": symbol,
                        "data": symbol_data,
                    }
                )

        # ---------------------------------------------------
        # REMOVE DUPLICATES
        # ---------------------------------------------------

        unique = []
        seen = set()

        for item in normalized:
            symbol = item.get(
                "symbol"
            )

            if not symbol:
                unique.append(item)
                continue

            normalized_symbol = (
                str(symbol)
                .strip()
                .lower()
            )

            if normalized_symbol in seen:
                continue

            seen.add(
                normalized_symbol
            )

            unique.append(item)

        # ---------------------------------------------------
        # NO MATCH
        # ---------------------------------------------------

        if not unique:
            return jsonify(
                {
                    "success": True,
                    "schema_version": decoder.schema_version,
                    "original": query,
                    "query": query,
                    "count": 0,
                    "decoded": [],
                    "message": (
                        f'No verified prophecy record matched "{query}".'
                    ),
                }
            ), 200

        # ---------------------------------------------------
        # SUCCESS
        # ---------------------------------------------------

        return jsonify(
            {
                "success": True,
                "schema_version": decoder.schema_version,
                "original": query,
                "query": query,
                "count": len(unique),
                "decoded": unique,
            }
        ), 200

    # ======================================================
    # ERRORS
    # ======================================================

    except ValueError as exc:
        return jsonify(
            {
                "success": False,
                "message": str(exc),
            }
        ), 400

    except Exception as exc:
        return jsonify(
            {
                "success": False,
                "message": "Failed to decode prophecy.",
                "error": str(exc),
            }
        ), 500
