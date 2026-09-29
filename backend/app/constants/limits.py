"""Field-level validation limits and patterns shared by schemas and controllers."""

# Repository: "repo" or "owner/repo" (GitHub-compatible characters only).
REPOSITORY_PATTERN = r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)?$"
# API keys are single tokens: whitespace/newlines are rejected so they can never inject config.
API_KEY_PATTERN = r"^[A-Za-z0-9_\-\.]{10,256}$"
TIME_OF_DAY_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"

NAME_MAX_LENGTH = 120
TITLE_MAX_LENGTH = 255
DESCRIPTION_MAX_LENGTH = 500
QUOTE_MAX_LENGTH = 2000
REFERENCE_MAX_LENGTH = 100
REPOSITORY_MAX_LENGTH = 200
CUSTOM_INSTRUCTIONS_MAX_LENGTH = 1000
PASSWORD_MAX_LENGTH = 64

MAX_REVIEW_BATCH = 200
MAX_RECURRING_AUDIT_DAYS = 366
EMAIL_HISTORY_LIMIT = 50
