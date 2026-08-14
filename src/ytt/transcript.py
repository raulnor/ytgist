from pathlib import Path
import re
import os
import sys
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter

def cache_dir() -> Path:
    """Get location of downloaded transcripts."""
    dir="yt-transcript"
    if xdg := os.environ.get("XDG_CACHE_HOME"):
        return Path(xdg)/dir
    if sys.platform == "darwin":
        return Path.home()/"Library"/"Caches"/dir
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home()))/dir
    return Path.home()/".cache"/dir

def get_video_id(url_or_id):
    """Extract video ID from URL if it's a full URL"""
    video_id_match = re.search(r'([a-zA-Z0-9_-]{11})', url_or_id)
    if video_id_match:
        return video_id_match.group(1)
    else:
        raise RuntimeError(f"video_id not found in {url_or_id}")

def get_transcript_path(url_or_id):
    video_id = get_video_id(url_or_id)
    cache = cache_dir()
    return cache/f"{video_id}.txt"

def fetch_transcript(url_or_id):
    """Download from YouTube."""
    ytt_api = YouTubeTranscriptApi()
    video_id = get_video_id(url_or_id)
    transcript = ytt_api.fetch(video_id)
    formatter = TextFormatter()
    return formatter.format_transcript(transcript)
    

def fetch_transcript_if_needed(url_or_id):
    video_id = get_video_id(url_or_id)
    cache = cache_dir()
    f = cache/f"{video_id}.txt"
    if f.exists() and f.stat().st_size > 0:
        print(f"fetch_transcript_if_needed: cached {f}", file=sys.stderr)
        return f.read_text()
    else:
        print(f"fetch_transcript_if_needed: downloading {f}", file=sys.stderr)
        text = fetch_transcript(video_id)
        if text.strip():
            cache.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp"); tmp.write_text(text); tmp.replace(f)
        return text

def main():
    try:
        if len(sys.argv) < 2:
            print('Usage: provide YouTube URL or video_id as argument', file=sys.stderr)
            sys.exit(1)
        url_or_id = sys.argv[1]
        print(fetch_transcript_if_needed(url_or_id))
    except Exception as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()