
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, FeatureNotFound

logger = logging.getLogger(__name__)

# =========================================================
# CONFIGURATION
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/138.0 Safari/537.36"
    )
}

CONNECT_TIMEOUT = 1.5
READ_TIMEOUT = 2.5
MAX_HTML_BYTES = 500_000
CHUNK_SIZE = 32 * 1024

# Reuse one HTTP session.
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

VIDEO_HOSTS = (
    "youtube",
    "youtu.be",
    "vimeo",
    "dailymotion",
)

IMAGE_PROPS = {
    "og:image",
    "og:image:url",
    "og:image:secure_url",
}

VIDEO_PROPS = {
    "og:video",
    "og:video:url",
    "og:video:secure_url",
}

TWITTER_IMAGES = {
    "twitter:image",
    "twitter:image:src",
}

TWITTER_VIDEOS = {
    "twitter:player",
    "twitter:player:stream",
}


# =========================================================
# HELPERS
# =========================================================

def add_unique(items, value):
    """Append a non-empty value only if it is not already present."""
    if value and value not in items:
        items.append(value)


def absolute_url(base, url):
    """Convert a relative media URL into an absolute URL."""
    if not url:
        return None

    url = str(url).strip()

    if not url:
        return None

    # Do not return executable or inline-data URLs as media links.
    if url.lower().startswith(("javascript:", "data:")):
        return None

    return urljoin(base, url)


def _read_limited_html(response, limit=MAX_HTML_BYTES):
    """
    Read at most `limit` response-body bytes.

    This avoids reading an arbitrarily large article when only its
    metadata and beginning of the HTML document are needed.
    """
    body = bytearray()

    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
        if not chunk:
            continue

        remaining = limit - len(body)

        if remaining <= 0:
            break

        body.extend(chunk[:remaining])

        if len(body) >= limit:
            break

    if not body:
        return ""

    encoding = response.encoding or "utf-8"

    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        # Guard against invalid or unsupported charset declarations.
        return body.decode("utf-8", errors="replace")


def _parse_html(html):
    """
    Prefer lxml when installed; otherwise use Python's built-in parser.

    This prevents BeautifulSoup FeatureNotFound exceptions from
    disabling media extraction when the optional lxml package is absent.
    """
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        logger.debug(
            "lxml parser is unavailable; falling back to html.parser"
        )
        return BeautifulSoup(html, "html.parser")


# =========================================================
# MEDIA EXTRACTION
# =========================================================

def extract_media(article_url):
    """
    Extract images and videos from an article page.

    Returns:
        {
            "images": [],
            "videos": []
        }

    Design goals:
    - Short connection/read timeouts.
    - Limited response-body reading.
    - lxml parser with a built-in parser fallback.
    - Safe handling of request and parsing failures.
    - No media extraction failure should break event ingestion.
    """

    media = {
        "images": [],
        "videos": [],
    }

    if not isinstance(article_url, str) or not article_url.strip():
        return media

    article_url = article_url.strip()

    try:
        # Context manager ensures the response is closed, including
        # when an early return occurs or the body is only partly read.
        with SESSION.get(
            article_url,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=True,
            stream=True,
        ) as response:

            if response.status_code != 200:
                logger.debug(
                    "Media extraction skipped: HTTP %s for %s",
                    response.status_code,
                    article_url,
                )
                return media

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            is_html = (
                "text/html" in content_type
                or "application/xhtml+xml" in content_type
            )

            if not is_html:
                return media

            html = _read_limited_html(response)

            if not html:
                return media

            # Use the final URL after redirects as the base for
            # resolving relative image, video, and iframe URLs.
            page_url = response.url or article_url

        soup = _parse_html(html)

        # -----------------------------------------------------
        # OpenGraph and Twitter metadata
        # -----------------------------------------------------

        for tag in soup.find_all("meta", limit=50):
            content = tag.get("content")

            if not content:
                continue

            prop = (tag.get("property") or "").strip().lower()
            name = (tag.get("name") or "").strip().lower()

            if prop in IMAGE_PROPS:
                add_unique(
                    media["images"],
                    absolute_url(page_url, content),
                )

            elif prop in VIDEO_PROPS:
                add_unique(
                    media["videos"],
                    absolute_url(page_url, content),
                )

            elif name in TWITTER_IMAGES:
                add_unique(
                    media["images"],
                    absolute_url(page_url, content),
                )

            elif name in TWITTER_VIDEOS:
                add_unique(
                    media["videos"],
                    absolute_url(page_url, content),
                )

            # Stop metadata scanning once both types are available.
            if media["images"] and media["videos"]:
                return media

        # -----------------------------------------------------
        # HTML image fallback
        # -----------------------------------------------------

        if not media["images"]:
            for img in soup.find_all("img", limit=10):
                src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-original")
                    or img.get("data-lazy-src")
                )

                if src:
                    add_unique(
                        media["images"],
                        absolute_url(page_url, src),
                    )

                if len(media["images"]) >= 3:
                    break

        # -----------------------------------------------------
        # HTML5 video fallback
        # -----------------------------------------------------

        if not media["videos"]:
            for video in soup.find_all("video", limit=3):
                src = video.get("src")

                if src:
                    add_unique(
                        media["videos"],
                        absolute_url(page_url, src),
                    )

                if media["videos"]:
                    break

                for source in video.find_all("source", limit=2):
                    src = source.get("src")

                    if src:
                        add_unique(
                            media["videos"],
                            absolute_url(page_url, src),
                        )

                if media["videos"]:
                    break

        # -----------------------------------------------------
        # Embedded video fallback
        # -----------------------------------------------------

        if not media["videos"]:
            for iframe in soup.find_all("iframe", limit=5):
                src = iframe.get("src")

                if not src:
                    continue

                resolved_src = absolute_url(page_url, src)

                if (
                    resolved_src
                    and any(
                        host in resolved_src.lower()
                        for host in VIDEO_HOSTS
                    )
                ):
                    add_unique(media["videos"], resolved_src)
                    break

    except requests.exceptions.Timeout:
        logger.debug("Media extraction timed out: %s", article_url)

    except requests.exceptions.RequestException as exc:
        logger.debug(
            "Media request failed for %s: %s",
            article_url,
            exc,
        )

    except Exception:
        # Keep a page-specific failure from breaking the larger
        # event ingestion pipeline.
        logger.exception(
            "Media extraction failed: %s",
            article_url,
        )

    return media