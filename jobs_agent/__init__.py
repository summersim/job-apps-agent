"""jobs_agent — ranked review queue for London legal and compliance roles.

Nothing in this package submits an application. It fetches, deduplicates,
scores, and stages roles; a human approves and submits.
"""

# Load API keys from a .env in the repository root as early as possible, so
# every entry point (cli, web, ad-hoc imports) sees them. Real environment
# variables always take precedence.
from .config import load_dotenv as _load_dotenv

_load_dotenv()
