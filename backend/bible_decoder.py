# backend/bible_decoder.py

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# =========================================================
# DATASET
# =========================================================

SYMBOLS_FILE = os.path.join(
    os.path.dirname(__file__),
    "symbols_data.json",
)


def load_symbols_data() -> Dict[str, Any]:
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

        symbols = payload.get("symbols")

        if not isinstance(symbols, dict):
            raise ValueError(
                "symbols_data.json is missing a valid 'symbols' object."
            )

        logger.info(
            "✅ Loaded symbols_data.json | schema=%s | records=%d",
            payload.get(
                "schema_version",
                "unknown",
            ),
            len(symbols),
        )

        return payload

    except Exception as exc:
        logger.exception(
            "❌ Failed to load symbols_data.json: %s",
            exc,
        )

        return {
            "schema_version": "unknown",
            "generated_for": "RevelaCode Prophecy Explorer",
            "generated_note": "",
            "symbols": {},
        }


SYMBOLS_DATA = load_symbols_data()


# =========================================================
# DECODER
# =========================================================

class BibleDecoder:

    def __init__(
        self,
        symbols: Optional[Dict[str, Any]] = None,
    ):
        """
        Accept either the complete dataset:

        {
            "schema_version": "2.0",
            "symbols": {...}
        }

        or only:

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
            and isinstance(
                source.get("symbols"),
                dict,
            )
        ):
            self.source = source
            self.schema_version = source.get(
                "schema_version",
                "unknown",
            )
            self.symbols = source["symbols"]

        else:
            self.source = {
                "schema_version": "unknown",
                "symbols": source or {},
            }
            self.schema_version = "unknown"
            self.symbols = source or {}

    # =====================================================
    # NORMALIZATION
    # =====================================================

    @staticmethod
    def normalize_text(
        text: Any,
    ) -> str:
        text = str(text or "").lower()

        # Turn punctuation into spaces.
        text = re.sub(
            r"[^\w\s]",
            " ",
            text,
        )

        # Collapse whitespace.
        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        return text

    @classmethod
    def tokenize(
        cls,
        text: Any,
    ) -> set:
        normalized = cls.normalize_text(
            text
        )

        if not normalized:
            return set()

        return set(
            normalized.split()
        )

    # =====================================================
    # FIELD COLLECTION
    # =====================================================

    def _flatten(
        self,
        value: Any,
    ) -> List[str]:
        """
        Convert nested lists/dictionaries into
        searchable text.
        """

        values: List[str] = []

        if value is None:
            return values

        if isinstance(value, str):
            values.append(value)
            return values

        if isinstance(value, (int, float)):
            values.append(str(value))
            return values

        if isinstance(value, list):
            for item in value:
                values.extend(
                    self._flatten(item)
                )
            return values

        if isinstance(value, dict):
            for key, item in value.items():
                values.append(str(key))
                values.extend(
                    self._flatten(item)
                )

        return values

    # =====================================================
    # TEXTUAL FIELD
    # =====================================================

    def _field_text(
        self,
        data: Dict[str, Any],
        field: str,
    ) -> str:
        return self.normalize_text(
            " ".join(
                self._flatten(
                    data.get(field)
                )
            )
        )

    # =====================================================
    # SCORE
    # =====================================================

    def score_record(
        self,
        query: str,
        symbol_key: str,
        data: Dict[str, Any],
    ) -> int:

        q = self.normalize_text(query)

        if not q:
            return 0

        q_tokens = self.tokenize(q)

        symbol = self.normalize_text(
            symbol_key
        )

        fields = {
            "symbol": self._field_text(
                data,
                "symbol",
            ),
            "title": self._field_text(
                data,
                "title",
            ),
            "primary_reference": self._field_text(
                data,
                "primary_reference",
            ),
            "cross_references": self._field_text(
                data,
                "cross_references",
            ),
            "summary": self._field_text(
                data,
                "summary",
            ),
            "category": self._field_text(
                data,
                "category",
            ),
            "status": self._field_text(
                data,
                "status",
            ),
            "key_question": self._field_text(
                data,
                "key_question",
            ),
            "curiosity": self._field_text(
                data,
                "curiosity",
            ),
            "related_symbols": self._field_text(
                data,
                "related_symbols",
            ),
            "textual_variants": self._field_text(
                data,
                "textual_variants",
            ),
            "historical_context": self._field_text(
                data,
                "historical_context",
            ),
            "textual_context": self._field_text(
                data,
                "textual_context",
            ),
            "interpretations": self._field_text(
                data,
                "interpretations",
            ),
            "sda_perspective": self._field_text(
                data,
                "sda_perspective",
            ),
            "evidence": self._field_text(
                data,
                "evidence_vs_interpretation",
            ),
        }

        score = 0

        # =================================================
        # EXACT HIGH-VALUE MATCHES
        # =================================================

        if q == symbol:
            score += 250

        if q == fields["symbol"]:
            score += 230

        if q == fields["title"]:
            score += 220

        if q == fields["primary_reference"]:
            score += 200

        # =================================================
        # EXACT PHRASE CONTAINMENT
        # =================================================

        if q in symbol:
            score += 140

        if q in fields["symbol"]:
            score += 130

        if q in fields["title"]:
            score += 120

        if q in fields["primary_reference"]:
            score += 110

        if q in fields["cross_references"]:
            score += 90

        if q in fields["summary"]:
            score += 65

        # =================================================
        # SPECIAL DISCOVERY FIELDS
        # =================================================

        if q in fields["key_question"]:
            score += 70

        if q in fields["curiosity"]:
            score += 60

        if q in fields["related_symbols"]:
            score += 55

        if q in fields["textual_variants"]:
            score += 85

        # =================================================
        # TOKEN OVERLAP
        # =================================================

        weighted_token_sources = [
            ("symbol", 35),
            ("title", 30),
            ("primary_reference", 28),
            ("cross_references", 20),
            ("summary", 15),
            ("key_question", 14),
            ("curiosity", 12),
            ("related_symbols", 10),
            ("interpretations", 8),
            ("historical_context", 7),
        ]

        for field, weight in weighted_token_sources:
            field_tokens = self.tokenize(
                fields[field]
            )

            overlap = (
                q_tokens &
                field_tokens
            )

            if overlap:
                score += min(
                    len(overlap) * weight,
                    weight * 3,
                )

        # =================================================
        # GENERAL FALLBACK
        # =================================================

        all_text = self.normalize_text(
            " ".join(
                fields.values()
            )
        )

        all_tokens = self.tokenize(
            all_text
        )

        overlap = (
            q_tokens &
            all_tokens
        )

        if overlap:
            score += min(
                len(overlap) * 5,
                30,
            )

        return score

    # =====================================================
    # DECODE
    # =====================================================

    def decode_verse(
        self,
        verse: str,
    ) -> Dict[str, Any]:

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

            score = self.score_record(
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

        # Highest relevance first.
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

        # Return only top useful records.
        top_matches = matches[:8]

        decoded = [
            {
                "symbol": item["symbol"],
                "data": item["data"],
            }
            for item in top_matches
        ]

        return {
            "schema_version":
                self.schema_version,
            "query": query,
            "decoded": decoded,
        }

    # =====================================================
    # TEXT ALIAS
    # =====================================================

    def decode_text(
        self,
        text: str,
    ) -> Dict[str, Any]:
        return self.decode_verse(
            text
        )
