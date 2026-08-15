import urllib.request
import json

def get_youtube_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"

def fetch_title(video_id):
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.load(r).get("title")
    except Exception:
        return None  # video private/deleted/etc — don't fail the whole request over a title