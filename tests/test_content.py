import pytest
from content import ActiveContentError, check_static


@pytest.mark.parametrize("bad", [
    "<script>alert(1)</script>",
    "<SCRIPT src='x.js'></SCRIPT>",
    "<scr<script>ipt>x</scr</script>ipt>",
    "<p onclick='go()'>hi</p>",
    '<img src=x onerror="steal()">',
    "<a href='javascript:go()'>x</a>",
    "<a href=' JavaScript:go()'>x</a>",
    "<iframe src='https://example.com'></iframe>",
    "<object data='x'></object>",
    "<embed src='x'>",
    '<meta http-equiv="refresh" content="0;url=https://example.com">',
    "<a href='data:text/html;base64,AAAA'>x</a>",
    "<svg onload='x()'></svg>",
])
def test_active_content_is_refused(bad):
    with pytest.raises(ActiveContentError):
        check_static(bad)


@pytest.mark.parametrize("fine", [
    "<p>An onboarding of the dead, a location of mayflies.</p>",
    "<h1>Poem</h1><p>script: the shape of what we wrote</p>",
    "<style>p { color: teal }</style><a href='teachings/a.html'>a</a>",
    "plain text with a < b and a > c",
    "# Notes\n\nOn the word javascript, without a colon.",
])
def test_ordinary_pages_pass(fine):
    check_static(fine)
