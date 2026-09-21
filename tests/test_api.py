"""API endpoints, called directly — no socket involved.

The approval gate is the point of this file: a posting must not reach
"submitted" without passing through "approved", and that has to be enforced
by the server, not just hidden in the UI.
"""

import pytest
from conftest import make_posting

from jobs_agent.web import api


def req(**payload):
    return api.Request(payload=payload)


@pytest.fixture
def staged(store):
    """A posting in the store, with its application row. Returns its key."""
    p = make_posting()
    store.upsert([p])
    return p.key


# -- the approval gate ----------------------------------------------------

def test_cannot_approve_without_a_letter(store, staged):
    res = api.post_status(store, req(key=staged, status="approved"))
    assert res.status == 400
    assert "draft a letter" in res.body["error"]
    assert store.get_application(staged)["status"] == "new"


def test_cannot_submit_without_approving_first(store, staged):
    store.set_letter(staged, "Dear hiring manager,")
    store.set_status(staged, "drafted")

    res = api.post_status(store, req(key=staged, status="submitted"))
    assert res.status == 400
    assert "Approve the application" in res.body["error"]
    assert store.get_application(staged)["status"] == "drafted"


def test_the_full_path_to_submitted_works(store, staged):
    store.set_letter(staged, "Dear hiring manager,")
    assert api.post_status(store, req(key=staged, status="drafted")).status == 200
    assert api.post_status(store, req(key=staged, status="approved")).status == 200
    assert api.post_status(store, req(key=staged, status="submitted")).status == 200
    assert store.get_application(staged)["status"] == "submitted"


def test_unknown_status_is_rejected(store, staged):
    assert api.post_status(store, req(key=staged, status="hired")).status == 400


def test_unknown_posting_is_a_404(store):
    res = api.post_status(store, req(key="nope", status="shortlisted"))
    assert res.status == 404


# -- drafting guards ------------------------------------------------------

def test_draft_requires_a_cv_and_a_template(store, staged):
    res = api.post_draft(store, req(key=staged))
    assert res.status == 400
    assert "Profile page" in res.body["error"]


def test_redraft_requires_an_existing_draft(store, staged):
    store.set_document("cv", "Jane Smith, LLB")
    res = api.post_redraft(store, req(key=staged, feedback="make it shorter"))
    assert res.status == 400
    assert "before redrafting" in res.body["error"]


def test_redraft_requires_feedback(store, staged):
    assert api.post_redraft(store, req(key=staged)).status == 400


# -- CV upload ------------------------------------------------------------

def test_cv_upload_rejects_other_extensions(store):
    res = api.post_cv(store, req(filename="cv.txt", data_b64=""))
    assert res.status == 400


def test_cv_upload_rejects_undecodable_base64(store):
    res = api.post_cv(store, req(filename="cv.pdf", data_b64="not base64!!"))
    assert res.status == 400


# -- documents ------------------------------------------------------------

def test_only_editable_documents_are_writable(store):
    api.post_documents(store, req(candidate_name="Jane", cv="malicious override"))
    assert store.get_document("candidate_name") == "Jane"
    assert store.get_document("cv") == ""
