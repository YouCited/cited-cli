from __future__ import annotations

import contextlib
import json
import os
import stat

from cited_core.config.constants import CONFIG_DIR, CREDENTIALS_FILE, KEYRING_SERVICE


class TokenStore:
    def __init__(self) -> None:
        self._keyring_available: bool | None = None

    def _has_keyring(self) -> bool:
        if self._keyring_available is None:
            try:
                import keyring
                from keyring.backends.fail import Keyring as FailKeyring

                backend = keyring.get_keyring()
                self._keyring_available = not isinstance(backend, FailKeyring)
            except Exception:
                self._keyring_available = False
        return self._keyring_available

    def save_token(self, env: str, token: str) -> None:
        if self._has_keyring():
            import keyring

            keyring.set_password(KEYRING_SERVICE, f"token:{env}", token)
        else:
            self._save_file(env, token)

    def get_token(self, env: str) -> str | None:
        if self._has_keyring():
            import keyring

            return keyring.get_password(KEYRING_SERVICE, f"token:{env}")
        return self._load_file(env)

    def delete_token(self, env: str) -> None:
        if self._has_keyring():
            import keyring

            with contextlib.suppress(keyring.errors.PasswordDeleteError):
                keyring.delete_password(KEYRING_SERVICE, f"token:{env}")
        else:
            self._delete_file(env)

    def has_token(self, env: str) -> bool:
        return self.get_token(env) is not None

    # --- file fallback ---

    @staticmethod
    def _ensure_config_dir() -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(CONFIG_DIR, stat.S_IRWXU)

    def _ensure_creds_file(self) -> dict[str, str]:
        self._ensure_config_dir()
        if CREDENTIALS_FILE.exists():
            with open(CREDENTIALS_FILE) as f:
                data: dict[str, str] = json.load(f)
                return data
        return {}

    def _write_creds(self, data: dict[str, str]) -> None:
        self._ensure_config_dir()
        fd = os.open(CREDENTIALS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)

    def _save_file(self, env: str, token: str) -> None:
        data = self._ensure_creds_file()
        data[env] = token
        self._write_creds(data)

    def _load_file(self, env: str) -> str | None:
        data = self._ensure_creds_file()
        return data.get(env)

    def _delete_file(self, env: str) -> None:
        data = self._ensure_creds_file()
        if env in data:
            del data[env]
            self._write_creds(data)
