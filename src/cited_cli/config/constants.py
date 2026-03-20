from pathlib import Path

ENVIRONMENTS: dict[str, str] = {
    "prod": "https://api.youcited.com",
    "dev": "https://dev.youcited.com",
    "local": "http://localhost:8000",
}

FRONTEND_URLS: dict[str, str] = {
    "prod": "https://app.youcited.com",
    "dev": "https://dev.youcited.com",
    "local": "http://localhost:3000",
}

DEFAULT_ENV = "prod"
CONFIG_DIR = Path.home() / ".cited"
CONFIG_FILE = CONFIG_DIR / "config.toml"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
KEYRING_SERVICE = "cited-cli"

VALID_INDUSTRIES = [
    "automotive",
    "beauty",
    "consulting",
    "education",
    "entertainment",
    "finance",
    "fitness",
    "government",
    "healthcare",
    "home_services",
    "hospitality",
    "legal",
    "manufacturing",
    "non_profit",
    "real_estate",
    "restaurant",
    "retail",
    "technology",
    "other",
]

VALID_SOURCE_TYPES = [
    "question_insight",
    "head_to_head",
    "strengthening_tip",
    "priority_action",
]
