"""legal_agent package."""

# Load REED/ADZUNA/GEMINI keys from a .env in the working directory as early
# as possible, so every entry point (cli, web, ad-hoc imports) sees them.
# Real environment variables always take precedence.
from .envfile import load_dotenv as _load_dotenv

_load_dotenv()
