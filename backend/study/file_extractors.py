# backend/study/file_extractors.py

from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any, Iterable, List, Optional


# =========================================================
# OPTIONAL DEPENDENCIES
# =========================================================
#
# pdfplumber gives better PDF text extraction than relying
# exclusively on PyPDF2.
#
# PyPDF2 remains the fallback extractor.
#
# python-docx is required for DOCX documents.
# =========================================================

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None


try:
    from docx import Document
    from docx.document import Document as DocxDocument
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
except ImportError:
    Document = None
    DocxDocument = None
    Table = None
    Paragraph = None
    CT_Tbl = None
    CT_P = None


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger(
    "revelacode.study.extractors"
)


# =========================================================
# CONSTANTS
# =========================================================

TEXT_ENCODINGS = (
    "utf-8-sig",
    "utf-8",
    "cp1252",
    "latin-1",
)

MIN_PDF_TEXT_LENGTH = 20


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def normalize_text(
    value: Any,
) -> str:
    """
    Normalize extracted document text without destroying
    useful paragraph/page structure.
    """

    if value is None:
        return ""

    text = str(
        value
    )

    # -----------------------------------------------------
    # Unicode normalization.
    # -----------------------------------------------------

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    # -----------------------------------------------------
    # Normalize common whitespace characters.
    # -----------------------------------------------------

    text = text.replace(
        "\xa0",
        " ",
    )

    text = text.replace(
        "\r\n",
        "\n",
    )

    text = text.replace(
        "\r",
        "\n",
    )

    # -----------------------------------------------------
    # Remove zero-width characters.
    # -----------------------------------------------------

    text = re.sub(
        r"[\u200b-\u200d\ufeff]",
        "",
        text,
    )

    # -----------------------------------------------------
    # Normalize spaces/tabs without destroying newlines.
    # -----------------------------------------------------

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    # -----------------------------------------------------
    # Remove spaces surrounding newlines.
    # -----------------------------------------------------

    text = re.sub(
        r" *\n *",
        "\n",
        text,
    )

    # -----------------------------------------------------
    # Prevent giant blank areas.
    # -----------------------------------------------------

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


def clean_lines(
    lines: Iterable[Any],
) -> List[str]:
    """
    Normalize a collection of text lines and remove empty
    entries.
    """

    cleaned = []

    for line in lines:

        value = normalize_text(
            line
        )

        if value:
            cleaned.append(
                value
            )

    return cleaned


# =========================================================
# TABLE HELPERS
# =========================================================

def _format_table(
    rows: Any,
) -> str:
    """
    Convert a table into readable plain text.

    Example:

        Name | Meaning | Reference
        Faith | Trust | Hebrews 11
    """

    if not isinstance(
        rows,
        list,
    ):
        return ""

    formatted_rows = []

    for row in rows:

        if not isinstance(
            row,
            (list, tuple),
        ):
            continue

        cells = []

        for cell in row:

            value = normalize_text(
                cell
            )

            if not value:
                value = ""

            cells.append(
                value
            )

        if not any(
            cells
        ):
            continue

        formatted_rows.append(
            " | ".join(
                cells
            )
        )

    if not formatted_rows:
        return ""

    return "\n".join(
        formatted_rows
    )


# =========================================================
# DOCX BLOCK ITERATOR
# =========================================================

def _iter_docx_blocks(
    parent: Any,
):
    """
    Iterate through DOCX paragraphs and tables in their
    original document order.

    This avoids the common problem where:

        paragraphs

    and:

        tables

    are extracted separately and lose their original order.
    """

    if DocxDocument is None:
        return

    if isinstance(
        parent,
        DocxDocument,
    ):
        parent_element = (
            parent.element.body
        )

    else:
        parent_element = (
            parent._tc
        )

    for child in parent_element.iterchildren():

        if CT_P is not None and isinstance(
            child,
            CT_P,
        ):

            yield Paragraph(
                child,
                parent,
            )

        elif CT_Tbl is not None and isinstance(
            child,
            CT_Tbl,
        ):

            yield Table(
                child,
                parent,
            )


