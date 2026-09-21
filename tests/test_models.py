"""Deduplication identity: the thing that keeps four agency reposts of the
same role from filling the queue."""

from conftest import make_posting


def test_key_ignores_agency_boilerplate_in_employer():
    a = make_posting(employer="Example Recruitment Ltd")
    b = make_posting(employer="Example Search & Selection Limited")
    assert a.key == b.key


def test_key_differs_on_a_different_body():
    a = make_posting()
    b = make_posting(description="Something else entirely, about catering.")
    assert a.key != b.key


def test_key_ignores_title_case_and_punctuation():
    assert make_posting(title="COMPLIANCE ANALYST!").key == make_posting().key


def test_soft_key_matches_across_rewritten_bodies():
    a = make_posting()
    b = make_posting(description="A completely rewritten advert body.")
    assert a.soft_key == b.soft_key
    assert a.key != b.key


def test_soft_key_differs_on_location():
    assert make_posting(location="Leeds").soft_key != make_posting().soft_key


def test_salary_display():
    assert make_posting(salary_min=30000, salary_max=35000).salary_display == "£30,000–£35,000"
    assert make_posting(salary_min=30000).salary_display == "£30,000+"
    assert make_posting().salary_display == "not stated"
