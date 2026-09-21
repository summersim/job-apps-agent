"""Page rendering and static-asset serving."""

from jobs_agent.web import pages


def test_nav_marks_the_active_page():
    assert 'href="/" class="active"' in pages.nav("queue")
    assert 'href="/documents" class="active"' in pages.nav("documents")


def test_queue_page_escapes_the_candidate_name():
    html = pages.queue_page('<script>alert("x")</script>')
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_pages_have_no_placeholders_left():
    for html in (pages.queue_page("Jane"), pages.documents_page()):
        assert "{nav}" not in html
        assert "{candidate_name}" not in html


def test_static_assets_resolve():
    for name in ("base.css", "queue.js", "documents.js", "queue.css"):
        asset = pages.static_asset(name)
        assert asset is not None, name
        assert asset[0]


def test_static_refuses_traversal_and_unknown_types():
    assert pages.static_asset("../handler.py") is None
    assert pages.static_asset("..%2Fhandler.py") is None
    assert pages.static_asset("queue.html.bak") is None
    assert pages.static_asset(".hidden.css") is None
