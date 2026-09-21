"""System instructions and prompt templates for cover-letter drafting.

Kept apart from the API plumbing in drafter.py: this is the part that gets
tuned by reading output, and it should be editable without scrolling past
client setup and error handling.
"""

from __future__ import annotations

#: How much of a job description to send. Postings past this length are
#: boilerplate about the agency, not the role.
DESCRIPTION_LIMIT = 4000

DRAFT_SYSTEM = (
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

REDRAFT_SYSTEM = (
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


def posting_block(*, title: str, employer: str, location: str,
                  description: str) -> str:
    return (
        f"Title: {title}\n"
        f"Employer: {employer}\n"
        f"Location: {location}\n"
        f"Description: {description[:DESCRIPTION_LIMIT]}"
    )


def draft_prompt(*, title: str, employer: str, location: str, description: str,
                 cv: str, template: str) -> str:
    posting = posting_block(title=title, employer=employer,
                            location=location, description=description)
    return f"""CANDIDATE CV (the only source of facts about the candidate):
{cv}

EXAMPLE COVER LETTER, WRITTEN BY THE CANDIDATE (match this voice and structure):
{template}

JOB POSTING TO WRITE FOR:
{posting}

Write the complete cover letter now, addressed appropriately, in the
candidate's voice, tailored to this posting."""


def redraft_prompt(*, title: str, employer: str, location: str, description: str,
                   cv: str, previous_letter: str, feedback: str) -> str:
    posting = posting_block(title=title, employer=employer,
                            location=location, description=description)
    return f"""CANDIDATE CV (the only source of facts about the candidate):
{cv}

JOB POSTING THIS LETTER IS FOR:
{posting}

PREVIOUS DRAFT:
{previous_letter}

CANDIDATE'S FEEDBACK ON THE PREVIOUS DRAFT:
{feedback}

Revise the letter to act on this feedback. Output the complete revised
letter."""
