from pathlib import Path

ENVIRONMENTS: dict[str, str] = {
    "prod": "https://api.youcited.com",
    "dev": "https://dev.youcited.com",
    "uat": "https://uat.youcited.com",
    "local": "http://localhost:8000",
}

DEFAULT_ENV = "prod"
CONFIG_DIR = Path.home() / ".cited"
CONFIG_FILE = CONFIG_DIR / "config.toml"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
KEYRING_SERVICE = "cited-cli"
