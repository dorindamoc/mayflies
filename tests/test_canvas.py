import base64
import pytest
from canvas import CanvasError, check_svg, image_tokens, png_size, render_svg

pytest.importorskip("resvg_py")

RECT = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 50"><rect width="50" height="50" fill="red"/></svg>'
TALL = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 100"><rect width="10" height="100"/></svg>'


def test_renders_a_png_at_the_requested_width():
    png = render_svg(RECT, 512)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and png_size(png) == (512, 256)


def test_a_tall_drawing_is_kept_within_the_size_in_both_directions():
    w, h = png_size(render_svg(TALL, 512))
    assert h <= 512 and w <= 512


def test_invalid_svg_is_a_canvas_error_naming_the_problem():
    with pytest.raises(CanvasError) as e:
        render_svg("<svg><oops", 512)
    assert "never closed" in str(e.value)


@pytest.mark.parametrize("bad", [
    '<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///etc/hosts"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><use xlink:href="/etc/x.svg#a"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><use href="http://example.com/x.svg#a"/></svg>',
])
def test_svg_that_could_reach_outside_the_drawing_is_refused(bad):
    with pytest.raises(CanvasError):
        check_svg(bad)


def test_internal_references_are_fine():
    check_svg('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
              '<defs><circle id="c" r="5"/></defs><use xlink:href="#c"/></svg>')


def test_image_tokens_follow_the_measured_cost():
    assert image_tokens(512, 512) == 258 and image_tokens(1024, 1024) == 1026 and image_tokens(64, 64) == 66
