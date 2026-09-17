"""Cover-letter drafting.

For each application the model writes a complete cover letter, tailored to
that posting, in the candidate's own voice. It gets three inputs:

  - the CV: the only source of facts about the candidate; nothing may be
    invented or embellished beyond it;
  - an example letter the candidate wrote themselves: the model matches its
    voice, tone, length, and structure;
  - the job posting: what the letter is tailored to.

This is a real generation step, so every draft is read, edited, and approved
by a human before anything is sent — see the workflow in web.py. This module
only produces text.
"""

from __future__ import annotations

import logging
import os

# google-genai logs an "AFC is not recommended" notice on every
# generate_content call even when no tools are used; keep it off the console.
logging.getLogger("google_genai").setLevel(logging.ERROR)

# Gemini. Flash handles a one-page letter well and keeps the per-application
# cost negligible; override with LEGAL_AGENT_GEMINI_MODEL.
MODEL = os.getenv("LEGAL_AGENT_GEMINI_MODEL", "gemini-3.6-flash")

_SYSTEM = (
    "You write a complete cover letter for a specific job, in the voice of "
    "the candidate. You are given the candidate's CV, an example cover "
    "letter the candidate wrote themselves, and the job posting. Match the "
    "example letter's voice, tone, register, length, and structure closely "
    "-- a reader who knows the candidate should recognise it as theirs. "
    "Tailor the content to THIS employer and posting with concrete, "
    "specific reasoning rather than generic enthusiasm. Use only facts "
    "present in the CV: do not invent experience, qualifications, "
    "employers, dates, or credentials. Output only the finished letter -- "
    "no preamble, no notes, no bracketed placeholders, no markdown."
)

_REDRAFT_SYSTEM = (
    "You revise a cover letter for a specific job, in the voice of the "
    "candidate, acting on the candidate's feedback about the previous "
    "draft. You are given the candidate's CV, the job posting, the "
    "previous draft, and the candidate's feedback on it. Apply the "
    "feedback precisely; keep the candidate's voice, tone, and structure "
    "everywhere the feedback doesn't ask you to change them. Write like a "
    "person, not an AI: natural phrasing and sentence rhythm, no stock "
    "cover-letter clichés ('I am writing to express my interest', "
    "'I am confident that my skills'), no over-polished or robotic "
    "transitions. Use only facts present in the CV: do not invent "
    "experience, qualifications, employers, dates, or credentials. Output "
    "only the finished letter -- no preamble, no notes, no bracketed "
    "placeholders, no markdown, no commentary about what you changed."
)


class DraftError(RuntimeError):
    """Raised when a letter can't be drafted (missing key, API failure, ...)."""


def _client():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise DraftError(
            "GEMINI_API_KEY is not set — export it before drafting letters."
        )
    try:
        from google import genai
    except ImportError as e:
        raise DraftError("the 'google-genai' package is not installed") from e
    return genai.Client(api_key=api_key)


def draft_letter(*, title: str, employer: str, location: str, description: str,
                 cv: str, template: str) -> str:
    """Write a full cover letter for one posting, in the candidate's voice.

    ``template`` is the candidate's own example letter, used purely as a
    voice and structure reference — it is not sent as-is.
    """
    client = _client()
    from google.genai import types

    prompt = f"""CANDIDATE CV (the only source of facts about the candidate):
{cv}

EXAMPLE COVER LETTER, WRITTEN BY THE CANDIDATE (match this voice and structure):
{template}

JOB POSTING TO WRITE FOR:
Title: {title}
Employer: {employer}
Location: {location}
Description: {description[:4000]}

Write the complete cover letter now, addressed appropriately, in the
candidate's voice, tailored to this posting."""
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM,
                temperature=0.7,
                max_output_tokens=4096,
            ),
        )
    except Exception as e:  # surface any SDK/API error to the caller
        raise DraftError(f"drafting failed: {e}") from e

    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        raise DraftError(f"the model returned no text{_finish_reason(resp)}")
    return text


def redraft_letter(*, title: str, employer: str, location: str, description: str,
                   cv: str, previous_letter: str, feedback: str) -> str:
    """Revise an existing draft to act on the candidate's feedback.

    ``previous_letter`` is the draft being revised (already in the
    candidate's voice); ``feedback`` is what the candidate wants changed
    about it.
    """
    client = _client()
    from google.genai import types

    prompt = f"""CANDIDATE CV (the only source of facts about the candidate):
{cv}

JOB POSTING THIS LETTER IS FOR:
Title: {title}
Employer: {employer}
Location: {location}
Description: {description[:4000]}

PREVIOUS DRAFT:
{previous_letter}

CANDIDATE'S FEEDBACK ON THE PREVIOUS DRAFT:
{feedback}

Revise the letter to act on this feedback. Output the complete revised
letter."""
    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_REDRAFT_SYSTEM,
                temperature=0.7,
                max_output_tokens=4096,
            ),
        )
    except Exception as e:  # surface any SDK/API error to the caller
        raise DraftError(f"redrafting failed: {e}") from e

    text = (getattr(resp, "text", None) or "").strip()
    if not text:
        raise DraftError(f"the model returned no text{_finish_reason(resp)}")
    return text


def _finish_reason(resp) -> str:
    """Best-effort ' (finish reason: ...)' suffix for an empty response."""
    try:
        return f" (finish reason: {resp.candidates[0].finish_reason})"
    except (AttributeError, IndexError, TypeError):
        return ""
