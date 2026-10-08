"""Ignored local mailbox adapter for synthetic magic-link development."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4


class LocalMagicLinkDelivery:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def deliver(self, recipient: str, link: str, expires_at: str) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        destination = self._root / "latest.json"
        temporary = self._root / f".{uuid4()}.tmp"
        payload = {
            "recipient": recipient,
            "link": link,
            "expires_at": expires_at,
            "synthetic": True,
        }
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(destination)
