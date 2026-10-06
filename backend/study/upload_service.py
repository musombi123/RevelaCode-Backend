# backend/study/upload_service.py

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from werkzeug.utils import secure_filename


# =========================================================
# LOGGING
# =========================================================

logger = logging.getLogger(
    "revelacode.study.upload_service"
)


# =========================================================
# PATHS
# =========================================================

# backend/study/upload_service.py
#              ↑
# backend/
BASE_DIR = Path(
    os.path.dirname(
        os.path.dirname(__file__)
    )
).resolve()


DEFAULT_UPLOAD_FOLDER = (
    BASE_DIR
    / "user_data"
    / "uploads"
)


# Allow deployment environments to override storage
# without changing source code.
UPLOAD_FOLDER = Path(
    os.getenv(
        "STUDY_UPLOAD_FOLDER",
        str(DEFAULT_UPLOAD_FOLDER),
    )
).expanduser().resolve()


# =========================================================
# LIMITS
# =========================================================

DEFAULT_MAX_UPLOAD_MB = 25

MAX_UPLOAD_MB = max(
    1,
    int(
        os.getenv(
            "STUDY_MAX_UPLOAD_MB",
            str(DEFAULT_MAX_UPLOAD_MB),
        )
    ),
)

MAX_UPLOAD_BYTES = (
    MAX_UPLOAD_MB
    * 1024
    * 1024
)


# =========================================================
# FILE TYPES
# =========================================================

ALLOWED_EXTENSIONS = {
    "pdf",
    "docx",
    "txt",
}


# =========================================================
# MIME TYPES
# =========================================================

EXPECTED_MIME_TYPES = {
    "pdf": {
        "application/pdf",
    },
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    "txt": {
        "text/plain",
        "application/octet-stream",
        "",
    },
}


# =========================================================
# UPLOAD SERVICE
# =========================================================

