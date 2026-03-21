from __future__ import annotations

from dataclasses import dataclass

from cited_cli.api.client import CitedClient


@dataclass
class CitedContext:
    client: CitedClient
    env: str
    api_url: str
