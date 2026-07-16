import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/138.0 Safari/537.36"
    )
}

# Reuse one HTTP session for all requests
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
    """
    Add an item only if it exists and is not already present.
    """
    if value and value not in lst:
        lst.append(value)


def absolute_url(base, url):
    """
    Convert relative URLs into absolute URLs.
    """
    if not url:
        return None
    return urljoin(base, url)


def extract_media(article_url):
    """
    Extract images and videos from an article page.

    Returns:
    {
        "images": [...],
        "videos": [...]
    }
    """

    media = {
        "images": [],
        "videos": []
    }

    try:

        response = SESSION.get(
            article_url,
            timeout=(3, 6),
            allow_redirects=True
        )

        if response.status_code != 200:
            logger.debug(
                "Skipped %s (HTTP %s)",
                article_url,
                response.status_code
            )
            return media

        soup = BeautifulSoup(response.text, "lxml")

        # ------------------------------------------------
        # OpenGraph + Twitter Cards
        # ------------------------------------------------

        for tag in soup.find_all("meta"):

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

            # Early exit
            if media["images"] and media["videos"]:
                break

        # ------------------------------------------------
        # HTML Images
        # ------------------------------------------------

        if len(media["images"]) < 3:

            for img in soup.find_all("img", limit=20):

                src = (
                    img.get("src")
                    or img.get("data-src")
                    or img.get("data-original")
                    or img.get("data-lazy-src")
                )

                if not src:
                    continue

                add_unique(
                    media["images"],
                    absolute_url(article_url, src)
                )

                if len(media["images"]) >= 3:
                    break

        # ------------------------------------------------
        # HTML5 Videos
        # ------------------------------------------------

        if not media["videos"]:

            for video in soup.find_all("video", limit=5):

                src = video.get("src")

                if src:
                    add_unique(
                        media["videos"],
                        absolute_url(article_url, src)
                    )

                for source in video.find_all("source"):

                    src = source.get("src")

                    if src:
                        add_unique(
                            media["videos"],
                            absolute_url(article_url, src)
                        )

                if media["videos"]:
                    break

        # ------------------------------------------------
        # Embedded Players
        # ------------------------------------------------

        if not media["videos"]:

            for iframe in soup.find_all("iframe", limit=10):

                src = iframe.get("src")

                if not src:
                    continue

                if any(host in src.lower() for host in VIDEO_HOSTS):

                    add_unique(
                        media["videos"],
                        absolute_url(article_url, src)
                    )

                    break

    except requests.exceptions.Timeout:
        logger.debug("Timeout extracting media: %s", article_url)

    except requests.exceptions.RequestException as e:
        logger.debug(
            "Request failed for %s: %s",
            article_url,
            e
        )

    except Exception as e:
        logger.debug(
            "Media extraction error for %s: %s",
            article_url,
            e
        )

    return media