# =========================================================
# FILE EXTRACTORS
# =========================================================

class FileExtractors:

    # =====================================================
    # PDF
    # =====================================================

    @staticmethod
    def extract_pdf(
        path: str,
    ) -> str:
        """
        Extract readable text from a PDF.

        Primary:
            pdfplumber

        Fallback:
            PyPDF2

        The output preserves page boundaries so AI/search
        systems can distinguish content from different pages.
        """

        if not path:
            raise ValueError(
                "PDF path is required."
            )

        if not os.path.exists(
            path
        ):
            raise FileNotFoundError(
                f"PDF file not found: {path}"
            )

        if not os.path.isfile(
            path
        ):
            raise ValueError(
                f"PDF path is not a file: {path}"
            )

        # -------------------------------------------------
        # Primary extraction: pdfplumber
        # -------------------------------------------------

        if pdfplumber is not None:

            try:

                text = (
                    FileExtractors
                    ._extract_pdf_pdfplumber(
                        path
                    )
                )

                if len(
                    normalize_text(
                        text
                    )
                ) >= MIN_PDF_TEXT_LENGTH:

                    logger.info(
                        "PDF extracted with pdfplumber: %s",
                        path,
                    )

                    return normalize_text(
                        text
                    )

            except Exception as exc:

                logger.warning(
                    "pdfplumber extraction failed for %s: %s",
                    path,
                    exc,
                )

        # -------------------------------------------------
        # Fallback extraction: PyPDF2
        # -------------------------------------------------

        if PdfReader is not None:

            try:

                text = (
                    FileExtractors
                    ._extract_pdf_pypdf2(
                        path
                    )
                )

                normalized = normalize_text(
                    text
                )

                if normalized:

                    logger.info(
                        "PDF extracted with PyPDF2 fallback: %s",
                        path,
                    )

                    return normalized

            except Exception as exc:

                logger.exception(
                    "PyPDF2 extraction failed for %s",
                    path,
                )

                raise ValueError(
                    "Unable to extract readable text from PDF."
                ) from exc

        # -------------------------------------------------
        # No PDF engine available.
        # -------------------------------------------------

        raise RuntimeError(
            "No PDF extraction engine is available. "
            "Install pdfplumber or PyPDF2."
        )

    # =====================================================
    # PDFPLUMBER
    # =====================================================

    @staticmethod
    def _extract_pdf_pdfplumber(
        path: str,
    ) -> str:
        """
        PDF extraction using pdfplumber.

        Tables are included only when the page's normal
        text extraction is empty or extremely sparse, which
        prevents the common problem of duplicating table text.
        """

        page_sections = []

        with pdfplumber.open(
            path
        ) as pdf:

            if not pdf.pages:

                return ""

            for page_number, page in enumerate(
                pdf.pages,
                start=1,
            ):

                page_parts = []

                # -----------------------------------------
                # Normal page text
                # -----------------------------------------

                page_text = ""

                try:

                    page_text = (
                        page.extract_text(
                            x_tolerance=2,
                            y_tolerance=3,
                        )
                        or ""
                    )

                except Exception as exc:

                    logger.warning(
                        "PDF page %d text extraction failed: %s",
                        page_number,
                        exc,
                    )

                page_text = normalize_text(
                    page_text
                )

                if page_text:
                    page_parts.append(
                        page_text
                    )

                # -----------------------------------------
                # Table fallback
                # -----------------------------------------
                #
                # If the page produced little/no normal
                # text, attempt to preserve table content.
                # -----------------------------------------

                if len(
                    page_text
                ) < MIN_PDF_TEXT_LENGTH:

                    try:

                        tables = (
                            page.extract_tables()
                        )

                        for table in tables or []:

                            table_text = (
                                _format_table(
                                    table
                                )
                            )

                            if table_text:
                                page_parts.append(
                                    table_text
                                )

                    except Exception as exc:

                        logger.debug(
                            "PDF table extraction skipped on page %d: %s",
                            page_number,
                            exc,
                        )

                page_text = normalize_text(
                    "\n\n".join(
                        page_parts
                    )
                )

                if page_text:

                    page_sections.append(
                        f"[Page {page_number}]\n"
                        f"{page_text}"
                    )

        return normalize_text(
            "\n\n".join(
                page_sections
            )
        )

    # =====================================================
    # PYPDF2 FALLBACK
    # =====================================================

    @staticmethod
    def _extract_pdf_pypdf2(
        path: str,
    ) -> str:
        """
        PDF extraction fallback using PyPDF2.
        """

        reader = PdfReader(
            path
        )

        page_sections = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):

            try:

                page_text = (
                    page.extract_text()
                    or ""
                )

            except Exception as exc:

                logger.warning(
                    "PyPDF2 page %d extraction failed: %s",
                    page_number,
                    exc,
                )

                continue

            page_text = normalize_text(
                page_text
            )

            if page_text:

                page_sections.append(
                    f"[Page {page_number}]\n"
                    f"{page_text}"
                )

        return normalize_text(
            "\n\n".join(
                page_sections
            )
        )

    # =====================================================
    # DOCX
    # =====================================================

    @staticmethod
    def extract_docx(
        path: str,
    ) -> str:
        """
        Extract DOCX content while preserving:

            paragraphs
            tables
            headers
            footers
            document order
        """

        if not path:
            raise ValueError(
                "DOCX path is required."
            )

        if not os.path.exists(
            path
        ):
            raise FileNotFoundError(
                f"DOCX file not found: {path}"
            )

        if Document is None:

            raise RuntimeError(
                "python-docx is not installed. "
                "Install python-docx."
            )

        try:

            document = Document(
                path
            )

        except Exception as exc:

            raise ValueError(
                "Unable to open DOCX document."
            ) from exc

        sections = []

        # -------------------------------------------------
        # Main document
        # -------------------------------------------------

        for block in (
            _iter_docx_blocks(
                document
            )
            or []
        ):

            # ---------------------------------------------
            # Paragraph
            # ---------------------------------------------

            if Paragraph is not None and isinstance(
                block,
                Paragraph,
            ):

                value = normalize_text(
                    block.text
                )

                if value:
                    sections.append(
                        value
                    )

            # ---------------------------------------------
            # Table
            # ---------------------------------------------

            elif Table is not None and isinstance(
                block,
                Table,
            ):

                rows = []

                for row in block.rows:

                    cells = []

                    for cell in row.cells:

                        cell_text_parts = []

                        for paragraph in (
                            cell.paragraphs
                            or []
                        ):

                            value = normalize_text(
                                paragraph.text
                            )

                            if value:

                                cell_text_parts.append(
                                    value
                                )

                        cells.append(
                            " ".join(
                                cell_text_parts
                            )
                        )

                    rows.append(
                        cells
                    )

                table_text = _format_table(
                    rows
                )

                if table_text:
                    sections.append(
                        table_text
                    )

        # -------------------------------------------------
        # Headers and footers
        # -------------------------------------------------
        #
        # Add them once per section instead of duplicating
        # the same header/footer for every page.
        # -------------------------------------------------

        supplementary = []

        for section_index, section in enumerate(
            document.sections,
            start=1,
        ):

            header_parts = []

            for paragraph in (
                section.header.paragraphs
                or []
            ):

                value = normalize_text(
                    paragraph.text
                )

                if value:
                    header_parts.append(
                        value
                    )

            if header_parts:

                supplementary.append(
                    f"[Section {section_index} Header]\n"
                    + "\n".join(
                        header_parts
                    )
                )

            footer_parts = []

            for paragraph in (
                section.footer.paragraphs
                or []
            ):

                value = normalize_text(
                    paragraph.text
                )

                if value:
                    footer_parts.append(
                        value
                    )

            if footer_parts:

                supplementary.append(
                    f"[Section {section_index} Footer]\n"
                    + "\n".join(
                        footer_parts
                    )
                )

        if supplementary:

            sections.extend(
                supplementary
            )

        result = normalize_text(
            "\n\n".join(
                sections
            )
        )

        if not result:

            raise ValueError(
                "DOCX document contains no readable text."
            )

        logger.info(
            "DOCX extracted successfully: %s",
            path,
        )

        return result

    # =====================================================
    # TXT
    # =====================================================

    @staticmethod
    def extract_txt(
        path: str,
    ) -> str:
        """
        Extract plain text with encoding fallback.

        Supported encodings:

            UTF-8 with BOM
            UTF-8
            Windows-1252
            Latin-1
        """

        if not path:
            raise ValueError(
                "TXT path is required."
            )

        if not os.path.exists(
            path
        ):
            raise FileNotFoundError(
                f"TXT file not found: {path}"
            )

        if not os.path.isfile(
            path
        ):
            raise ValueError(
                f"TXT path is not a file: {path}"
            )

        last_error: Optional[
            Exception
        ] = None

        for encoding in TEXT_ENCODINGS:

            try:

                with open(
                    path,
                    "r",
                    encoding=encoding,
                ) as file:

                    content = file.read()

                content = normalize_text(
                    content
                )

                if content:

                    logger.info(
                        "TXT extracted successfully using %s: %s",
                        encoding,
                        path,
                    )

                    return content

                # Empty file.
                if content == "":

                    logger.info(
                        "TXT file is empty: %s",
                        path,
                    )

                    return ""

            except UnicodeDecodeError as exc:

                last_error = exc
                continue

            except Exception as exc:

                logger.exception(
                    "TXT extraction failed: %s",
                    path,
                )

                raise ValueError(
                    "Unable to read text file."
                ) from exc

        raise ValueError(
            "Unable to decode text file using supported "
            "encodings."
        ) from last_error

    # =====================================================
    # GENERIC DISPATCHER
    # =====================================================

    @staticmethod
    def extract(
        path: str,
        file_type: Optional[str] = None,
    ) -> str:
        """
        Generic extractor dispatcher.

        Examples:

            FileExtractors.extract("lesson.pdf")
            FileExtractors.extract(
                "lesson.docx",
                "docx"
            )

        Supported:

            pdf
            docx
            txt
        """

        if not path:
            raise ValueError(
                "File path is required."
            )

        extension = (
            str(
                file_type or ""
            )
            .strip()
            .lower()
            .lstrip(".")
        )

        if not extension:

            extension = (
                os.path.splitext(
                    path
                )[1]
                .lower()
                .lstrip(".")
            )

        extractors = {
            "pdf":
                FileExtractors.extract_pdf,

            "docx":
                FileExtractors.extract_docx,

            "txt":
                FileExtractors.extract_txt,
        }

        extractor = extractors.get(
            extension
        )

        if extractor is None:

            supported = ", ".join(
                sorted(
                    extractors.keys()
                )
            )

            raise ValueError(
                f"Unsupported document type '.{extension}'. "
                f"Supported types: {supported}."
            )

        return extractor(
            path
        )

    # =====================================================
    # FILE TYPE
    # =====================================================

    @staticmethod
    def detect_file_type(
        path: str,
    ) -> str:
        """
        Detect file type from filename extension.
        """

        if not path:
            return ""

        return (
            os.path.splitext(
                path
            )[1]
            .lower()
            .lstrip(".")
        )

    # =====================================================
    # SUPPORTED TYPES
    # =====================================================

    @staticmethod
    def supported_types() -> List[str]:
        return [
            "pdf",
            "docx",
            "txt",
        ]
