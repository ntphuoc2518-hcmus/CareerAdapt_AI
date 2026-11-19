"""Single source of "now" so due dates, reminders and retries can be tested with a fake clock."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

_override: Optional[Callable[[], datetime]] = None


def utcnow() -> datetime:
    return _override() if _override else datetime.now(timezone.utc)


def set_clock(provider: Optional[Callable[[], datetime]]) -> None:
    """Tests only: pass a callable returning an aware datetime, or None to restore the real clock."""
    global _override
    _override = provider
