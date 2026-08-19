# backend/bible_decoder.py

import json
import logging
import os
import re


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO
)


# =========================================================
# DATASET
# =========================================================

SYMBOLS_FILE = os.path.join(
    os.path.dirname(__file__),
    "symbols_data.json",
)


def load_symbols_data():
    try:
        with open(
            SYMBOLS_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)

        if not isinstance(payload, dict):
            raise ValueError(
                "symbols_data.json must contain a JSON object."
            )

        symbols = payload.get(
            "symbols",
            {},
        )

        if not isinstance(symbols, dict):
            raise ValueError(
                "symbols_data.json must contain a valid 'symbols' object."
            )

        logger.info(
            "✅ Loaded symbols_data.json | schema=%s | symbols=%d",
            payload.get(
                "schema_version",
                "unknown",
            ),
            len(symbols),
        )

        return payload

    except Exception as exc:
        logger.exception(
            "❌ Could not load symbols_data.json: %s",
            exc,
        )

        return {
            "schema_version": "unknown",
            "symbols": {},
        }


SYMBOLS_DATA = load_symbols_data()


# =========================================================
# DECODER
# =========================================================

class BibleDecoder:

    def __init__(self, symbols=None):
        """
        Supports either:

        Full dataset:
        {
            "schema_version": "2.0",
            "symbols": {...}
        }

        OR directly supplied symbols:
        {
            "666": {...},
            "beast": {...}
        }
        """

        source = (
            symbols
            if symbols is not None
            else SYMBOLS_DATA
        )

        if (
            isinstance(source, dict)
            and "symbols" in source
        ):
            self.source = source

            self.schema_version = source.get(
                "schema_version",
                "unknown",
            )

            self.symbols = source.get(
                "symbols",
                {},
            )

        else:
            self.source = {
                "schema_version": "unknown",
                "symbols": source or {},
            }

            self.schema_version = "unknown"
            self.symbols = source or {}

        if not isinstance(
            self.symbols,
            dict,
        ):
            self.symbols = {}

    # =====================================================
    # TEXT NORMALIZATION
    # =====================================================

    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize text for reliable matching.

        Examples:

        "Mark of the Beast!"
        -> "mark of the beast"

        "Revelation 13:18"
        -> "revelation 13 18"
        """

        text = str(
            text or ""
        ).lower()

        text = re.sub(
            r"[^\w\s]",
            " ",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        return text

    # =====================================================
    # TOKENIZATION
    # =====================================================

    @classmethod
    def tokenize(cls, text: str):
        normalized = cls.normalize_text(
            text
        )

        if not normalized:
            return set()

        return set(
            normalized.split()
        )

    # =====================================================
    # COLLECT SEARCHABLE VALUES
    # =====================================================

    def _collect_search_values(
        self,
        value,
        output,
    ):
        """
        Recursively collect strings/numbers
        from nested dictionaries and lists.

        This lets the decoder search fields such as:

        - symbol
        - title
        - summary
        - primary_reference
        - cross_references
        - historical_context
        - interpretations
        - sda_perspective
        - textual_variants
        - curiosity
        - related_symbols
        - evidence_vs_interpretation
        - confidence
        - sources
        """

        if value is None:
            return

        if isinstance(value, str):
            output.append(value)
            return

        if isinstance(value, (int, float)):
            output.append(str(value))
            return

        if isinstance(value, list):
            for item in value:
                self._collect_search_values(
                    item,
                    output,
                )
            return

        if isinstance(value, dict):
            for key, item in value.items():
                output.append(str(key))

                self._collect_search_values(
                    item,
                    output,
                )

    # =====================================================
    # SEARCH DOCUMENT
    # =====================================================

    def build_search_text(
        self,
        symbol_key,
        data,
    ):
        values = [
            str(symbol_key)
        ]

        self._collect_search_values(
            data,
            values,
        )

        return self.normalize_text(
            " ".join(values)
        )

    # =====================================================
    # FIELD-SPECIFIC SCORING
    # =====================================================

    def score_match(
        self,
        query,
        symbol_key,
        data,
    ):
        normalized_query = (
            self.normalize_text(query)
        )

        if not normalized_query:
            return 0

        symbol = self.normalize_text(
            symbol_key
        )

        data_symbol = self.normalize_text(
            data.get(
                "symbol",
                "",
            )
        )

        title = self.normalize_text(
            data.get(
                "title",
                "",
            )
        )

        summary = self.normalize_text(
            data.get(
                "summary",
                "",
            )
        )

        primary_reference = (
            self.normalize_text(
                data.get(
                    "primary_reference",
                    "",
                )
            )
        )

        category = self.normalize_text(
            data.get(
                "category",
                "",
            )
        )

        keywords = self.tokenize(
            " ".join(
                str(item)
                for item in data.get(
                    "keywords",
                    [],
                )
                if item is not None
            )
        )

        query_tokens = self.tokenize(
            normalized_query
        )

        score = 0

        # -------------------------------------------------
        # EXACT MATCHES
        # -------------------------------------------------

        if normalized_query == symbol:
            score += 150

        if normalized_query == data_symbol:
            score += 145

        if normalized_query == title:
            score += 135

        if normalized_query == primary_reference:
            score += 125

        # -------------------------------------------------
        # PREFIX MATCHES
        # -------------------------------------------------

        if symbol.startswith(
            normalized_query
        ):
            score += 80

        if title.startswith(
            normalized_query
        ):
            score += 75

        # -------------------------------------------------
        # PHRASE MATCHES
        # -------------------------------------------------

        if normalized_query in title:
            score += 65

        if normalized_query in primary_reference:
            score += 60

        if normalized_query in summary:
            score += 40

        if normalized_query in category:
            score += 30

        # -------------------------------------------------
        # KEYWORD OVERLAP
        # -------------------------------------------------

        keyword_overlap = (
            query_tokens & keywords
        )

        if keyword_overlap:
            score += min(
                len(keyword_overlap) * 15,
                60,
            )

        # -------------------------------------------------
        # FULL KNOWLEDGE-BASE OVERLAP
        # -------------------------------------------------

        searchable_text = (
            self.build_search_text(
                symbol_key,
                data,
            )
        )

        searchable_tokens = (
            self.tokenize(
                searchable_text
            )
        )

        overlap = (
            query_tokens
            &
            searchable_tokens
        )

        if overlap:
            score += min(
                len(overlap) * 8,
                40,
            )

        return score

    # =====================================================
    # DECODE
    # =====================================================

    def decode_verse(
        self,
        verse: str,
    ):
        """
        Search the prophecy knowledge base.

        Returns:

        {
            "schema_version": "2.0",
            "query": "666",
            "decoded": [
                {
                    "666": {...}
                }
            ]
        }
        """

        query = str(
            verse or ""
        ).strip()

        if not query:
            return {
                "schema_version":
                    self.schema_version,
                "query": "",
                "decoded": [],
            }

        matches = []

        for symbol_key, data in self.symbols.items():
            if not isinstance(
                data,
                dict,
            ):
                continue

            score = self.score_match(
                query,
                symbol_key,
                data,
            )

            if score <= 0:
                continue

            matches.append(
                {
                    "score": score,
                    "symbol": symbol_key,
                    "data": data,
                }
            )

        # -------------------------------------------------
        # SORT BY RELEVANCE
        # -------------------------------------------------

        matches.sort(
            key=lambda item: (
                item["score"],
                len(
                    str(
                        item["symbol"]
                    )
                ),
            ),
            reverse=True,
        )

        # -------------------------------------------------
        # RETURN TOP RESULTS
        # -------------------------------------------------

        decoded = []

        for item in matches[:10]:
            decoded.append(
                {
                    item["symbol"]: item["data"]
                }
            )

        # -------------------------------------------------
        # NO MATCH
        # -------------------------------------------------

        if not decoded:
            decoded = [
                {
                    "message": (
                        "No symbolic meaning detected "
                        f"for '{query}'."
                    )
                }
            ]

        return {
            "schema_version":
                self.schema_version,
            "query": query,
            "decoded": decoded,
        }

    # =====================================================
    # FRONTEND/API ALIAS
    # =====================================================

    def decode_text(
        self,
        verse: str,
    ):
        return self.decode_verse(
            verse
        )