class UploadService:

    # =====================================================
    # DIRECTORY
    # =====================================================

    @staticmethod
    def ensure_upload_folder() -> Path:
        """
        Create the upload directory when necessary.

        The resulting directory is returned as an absolute
        resolved Path.
        """

        UPLOAD_FOLDER.mkdir(
            parents=True,
            exist_ok=True,
        )

        return UPLOAD_FOLDER

    # =====================================================
    # FILENAME
    # =====================================================

    @staticmethod
    def normalize_filename(
        filename: Any,
    ) -> str:
        """
        Sanitize a client-provided filename.

        Only the basename is retained so directory traversal
        attempts cannot influence the destination path.
        """

        raw = str(
            filename or ""
        ).strip()

        if not raw:
            return ""

        raw = os.path.basename(
            raw
        )

        return secure_filename(
            raw
        )

    # =====================================================
    # EXTENSION
    # =====================================================

    @staticmethod
    def get_extension(
        filename: str,
    ) -> str:
        """
        Return the normalized extension without '.'.
        """

        filename = (
            UploadService.normalize_filename(
                filename
            )
        )

        if "." not in filename:
            return ""

        return (
            filename
            .rsplit(
                ".",
                1,
            )[-1]
            .lower()
            .strip()
        )

    # =====================================================
    # VALIDATE EXTENSION
    # =====================================================

    @staticmethod
    def validate_extension(
        filename: str,
    ) -> str:
        """
        Validate and return the file extension.
        """

        extension = (
            UploadService.get_extension(
                filename
            )
        )

        if extension not in ALLOWED_EXTENSIONS:

            raise ValueError(
                f"Unsupported file type '.{extension or 'file'}'. "
                "Supported formats are PDF, DOCX and TXT."
            )

        return extension

    # =====================================================
    # MIME VALIDATION
    # =====================================================

    @staticmethod
    def validate_mimetype(
        file: Any,
        extension: str,
    ) -> None:
        """
        Perform a lightweight MIME consistency check.

        Browsers/proxies can legitimately send generic MIME
        values such as application/octet-stream, therefore
        this validation is intentionally tolerant.
        """

        mimetype = str(
            getattr(
                file,
                "mimetype",
                "",
            )
            or ""
        ).lower().strip()

        expected = EXPECTED_MIME_TYPES.get(
            extension,
            set(),
        )

        if not expected:
            return

        if mimetype and mimetype not in expected:

            logger.warning(
                "Upload MIME mismatch: extension=%s mimetype=%s",
                extension,
                mimetype,
            )

            # Do not reject solely on browser MIME metadata.
            # Actual file signatures are checked after writing.
    
    # =====================================================
    # COPY STREAM WITH LIMIT
    # =====================================================

    @staticmethod
    def _copy_stream(
        source: Any,
        destination: Any,
    ) -> int:
        """
        Copy an upload stream while enforcing the configured
        maximum size.

        Returns:
            Number of bytes written.
        """

        total = 0

        while True:

            chunk = source.read(
                1024 * 1024
            )

            if not chunk:
                break

            total += len(
                chunk
            )

            if total > MAX_UPLOAD_BYTES:

                raise ValueError(
                    "Uploaded file exceeds the maximum "
                    f"allowed size of {MAX_UPLOAD_MB} MB."
                )

            destination.write(
                chunk
            )

        return total

    # =====================================================
    # STREAM POSITION
    # =====================================================

    @staticmethod
    def _rewind(
        file: Any,
    ) -> None:
        """
        Rewind the uploaded stream when possible.
        """

        try:

            stream = getattr(
                file,
                "stream",
                file,
            )

            stream.seek(
                0
            )

        except Exception:

            # Some custom upload streams may not support seek.
            pass

    # =====================================================
    # SIGNATURE VALIDATION
    # =====================================================

    @staticmethod
    def validate_file_signature(
        path: Path,
        extension: str,
    ) -> None:
        """
        Validate lightweight file signatures.

        PDF:
            %PDF-

        DOCX:
            ZIP container containing Office XML.

        TXT:
            No binary signature is required.
            FileExtractors performs the actual decoding.
        """

        try:

            with open(
                path,
                "rb",
            ) as stream:

                header = stream.read(
                    8
                )

        except OSError as exc:

            raise ValueError(
                "Unable to inspect uploaded file."
            ) from exc

        # -------------------------------------------------
        # PDF
        # -------------------------------------------------

        if extension == "pdf":

            if not header.startswith(
                b"%PDF-"
            ):

                raise ValueError(
                    "The uploaded file does not appear to be a valid PDF."
                )

            return

        # -------------------------------------------------
        # DOCX
        # -------------------------------------------------

        if extension == "docx":

            if not header.startswith(
                b"PK"
            ):

                raise ValueError(
                    "The uploaded DOCX file is not a valid Office document."
                )

            try:

                with zipfile.ZipFile(
                    path,
                    "r",
                ) as archive:

                    names = set(
                        archive.namelist()
                    )

                    required_files = {
                        "[Content_Types].xml",
                        "word/document.xml",
                    }

                    missing = (
                        required_files
                        - names
                    )

                    if missing:

                        raise ValueError(
                            "The uploaded DOCX document is missing "
                            "required Office document components."
                        )

                    if archive.testzip() is not None:

                        raise ValueError(
                            "The uploaded DOCX archive is corrupted."
                        )

            except zipfile.BadZipFile as exc:

                raise ValueError(
                    "The uploaded DOCX document is corrupted."
                ) from exc

            return

        # -------------------------------------------------
        # TXT
        # -------------------------------------------------

        if extension == "txt":
            return

        raise ValueError(
            f"Unsupported file type '.{extension}'."
        )

    # =====================================================
    # SAVE
    # =====================================================

    @staticmethod
    def save(
        file: Any,
    ) -> str:
        """
        Save an uploaded study document safely.

        Pipeline:

            validate filename
                 ↓
            validate extension
                 ↓
            validate MIME metadata
                 ↓
            stream to temporary file
                 ↓
            enforce size limit
                 ↓
            validate file signature
                 ↓
            atomically move to final location

        Returns:
            Absolute file path as a string.
        """

        if file is None:

            raise ValueError(
                "No file was provided."
            )

        raw_filename = getattr(
            file,
            "filename",
            "",
        )

        filename = (
            UploadService.normalize_filename(
                raw_filename
            )
        )

        if not filename:

            raise ValueError(
                "No valid filename was provided."
            )

        extension = (
            UploadService.validate_extension(
                filename
            )
        )

        UploadService.validate_mimetype(
            file,
            extension,
        )

        upload_folder = (
            UploadService.ensure_upload_folder()
        )

        # -------------------------------------------------
        # Generate server-side filename.
        # -------------------------------------------------
        #
        # Never use the client filename as the actual stored
        # filename.
        # -------------------------------------------------

        unique_name = (
            f"{uuid4().hex}.{extension}"
        )

        final_path = (
            upload_folder
            / unique_name
        ).resolve()

        # Extra safety: make sure generated path remains
        # inside configured upload directory.
        try:

            final_path.relative_to(
                upload_folder
            )

        except ValueError as exc:

            raise RuntimeError(
                "Invalid upload destination."
            ) from exc

        temporary_path: Optional[
            Path
        ] = None

        try:

            # -------------------------------------------------
            # Rewind source before copying.
            # -------------------------------------------------

            UploadService._rewind(
                file
            )

            source = getattr(
                file,
                "stream",
                file,
            )

            # -------------------------------------------------
            # Temporary file in the same directory.
            #
            # This makes os.replace() atomic on the same
            # filesystem.
            # -------------------------------------------------

            fd, temp_name = tempfile.mkstemp(
                prefix=".study-upload-",
                suffix=f".{extension}.tmp",
                dir=str(
                    upload_folder
                ),
            )

            temporary_path = Path(
                temp_name
            )

            try:

                with os.fdopen(
                    fd,
                    "wb",
                ) as destination:

                    size = (
                        UploadService._copy_stream(
                            source,
                            destination,
                        )
                    )

                    destination.flush()

                    os.fsync(
                        destination.fileno()
                    )

            except Exception:

                # File descriptor is closed by the context
                # manager if it was successfully opened.
                raise

            # -------------------------------------------------
            # Empty file check.
            # -------------------------------------------------

            if size <= 0:

                raise ValueError(
                    "The uploaded file is empty."
                )

            # -------------------------------------------------
            # Signature validation.
            # -------------------------------------------------

            UploadService.validate_file_signature(
                temporary_path,
                extension,
            )

            # -------------------------------------------------
            # Move into final location.
            # -------------------------------------------------

            os.replace(
                temporary_path,
                final_path,
            )

            temporary_path = None

            logger.info(
                "Study file uploaded: filename=%s type=%s size=%d path=%s",
                filename,
                extension,
                size,
                final_path,
            )

            return str(
                final_path
            )

        except Exception:

            logger.exception(
                "Study file upload failed: %s",
                filename,
            )

            raise

        finally:

            # -------------------------------------------------
            # Remove temporary file if processing failed.
            # -------------------------------------------------

            if (
                temporary_path is not None
                and temporary_path.exists()
            ):

                try:

                    temporary_path.unlink()

                except OSError:

                    logger.warning(
                        "Unable to remove temporary upload: %s",
                        temporary_path,
                    )

    # =====================================================
    # DELETE
    # =====================================================

    @staticmethod
    def delete(
        path: Optional[str],
    ) -> bool:
        """
        Delete a previously uploaded study file.

        Returns:
            True when a file was removed or did not exist.
            False when deletion failed.
        """

        if not path:
            return True

        try:

            target = Path(
                path
            ).resolve()

            upload_folder = (
                UploadService
                .ensure_upload_folder()
                .resolve()
            )

            # Do not allow this service to delete arbitrary
            # files outside the configured upload directory.
            try:

                target.relative_to(
                    upload_folder
                )

            except ValueError:

                logger.warning(
                    "Refusing to delete file outside upload directory: %s",
                    target,
                )

                return False

            if not target.exists():
                return True

            if not target.is_file():
                return False

            target.unlink()

            logger.info(
                "Study upload deleted: %s",
                target,
            )

            return True

        except Exception as exc:

            logger.warning(
                "Unable to delete study upload %s: %s",
                path,
                exc,
            )

            return False

    # =====================================================
    # INFO
    # =====================================================

    @staticmethod
    def max_upload_bytes() -> int:
        """
        Return configured maximum upload size in bytes.
        """

        return MAX_UPLOAD_BYTES

    @staticmethod
    def max_upload_mb() -> int:
        """
        Return configured maximum upload size in MB.
        """

        return MAX_UPLOAD_MB

    @staticmethod
    def allowed_extensions() -> list[str]:
        """
        Return supported upload extensions.
        """

        return sorted(
            ALLOWED_EXTENSIONS
        )