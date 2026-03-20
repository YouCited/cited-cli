from __future__ import annotations

import tomllib
from typing import Any

import tomli_w

from cited_cli.config.constants import CONFIG_DIR, CONFIG_FILE, DEFAULT_ENV, ENVIRONMENTS

VALID_KEYS = {
    "environment",
    "default_business_id",
    "agent_api_key",
    "output",
}

VALID_OUTPUT_VALUES = {"json", "text"}


class ConfigManager:
    def __init__(self) -> None:
        self._ensure_config_dir()
        self._data: dict[str, Any] = self._load()

    def _ensure_config_dir(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not CONFIG_FILE.exists():
            return {"default": {}}
        with open(CONFIG_FILE, "rb") as f:
            return tomllib.load(f)

    def _save(self) -> None:
        with open(CONFIG_FILE, "wb") as f:
            tomli_w.dump(self._data, f)

    def get(self, key: str, profile: str = "default") -> Any:
        section = self._data.get(profile, self._data.get("default", {}))
        return section.get(key)

    def set(self, key: str, value: str, profile: str = "default") -> None:
        if profile not in self._data:
            self._data[profile] = {}
        self._data[profile][key] = value
        self._save()

    def delete(self, key: str, profile: str = "default") -> bool:
        section = self._data.get(profile, {})
        if key in section:
            del section[key]
            self._save()
            return True
        return False

    def get_all(self, profile: str = "default") -> dict[str, Any]:
        return dict(self._data.get(profile, {}))

    def get_environment(self, profile: str = "default", override: str | None = None) -> str:
        if override:
            return override
        return self.get("environment", profile) or DEFAULT_ENV

    def get_api_url(self, profile: str = "default", env_override: str | None = None) -> str:
        env = self.get_environment(profile, env_override)
        return ENVIRONMENTS.get(env, ENVIRONMENTS[DEFAULT_ENV])

    def get_profiles(self) -> list[str]:
        return [k for k in self._data if k != "default" and isinstance(self._data[k], dict)]
