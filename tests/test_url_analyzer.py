import pytest

from core import url_analyzer as ua


@pytest.mark.parametrize("url,ok", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True),
    ("https://vimeo.com/76979871", True),
    ("http://127.0.0.1/video.mp4", False),
    ("http://192.168.1.10/a", False),
    ("http://10.0.0.1/a", False),
    ("http://[::1]/a", False),
    ("https://localhost/a", False),
    ("https://printer.local/a", False),
    ("file:///etc/passwd", False),
    ("javascript:alert(1)", False),
    ("https://user:pass@youtube.com/x", False),
    ("ftp://example.com/a", False),
    ("https://exa mple.com", False),
    ("", False),
    ("https://a.com/" + "x" * 3000, False),
])
def test_is_valid_url(url, ok):
    assert ua.is_valid_url(url) is ok


def test_supported():
    assert ua.is_supported("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not ua.is_supported("https://example.com/page")


def test_split_urls_dedup():
    assert ua.split_urls("a\nb, a\n  c ") == ["a", "b", "c"]


def test_parse_info_qualities():
    info = {
        "title": "T", "duration": 100, "extractor_key": "Youtube", "id": "x",
        "formats": [
            {"format_id": "a", "vcodec": "none", "acodec": "opus", "abr": 128, "filesize": 1_000_000},
            {"format_id": "1", "vcodec": "avc1.64", "acodec": "none", "height": 1080, "fps": 30, "filesize": 50_000_000},
            {"format_id": "2", "vcodec": "vp9", "acodec": "none", "height": 1080, "fps": 60, "filesize": 70_000_000},
            {"format_id": "3", "vcodec": "avc1", "acodec": "none", "height": 720, "fps": 30, "tbr": 2000},
        ],
    }
    v = ua.parse_info(info, "u")
    assert [q.height for q in v.qualities] == [1080, 720]
    assert v.best.fps == 60 and v.best.size == 71_000_000
    assert v.qualities[1].size == 2000 * 1000 / 8 * 100 + 1_000_000
    assert v.audio_size == 1_000_000


def test_human():
    assert ua.human_duration(3725) == "1:02:05"
    assert ua.human_duration(65) == "1:05"
    assert ua.human_size(1536) == "1.5 Ko"
