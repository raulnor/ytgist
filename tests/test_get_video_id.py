import pytest

from ytt.transcript import get_video_id

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize("url", [
    VID,
    f"https://www.youtube.com/watch?v={VID}",
    f"https://youtu.be/{VID}",
    f"https://youtu.be/{VID}?si=AbCdEfGhIjKl",
    f"https://www.youtube.com/live/{VID}",
    f"https://www.youtube.com/shorts/{VID}",
    f"https://m.youtube.com/watch?v={VID}&list=PLrAXtmErZgOeiKm4sgNOkn",
    f"https://www.youtube.com/watch?time_continue=5&v={VID}",
    f"https://www.youtube-nocookie.com/embed/{VID}",
    f"https://www.youtube.com/watch?ab_channel=SomeLongChannel&v={VID}",
])
def test_extracts_video_id(url):
    assert get_video_id(url) == VID


@pytest.mark.parametrize("bad", [
    "",
    "not a video",
    "../../../tmp/secret",
    "https://www.youtube.com/@RickAstleyYT",
    VID + "ZZ",
])
def test_rejects_non_ids(bad):
    with pytest.raises(RuntimeError):
        get_video_id(bad)