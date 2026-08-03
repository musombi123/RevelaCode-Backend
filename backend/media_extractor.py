import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/138.0 Safari/537.36"
    )
}

# Reuse one HTTP session
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


def add_unique(lst, value):
    if value and value not in lst:
        lst.append(value)


def absolute_url(base, url):
    if not url:
        return None
    return urljoin(base, url)


def extract_media(article_url):
    """
    Fast, non-blocking media extraction.

    Returns:
    {
        "images": [],
        "videos": []
    }

    This function is intentionally designed to fail fast so it never
    delays event ingestion.
    """

    media = {
        "images": [],
        "videos": []
    }

    try:

        response = SESSION.get(
            article_url,
            timeout=(1.5, 2.5),      # MUCH faster timeout
            allow_redirects=True,
            stream=True
        )

        if response.status_code != 200:
            return media

        content_type = response.headers.get("Content-Type", "").lower()

        if "text/html" not in content_type:
            return media

        # Parse only the beginning of the page.
        html = response.text[:500000]

        soup = BeautifulSoup(html, "lxml")

        # ----------------------------------------------------
        # OpenGraph / Twitter Metadata
        # ----------------------------------------------------

        for tag in soup.find_all("meta", limit=50):

            content = tag.get("content")

            if not content:
                continue

            prop = tag.get("property", "")
            name = tag.get("name", "")

            if prop in IMAGE_PROPS:
                add_unique(
                    media["images"],
                    absolute_url(article_url, content)
                )

            elif prop in VIDEO_PROPS:
                add_unique(
                    media["videos"],
                    absolute_url(article_url, content)
                )

            elif name in TWITTER_IMAGES:
                add_unique(
                    media["images"],
                    absolute_url(article_url, content)
                )

            elif name in TWITTER_VIDEOS:
                add_unique(
                    media["videos"],
                    absolute_url(article_url, content)
                )

            # We already found enough.
            if len(media["images"]) >= 1 and len(media["videos"]) >= 1:
                return media

        # ----------------------------------------------------
        # Images
        # ----------------------------------------------------

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
                        absolute_url(article_url, src)
                    )

                if len(media["images"]) >= 3:
                    break

        # ----------------------------------------------------
        # HTML5 Video
        # ----------------------------------------------------

        if not media["videos"]:

            for video in soup.find_all("video", limit=3):

                src = video.get("src")

                if src:
                    add_unique(
                        media["videos"],
                        absolute_url(article_url, src)
                    )

                if media["videos"]:
                    break

                for source in video.find_all("source", limit=2):

                    src = source.get("src")

                    if src:
                        add_unique(
                            media["videos"],
                            absolute_url(article_url, src)
                        )

                if media["videos"]:
                    break

        # ----------------------------------------------------
        # Embedded Video
        # ----------------------------------------------------

        if not media["videos"]:

            for iframe in soup.find_all("iframe", limit=5):

                src = iframe.get("src")

                if (
                    src
                    and any(host in src.lower() for host in VIDEO_HOSTS)
                ):
                    add_unique(
                        media["videos"],
                        absolute_url(article_url, src)
                    )
                    break

    except requests.exceptions.Timeout:
        logger.debug("Media timeout: %s", article_url)

    except requests.exceptions.RequestException as e:
        logger.debug("Media request failed: %s (%s)", article_url, e)

    except Exception:
        logger.exception("Media extraction failed: %s", article_url)

    return media
