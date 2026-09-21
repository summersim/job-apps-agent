"""Cover-letter drafting: prompts, and the model call that runs them."""

from .drafter import DraftError, draft_letter, redraft_letter

__all__ = ["DraftError", "draft_letter", "redraft_letter"]
