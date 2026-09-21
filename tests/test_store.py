"""Store: dedupe on insert, and the document/file round-trips."""

from conftest import make_posting


def test_exact_duplicate_is_suppressed(store):
    assert store.upsert([make_posting()]) == (1, 0)
    assert store.upsert([make_posting()]) == (0, 1)


def test_repost_with_a_lightly_edited_body_is_suppressed(store):
    """Same title and location, body overlapping above the 0.75 threshold."""
    store.upsert([make_posting()])
    tweaked = make_posting(
        employer="Another Agency",
        description="Sanctions screening and due diligence for a law graduate. "
                    "Immediate start.",
    )
    assert store.upsert([tweaked]) == (0, 1)


def test_a_heavily_rewritten_body_is_not_suppressed(store):
    """Below the threshold it counts as a new posting -- the soft key alone
    isn't enough to merge two roles."""
    store.upsert([make_posting()])
    rewritten = make_posting(description="Drafting contracts for a retail client.")
    assert store.upsert([rewritten]) == (1, 0)


def test_a_genuinely_different_role_is_kept(store):
    store.upsert([make_posting()])
    other = make_posting(title="Paralegal", description="Bundling and disclosure work.")
    assert store.upsert([other]) == (1, 0)


def test_upsert_creates_a_new_application(store):
    p = make_posting()
    store.upsert([p])
    assert store.get_application(p.key)["status"] == "new"
    assert store.stats() == {"new": 1}


def test_queue_filters_by_status_and_location(store):
    p = make_posting(score=50)
    store.upsert([p])
    assert len(list(store.queue(status="new", location="London"))) == 1
    assert len(list(store.queue(status="new", location="Leeds"))) == 0
    assert len(list(store.queue(status="approved"))) == 0


def test_documents_and_files_overwrite_in_place(store):
    store.set_document("cv", "first")
    store.set_document("cv", "second")
    assert store.get_document("cv") == "second"
    assert store.get_document("never-written") == ""

    store.set_file("cv", "cv.pdf", b"%PDF-1.4")
    store.set_file("cv", "cv2.pdf", b"%PDF-1.7")
    row = store.get_file("cv")
    assert row["filename"] == "cv2.pdf"
    assert bytes(row["data"]) == b"%PDF-1.7"
