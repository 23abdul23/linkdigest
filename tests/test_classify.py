import _run
from linkdigest.classify import canonical, classify, normalize_url


def test_classify_hosts():
    assert classify("https://www.youtube.com/watch?v=abc") == "youtube"
    assert classify("https://youtu.be/abc") == "youtube"
    assert classify("https://m.youtube.com/watch?v=abc") == "youtube"
    assert classify("https://music.youtube.com/watch?v=abc") == "youtube"
    assert classify("https://www.instagram.com/reel/C-cTZA1M9mE/") == "instagram"
    assert classify("https://instagram.com/p/abc/") == "instagram"
    assert classify("https://example.com/blog/post") == "web"
    assert classify("https://notyoutube.com/x") == "web"


def test_normalize_url():
    assert normalize_url("  youtu.be/abc  ") == "https://youtu.be/abc"
    assert normalize_url("https://example.com/a b") == "https://example.com/a b"
    assert normalize_url("hello world") == ""
    assert normalize_url("") == ""
    assert normalize_url("ftp://example.com/x") == ""
    assert normalize_url("javascript:alert(1)") == ""


def test_canonical_youtube_variants_share_one_key():
    want = "https://youtube.com/watch?v=abc123"
    for u in [
        "https://www.youtube.com/watch?v=abc123",
        "https://m.youtube.com/watch?v=abc123&t=30s",
        "https://youtu.be/abc123?si=XYZ",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/watch?v=abc123&list=PL1&index=2&utm_source=x",
    ]:
        assert canonical(u) == want, u


def test_canonical_strips_tracking_and_instagram_query():
    assert canonical("https://www.instagram.com/reel/AbC/?igsh=zzz") == "https://instagram.com/reel/AbC"
    assert canonical("https://Example.com/a/?utm_medium=x&id=5&fbclid=1#top") == "https://example.com/a?id=5"


if __name__ == "__main__":
    _run.main(globals())
