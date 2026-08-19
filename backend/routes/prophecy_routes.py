# backend/routes/prophecy_routes.py

from flask import Blueprint, jsonify, request

from backend.bible_decoder import BibleDecoder


# =========================================================
# BLUEPRINT
# =========================================================

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
# HELPERS
# =========================================================

def normalize_decoded_results(decoded):
    """
    Ensure the decoder output always uses the frontend-ready
    structure:

    {
        "symbol": "666",
        "data": {...}
    }

    Also supports the legacy shape:

    {
        "666": {...}
    }
    """

    if not isinstance(decoded, list):
        return []

    normalized = []
    seen = set()

    for item in decoded:

        if not isinstance(item, dict):
            continue

        # -------------------------------------------------
        # Error/message response
        # -------------------------------------------------

        if item.get("message"):
            normalized.append({
                "message": str(item["message"])
            })
            continue

        # -------------------------------------------------
        # NEW FORMAT
        #
        # {
        #   "symbol": "666",
        #   "data": {...}
        # }
        # -------------------------------------------------

        if (
            item.get("symbol") and
            isinstance(item.get("data"), dict)
        ):
            symbol = str(
                item["symbol"]
            ).strip()

            normalized_symbol = (
                symbol.lower()
            )

            if normalized_symbol in seen:
                continue

            seen.add(
                normalized_symbol
            )

            normalized.append({
                "symbol": symbol,
                "data": item["data"],
            })

            continue

        # -------------------------------------------------
        # LEGACY FORMAT
        #
        # {
        #   "666": {...}
        # }
        # -------------------------------------------------

        for symbol, symbol_data in item.items():

            if not isinstance(
                symbol_data,
                dict,
            ):
                continue

            symbol_text = str(
                symbol
            ).strip()

            normalized_symbol = (
                symbol_text.lower()
            )

            if normalized_symbol in seen:
                continue

            seen.add(
                normalized_symbol
            )

            normalized.append({
                "symbol": symbol_text,
                "data": symbol_data,
            })

    return normalized


# =========================================================
# DECODE
# =========================================================

@prophecy_bp.route(
    "/decode",
    methods=["POST"],
)
def decode_prophecy():
    """
    Decode a prophecy symbol, verse, reference,
    phrase, or related topic against symbols_data.json.

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
                "data": {...}
            }
        ]
    }
    """

    try:
        # =================================================
        # REQUEST
        # =================================================

        payload = (
            request.get_json(
                silent=True
            )
            or {}
        )

        query = str(
            payload.get(
                "verse",
                ""
            )
        ).strip()

        if not query:
            return jsonify({
                "success": False,
                "message": (
                    "A prophecy, symbol, verse, "
                    "reference, or topic is required."
                ),
            }), 400

        # =================================================
        # DECODE
        # =================================================

        result = decoder.decode_text(
            query
        )

        if not isinstance(
            result,
            dict,
        ):
            return jsonify({
                "success": False,
                "original": query,
                "query": query,
                "count": 0,
                "decoded": [],
                "message": (
                    "Decoder returned an invalid response."
                ),
            }), 500

        # =================================================
        # SCHEMA
        # =================================================

        schema_version = result.get(
            "schema_version",
            getattr(
                decoder,
                "schema_version",
                "unknown",
            ),
        )

        # =================================================
        # RESULTS
        # =================================================

        decoded = normalize_decoded_results(
            result.get(
                "decoded",
                [],
            )
        )

        # =================================================
        # COUNT ONLY REAL RECORDS
        # =================================================

        record_count = sum(
            1
            for item in decoded
            if (
                isinstance(item, dict)
                and item.get("symbol")
                and isinstance(
                    item.get("data"),
                    dict,
                )
            )
        )

        # =================================================
        # NO MATCH
        # =================================================

        if record_count == 0:

            message = next(
                (
                    item.get("message")
                    for item in decoded
                    if isinstance(
                        item,
                        dict,
                    )
                    and item.get("message")
                ),
                (
                    f'No verified prophecy record '
                    f'matched "{query}".'
                ),
            )

            return jsonify({
                "success": True,
                "schema_version":
                    schema_version,
                "original": query,
                "query": query,
                "count": 0,
                "decoded": [],
                "message": message,
            }), 200

        # =================================================
        # SUCCESS
        # =================================================

        return jsonify({
            "success": True,
            "schema_version":
                schema_version,
            "original": query,
            "query": query,
            "count": record_count,
            "decoded": decoded,
        }), 200

    # =====================================================
    # CLIENT / VALIDATION ERROR
    # =====================================================

    except ValueError as exc:

        return jsonify({
            "success": False,
            "message": str(exc),
        }), 400

    # =====================================================
    # SERVER ERROR
    # =====================================================

    except Exception as exc:

        print(
            "❌ Prophecy decode error:",
            exc,
        )

        return jsonify({
            "success": False,
            "message": (
                "Failed to decode prophecy."
            ),
            "error": str(exc),
        }), 500
