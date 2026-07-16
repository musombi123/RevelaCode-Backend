import requests
from bs4 import BeautifulSoup


def extract_media(article_url):
    media = {
        "images": [],
        "videos": [],
    }

    try:
        headers = {
            "User-Agent":
            "Mozilla/5.0"
        }

        r = requests.get(article_url, timeout=10, headers=headers)

        soup = BeautifulSoup(r.text, "html.parser")

        # OpenGraph Image
        og = soup.find("meta", property="og:image")

        if og:
            media["images"].append(og.get("content"))

        # Twitter Image
        tw = soup.find("meta", attrs={"name": "twitter:image"})

        if tw:
            media["images"].append(tw.get("content"))

        # OpenGraph Video
        ogv = soup.find("meta", property="og:video")

        if ogv:
            media["videos"].append(ogv.get("content"))

        # HTML5 videos
        for video in soup.find_all("video"):
            src = video.get("src")

            if src:
                media["videos"].append(src)

        # YouTube iframes
        for iframe in soup.find_all("iframe"):

            src = iframe.get("src")

            if src and "youtube" in src:
                media["videos"].append(src)

        media["images"] = list(set(media["images"]))
        media["videos"] = list(set(media["videos"]))

    except Exception:
        pass

    return media