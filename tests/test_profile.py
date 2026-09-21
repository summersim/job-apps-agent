"""Scoring profile: the text format the UI edits, and the database round-trip."""

import pytest

from jobs_agent.profile import (
    DEFAULT_PROFILE,
    Profile,
    ProfileError,
    format_lines,
    format_weights,
    load_profile,
    parse_lines,
    parse_weights,
    save_profile,
)


def test_weights_round_trip():
    weights = {"compliance analyst": 30, "paralegal": 26}
    assert parse_weights(format_weights(weights), what="x") == weights


def test_weights_accept_an_equals_sign_in_the_term():
    assert parse_weights("a = b = 5", what="x") == {"a = b": 5}


def test_weights_skip_blank_and_comment_lines():
    assert parse_weights("# a note\n\nparalegal = 26\n", what="x") == {"paralegal": 26}


def test_weights_report_the_offending_line():
    with pytest.raises(ProfileError, match="Titles, line 2"):
        parse_weights("paralegal = 26\nno weight here", what="Titles")

    with pytest.raises(ProfileError, match="line 1"):
        parse_weights("paralegal = lots", what="Titles")


def test_blocker_lines_keep_significant_trailing_spaces():
    assert parse_lines("vp \nlead \n") == ["vp ", "lead "]


def test_blocker_lines_round_trip():
    terms = ["head of", "vp ", "director"]
    assert parse_lines(format_lines(terms)) == terms


def test_terms_are_lowercased_to_match_the_scorer():
    assert parse_weights("Compliance Analyst = 30", what="x") == {"compliance analyst": 30}
    assert parse_lines("Head Of") == ["head of"]


def test_json_round_trip():
    assert Profile.from_json(DEFAULT_PROFILE.to_json()) == DEFAULT_PROFILE


def test_load_returns_the_default_when_nothing_is_stored(store):
    assert load_profile(store) == DEFAULT_PROFILE


def test_save_then_load(store):
    custom = Profile(name="Jane", location="Leeds", target_titles={"clerk": 10})
    save_profile(store, custom)
    assert load_profile(store) == custom


def test_a_corrupt_row_falls_back_to_the_default(store):
    from jobs_agent.storage import DOC_SCORING_PROFILE

    store.set_document(DOC_SCORING_PROFILE, "{not json")
    assert load_profile(store) == DEFAULT_PROFILE
