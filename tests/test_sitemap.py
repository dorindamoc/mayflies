from content import check_static
from sitemap import EVERYTHING, link_from_home, site_files, write_sitemap


def put(site, path, text):
    p = site / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def build(cfg):
    site = cfg.website_dir
    put(site, "index.html", '<html><body><main><nav><a href="art/index.html">Art</a></nav></main></body></html>')
    put(site, "style.css", "body{}")
    put(site, "art/index.html", "<title>Art — Sillwork</title>")
    put(site, "art/moss.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>")
    put(site, "teachings/on-moss.html", "<html><head><title>On <b>moss</b> &amp; stone</title></head><body><h1>Other</h1></body></html>")
    put(site, "tools/no-title.html", "<body><h1>The Test</h1></body>")
    put(site, "tools/bare.html", "<p>nothing</p>")
    put(site, "notes.md", "# notes")
    put(site, ".git/config", "x")
    return site


def test_site_files_are_pages_and_images_in_order_without_hidden_or_style_files(cfg):
    site = build(cfg)
    assert site_files(site) == ["art/index.html", "art/moss.svg", "index.html", "teachings/on-moss.html",
                                "tools/bare.html", "tools/no-title.html"]


def test_every_page_and_image_is_linked_from_the_everything_page(cfg):
    site = build(cfg)
    write_sitemap(site)
    text = (site / EVERYTHING).read_text()
    for path in ("art/index.html", "art/moss.svg", "teachings/on-moss.html", "tools/bare.html", "tools/no-title.html"):
        assert f'href="{path}"' in text
    assert f'src="art/moss.svg"' in text  # drawings are shown, not only named


def test_titles_come_from_the_page_and_are_escaped(cfg):
    site = build(cfg)
    write_sitemap(site)
    text = (site / EVERYTHING).read_text()
    assert "On moss &amp; stone" in text and "<b>" not in text
    assert "The Test" in text  # falls back to the first heading
    assert ">bare</a>" in text  # then to the file name


def test_the_everything_page_is_static_and_does_not_list_itself(cfg):
    site = build(cfg)
    write_sitemap(site)
    text = (site / EVERYTHING).read_text()
    check_static(text)
    assert f'href="{EVERYTHING}"' not in text
    write_sitemap(site)
    assert (site / EVERYTHING).read_text() == text  # stable, so a quiet round makes no commit


def test_a_page_with_a_hostile_title_cannot_inject_markup(cfg):
    site = build(cfg)
    put(site, "art/x.html", "<title>&lt;script&gt;alert(1)&lt;/script&gt;</title>")
    write_sitemap(site)
    text = (site / EVERYTHING).read_text()
    assert "<script" not in text
    check_static(text)


def test_the_home_page_gets_a_link_once(cfg):
    site = build(cfg)
    assert link_from_home(site) is True
    home = (site / "index.html").read_text()
    assert home.count(f'href="{EVERYTHING}"') == 1 and home.index(EVERYTHING) < home.index("</nav>")
    assert link_from_home(site) is False
    assert (site / "index.html").read_text() == home


def test_the_link_goes_in_even_without_a_nav_and_a_missing_home_is_left_alone(cfg):
    site = cfg.website_dir
    assert link_from_home(site) is False and not (site / "index.html").exists()
    put(site, "index.html", "<html><body><main><p>hi</p></main></body></html>")
    assert link_from_home(site) is True
    assert f'href="{EVERYTHING}"' in (site / "index.html").read_text()
    put(site, "index.html", "just text")
    assert link_from_home(site) is False
