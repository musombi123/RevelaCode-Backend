import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/138.0 Safari/537.36"
    )
}


def add_unique(lst, value):
    if value and value not in lst:
        lst.append(value)


def extract_media(article_url):
    media = {
        "images": [],
        "videos": []
    }

    try:
        r = requests.get(
            article_url,
            headers=HEADERS,
            timeout=10,
            allow_redirects=True
        )

        if r.status_code != 200:
            return media

        soup = BeautifulSoup(r.text, "lxml")

        # -----------------------------------
        # Open Graph
        # -----------------------------------

        for tag in soup.find_all("meta"):
            prop = tag.get("property", "")
            name = tag.get("name", "")
            content = tag.get("content")

            if not content:
                continue

            if prop in (
                "og:image",
                "og:image:url",
                "og:image:secure_url"
            ):
                add_unique(media["images"], content)

            elif prop in (
                "og:video",
                "og:video:url",
                "og:video:secure_url"
            ):
                add_unique(media["videos"], content)

            elif name in (
                "twitter:image",
                "twitter:image:src"
            ):
                add_unique(media["images"], content)

            elif name in (
                "twitter:player",
                "twitter:player:stream"
            ):
                add_unique(media["videos"], content)

        # -----------------------------------
        # IMG tags
        # -----------------------------------

        for img in soup.find_all("img"):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
            )

            if src:
                add_unique(media["images"], src)

        # -----------------------------------
        # VIDEO tags
        # -----------------------------------

        for video in soup.find_all("video"):

            if video.get("src"):
                add_unique(media["videos"], video["src"])

            for source in video.find_all("source"):
                if source.get("src"):
                    add_unique(media["videos"], source["src"])

        # -----------------------------------
        # IFRAMES
        # -----------------------------------

        for iframe in soup.find_all("iframe"):

            src = iframe.get("src")

            if not src:
                continue

            if any(
                x in src.lower()
                for x in (
                    "youtube",
                    "youtu.be",
                    "vimeo",
                    "dailymotion"
                )
            ):
                add_unique(media["videos"], src)

    except Exception:
        pass

    return media